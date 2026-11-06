"""Test helpers for keybr recordings: the shared fixtures, and recordings files built from them.

The fixtures are keybr's own files in keybr/packages/keybr-recording/fixtures/. The tests of both
apps read these same files, so a change on one side that breaks the other side fails a test.

keybr has no fixture recordings file, so `build_recordings` writes one, as keybr would: with
keybr's own tables (STORE_SCHEMA), the keyboards imported from a keyboard export, and the records
of the fixture scenarios.
"""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KEYBR_FIXTURES = Path(__file__).parents[1] / "keybr" / "packages" / "keybr-recording" / "fixtures"

# The tables of keybr's recording database: migrations 0 and 1 in
# keybr/packages/keybr-recording-store/lib/index.ts, copied from there.
STORE_SCHEMA_V1 = """
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
INSERT INTO metadata VALUES ('schemaVersion', '1');
CREATE TABLE snapshots(kind TEXT NOT NULL, id TEXT NOT NULL, version TEXT NOT NULL, json TEXT NOT NULL, PRIMARY KEY(kind,id,version)) STRICT;
CREATE TABLE attempts(id TEXT PRIMARY KEY, context TEXT, incomplete INTEGER NOT NULL DEFAULT 0, interrupted INTEGER NOT NULL DEFAULT 0) STRICT;
CREATE TABLE records(attempt_id TEXT NOT NULL REFERENCES attempts(id), sequence INTEGER NOT NULL, observed_at REAL NOT NULL, type TEXT NOT NULL, schema_version INTEGER NOT NULL, json TEXT NOT NULL, PRIMARY KEY(attempt_id,sequence)) STRICT;
CREATE INDEX records_time ON records(observed_at);
CREATE INDEX records_type ON records(attempt_id,type);
PRAGMA user_version=1;
"""
STORE_SCHEMA_V2 = """
INSERT INTO metadata VALUES ('databaseVersion', '2');
CREATE TABLE keyboard_sources(
  seq INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  id TEXT NOT NULL,
  version TEXT NOT NULL,
  source TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  UNIQUE(kind,id,version,source),
  FOREIGN KEY(kind,id,version) REFERENCES snapshots(kind,id,version)
) STRICT;
PRAGMA user_version=2;
"""
STORE_SCHEMA = STORE_SCHEMA_V1 + STORE_SCHEMA_V2

IMPORTED_AT = "2026-11-01T09:30:00.000Z"


def scenarios() -> dict[str, dict[str, Any]]:
    """The scenarios of v1.json, by name."""
    return {s["name"]: s for s in json.loads((KEYBR_FIXTURES / "v1.json").read_text())["scenarios"]}


def records(name: str) -> list[dict[str, Any]]:
    """The expected records of one scenario."""
    return scenarios()[name]["expected"]["records"]


def keyboard_export(name: str = "initial.json") -> dict[str, Any]:
    return json.loads((KEYBR_FIXTURES / "keyboards" / name).read_text())


def keyboard_pictures() -> dict[str, Any]:
    """The keyboard pictures of the keyboards in `keyboard_export()`."""
    return json.loads((KEYBR_FIXTURES / "pictures" / "initial.json").read_text())


def canonical_json(value: Any) -> str:
    """keybr's canonicalJson: keys sorted, no spaces."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def keyboard_snapshots(export: dict[str, Any]) -> list[dict[str, Any]]:
    """The board and keymap snapshots that keybr's importKeyboards makes from a keyboard export,
    each with the source that keyboard_sources keeps for it."""
    found = []
    application = export["source"]["application"]
    for board in export["boards"]:
        ref = {"id": board["name"], "version": sha256(board["vial"])}
        configuration = {"name": board["name"], "vial": board["vial"], "vialHash": ref["version"]}
        source = {"application": application, "boardId": board["sourceId"], "name": board["name"]}
        found.append({"kind": "board", **ref, "configuration": configuration, "source": source})
        for keymap in board["keymaps"]:
            configuration = {
                "board": ref,
                "letterLayout": keymap["letterLayout"],
                "layers": keymap["layers"],
                "vil": keymap["vil"],
                "vilHash": sha256(keymap["vil"]),
            }
            found.append({
                "kind": "keymap",
                "id": f"{board['name']}/{keymap['letterLayout']}",
                "version": sha256(canonical_json(configuration)),
                "configuration": configuration,
                "source": {"application": application, "boardId": board["sourceId"], "sourceHash": keymap["sourceHash"]},
            })
    return found


def keymap_snapshot(export: dict[str, Any], board: str, letter_layout: str, n: int = -1) -> dict[str, Any]:
    """The nth keymap snapshot of the Board with the Letter layout (the newest by default)."""
    return [
        s for s in keyboard_snapshots(export) if s["kind"] == "keymap" and s["id"] == f"{board}/{letter_layout}"
    ][n]


def on_keyboard(found: list[dict[str, Any]], keymap: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The records with the board and keymap references of their start records set to a keymap snapshot."""
    if keymap is None:
        return found
    refs = {"board": keymap["configuration"]["board"], "keymap": {"id": keymap["id"], "version": keymap["version"]}}
    return [r | {"context": r["context"] | refs} if r["type"] == "start" else r for r in found]


