"""Lessons: Sources that an LLM writes about a programming topic (spec §9).

The model is called through a `Provider`, so OpenRouter can be replaced by another provider.
The prompt is a named, swappable step (spec §12): the [lessons] settings name the one in use,
and each Lesson records it with the settings. Each code block of a Lesson is run with
`run_code`, and the model is asked to repair the ones that fail.
"""

import os
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple, Protocol
from zoneinfo import ZoneInfo

from typokiller.sources import CODE_BLOCK


class Reply(NamedTuple):
    text: str
    usage: dict[str, Any]  # the token counts, as the provider gives them
    dollars: float  # the cost, as charged


class Provider(Protocol):
    def prices(self, model: str) -> tuple[float, float]:
        """The model's price in dollars for one prompt token and for one output token."""
        ...

    def write(self, model: str, messages: list[dict[str, str]], max_tokens: int, reasoning: str) -> Reply:
        """The model's answer to the messages, each {role, content}. It writes at most
        `max_tokens` tokens, thinking included, and thinks with the effort `reasoning`
        ("low", "medium" or "high")."""
        ...


# What the prompt tells the model about each language: its name, and the rule for examples.
LANGUAGES = {
    "python": ("Python", "Python 3.14. Each example is a complete script that uses only the standard library."),
}

SYSTEM_V1 = """\
You write Lessons for a touch-typing trainer. The learner reads and types the whole Lesson, \
code included, so it must be accurate and idiomatic. The learner is at the {level} level.

Write the Lesson in Markdown, using only paragraphs, ## headings and fenced code blocks: no \
lists, tables, block quotes or images. Write about {words} words, code included, and not \
fewer than {least}: 5 or 6 sections, each with a ## heading, two or three paragraphs and one \
code example. Every code block is an example tagged with the language. {rules} {runs} Do not \
show the output in a separate block; put it in a comment if it helps. Use plain ASCII."""

RUNS = """\
Every example runs on its own, without input, without the network, writes files only in the \
current folder and finishes within a few seconds."""

REPAIR_V1 = """\
You fix a code example in a Lesson for a touch-typing trainer. The learner types the example, \
so keep it short, accurate and idiomatic. {rules} {runs} Use plain ASCII. Answer with the whole \
fixed example in one fenced code block."""


def lesson_prompt_v1(language: str, topic: str, settings: dict[str, Any]) -> list[dict[str, str]]:
    """The messages that ask for a Lesson on `topic`, with the length and level of the
    [lessons] settings. The trial's Python Lessons from Haiku 5.5 were shorter than asked
    (751 to 1,267 words for 1,200 to 1,500), so this asks for a minimum and a structure too."""
    name, rules = LANGUAGES[language]
    words = settings["words"]
    system = SYSTEM_V1.format(level=settings["level"], words=words, least=round(words * 0.85), rules=rules, runs=RUNS)
    return [{"role": "system", "content": system}, {"role": "user", "content": f"Write a {name} Lesson on {topic}."}]


def repair_prompt_v1(language: str, code: str, error: str) -> list[dict[str, str]]:
    """The messages that ask the model to fix a code block that failed with `error`."""
    system = REPAIR_V1.format(rules=LANGUAGES[language][1], runs=RUNS)
    return [{"role": "system", "content": system}, {"role": "user", "content": f"```{language}\n{code}```\n\n{error}"}]


class LessonPrompt(NamedTuple):
    write: Callable[[str, str, dict[str, Any]], list[dict[str, str]]]  # (language, topic, [lessons] settings)
    repair: Callable[[str, str, str], list[dict[str, str]]]  # (language, code, error)
    blocks: int  # the most code blocks that it asks for


# The Lesson prompts, by name (spec §12). The [lessons] settings name the one in use. A
# prompt asks for a Lesson and for the repair of a code block.
LESSON_PROMPTS = {"lesson-prompt-v1": LessonPrompt(lesson_prompt_v1, repair_prompt_v1, 6)}

WRITES = 2  # a Lesson whose code fails the check is written once again (spec §9)
ERROR_CHARS = 2000  # the end of a block's error output that the check log and repair calls get


