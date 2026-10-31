import asyncio
import hashlib
import json
import os
import random
import sqlite3
import ssl
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Coroutine, Sequence
from contextlib import asynccontextmanager, suppress
from itertools import zip_longest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import polars as pl
import tomlkit
import truststore
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from typokiller.analysis import (
    TREND_WEEKS,
    Unlocking,
    attempts,
    progress,
    trend_chart,
    unlock_due,
    unlocking,
    weakness,
)
from typokiller.drawing import draw_layers
from typokiller.drills import DRILL_GENERATORS, SYMBOLS, NoLines, line_pool
from typokiller.keymap import keymap_letters, read_keymap
from typokiller.lessons import (
    LESSON_PROMPTS,
    WRITES,
    Provider,
    Reply,
    build_gleam_project,
    cap_refusal,
    code_in,
    heading,
    run_code,
    spent,
    with_codes,
    worst_case,
)
from typokiller.sources import (
    CODE_BLOCK,
    article_paragraphs,
    code_passages,
    cut_stored_passages,
    git,
    gutenberg_paragraphs,
    lesson_passages,
    prose_passages,
    repo_text,
    search_catalogue,
)
from typokiller.symbol_docs import symbol_docs

# The Passage typed when no Source is open. It is Passage 1, which has no Source.
PASSAGE = (
    "It is a truth universally acknowledged, that a single man in possession "
    "of a good fortune, must be in want of a wife."
)
BUILT_IN = {"id": 1, "text": PASSAGE}

SCHEMA = """
CREATE TABLE IF NOT EXISTS board (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, vial TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS keymap_version (hash TEXT PRIMARY KEY, board INTEGER NOT NULL, vil TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session (id INTEGER PRIMARY KEY, started TEXT NOT NULL, keymap_version TEXT);
CREATE TABLE IF NOT EXISTS source (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    total INTEGER NOT NULL,  -- its number of Passages
    bookmark INTEGER NOT NULL DEFAULT 0,  -- the ord of the next Passage to serve
    opened TEXT NOT NULL,
    symbol_source INTEGER NOT NULL DEFAULT 0  -- 1 for a Symbol Source, which is never opened to type in order
);
CREATE TABLE IF NOT EXISTS passage (
    id INTEGER PRIMARY KEY,
    source INTEGER,
    ord INTEGER NOT NULL,
    text TEXT NOT NULL,
    normaliser TEXT NOT NULL,
    heading TEXT,  -- a Lesson's heading, shown above the Passage and not typed
    code INTEGER NOT NULL DEFAULT 0,  -- 1 for code: from a code Source or a Lesson's code block
    replaced INTEGER NOT NULL DEFAULT 0  -- 1 when it was cut into pieces after it was stored; the pieces are other Passages
);
CREATE TABLE IF NOT EXISTS drill (
    passage INTEGER PRIMARY KEY,  -- a Drill is a Passage with no Source
    made TEXT NOT NULL,
    session INTEGER NOT NULL,  -- the Session it was made for, so its Board and Letter layout
    model TEXT NOT NULL,  -- the Weakness model
    generator TEXT NOT NULL,  -- the Drill generator
    targets TEXT NOT NULL,  -- JSON: a list of {unit, reason, cost, seen}, as the generator chose them
    unlocked TEXT,  -- JSON: the Unlocked keys it was built from; NULL when it could use every key
    made_up TEXT  -- JSON: the Made-up words of its text; NULL when there are none
);
CREATE TABLE IF NOT EXISTS unlock (  -- the unlock log of the Letter layout being learned
    letter_layout TEXT NOT NULL,
    key TEXT NOT NULL,  -- the character it types without Shift
    time TEXT NOT NULL,
    how TEXT NOT NULL,  -- "rule" or "manual"
    settings TEXT NOT NULL,  -- JSON: the [unlocking] settings then
    model TEXT NOT NULL  -- the Weakness model then
);
CREATE TABLE IF NOT EXISTS lesson (  -- one row per Lesson that the model wrote
    id INTEGER PRIMARY KEY,
    made TEXT NOT NULL,
    topic TEXT NOT NULL,  -- as typed, or "Symbol ^: <heading>" for a Symbol Lesson; also the Source's title
    language TEXT NOT NULL,
    model TEXT NOT NULL,  -- the model ID, as the provider names it
    prompt TEXT NOT NULL,  -- the Lesson prompt
    settings TEXT NOT NULL,  -- JSON: the [lessons] settings then
    output TEXT NOT NULL,  -- the model's raw output
    source INTEGER,  -- the Source made from it; NULL when it failed the check or had no Passage to type
    checks TEXT  -- JSON: the check log, a list of checks for each code block (see check_code)
);
CREATE TABLE IF NOT EXISTS spend (  -- the spend ledger: one row per call to a model
    lesson INTEGER NOT NULL,
    time TEXT NOT NULL,
    usage TEXT NOT NULL,  -- JSON: the token counts, as the provider gave them
    dollars REAL NOT NULL  -- the cost, as charged
);
CREATE INDEX IF NOT EXISTS passage_source ON passage (source, ord);
CREATE TABLE IF NOT EXISTS attempt (
    session INTEGER NOT NULL,
    ord INTEGER NOT NULL,
    finished INTEGER NOT NULL,
    settings TEXT,
    passage INTEGER,
    PRIMARY KEY (session, ord)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS key_event (
    session INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    attempt INTEGER NOT NULL,
    t REAL NOT NULL,
    type TEXT NOT NULL,
    code TEXT NOT NULL,
    key TEXT NOT NULL,
    shift INTEGER NOT NULL,
    ctrl INTEGER NOT NULL,
    alt INTEGER NOT NULL,
    meta INTEGER NOT NULL,
    repeat INTEGER NOT NULL,
    PRIMARY KEY (session, seq)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS key_event_attempt ON key_event (session, attempt);
"""

