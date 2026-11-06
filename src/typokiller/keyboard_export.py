"""The keyboard export: the Boards and Keymap versions of the typokiller database, in the format
that keybr imports. keybr reads it from `GET /api/keyboards/export` each time its typing page
loads. The format is defined in keybr/packages/keybr-recording/lib/keyboards.ts and
keybr/docs/detailed_recording.md.

It holds configuration only: no typing history, secrets or environment settings."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from typokiller.keymap import keymap_letters

FORMAT = "keybr-keyboard-export"
FORMAT_VERSION = 1


def export_keyboards(db: sqlite3.Connection, settings: dict[str, Any]) -> dict[str, Any]:
    """The keyboard export of every Board in the database, ordered by id. Each Board lists every
    saved .vil, oldest first. `vial` and `vil` are the stored texts exactly: a .vil `uid` can be
    larger than JavaScript's safe integers, so the texts are never parsed and written again.
    `settings` are the settings file's tables, as `app.read_settings` gives them; the layer names
    come from their [keymaps] table."""
    boards = []
    for board, name, vial in db.execute("SELECT id, name, vial FROM board ORDER BY id"):
        versions = []
        for hash, vil in db.execute("SELECT hash, vil FROM keymap_version WHERE board = ? ORDER BY rowid", (board,)):
            letters = keymap_letters(vil, vial)
            versions.append({
                "sourceHash": hash,
                "vil": vil,
                "letterLayout": letters,
                "layers": list(settings["keymaps"].get(name, {}).get(letters, {}).get("layers", [])),
            })
        boards.append({"sourceId": board, "name": name, "vial": vial, "keymaps": versions})
    return {
        "format": FORMAT,
        "formatVersion": FORMAT_VERSION,
        "exportedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": {"application": "typokiller"},
        "boards": boards,
    }
