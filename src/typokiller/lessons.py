"""Lessons: Sources that an LLM writes about a programming topic (spec §9).

The model is called through a `Provider`, so OpenRouter can be replaced by another provider.
The prompt is a named, swappable step (spec §12): the [lessons] settings name the one in use,
and each Lesson records it with the settings.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple, Protocol
from zoneinfo import ZoneInfo


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
code example. Every code block is an example tagged with the language. {rules} Every example \
runs on its own, without input, without the network, writes files only in the current folder \
and finishes within a few seconds. Do not show the output in a separate block; put it in a \
comment if it helps. Use plain ASCII."""


def lesson_prompt_v1(language: str, topic: str, settings: dict[str, Any]) -> list[dict[str, str]]:
    """The messages that ask for a Lesson on `topic`, with the length and level of the
    [lessons] settings. The trial's Python Lessons from Haiku 5.5 were shorter than asked
    (751 to 1,267 words for 1,200 to 1,500), so this asks for a minimum and a structure too."""
    name, rules = LANGUAGES[language]
    words = settings["words"]
    system = SYSTEM_V1.format(level=settings["level"], words=words, least=round(words * 0.85), rules=rules)
    return [{"role": "system", "content": system}, {"role": "user", "content": f"Write a {name} Lesson on {topic}."}]


# The Lesson prompts, by name (spec §12). The [lessons] settings name the one in use.
LESSON_PROMPTS = {"lesson-prompt-v1": lesson_prompt_v1}


def worst_case(provider: Provider, model: str, messages: list[dict[str, str]], max_tokens: int) -> float:
    """The most that one call can cost, in dollars: a token for each character of the prompt
    (a token is never shorter than a character) and `max_tokens` output tokens."""
    prompt, output = provider.prices(model)
    return sum(len(m["content"]) for m in messages) * prompt + max_tokens * output


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
