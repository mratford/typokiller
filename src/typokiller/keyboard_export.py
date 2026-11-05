"""typokiller-export-keyboards: writes the Boards and Keymap versions of a typokiller database in
the import format of keybr (`keybr recording import-keyboards`). The format is defined in
keybr/packages/keybr-recording/lib/keyboards.ts and keybr/docs/detailed_recording.md.

It exports configuration only: no typing history, secrets or environment settings. It opens the
database read-only and only reads the settings file, so it does not need the server, and it
changes neither file. Its messages are screen text, so they use plain words."""

import argparse
import json
import sqlite3
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from typokiller import service
from typokiller.app import layer_names
from typokiller.keymap import keymap_letters

FORMAT = "keybr-keyboard-export"
FORMAT_VERSION = 1


def open_read_only(path: Path) -> sqlite3.Connection:
    """The database at `path`, opened read-only. Raises sqlite3.OperationalError when it does not exist."""
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def read_settings_file(path: Path) -> dict[str, Any]:
    """The settings file's tables, or {} when there is no file. This does not use
    `app.read_settings`, because that writes the file when it is missing or old."""
    return tomllib.loads(path.read_text()) if path.exists() else {}


def export_keyboards(db: sqlite3.Connection, settings: dict[str, Any]) -> dict[str, Any]:
    """The keyboard export of every Board in the database, ordered by id. Each Board lists every
    saved .vil, oldest first. `vial` and `vil` are the stored texts exactly: a .vil `uid` can be
    larger than JavaScript's safe integers, so the texts are never parsed and written again.
    `settings` are the settings file's tables; the layer names come from its [keymaps] table."""
    keymaps = {"keymaps": settings.get("keymaps", {})}
    boards = []
    for board, name, vial in db.execute("SELECT id, name, vial FROM board ORDER BY id"):
        versions = []
        for hash, vil in db.execute("SELECT hash, vil FROM keymap_version WHERE board = ? ORDER BY rowid", (board,)):
            letters = keymap_letters(vil, vial)
            versions.append({
                "sourceHash": hash,
                "vil": vil,
                "letterLayout": letters,
                "layers": list(layer_names(keymaps, name, letters)),
            })
        boards.append({"sourceId": board, "name": name, "vial": vial, "keymaps": versions})
    return {
        "format": FORMAT,
        "formatVersion": FORMAT_VERSION,
        "exportedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": {"application": "typokiller"},
        "boards": boards,
    }


def main(args: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="typokiller-export-keyboards",
        description="Writes your keyboards and their saved layouts to a file that keybr can import. See the README.",
    )
    parser.add_argument("output", type=Path, help="the file to write; it must not exist yet")
    parser.add_argument("--db", type=Path, help="the database to read (default: the service's database)")
    parser.add_argument("--settings", type=Path, help="the settings file to read (default: typokiller.toml next to the database)")
    opts = parser.parse_args(args)
    db_path = opts.db or service.notebook_db(service.data_folder())
    settings_path = opts.settings or db_path.with_name("typokiller.toml")
    if opts.output.exists():
        parser.exit(1, f"{opts.output} already exists. Choose a new file name.\n")
    if not db_path.exists():
        parser.exit(1, f"There is no database at {db_path.resolve()}.\n")
    db = open_read_only(db_path)
    try:
        export = export_keyboards(db, read_settings_file(settings_path))
    finally:
        db.close()
    if not export["boards"]:
        parser.exit(1, f"The database {db_path.resolve()} has no keyboards. Add a keyboard in typokiller first.\n")
    # "x": fails rather than overwrite a file made since the check above.
    with opts.output.open("x") as file:
        json.dump(export, file, ensure_ascii=False, indent=2)
        file.write("\n")
    layouts = sum(len(board["keymaps"]) for board in export["boards"])
    print(f"Wrote {len(export['boards'])} keyboards with {layouts} saved layouts to {opts.output}.")
    print(f"Database: {db_path.resolve()}")
    print(f"Settings: {settings_path.resolve()}" + ("" if settings_path.exists() else " (not found: no layer names)"))
    sys.stdout.flush()
