import hashlib
import json
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import tomlkit
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from typokiller.keymap import letter_layout

# A placeholder until Sources are imported.
PASSAGE = (
    "It is a truth universally acknowledged, that a single man in possession "
    "of a good fortune, must be in want of a wife."
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS board (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, vial TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS keymap_version (hash TEXT PRIMARY KEY, board INTEGER NOT NULL, vil TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session (id INTEGER PRIMARY KEY, started TEXT NOT NULL, keymap_version TEXT);
CREATE TABLE IF NOT EXISTS attempt (
    session INTEGER NOT NULL,
    ord INTEGER NOT NULL,
    finished INTEGER NOT NULL,
    settings TEXT,
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
"""


def read_settings(path: Path) -> tomlkit.TOMLDocument:
    if not path.exists():
        path.write_text(DEFAULT_SETTINGS)
    return tomlkit.parse(path.read_text())


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


class Batch(BaseModel):
    events: list[KeyEvent] = []
    finished: list[int] = []  # the ords of Attempts that finished
    settings: dict[int, dict] = {}  # the settings each Attempt in `events` was typed with, by ord


class NewSession(BaseModel):
    keymap_version: str  # its hash


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

    app = FastAPI()

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
            started = datetime.now(UTC).isoformat()
            session = db.execute(
                "INSERT INTO session (started, keymap_version) VALUES (?, ?)", (started, new.keymap_version)
            ).lastrowid
        return {"session": session, "passage": PASSAGE}

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
                "INSERT OR IGNORE INTO attempt VALUES (?, ?, 0, ?)",
                [(session, a, json.dumps(batch.settings[a])) for a in {e.attempt for e in batch.events}],
            )
            db.executemany(
                "INSERT INTO attempt (session, ord, finished) VALUES (?, ?, 1) ON CONFLICT DO UPDATE SET finished = 1",
                [(session, attempt) for attempt in batch.finished],
            )

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

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))
    return app


def main():
    uvicorn.run(create_app(Path("typokiller.db"), Path("typokiller.toml")), host="0.0.0.0", port=8000)
