import argparse
import hashlib
import sqlite3
from pathlib import Path

import tomlkit
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from typokiller.keymap import keymap_letters

SCHEMA = """
CREATE TABLE IF NOT EXISTS board (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, vial TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS keymap_version (hash TEXT PRIMARY KEY, board INTEGER NOT NULL, vil TEXT NOT NULL);
"""

# The tables of typokiller's own practice, from before keybr was the typing app (ADR 0004).
# A database made then loses them at the first start.
PRACTICE_TABLES = ["session", "source", "passage", "drill", "unlock", "lesson", "spend", "attempt", "key_event"]

# Written to the settings file when it is missing.
DEFAULT_SETTINGS = """\
# typokiller settings. Edit this file in any editor.

[lists]
# The letters that label the items of a list, such as the Board list. An item is chosen by
# typing its label. The first items get one letter, in this order, and the others two. j and k,
# and n in the Board list, are never labels.
letters = "sadflewcmpgh"

[keymaps]
# The layer names in Keymap drawings, for each Board and Letter layout. A layer with no
# name is named after the key that opens it. Put a Board name with spaces in quotes,
# such as [keymaps."Q3 Max".QWERTY]. For example:
# [keymaps.Sweep.QWERTY]
# layers = ["Base", "Sym", "Nav", "Stack", "Num"]
"""

# The settings tables of typokiller's own practice. A file made then loses them.
PRACTICE_SETTINGS = ["typing", "passages", "weakness", "drills", "symbols", "unlocking", "lessons"]


def read_settings(path: Path) -> tomlkit.TOMLDocument:
    if not path.exists():
        path.write_text(DEFAULT_SETTINGS)
    doc = tomlkit.parse(path.read_text())
    # A file made by an older typokiller gets the tables added since, with their comments,
    # and the settings added since to its tables, without their comments. It loses the
    # tables of typokiller's own practice.
    text = tomlkit.dumps(doc)
    for name in PRACTICE_SETTINGS:
        doc.pop(name, None)
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


class NewBoard(BaseModel):
    name: str
    vil: str  # the text of the .vil file
    vial: str  # the text of the vial.json file


def create_app(db_path: Path, settings_path: Path) -> FastAPI:
    db = sqlite3.connect(db_path, check_same_thread=False)
    with db:
        for table in PRACTICE_TABLES:
            db.execute(f"DROP TABLE IF EXISTS {table}")
    db.executescript(SCHEMA)
    read_settings(settings_path)

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

    # A Keymap is a Board with one Letter layout. Its versions are the .vil files with that
    # Letter layout. Each Board lists its Keymaps in the order they were first added, each
    # with its newest version.
    @app.get("/api/boards")
    async def boards():
        found: dict[int, dict] = {}
        for board, name, vial, version, vil in db.execute(
            "SELECT board.id, name, vial, hash, vil FROM board JOIN keymap_version ON board = board.id"
            " ORDER BY board.id, keymap_version.rowid"  # oldest version first
        ):
            keymaps = found.setdefault(board, {"id": board, "name": name, "keymaps": {}})["keymaps"]
            letters = keymap_letters(vil, vial)
            keymaps[letters] = {"letter_layout": letters, "version": version}
        return {"boards": [b | {"keymaps": list(b["keymaps"].values())} for b in found.values()]}

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))
    return app


def options(args: list[str] | None = None) -> argparse.Namespace:
    """The command-line options: `port` and `access_log`. `args` is sys.argv[1:] when None."""
    parser = argparse.ArgumentParser(prog="typokiller")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-access-log", dest="access_log", action="store_false", help="log only errors and start-up")
    return parser.parse_args(args)


def main():
    opts = options()
    app = create_app(Path("typokiller.db"), Path("typokiller.toml"))
    uvicorn.run(app, host="0.0.0.0", port=opts.port, access_log=opts.access_log)