def build_recordings(
    path: Path,
    found: list[dict[str, Any]],
    *,
    export: dict[str, Any] | None = None,
    keymap: tuple[str, str] | None = ("Sweep", "free-range"),
    recovery: dict[str, dict[str, bool]] | None = None,
    version: int = 2,
) -> Path:
    """Writes a recordings file at `path` that holds `found` (records) as keybr stores them.

    - export: the keyboard export imported first (initial.json by default).
    - keymap: the (Board, Letter layout) whose newest keymap snapshot the start records name,
      or None to keep the fixture's references.
    - recovery: the incomplete and interrupted flags of some Attempts, by Attempt id.
    - version: the database version; version 1 has no keyboard_sources table.
    """
    export = export or keyboard_export()
    db = sqlite3.connect(path)
    db.executescript(STORE_SCHEMA if version == 2 else STORE_SCHEMA_V1)
    for s in keyboard_snapshots(export):
        snapshot = {key: s[key] for key in ("kind", "id", "version", "configuration")}
        db.execute("INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, ?)", (s["kind"], s["id"], s["version"], canonical_json(snapshot)))
        if version == 2:
            db.execute(
                "INSERT OR IGNORE INTO keyboard_sources (kind, id, version, source, imported_at) VALUES (?, ?, ?, ?, ?)",
                (s["kind"], s["id"], s["version"], canonical_json(s["source"]), IMPORTED_AT),
            )
    chosen = keymap_snapshot(export, *keymap) if keymap else None
    for r in on_keyboard(found, chosen):
        db.execute("INSERT OR IGNORE INTO attempts (id) VALUES (?)", (r["attemptId"],))
        if r["type"] == "start":
            db.execute("UPDATE attempts SET context = ? WHERE id = ?", (canonical_json(r["context"]), r["attemptId"]))
        db.execute(
            "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
            (r["attemptId"], r["sequence"], r["observedAt"], r["type"], r["schemaVersion"], canonical_json(r)),
        )
    for attempt, flags in (recovery or {}).items():
        db.execute(
            "INSERT INTO attempts (id, incomplete, interrupted) VALUES (?, ?, ?) ON CONFLICT (id) DO UPDATE"
            " SET incomplete = excluded.incomplete, interrupted = excluded.interrupted",
            (attempt, int(flags.get("incomplete", False)), int(flags.get("interrupted", False))),
        )
    db.commit()
    db.close()
    return path


def change(path: Path, sql: str, *args: Any) -> None:
    """Runs one SQL statement on a recordings file, to break it in a test."""
    with sqlite3.connect(path) as db:
        db.execute(sql, args)
    db.close()


def scenario_recordings(tmp_path: Path, name: str, **options: Any) -> Path:
    """A recordings file that holds the records of one scenario, in a new file."""
    path, n = tmp_path / f"{name}.sqlite", 1
    while path.exists():
        path, n = tmp_path / f"{name}-{n}.sqlite", n + 1
    return build_recordings(path, records(name), **options)