# Written to the settings file when it is missing. Later tickets add their settings here.
DEFAULT_SETTINGS = """\
# typokiller settings. Edit this file, or press , in the app's Escape menu.
# The app reads this file again before each Attempt.

[typing]
# What a wrong key does: "keep typing" puts it in and moves the cursor on;
# "locked until fixed" keeps the cursor in place until the right key is typed.
wrong_key_mode = "keep typing"
# Whether the practice screen draws the Keymap faintly under the Passage. m in the
# Escape menu turns it on and off. Each Attempt records it with its settings.
show_keymap = false

[passages]
# A paragraph or function is not made into a Passage when normalising it to ASCII
# dropped more than this share of its characters, or left it shorter than min_length
# characters.
max_dropped = 0.05
min_length = 20
# A paragraph is cut into Passages of at most this many characters, at the ends of sentences.
# A Lesson's paragraphs are cut the same way. A Passage already stored that is longer than this
# is cut again when typokiller starts.
prose_chars = 400
# A function or code block is cut into Passages of about this many characters, at blank lines
# (up to a quarter more) or at line breaks. Code up to a quarter more is not cut. A single line
# stays whole.
code_chars = 200
# A code Source takes Passages only from the files with one of these extensions, so lock
# files, dotfiles and docs are left out. A change applies to the next import.
code_extensions = [".py", ".gleam"]

[weakness]
# The Weakness model that ranks characters and pairs by cost. There is one so far:
# "recent-cost-v1", where cost (ms) = median time + error rate × fix time.
model = "recent-cost-v1"
# recent-cost-v1 uses the last `weeks` weeks of typing, and leaves out characters and
# pairs seen fewer than min_seen times. The Attempt summary medians use the same weeks.
weeks = 4
min_seen = 20

[drills]
# The Drill generator. There is one so far: "density-v1", which takes the Targets from
# the Weakness ranking and the under-measured characters and pairs, and then picks words
# from the Sources that hold many Targets.
generator = "density-v1"
# A Drill has `weak` Targets that the Weakness model ranks highest, and `under_measured`
# Targets: characters and pairs common in the Sources but seen fewer than min_seen times
# on this Board and Letter layout, in the Weakness model's weeks. This min_seen is apart
# from the one in [weakness], so a unit can stay a Target until it is better measured.
weak = 2
under_measured = 1
min_seen = 20
# The number of words in a Drill.
words = 40

[symbols]
# Symbol Drills (y in the Escape menu) are made of lines of code from the Sources. Their
# Targets are only Symbols (the digits and !"#$%&()*+-/:;<=>?@[\\]^`{|}~) and symbol pairs
# (pairs with a Symbol and no space or newline). They are chosen like those of usual Drills:
# `weak` that the Weakness model ranks highest, then `under_measured` that are common in the
# lines of code and seen fewer than the [drills] min_seen times. A Symbol Drill has `lines`
# lines, each with at most 80 characters and at least 2 Symbols.
weak = 2
under_measured = 2
lines = 6
# The import of the symbol docs (i then s in the Escape menu) takes the Python tutorial
# and library from this branch of python/cpython. It also takes the Gleam language tour and
# standard library, the GNU bash examples and the tldr pages. A change of the branch applies
# to the next import. A doc whose title is already stored is not stored again, so an import
# adds only the docs that are new.
python_branch = "3.15"
# After that import, each Symbol that fewer than min_lines lines of the line pool hold gets one
# Symbol Lesson: a Python Lesson, written by python_model, on a topic that uses the Symbol. Each
# is checked against the [lessons] cap when it is queued.
min_lines = 50
# When a Symbol Lesson is written, the lines that hold its Symbol are counted again, and the
# Symbol gets one more Symbol Lesson while it is still in fewer than min_lines lines. A Symbol gets at most max_lessons
# Symbol Lessons in all, also over several imports.
max_lessons = 3

[unlocking]
# The Letter layout being learned. Drills use only its Unlocked keys until all 30 of its main
# keys are unlocked, so no capitals, digits or symbols of other layers either. Their words come
# from the Word list, not from the Sources. Reading and Lessons use every key. Other Letter
# layouts have no locked keys.
letter_layout = "free-range"
# The keys unlocked at the start, and the order in which the others unlock. Each key is
# written as the character it types without Shift, with a space between keys.
start = "t s r e"
order = "a n o i l h d u c m w f g y p b , v . _ k ' j x q z"
# After each finished Attempt, the next key unlocks when each Unlocked key costs less than
# threshold ms by the Weakness model, over its last `last` keystrokes on every Board with
# this Letter layout, and was seen at least min_seen times in them. u in the Escape menu
# unlocks the next key at once. After an unlock, Drills are Introduction Drills of the new
# key until it has been seen min_seen times.
threshold = 400
last = 50
min_seen = 20
# While keys are locked, the words of Drills are the words of the Word list (at least 2 letters)
# that use only Unlocked keys, not the words of the Sources. When there are fewer than min_words
# of them, Made-up words fill the list up to min_words different words.
min_words = 200

[lessons]
# The prompt that asks the model for a Lesson. There is one so far: "lesson-prompt-v1", which
# asks for paragraphs, ## headings and code blocks only, each example a complete program.
# Symbol Lessons always use "symbol-lesson-v1", which asks for the same.
prompt = "lesson-prompt-v1"
# The model that writes Python Lessons, by its OpenRouter ID, and how hard it thinks before it
# writes: "low", "medium" or "high". It writes at most max_tokens tokens, thinking included.
python_model = "anthropic/claude-haiku-5.5"
# The model that writes Gleam Lessons. The first other one to try is "openai/gpt-6.1-sol".
gleam_model = "anthropic/claude-sonnet-5.5"
reasoning = "low"
max_tokens = 8000
# The length that the prompt asks for, in words with the code, and the learner's level.
words = 1300
level = "intermediate"
# Each code block is run on its own in a new folder under sandbox-exec, with no network and no
# writes outside that folder. It passes when it ends with exit code 0 within `timeout` seconds.
# One that fails is sent back to the model with its error, up to `repairs` times, and each
# answer has at most repair_tokens tokens; then it is dropped. When more than drop_share of the
# blocks are dropped (0.34: more than a third), or no code is left, the Lesson is written once
# again, and then rejected.
timeout = 10
repairs = 2
repair_tokens = 4000
drop_share = 0.34
# The most that calls to models may cost in a calendar month (UK time), in pounds. A request
# that could make the cost more than this is refused: it counts the Lesson written twice, each
# time with every repair call that the prompt's code blocks could have. The dollars charged
# become pounds at this fixed rate.
cap = 5.0
dollars_per_pound = 1.337

[lists]
# The letters that label the items of the Board list, the Keymap list, the list of Sources (o in
# the Escape menu) and the Gutenberg search results. An item is chosen by typing its label. The
# first items get one letter, in this order, and the others two. j and k, and n in the Board list,
# are never labels.
letters = "sadflewcmpgh"

[keymaps]
# The layer names in Keymap drawings, for each Board and Letter layout. A layer with no
# name is named after the key that opens it. Put a Board name with spaces in quotes,
# such as [keymaps."Q3 Max".QWERTY]. For example:
# [keymaps.Sweep.QWERTY]
# layers = ["Base", "Sym", "Nav", "Stack", "Num"]
"""


def now() -> str:
    return datetime.now(UTC).isoformat()