def worst_case(provider: Provider, model: str, language: str, messages: list[dict[str, str]], lessons: dict) -> float:
    """The most that one Lesson can cost, in dollars, by the [lessons] settings: it is written
    WRITES times, and each time each of the prompt's `blocks` code blocks has `repairs` repair
    calls. A call costs at most a token for each character of the prompt (a token is never
    shorter than a character) and its most output tokens. A repair prompt is counted with a
    block of `repair_tokens` characters, as long as the most that a repair can write, and
    ERROR_CHARS of error."""
    price, output = provider.prices(model)

    def call(messages: list[dict[str, str]], max_tokens: int) -> float:
        return sum(len(m["content"]) for m in messages) * price + max_tokens * output

    prompt = LESSON_PROMPTS[lessons["prompt"]]
    repair = prompt.repair(language, "x" * lessons["repair_tokens"], "x" * ERROR_CHARS)
    repairs = prompt.blocks * lessons["repairs"] * call(repair, lessons["repair_tokens"])
    return WRITES * (call(messages, lessons["max_tokens"]) + repairs)


def code_in(reply: str) -> str:
    """The code of the first fenced code block in a repair reply, else the whole reply."""
    found = CODE_BLOCK.search(reply)
    return found[1] if found else reply.strip("\n") + "\n"


def with_codes(markdown: str, codes: list[str | None]) -> str:
    """The Markdown with the code of each code block replaced by the next of `codes`, or the
    block left out for None."""
    each = iter(codes)

    def swap(block: re.Match) -> str:
        code = next(each)
        start, end = block.start(1) - block.start(), block.end(1) - block.start()
        return "" if code is None else block[0][:start] + code + block[0][end:]

    return CODE_BLOCK.sub(swap, markdown)


# A code block runs under sandbox-exec with this profile: no network, and writes only in the
# FOLDER that it runs in (and /dev/null). Everything else is allowed, such as reading files.
SANDBOX = """\
(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath (param "FOLDER")) (literal "/dev/null"))"""


def python_command(code: str, folder: Path) -> list[str]:
    """Runs the block with the server's Python. -I -S leaves out the packages installed for the
    server and the environment's PYTHON settings, so an example may use only the standard library."""
    (folder / "main.py").write_text(code)
    return [sys.executable, "-I", "-S", "main.py"]


# How a code block of each language is run: the function writes the block's files into an empty
# folder and gives the command that builds and runs it there.
RUNNERS: dict[str, Callable[[str, Path], list[str]]] = {"python": python_command}


def run_code(language: str, code: str, timeout: float) -> str | None:
    """Builds and runs a code block in a new temp folder, under sandbox-exec with SANDBOX.
    None when it ends with exit code 0 within `timeout` seconds; else what went wrong, with
    the last ERROR_CHARS of its error output. TMPDIR is the folder, so the block can make
    temp files. Its output is thrown away, and its child processes are stopped at the end."""
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryFile() as errors:
        folder = Path(tmp).resolve()  # the sandbox needs the real path, /private/var/..., not /var/...
        command = ["sandbox-exec", "-p", SANDBOX, "-D", f"FOLDER={folder}", *RUNNERS[language](code, folder)]
        process = subprocess.Popen(
            command, cwd=folder, env=os.environ | {"TMPDIR": str(folder)},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors, start_new_session=True,
        )  # fmt: skip
        try:
            exit_code = process.wait(timeout)
        except subprocess.TimeoutExpired:
            exit_code = None
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        if exit_code == 0:
            return None
        errors.seek(max(0, errors.seek(0, os.SEEK_END) - ERROR_CHARS))
        tail = errors.read().decode(errors="replace")
    ended = f"did not finish within {timeout} seconds" if exit_code is None else f"ended with exit code {exit_code}"
    return f"It {ended}.\n{tail}"


def month_start() -> datetime:
    """The start of this calendar month in UK time."""
    return datetime.now(ZoneInfo("Europe/London")).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def spent(db: sqlite3.Connection, dollars_per_pound: float) -> float:
    """The month-to-date spend in pounds, from the spend ledger, at the fixed exchange rate."""
    start = month_start().astimezone(UTC).isoformat()
    (dollars,) = db.execute("SELECT coalesce(sum(dollars), 0) FROM spend WHERE time >= ?", (start,)).fetchone()
    return dollars / dollars_per_pound


def cap_refusal(db: sqlite3.Connection, worst: float, settings: dict[str, Any]) -> str | None:
    """Why calls that cost at most `worst` dollars may not be sent: when they could make the
    month-to-date spend more than the cap of the [lessons] settings. None when they may be sent."""
    if spent(db, settings["dollars_per_pound"]) + worst / settings["dollars_per_pound"] <= settings["cap"]:
        return None
    resets = (month_start() + timedelta(days=32)).replace(day=1)
    return f"Cap reached: resets 1 {resets:%b}"