def renamed(found: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    """The records with new Attempt ids, so that several scenarios fit in one file. The
    scenarios use the same ids. `prefix` is 8 hex digits."""
    return [r | {"attemptId": prefix + r["attemptId"][8:]} for r in found]


def all_scenarios_recordings(path: Path, **options: Any) -> Path:
    """A recordings file that holds the records of every scenario."""
    found = [r for n, s in enumerate(scenarios().values()) for r in renamed(s["expected"]["records"], f"{n:08x}")]
    return build_recordings(path, found, **options)


BLANK = {
    "isTrusted": True, "key": None, "code": None, "location": None, "repeat": None, "modifiers": {},
    "inputType": None, "data": None, "isComposing": None,
}  # fmt: skip


def typing_records(
    text: str,
    actions: list[tuple],
    attempt: str = "00000000-0000-4000-8000-0000000000aa",
    end: str = "reset",
    layout: str = "en-free-range",
) -> list[dict[str, Any]]:
    """The records of a hand-built Attempt at `text`, with keybr's rules in their simplest form:
    a correct character is accepted, and a wrong one is rejected and kept as pending. `actions`
    are ("down", key, code, t), ("up", code, t) and ("input", char, t), in time order (ms)."""
    found: list[dict[str, Any]] = []

    def add(record: dict[str, Any]) -> int:
        n = len(found)
        found.append({"schemaVersion": 1, "attemptId": attempt, "sequence": n, "observedAt": n} | record)
        return n

    settings = {"typing": {}, "exercise": {}, "layout": {"keyboard.layout": layout}}
    add({"type": "start", "context": {"text": text, "applicationRevision": "test", "board": None, "keymap": None, "settings": settings}})
    state = {"cursor": 0, "steps": [], "pending": [], "typo": False, "completed": False}
    held, last = {}, 0
    for kind, *args in actions:
        if kind in ("down", "up"):
            key, code, t = args if kind == "down" else (None, *args)
            press = held.pop(code) if kind == "up" else None
            key = key if press is None else found[press]["event"]["key"]
            event = BLANK | {"type": f"key{kind}", "timeStamp": t, "timeOrigin": 1.7e12, "key": key, "code": code, "location": 0, "repeat": False}
            original = add({"type": "original", "event": event, "pressSequence": press})
            if kind == "down":
                held[code] = original
            processed = {"type": f"key{kind}", "timeStamp": t, "code": code, "key": key, "modifiers": []}
            add({"type": "processed", "originalSequence": original, "synthetic": False, "event": processed})
            continue
        char, t = args
        event = BLANK | {"type": "input", "timeStamp": t, "timeOrigin": 1.7e12, "inputType": "insertText", "data": char}
        original = add({"type": "original", "event": event, "pressSequence": None})
        step = {"timeStamp": t, "codePoint": ord(char), "timeToType": t - last, "typo": False}
        last = t
        processed = {"type": "input", "timeStamp": t, "inputType": "appendChar", "codePoint": ord(char), "timeToType": step["timeToType"]}
        cause = add({"type": "processed", "originalSequence": original, "synthetic": False, "event": processed})
        before = state
        splices = {name: {"from": len(before[name]), "removed": [], "inserted": []} for name in ("steps", "pending")}
        if not state["pending"] and char == text[state["cursor"]]:
            steps = state["steps"] + [step]
            state = state | {"cursor": len(steps), "steps": steps, "completed": len(steps) == len(text)}
            splices["steps"]["inserted"], effect, feedback = [step], "accepted", 0
        else:
            state = state | {"pending": state["pending"] + [step], "typo": True}
            splices["pending"]["inserted"], effect, feedback = [step], "rejected", 2
        add({
            "type": "state", "processedSequence": cause, "effect": effect, "feedback": feedback, "before": before,
            "after": state, "accepted": splices["steps"], "pending": splices["pending"],
        })  # fmt: skip
    add({"type": "end", "reason": end, "result": None, "resultAccepted": None})
    return found


ORIGIN = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)  # the time origin of typing_records (1.7e12 ms)
DAY_MS = 86_400_000


def attempt(
    n: int,
    day: float,
    typed: str,
    text: str | None = None,
    *,
    gaps: dict[str, int] | None = None,
    keymap: dict[str, Any] | None = None,
    layout: str = "en-free-range",
    wpm: float | None = None,
) -> list[dict[str, Any]]:
    """The records of Attempt n at `text` (`typed` by default), typed `day` days after ORIGIN.
    Each character of `typed` is an input, gaps[char] ms (100 by default) after the one before.
    keymap: the keymap snapshot that it names, or None for no Board. layout: keybr's layout
    setting. With `wpm`, it is completed with keybr's result at that WPM; otherwise it is reset."""
    text = text or typed
    t, actions = day * DAY_MS, []
    for char in typed:
        t += (gaps or {}).get(char, 100)
        actions.append(("input", char, t))
    found = typing_records(text, actions, f"00000000-0000-4000-8000-{n:012x}", "completed" if wpm else "reset", layout)
    if wpm:
        result = {"length": len(text), "time": len(text) / (wpm * 5) * 60_000, "errors": 0, "speed": wpm * 5, "histogram": [{}]}
        found[-1] |= {"result": result, "resultAccepted": True}
    return on_keyboard(found, keymap)