def read_settings(path: Path) -> tomlkit.TOMLDocument:
    if not path.exists():
        path.write_text(DEFAULT_SETTINGS)
    doc = tomlkit.parse(path.read_text())
    # A file made by an older typokiller gets the tables added since, with their comments,
    # and the settings added since to its tables, without their comments.
    text = tomlkit.dumps(doc)
    for name, table in tomlkit.parse(DEFAULT_SETTINGS).items():
        if name not in doc:
            doc[name] = table
        doc[name].update({key: value for key, value in table.items() if key not in doc[name]})
    if tomlkit.dumps(doc) != text:
        path.write_text(tomlkit.dumps(doc))
    return doc


def layer_names(settings: dict, board: str | None, letters: str | None) -> list[str]:
    """The layer names of a Keymap in the [keymaps] settings."""
    return settings["keymaps"].get(board, {}).get(letters, {}).get("layers", [])


CATALOGUE_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"


# Checks certificates with the macOS keychain, as browsers and curl do. Python's
# default, /etc/ssl/cert.pem, lacks the root certificate that gutenberg.org uses.
TLS = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def fetch(url: str, body: dict | None = None, headers: dict[str, str] | None = None, timeout: int = 60) -> bytes:
    """GETs the URL, or POSTs `body` to it as JSON."""
    headers = {"User-Agent": "typokiller", "Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(url, None if body is None else json.dumps(body).encode(), headers)
    with urllib.request.urlopen(request, timeout=timeout, context=TLS) as response:
        return response.read()


class OpenRouter:
    """The Provider of the models that write Lessons: OpenRouter's chat API. The API key is
    OPENROUTER_API_KEY, from the environment or else from the file `env`, read for each call."""

    API = "https://openrouter.ai/api/v1"

    def __init__(self, env: Path):
        self.env = env
        self.price_list: dict[str, tuple[float, float]] = {}

    # The model list needs no key. It is read once, when the first Lesson is asked for.
    def prices(self, model: str) -> tuple[float, float]:
        if not self.price_list:
            listed = json.loads(fetch(f"{self.API}/models"))["data"]
            self.price_list = {m["id"]: (float(m["pricing"]["prompt"]), float(m["pricing"]["completion"])) for m in listed}
        return self.price_list[model]

    def write(self, model: str, messages: list[dict[str, str]], max_tokens: int, reasoning: str) -> Reply:
        body = {
            "model": model, "messages": messages, "max_tokens": max_tokens,
            "reasoning": {"effort": reasoning}, "usage": {"include": True},
        }  # fmt: skip
        answer = json.loads(fetch(f"{self.API}/chat/completions", body, {"Authorization": f"Bearer {self.key()}"}, 300))
        return Reply(answer["choices"][0]["message"]["content"] or "", answer["usage"], answer["usage"]["cost"])

    def key(self) -> str:
        if key := os.environ.get("OPENROUTER_API_KEY"):
            return key
        for line in self.env.read_text().splitlines() if self.env.exists() else []:
            name, _, value = line.partition("=")
            if name.strip() == "OPENROUTER_API_KEY":
                return value.strip().strip("\"'")
        raise ValueError(f"OPENROUTER_API_KEY is not set and not in {self.env}.")


async def refresh_catalogue(catalogue: Path):
    """Downloads Gutenberg's catalogue when it is missing or a week old. Checks once an hour."""
    while True:
        if not catalogue.exists() or time.time() - catalogue.stat().st_mtime > 7 * 24 * 3600:
            try:
                catalogue.write_bytes(await asyncio.to_thread(fetch, CATALOGUE_URL))
            except OSError as e:  # tries again in an hour
                print(f"Could not download the Gutenberg catalogue: {e}")
        await asyncio.sleep(3600)


def clone(url: str) -> list[tuple[str, str]]:
    """The path and text of each text file that git tracks in the repo at `url`. Private repos
    work (see `git`). Symbolic links are not followed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        git("clone", "--depth", "1", "-q", url, tmp)
        listed = git("-C", tmp, "ls-files", "-z")
        files = []
        for path in listed.split("\0")[:-1]:
            file = Path(tmp, path)
            if file.is_file() and not file.is_symlink():
                with suppress(UnicodeDecodeError):
                    if "\0" not in (text := file.read_text("utf-8")):
                        files.append((path, text))
        return files


class KeyEvent(BaseModel):
    seq: int
    attempt: int
    t: float
    type: Literal["keydown", "keyup"]
    code: str
    key: str
    shift: bool
    ctrl: bool
    alt: bool
    meta: bool
    repeat: bool


class Attempt(BaseModel):
    passage: int  # its id
    settings: dict  # the settings it was typed with


class Batch(BaseModel):
    events: list[KeyEvent] = []
    finished: list[int] = []  # the ords of Attempts that finished
    attempts: dict[int, Attempt] = {}  # each Attempt in `events`, by ord


class NewSession(BaseModel):
    keymap_version: str  # its hash


class Bookmark(BaseModel):
    at: int  # the ord of the next Passage to serve


class Book(BaseModel):
    number: int  # its Project Gutenberg book number
    title: str  # from the catalogue


class Repo(BaseModel):
    url: str  # anything `git clone` takes


class Article(BaseModel):
    title: str
    text: str  # the page's selected text, or else the text of its `article` or `body`


class LessonRequest(BaseModel):
    topic: str  # free text, as typed; "Symbol ^" for a Symbol Lesson until it is written
    language: Literal["python", "gleam"] = "python"  # a key of lessons.LANGUAGES
    symbol: str | None = None  # the Symbol of a Symbol Lesson, which is in Python


class DrillRequest(BaseModel):
    # True when the page wants an Introduction Drill. If none is due, no Drill is made.
    introduction: bool = False
    # True when the page wants a Symbol Drill. It is one even while Introduction Drills are due.
    symbols: bool = False


class NewBoard(BaseModel):
    name: str
    vil: str  # the text of the .vil file
    vial: str  # the text of the vial.json file


def create_app(db_path: Path, settings_path: Path, provider: Provider) -> FastAPI:
    db = sqlite3.connect(db_path, check_same_thread=False)
    db.executescript(SCHEMA)
    # Databases made before these columns existed get them here. Their old rows keep NULL.
    for table, column in [
        ("session", "keymap_version"), ("attempt", "settings"), ("passage", "heading"), ("lesson", "checks"),
        ("drill", "made_up"),
    ]:
        with suppress(sqlite3.OperationalError):  # fails when the column is there already
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    with db:
        db.execute("INSERT OR IGNORE INTO passage (id, ord, text, normaliser) VALUES (1, 0, ?, 'ascii-v1')", (PASSAGE,))
        with suppress(sqlite3.OperationalError):
            db.execute("ALTER TABLE attempt ADD COLUMN passage INTEGER")
            db.execute("UPDATE attempt SET passage = 1")  # every Attempt before there were Sources typed it
        with suppress(sqlite3.OperationalError):
            db.execute("ALTER TABLE passage ADD COLUMN code INTEGER NOT NULL DEFAULT 0")
            # Before, no column said which Passages are code. One that holds a newline is taken as code.
            db.execute("UPDATE passage SET code = 1 WHERE instr(text, char(10))")
        with suppress(sqlite3.OperationalError):
            db.execute("ALTER TABLE source ADD COLUMN symbol_source INTEGER NOT NULL DEFAULT 0")
            # The Symbol Sources from before: the Symbol Lessons, and the Sources of the symbol
            # docs import, by the titles that `symbol_docs` gives them.
            db.execute(
                "UPDATE source SET symbol_source = 1 WHERE id IN (SELECT source FROM lesson WHERE topic GLOB 'Symbol ?: *')"
                " OR title IN ('Gleam tour', 'Gleam stdlib') OR title GLOB 'Python * tutorial' OR title GLOB 'Python * library'"
            )
        with suppress(sqlite3.OperationalError):
            db.execute("ALTER TABLE passage ADD COLUMN replaced INTEGER NOT NULL DEFAULT 0")
    limits = read_settings(settings_path)["passages"]
    cut_stored_passages(db, limits["prose_chars"], limits["code_chars"], limits["min_length"])

    def served(source: dict | None) -> dict:
        """The Source's Passage at its bookmark and the one after it. After the Source's
        last Passage comes the built-in Passage, and a finished Source is closed."""
        rows = []
        if source:
            rows = db.execute(
                "SELECT id, text, heading FROM passage WHERE source = ? AND NOT replaced AND ord >= ? ORDER BY ord LIMIT 2",
                (source["id"], source["at"]),
            ).fetchall()
        passages = [{"id": id, "text": text, "heading": heading} for id, text, heading in rows] + [BUILT_IN]
        return {"source": source if rows else None, "passages": passages[:2]}

    def add_source(
        title: str,
        text: str,
        passages: list[str],
        headings: Sequence[str | None] = (),
        codes: Sequence[bool] = (),
        symbol_source: bool = False,
    ) -> int:
        """Stores a Source with its Passages, with the heading above each Passage of a Lesson or
        of the symbol docs, and with whether each Passage is code. Passages with no flag in `codes` are not code.
        `symbol_source` marks a Symbol Source."""
        with db:
            (source,) = db.execute(
                "INSERT INTO source (title, text, total, opened, symbol_source) VALUES (?, ?, ?, ?, ?) RETURNING id",
                (title, text, len(passages), now(), symbol_source),
            ).fetchone()
            db.executemany(
                "INSERT INTO passage (source, ord, text, normaliser, heading, code) VALUES (?, ?, ?, 'ascii-v1', ?, ?)",
                [(source, i, p, h, bool(c)) for i, (p, h, c) in enumerate(zip_longest(passages, headings, codes))],
            )
        return source

    notices: list[str] = []  # every open practice page shows each new one on its message line

    tasks: set[asyncio.Task] = set()  # background work, kept here until it is done so Python does not delete it

    def in_background(work: Coroutine):
        """Runs the work in a task of its own, and returns at once."""
        task = asyncio.create_task(work)
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    def add_unlock(letters: str | None, key: str, settings: dict, how: str):
        """Writes the next key of the Letter layout being learned to the unlock log, by the
        rule or by hand ("rule" or "manual"), with the settings then, and says so in a notice."""
        with db:
            db.execute(
                "INSERT INTO unlock VALUES (?, ?, ?, ?, ?, ?)",
                (letters, key, now(), how, json.dumps(settings["unlocking"]), settings["weakness"]["model"]),
            )
        notices.append(f"Unlocked {key}. Next come drills for {key}.")

    async def import_repo(url: str):
        title = Path(url).name.removesuffix(".git")
        try:
            files = await asyncio.to_thread(clone, url)
        except subprocess.CalledProcessError as e:
            notices.append(f"Could not clone {url}: {e.stderr.strip()}")
            return
        rule = read_settings(settings_path)["passages"]
        extensions = rule["code_extensions"]
        files = [(path, text) for path, text in files if Path(path).suffix in extensions]
        if not files:
            notices.append(f"No files in {title} have an extension in code_extensions ({', '.join(extensions)}).")
            return
        random.shuffle(files)  # once: the Passages' ords then keep this order
        passages, skipped = [], 0
        for _, text in files:
            found, n = code_passages(text, rule["max_dropped"], rule["min_length"], rule["code_chars"])
            passages += found
            skipped += n
        add_source(title, repo_text(files), passages, codes=[True] * len(passages))
        notices.append(f"Imported {title}: {len(passages)} parts, {skipped} functions skipped.")

    async def import_symbol_docs():
        """Clones the doc repos and stores the symbol doc Sources whose titles are not stored yet."""
        settings = read_settings(settings_path).unwrap()
        rule = settings["passages"]
        try:
            found = await asyncio.to_thread(
                symbol_docs,
                settings["symbols"]["python_branch"],
                rule["max_dropped"],
                rule["min_length"],
                rule["code_chars"],
            )
        except subprocess.CalledProcessError as e:
            notices.append(f"Could not clone the Python, Gleam and shell docs: {e.stderr.strip()}")
            return
        except Exception as e:  # such as a repo whose files are no longer where they were
            notices.append(f"Could not import the Python, Gleam and shell docs: {e!r}")
            return
        stored = {title for (title,) in db.execute("SELECT title FROM source")}
        found = [(title, text, parts) for title, text, parts in found if title not in stored]
        for title, text, parts in found:
            add_source(title, text, [p for _, p in parts], [h for h, _ in parts], [True] * len(parts), symbol_source=True)
        await symbol_docs_imported([(title, len(parts)) for title, _, parts in found])

    async def symbol_docs_imported(counts: list[tuple[str, int]]):
        """The end of an import of the symbol docs, after its Sources are stored. Each Symbol in
        fewer than [symbols] min_lines lines of the line pool, and with fewer than max_lessons
        Symbol Lessons, gets a Symbol Lesson in the queue, the rarest first. A notice gives
        each Source's number of Passages, the size of the line pool, the 5 rarest Symbols with
        their numbers of lines, and the Symbols queued. Each Symbol Lesson that is refused gets a
        notice of its own with the reason."""
        settings = read_settings(settings_path).unwrap()
        lines = line_pool(db)
        held = {s: lines_holding(s, lines) for s in SYMBOLS}
        rarest = sorted(SYMBOLS, key=held.__getitem__)
        queued, refusals = [], []
        for s in rarest:
            if not wants_symbol_lesson(s, held[s], settings["symbols"]):
                continue
            if refused := await queue_symbol_lesson(s, settings["lessons"]):
                refusals.append(refused)
            else:
                queued.append(s)
        listed = ", ".join(f"{title} ({n} parts)" for title, n in counts) or "no new texts"
        fewest = ", ".join(f"{s} {held[s]}" for s in rarest[:5])
        queued_text = f"Symbol lessons queued for {' '.join(queued)}." if queued else "No symbol lessons queued."
        notices.append(
            f"Imported the Python, Gleam and shell docs: {listed}. Symbol drills can use {len(lines):,} lines of code;"
            f" the rarest symbols, with their numbers of lines: {fewest}. {queued_text}"
        )
        notices.extend(refusals)

    def lines_holding(symbol: str, lines: list[str]) -> int:
        """The number of `lines` (of the line pool) that hold `symbol`."""
        return sum(symbol in line for line in lines)

    def symbol_lesson_topics(symbol: str) -> list[str]:
        """The topics of the Symbol Lessons for `symbol` written so far: the Sources whose titles
        start with "Symbol <s>: ", without that start."""
        start = f"Symbol {symbol}: "
        found = db.execute("SELECT title FROM source WHERE instr(title, ?) = 1 ORDER BY id", (start,))
        return [title.removeprefix(start) for (title,) in found]

    def wants_symbol_lesson(symbol: str, held: int, symbols: dict) -> bool:
        """Whether `symbol` gets one more Symbol Lesson: when `held`, its number of lines in the
        line pool, is fewer than [symbols] min_lines, and it has fewer than max_lessons Symbol
        Lessons."""
        return held < symbols["min_lines"] and len(symbol_lesson_topics(symbol)) < symbols["max_lessons"]

    async def queue_symbol_lesson(symbol: str, lessons: dict) -> str | None:
        """Puts a Symbol Lesson for `symbol` in the queue, or returns the notice of why not."""
        try:
            await queue_lesson(LessonRequest(topic=f"Symbol {symbol}", symbol=symbol), lessons)
        except HTTPException as e:
            return f"No symbol lesson for {symbol}: {e.detail}"

    def lesson_call(request: LessonRequest, lessons: dict) -> tuple[dict, str, list[dict[str, str]]]:
        """The [lessons] settings, the model and the prompt messages of a Lesson. A Symbol Lesson
        uses the prompt symbol-lesson-v1 in place of the [lessons] prompt, and is told the topics
        of the earlier Symbol Lessons for its Symbol."""
        model = lessons[f"{request.language}_model"]
        if request.symbol is None:
            return lessons, model, LESSON_PROMPTS[lessons["prompt"]].write(request.language, request.topic, lessons)
        lessons = lessons | {"prompt": "symbol-lesson-v1"}
        earlier = symbol_lesson_topics(request.symbol)
        return lessons, model, LESSON_PROMPTS[lessons["prompt"]].write(request.language, request.symbol, lessons, earlier)

    def add_spend(lesson: int, reply: Reply):
        with db:
            db.execute(
                "INSERT INTO spend (lesson, time, usage, dollars) VALUES (?, ?, ?, ?)",
                (lesson, now(), json.dumps(reply.usage), reply.dollars),
            )

    async def check_code(lesson: int, language: str, model: str, markdown: str, lessons: dict) -> tuple[str, list]:
        """Runs each code block of a Lesson with `run_code`. A block that fails is sent to the
        model with its error for a repair, up to `repairs` times, and is dropped if it still
        fails. Each repair call is in the spend ledger with the Lesson. Gives the Markdown with
        the repaired blocks and without the dropped ones, and the check log: for each block, a
        list of its checks, each {code, error}, where error is None when it passed."""
        repair = LESSON_PROMPTS[lessons["prompt"]].repair
        log = []
        for block in CODE_BLOCK.finditer(markdown):
            checks = [{"code": block[1], "error": await asyncio.to_thread(run_code, language, block[1], lessons["timeout"])}]
            while checks[-1]["error"] and len(checks) <= lessons["repairs"]:
                messages = repair(language, checks[-1]["code"], checks[-1]["error"])
                reply = await asyncio.to_thread(provider.write, model, messages, lessons["repair_tokens"], lessons["reasoning"])
                add_spend(lesson, reply)
                code = code_in(reply.text)
                checks.append({"code": code, "error": await asyncio.to_thread(run_code, language, code, lessons["timeout"])})
            log.append(checks)
        return with_codes(markdown, [None if checks[-1]["error"] else checks[-1]["code"] for checks in log]), log

    async def write_lesson(request: LessonRequest) -> tuple[str, bool]:
        """Has the model write a Lesson, checks its code, stores it as a Source, and returns the
        notice and whether it was stored. When too many code blocks are dropped, the Lesson is
        written again, up to WRITES times in all, and then rejected. Each time it is written has
        its own lesson row. A Symbol Lesson is stored as a Symbol Source, so its notice does not
        point to the list of Sources (o). The topic of a Symbol Lesson, and so its title, is
        "Symbol <s>: <the Lesson's # heading>"."""
        topic, language = request.topic, request.language
        settings = read_settings(settings_path).unwrap()
        lessons, model, messages = lesson_call(request, settings["lessons"])
        writes = 0
        while True:
            writes += 1
            reply = await asyncio.to_thread(provider.write, model, messages, lessons["max_tokens"], lessons["reasoning"])
            if request.symbol:
                topic = f"Symbol {request.symbol}: {heading(reply.text)}"
            with db:
                (lesson,) = db.execute(
                    "INSERT INTO lesson (made, topic, language, model, prompt, settings, output)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
                    (now(), topic, language, model, lessons["prompt"], json.dumps(lessons), reply.text),
                ).fetchone()
            add_spend(lesson, reply)
            text, log = await check_code(lesson, language, model, reply.text, lessons)
            with db:
                db.execute("UPDATE lesson SET checks = ? WHERE id = ?", (json.dumps(log), lesson))
            dropped = sum(bool(checks[-1]["error"]) for checks in log)
            if log and dropped < len(log) and dropped <= lessons["drop_share"] * len(log):
                break
            if writes == WRITES:
                why = f"{dropped} of {len(log)} code examples failed after repairs" if log else "it had no code example"
                return f"The lesson on {topic} failed: it was written {writes} times; the last time, {why}.", False
        rule = settings["passages"]
        parts, skipped = lesson_passages(
            text, rule["max_dropped"], rule["min_length"], rule["prose_chars"], rule["code_chars"]
        )
        if not parts:
            return f"The lesson on {topic} failed: it has nothing long enough to type.", False
        headings, passages, codes = zip(*parts)
        source = add_source(topic, text, list(passages), headings, codes, symbol_source=bool(request.symbol))
        with db:
            db.execute("UPDATE lesson SET source = ? WHERE id = ?", (source, lesson))
        notice = f"New lesson ready: {topic}: {len(parts)} parts, {skipped} skipped; {dropped} of {len(log)} code examples dropped."
        return notice + ("" if request.symbol else " It is first in the list of texts (o)."), True

    async def symbol_lesson_written(symbol: str, settings: dict) -> str:
        """After a Symbol Lesson for `symbol` is stored: counts again the lines of the line pool
        that hold `symbol`, and queues one more Symbol Lesson for it if `wants_symbol_lesson`.
        Returns the end of the Lesson's notice, with the count and whether one more was queued."""
        held = lines_holding(symbol, line_pool(db))
        held_text = f" {symbol} is in {held} lines of code"
        if not wants_symbol_lesson(symbol, held, settings["symbols"]):
            return held_text + "."
        if refused := await queue_symbol_lesson(symbol, settings["lessons"]):
            return f"{held_text}. {refused}"
        return held_text + "; another symbol lesson queued."

    # The Lessons asked for and not written yet, in the order asked for, each with its worst
    # case in dollars. `waiting` is the sum of those worst cases, which the cap counts.
    lesson_requests: asyncio.Queue[tuple[LessonRequest, float]] = asyncio.Queue()
    waiting = 0.0

    async def write_lessons():
        """Writes the Lessons asked for, one at a time. A notice says when each is ready, or why not.
        The notice of a stored Symbol Lesson ends with `symbol_lesson_written`. It runs after the
        Lesson's worst case leaves `waiting`, so its cap check counts only what the Lesson cost."""
        nonlocal waiting
        while True:
            request, worst = await lesson_requests.get()
            try:
                notice, stored = await write_lesson(request)
            except Exception as e:  # reported, so the next Lesson is still written
                notice, stored = f"The lesson on {request.topic} failed: {e}", False
            waiting -= worst
            if stored and request.symbol:
                try:
                    notice += await symbol_lesson_written(request.symbol, read_settings(settings_path).unwrap())
                except Exception as e:  # reported, so the next Lesson is still written
                    notice += f" Could not count the lines of code with {request.symbol} again: {e}"
            notices.append(notice)

    async def queue_lesson(request: LessonRequest, lessons: dict):
        """Puts a Lesson request in the queue, by the [lessons] settings, or raises HTTPException
        with why not. It is refused, and nothing is sent, when the month-to-date spend plus the
        worst cases of the Lessons still waiting and of this one (`worst_case`: written twice, with
        every repair call) could be more than the cap (spec §9)."""
        nonlocal waiting
        lessons, model, messages = lesson_call(request, lessons)
        try:
            worst = await asyncio.to_thread(worst_case, provider, model, request.language, messages, lessons)
        except (OSError, ValueError, KeyError) as e:  # the price list could not be read, or has no such model
            raise HTTPException(502, f"No price for {model}: {e!r}")
        if refused := cap_refusal(db, waiting + worst, lessons):
            raise HTTPException(409, refused)
        # Gleam blocks are built in the pre-made project, so it must be built before anything is paid for.
        if request.language == "gleam" and (error := await asyncio.to_thread(build_gleam_project)):
            raise HTTPException(502, f"Could not build the Gleam project: {error}")
        waiting += worst
        lesson_requests.put_nowait((request, worst))

    catalogue = db_path.with_name("pg_catalog.csv")
    static = Path(__file__).parent / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        background = [asyncio.create_task(refresh_catalogue(catalogue)), asyncio.create_task(write_lessons())]
        yield
        for task in background:
            task.cancel()

    app = FastAPI(lifespan=lifespan)

    # Adding a Board with a name that exists adds the .vil to that Board and
    # replaces its vial.json. A .vil that is already stored changes nothing.
    @app.post("/api/boards")
    async def add_board(new: NewBoard):
        with db:
            (board,) = db.execute(
                "INSERT INTO board (name, vial) VALUES (?, ?)"
                " ON CONFLICT (name) DO UPDATE SET vial = excluded.vial RETURNING id",
                (new.name, new.vial),
            ).fetchone()
            db.execute(
                "INSERT OR IGNORE INTO keymap_version VALUES (?, ?, ?)",
                (hashlib.sha256(new.vil.encode()).hexdigest(), board, new.vil),
            )
        return {"board": board}

    # A Keymap is a Board with one Letter layout. Its versions are the .vil files
    # with that Letter layout, and a new Session uses the newest one. Each Board
    # lists its Keymaps with the last used first. `last` is the last used Board.
    @app.get("/api/boards")
    async def boards():
        found: dict[int, dict] = {}
        for board, name, vial, version, vil, used in db.execute(
            "SELECT board.id, name, vial, hash, vil, (SELECT max(id) FROM session WHERE keymap_version = hash)"
            " FROM board JOIN keymap_version ON board = board.id"
            " ORDER BY board.id, keymap_version.rowid"  # oldest version first
        ):
            keymaps = found.setdefault(board, {"id": board, "name": name, "keymaps": {}})["keymaps"]
            letters = keymap_letters(vil, vial)
            used = max(used or 0, keymaps.get(letters, {"used": 0})["used"])  # the last Session's id, or 0
            keymaps[letters] = {"letter_layout": letters, "version": version, "used": used}
        for b in found.values():
            b["keymaps"] = sorted(b["keymaps"].values(), key=lambda k: -k["used"])
        last = max(found.values(), key=lambda b: b["keymaps"][0]["used"], default={"id": None})["id"]
        return {"boards": list(found.values()), "last": last}

    @app.post("/api/sessions")
    async def start_session(new: NewSession):
        with db:
            session = db.execute(
                "INSERT INTO session (started, keymap_version) VALUES (?, ?)", (now(), new.keymap_version)
            ).lastrowid
        return {"session": session, **served(None)}

    # An Attempt is stored with its first key event and stays abandoned unless a
    # batch lists it as finished. Resent events and finishes change nothing.
    @app.post("/api/sessions/{session}/batch", status_code=204)
    async def ingest(session: int, batch: Batch):
        with db:
            db.executemany(
                "INSERT OR IGNORE INTO key_event VALUES"
                " (:session, :seq, :attempt, :t, :type, :code, :key, :shift, :ctrl, :alt, :meta, :repeat)",
                [{"session": session, **e.model_dump()} for e in batch.events],
            )
            db.executemany(
                "INSERT OR IGNORE INTO attempt (session, ord, finished, settings, passage) VALUES (?, ?, 0, ?, ?)",
                [
                    (session, a, json.dumps(batch.attempts[a].settings), batch.attempts[a].passage)
                    for a in {e.attempt for e in batch.events}
                ],
            )
            newly_finished = db.executemany(
                "INSERT INTO attempt (session, ord, finished) VALUES (?, ?, 1)"
                " ON CONFLICT DO UPDATE SET finished = 1 WHERE finished = 0",
                [(session, attempt) for attempt in batch.finished],
            ).rowcount
        # After a batch that finishes an Attempt for the first time, the next key of a Letter
        # layout being learned may unlock.
        if newly_finished:
            settings = read_settings(settings_path).unwrap()
            _, letters, _, _ = session_keymap(session)
            state = unlocking(db, letters, settings["unlocking"])
            if state and state.locked and unlock_due(db, letters, state.unlocked, settings):
                add_unlock(letters, state.locked[0], settings, "rule")

    # The page shows this on the message line after each finished Attempt. The medians are
    # over the finished Attempts on the same Board and Letter layout in the last `weeks` weeks
    # (of the [weakness] settings). The slowest pairs are the 3 pairs of the Passage that the
    # Weakness model in use ranks highest.
    # It also has the unlock state, which the rule may have changed after the Attempt.
    @app.get("/api/sessions/{session}/attempts/{ord}/summary")
    async def attempt_summary(session: int, ord: int):
        settings = read_settings(settings_path).unwrap()
        table = attempts(db, since=datetime.now(UTC) - timedelta(weeks=settings["weakness"]["weeks"]))
        attempt = table.filter(session=session, ord=ord).row(0, named=True)
        (text,) = db.execute("SELECT text FROM passage WHERE id = ?", (attempt["passage"],)).fetchone()
        pairs = {text[i : i + 2] for i in range(len(text) - 1)}
        ranking = weakness(db, attempt["board"], attempt["letter_layout"], settings["weakness"])
        same_keymap = table.filter(
            pl.col("finished"),
            pl.col("board").eq_missing(attempt["board"]),
            pl.col("letter_layout").eq_missing(attempt["letter_layout"]),
        )
        return {
            "wpm": attempt["wpm"],
            "accuracy": attempt["accuracy"],
            "median_wpm": same_keymap["wpm"].median(),
            "median_accuracy": same_keymap["accuracy"].median(),
            "slowest_pairs": ranking.filter(pl.col("unit").is_in(pairs))["unit"].head(3).to_list(),
            "unlocking": unlock_progress(unlocking(db, attempt["letter_layout"], settings["unlocking"])),
        }

    def version_keymap(version: str | None) -> tuple[str | None, str | None, str | None, str | None]:
        """The Board name, the Letter layout, the .vil and the vial.json of a Keymap version.
        All are None for a version that is not stored, as for Sessions from before Boards."""
        found = db.execute(
            "SELECT b.name, k.vil, b.vial FROM keymap_version k JOIN board b ON b.id = k.board WHERE k.hash = ?",
            (version,),
        ).fetchone()
        board, vil, vial = found or (None, None, None)
        return board, keymap_letters(vil, vial) if vil else None, vil, vial

    def session_keymap(session: int) -> tuple[str | None, str | None, str | None, str | None]:
        """`version_keymap` of a Session's Keymap version."""
        (version,) = db.execute("SELECT keymap_version FROM session WHERE id = ?", (session,)).fetchone()
        return version_keymap(version)

    def unlock_progress(state: Unlocking | None) -> dict | None:
        """The unlock state as the page shows it, as in "10/30 keys · next o"; None for a
        Letter layout that is not being learned."""
        if not state:
            return None
        return {
            "unlocked": len(state.unlocked),
            "total": len(state.unlocked) + len(state.locked),
            "next": state.locked[:1] or None,
            "introducing": state.introducing,
        }

    # Makes a Drill for the Session's Board and Letter layout, and stores it as a Passage with
    # no Source. A Symbol Drill is made by symbols-v1 and may use every key. Else, while
    # Introduction Drills are due, it is one; else the settings name the generator. On a Letter
    # layout being learned, it uses only the Unlocked keys until all are unlocked. The
    # Introduction Drills of the last key to unlock use them too. 409 when the line pool for
    # a Symbol Drill is empty.
    @app.post("/api/sessions/{session}/drills")
    async def make_drill(session: int, request: DrillRequest = DrillRequest()):
        settings = read_settings(settings_path).unwrap()
        board, letters, _, _ = session_keymap(session)
        state = unlocking(db, letters, settings["unlocking"])
        introducing = bool(state and state.introducing)
        if request.introduction and not introducing:
            return {"unlocking": unlock_progress(state)}
        if request.symbols:
            generator, unlocked = "symbols-v1", None
        else:
            generator = "introduction" if introducing else settings["drills"]["generator"]
            unlocked = state.unlocked if state and (state.locked or introducing) else None
        try:
            drill = DRILL_GENERATORS[generator](db, board, letters, settings, unlocked)
        except NoLines as e:
            raise HTTPException(409, str(e))
        with db:
            (passage,) = db.execute(
                "INSERT INTO passage (source, ord, text, normaliser) VALUES (NULL, 0, ?, 'ascii-v1') RETURNING id",
                (drill.text,),
            ).fetchone()
            db.execute(
                "INSERT INTO drill VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    passage, now(), session, settings["weakness"]["model"], generator, json.dumps(drill.targets),
                    unlocked and json.dumps(list(unlocked)), json.dumps(drill.made_up) if drill.made_up else None,
                ),
            )
        return {
            "id": passage, "text": drill.text, "targets": drill.targets, "generator": generator,
            "unlocking": unlock_progress(state),
        }

    # u in the Escape menu: unlocks the next key of the Letter layout being learned at once.
    @app.post("/api/sessions/{session}/unlocks")
    async def unlock_by_hand(session: int):
        settings = read_settings(settings_path).unwrap()
        _, letters, _, _ = session_keymap(session)
        state = unlocking(db, letters, settings["unlocking"])
        if not state:
            raise HTTPException(409, f"Only {settings['unlocking']['letter_layout']} has locked keys.")
        if not state.locked:
            raise HTTPException(409, "Every key is unlocked.")
        add_unlock(letters, state.locked[0], settings, "manual")
        return unlock_progress(unlocking(db, letters, settings["unlocking"]))

    # The practice screen fetches this when a Session starts and after an unlock: a drawing
    # of each layer of the Keymap, with the layer names of the [keymaps] settings and the
    # locked keys; the key to press for each character; and the unlock state. That key is the
    # character's first candidate, which key attribution picks for a correct keystroke.
    @app.get("/api/sessions/{session}/keymap")
    async def keymap_drawing(session: int):
        board, letters, vil, vial = session_keymap(session)
        if not vil:
            return {"layers": [], "keys": {}, "unlocking": None}
        settings = read_settings(settings_path).unwrap()
        names = layer_names(settings, board, letters)
        state = unlocking(db, letters, settings["unlocking"])
        locked = state.locked if state else ""
        return {
            "layers": [svg for _, svg in draw_layers(vil, vial, names, locked=locked)],
            "keys": {char: {"layer": keys[0].layer, "key": keys[0].key} for char, keys in read_keymap(vil).keys.items()},
            "unlocking": unlock_progress(state),
        }

    # The progress page of the Board and Letter layout of a Keymap version (spec §11): the
    # trend chart as a Vega-Lite spec, with its number of days and weeks; the name and heat
    # drawing of each layer, with an arc for each of the weakest pairs; and the 10 weakest
    # characters and pairs. The page lists the Keymaps from GET /api/boards, which gives
    # the newest version of each.
    @app.get("/api/keymaps/{version}/progress")
    async def progress_page(version: str):
        board, letters, vil, vial = version_keymap(version)
        assert vil  # the page asks only for versions that GET /api/boards lists
        settings = read_settings(settings_path).unwrap()
        found = progress(db, board, letters, settings["weakness"])
        state = unlocking(db, letters, settings["unlocking"])
        locked = state.locked if state else ""
        pairs = found.pairs["unit"].to_list()
        layers = draw_layers(vil, vial, layer_names(settings, board, letters), found.heat, pairs, locked)
        weakest = ["unit", "cost", "seen"]
        return {
            "weeks": TREND_WEEKS,
            "days": found.trend.height,
            "trend": trend_chart(found.trend).to_dict(),
            "names": [name for name, _ in layers],
            "layers": [svg for _, svg in layers],
            "unlocking": unlock_progress(state),
            "chars": found.chars.select(weakest).to_dicts(),
            "pairs": found.pairs.select(weakest).to_dicts(),
        }

    @app.get("/api/gutenberg")
    async def search_books(q: str):
        if not catalogue.exists():
            raise HTTPException(503, "The Gutenberg catalogue is still downloading. Try again in a minute.")
        return await asyncio.to_thread(search_catalogue, catalogue, q)

    # Downloads the book's plain text. Paragraphs that lose too much when made ASCII are skipped.
    @app.post("/api/gutenberg")
    async def import_book(book: Book):
        n = book.number
        text = (await asyncio.to_thread(fetch, f"https://www.gutenberg.org/cache/epub/{n}/pg{n}.txt")).decode()
        rule = read_settings(settings_path)["passages"]
        passages, skipped = prose_passages(
            gutenberg_paragraphs(text), rule["max_dropped"], rule["min_length"], rule["prose_chars"]
        )
        return {"source": add_source(book.title, text, passages), "passages": len(passages), "skipped": skipped}

    # Clones in the background. A notice says when it is done.
    @app.post("/api/code", status_code=202)
    async def import_code(repo: Repo):
        in_background(import_repo(repo.url))

    # i then s in the Escape menu. Clones in the background, and stores Symbol Sources. A notice says when it is done.
    @app.post("/api/symbol-docs", status_code=202)
    async def request_symbol_docs():
        in_background(import_symbol_docs())

    # l in the Escape menu. The Lesson is written in the background after the ones asked for
    # before it, unless `queue_lesson` refuses it.
    @app.post("/api/lessons", status_code=202)
    async def request_lesson(request: LessonRequest):
        await queue_lesson(request, read_settings(settings_path).unwrap()["lessons"])

    # The month-to-date spend in pounds, which the Lesson form shows, and the cap. Also the
    # language of the last Lesson, which the form chooses at first.
    @app.get("/api/lessons/spend")
    async def lesson_spend():
        lessons = read_settings(settings_path).unwrap()["lessons"]
        (language,) = db.execute("SELECT language FROM lesson ORDER BY id DESC LIMIT 1").fetchone() or ("python",)
        return {"spent": spent(db, lessons["dollars_per_pound"]), "cap": lessons["cap"], "language": language}

    # The /send page posts the text that the article bookmarklet took from a web page.
    @app.post("/api/articles")
    async def import_article(article: Article):
        rule = read_settings(settings_path)["passages"]
        passages, skipped = prose_passages(
            article_paragraphs(article.text), rule["max_dropped"], rule["min_length"], rule["prose_chars"]
        )
        if not passages:
            raise HTTPException(422, "No paragraph in it is long enough to type.")
        source = add_source(article.title, article.text, passages)
        notices.append(
            f"Imported article {article.title}: {len(passages)} parts, {skipped} paragraphs skipped."
            " It is first in the list of texts (o)."
        )
        return {"source": source}

    @app.get("/api/notices")
    async def get_notices():
        return notices

    # The o list, which a new Session also resumes from. Symbol Sources are left out.
    # Unfinished Sources come first, the last opened first.
    @app.get("/api/sources")
    async def sources():
        return [
            {"id": id, "title": title, "at": at, "total": total}
            for id, title, at, total in db.execute(
                "SELECT id, title, bookmark, total FROM source WHERE NOT symbol_source ORDER BY bookmark >= total, opened DESC"
            )
        ]

    # Opening a Source, finishing a Passage and skipping one all set the bookmark.
    @app.put("/api/sources/{source}/bookmark")
    async def set_bookmark(source: int, bookmark: Bookmark):
        with db:
            title, total = db.execute(
                "UPDATE source SET bookmark = ?, opened = ? WHERE id = ? RETURNING title, total",
                (bookmark.at, now(), source),
            ).fetchone()
        return served({"id": source, "title": title, "at": bookmark.at, "total": total})

    @app.get("/api/settings")
    async def get_settings():
        return read_settings(settings_path).unwrap()

    # Changes only the values, so comments and formatting in the file stay as they are.
    @app.put("/api/settings", status_code=204)
    async def save_settings(settings: dict[str, dict]):
        doc = read_settings(settings_path)
        for table, values in settings.items():
            doc[table].update(values)
        settings_path.write_text(tomlkit.dumps(doc))

    # The page that the article bookmarklet opens. StaticFiles serves it only as /send.html.
    @app.get("/send")
    async def send_page():
        return FileResponse(static / "send.html")

    app.mount("/", StaticFiles(directory=static, html=True))
    return app


def main():
    app = create_app(Path("typokiller.db"), Path("typokiller.toml"), OpenRouter(Path(".env")))
    uvicorn.run(app, host="0.0.0.0", port=8000)
