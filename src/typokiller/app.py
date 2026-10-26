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
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import tomlkit
import truststore
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from typokiller.keymap import letter_layout
from typokiller.sources import (
    article_paragraphs,
    code_passages,
    gutenberg_paragraphs,
    prose_passages,
    search_catalogue,
)

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
    opened TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS passage (
    id INTEGER PRIMARY KEY,
    source INTEGER,
    ord INTEGER NOT NULL,
    text TEXT NOT NULL,
    normaliser TEXT NOT NULL
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
"""

# Written to the settings file when it is missing. Later tickets add their settings here.
DEFAULT_SETTINGS = """\
# typokiller settings. Edit this file, or press , in the app's Escape menu.
# The app reads this file again before each Attempt.

[typing]
# What a wrong key does: "keep typing" puts it in and moves the cursor on;
# "locked until fixed" keeps the cursor in place until the right key is typed.
wrong_key_mode = "keep typing"

[passages]
# A paragraph or function is not made into a Passage when normalising it to ASCII
# dropped more than this share of its characters, or left it shorter than min_length
# characters.
max_dropped = 0.05
min_length = 20
"""


def now() -> str:
    return datetime.now(UTC).isoformat()


def read_settings(path: Path) -> tomlkit.TOMLDocument:
    if not path.exists():
        path.write_text(DEFAULT_SETTINGS)
    doc = tomlkit.parse(path.read_text())
    # A file made by an older typokiller gets the tables added since, with their comments.
    missing = {name: table for name, table in tomlkit.parse(DEFAULT_SETTINGS).items() if name not in doc}
    if missing:
        doc.update(missing)
        path.write_text(tomlkit.dumps(doc))
    return doc


CATALOGUE_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"


# Checks certificates with the macOS keychain, as browsers and curl do. Python's
# default, /etc/ssl/cert.pem, lacks the root certificate that gutenberg.org uses.
TLS = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "typokiller"})
    with urllib.request.urlopen(request, timeout=60, context=TLS) as response:
        return response.read()


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
    """The path and text of each text file that git tracks in the repo at `url`.

    git uses the Mac's own credentials, so private repos work. GIT_TERMINAL_PROMPT=0 stops
    git from asking for a password that nobody would see. Symbolic links are not followed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ | {"GIT_TERMINAL_PROMPT": "0"}
        subprocess.run(
            ["git", "clone", "--depth", "1", "-q", url, tmp], check=True, capture_output=True, text=True, env=env
        )
        listed = subprocess.run(["git", "-C", tmp, "ls-files", "-z"], check=True, capture_output=True, text=True).stdout
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


class NewBoard(BaseModel):
    name: str
    vil: str  # the text of the .vil file
    vial: str  # the text of the vial.json file


def create_app(db_path: Path, settings_path: Path) -> FastAPI:
    db = sqlite3.connect(db_path, check_same_thread=False)
    db.executescript(SCHEMA)
    # Databases made before these columns existed get them here. Their old rows keep NULL.
    for table, column in [("session", "keymap_version"), ("attempt", "settings")]:
        with suppress(sqlite3.OperationalError):  # fails when the column is there already
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    with db:
        db.execute("INSERT OR IGNORE INTO passage VALUES (1, NULL, 0, ?, 'ascii-v1')", (PASSAGE,))
        with suppress(sqlite3.OperationalError):
            db.execute("ALTER TABLE attempt ADD COLUMN passage INTEGER")
            db.execute("UPDATE attempt SET passage = 1")  # every Attempt before there were Sources typed it

    def served(source: dict | None) -> dict:
        """The Source's Passage at its bookmark and the one after it. After the Source's
        last Passage comes the built-in Passage, and a finished Source is closed."""
        rows = []
        if source:
            rows = db.execute(
                "SELECT id, text FROM passage WHERE source = ? AND ord >= ? ORDER BY ord LIMIT 2",
                (source["id"], source["at"]),
            ).fetchall()
        passages = [{"id": id, "text": text} for id, text in rows] + [BUILT_IN]
        return {"source": source if rows else None, "passages": passages[:2]}

    def add_source(title: str, text: str, passages: list[str]) -> int:
        with db:
            (source,) = db.execute(
                "INSERT INTO source (title, text, total, opened) VALUES (?, ?, ?, ?) RETURNING id",
                (title, text, len(passages), now()),
            ).fetchone()
            db.executemany(
                "INSERT INTO passage (source, ord, text, normaliser) VALUES (?, ?, ?, 'ascii-v1')",
                [(source, i, p) for i, p in enumerate(passages)],
            )
        return source

    notices: list[str] = []  # every open practice page shows each new one on its message line
    tasks: set[asyncio.Task] = set()  # background work, kept here until it is done so Python does not delete it

    async def import_repo(url: str):
        title = Path(url).name.removesuffix(".git")
        try:
            files = await asyncio.to_thread(clone, url)
        except subprocess.CalledProcessError as e:
            notices.append(f"Could not clone {url}: {e.stderr.strip()}")
            return
        random.shuffle(files)  # once: the Passages' ords then keep this order
        rule = read_settings(settings_path)["passages"]
        passages, skipped = [], 0
        for _, text in files:
            found, n = code_passages(text, rule["max_dropped"], rule["min_length"])
            passages += found
            skipped += n
        add_source(title, "".join(f"--- {path}\n{text}" for path, text in files), passages)
        notices.append(f"Imported {title}: {len(passages)} Passages, {skipped} functions skipped.")

    catalogue = db_path.with_name("pg_catalog.csv")
    static = Path(__file__).parent / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        refresh = asyncio.create_task(refresh_catalogue(catalogue))
        yield
        refresh.cancel()

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
            letters = letter_layout(json.loads(vil), json.loads(vial))
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
            db.executemany(
                "INSERT INTO attempt (session, ord, finished) VALUES (?, ?, 1) ON CONFLICT DO UPDATE SET finished = 1",
                [(session, attempt) for attempt in batch.finished],
            )

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
        passages, skipped = prose_passages(gutenberg_paragraphs(text), rule["max_dropped"], rule["min_length"])
        return {"source": add_source(book.title, text, passages), "passages": len(passages), "skipped": skipped}

    # Clones in the background. A notice says when it is done.
    @app.post("/api/code", status_code=202)
    async def import_code(repo: Repo):
        task = asyncio.create_task(import_repo(repo.url))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    # The /send page posts the text that the article bookmarklet took from a web page.
    @app.post("/api/articles")
    async def import_article(article: Article):
        rule = read_settings(settings_path)["passages"]
        passages, skipped = prose_passages(article_paragraphs(article.text), rule["max_dropped"], rule["min_length"])
        if not passages:
            raise HTTPException(422, "No paragraph in it is long enough to type.")
        source = add_source(article.title, article.text, passages)
        notices.append(
            f"Imported article {article.title}: {len(passages)} Passages, {skipped} paragraphs skipped."
            " It is first in the list of Sources (o)."
        )
        return {"source": source}

    @app.get("/api/notices")
    async def get_notices():
        return notices

    # Unfinished Sources come first, the last opened first.
    @app.get("/api/sources")
    async def sources():
        return [
            {"id": id, "title": title, "at": at, "total": total}
            for id, title, at, total in db.execute(
                "SELECT id, title, bookmark, total FROM source ORDER BY bookmark >= total, opened DESC"
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
    uvicorn.run(create_app(Path("typokiller.db"), Path("typokiller.toml")), host="0.0.0.0", port=8000)
