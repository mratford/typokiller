"""Reads keybr recordings: the SQLite database recordings.sqlite in keybr's data folder, or a copy
of it, such as a backup. Its layout is in
keybr/packages/keybr-recording-store/lib/index.ts, and the records are defined in
keybr/packages/keybr-recording/lib/index.ts (see keybr/docs/typing-recordings.md):

- `PRAGMA user_version` is the database version, 1 or 2. Version 2 adds `keyboard_sources`.
- `metadata` has `schemaVersion`, the version of the record contract, which must be "1".
- `snapshots` holds the imported keyboards: a board snapshot per vial.json, and a keymap
  snapshot per saved .vil with its Board version, Letter layout and layer names.
- `attempts` holds each Attempt's context and its recovery flags, `incomplete` and `interrupted`.
- `records` holds every record as JSON, by Attempt and sequence.

The reader opens the file read-only and never changes it. A problem with the file gives a
RecordingError. A problem in one Attempt, such as a lost record, does not: the Attempt's row in
`attempts` lists it, and nothing is invented in place of the lost records.
"""

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import polars as pl

SOURCE = "keybr"
DATABASE_VERSIONS = (1, 2)
CONTRACT_VERSION = 1  # the record contract (`schemaVersion`)

# The tables and columns the reader needs, by database version.
COLUMNS = {
    "metadata": ["key", "value"],
    "snapshots": ["kind", "id", "version", "json"],
    "attempts": ["id", "context", "incomplete", "interrupted"],
    "records": ["attempt_id", "sequence", "observed_at", "type", "schema_version", "json"],
}
COLUMNS_V2 = COLUMNS | {"keyboard_sources": ["kind", "id", "version", "source", "imported_at"]}

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
JSON = pl.String  # JSON text
TIME = pl.Datetime("us", "UTC")

KEYBOARDS = {
    "board_id": pl.String, "board_version": pl.String, "keymap_id": pl.String, "keymap_version": pl.String,
    "letter_layout": pl.String, "layers": pl.List(pl.String), "vil": pl.String, "vil_hash": pl.String,
    "vial": pl.String, "imported_at": TIME,
}  # fmt: skip
ATTEMPTS = {
    "attempt": pl.String, "board_id": pl.String, "board_version": pl.String, "keymap_id": pl.String,
    "keymap_version": pl.String, "letter_layout": pl.String, "text": pl.String, "application_revision": pl.String,
    "keybr_layout": pl.String, "settings": JSON, "started": TIME, "records": pl.Int64,
    "interrupted": pl.Boolean, "incomplete": pl.Boolean, "has_start": pl.Boolean, "has_end": pl.Boolean,
    "end_reason": pl.String, "sequence_gaps": pl.Int64, "broken_links": pl.Int64,
    "discontinuous_states": pl.Int64, "missing_releases": pl.Int64, "status": pl.String,
    "speed": pl.Float64, "errors": pl.Int64, "length": pl.Int64, "time": pl.Float64,
    "result_accepted": pl.Boolean, "result": JSON,
}  # fmt: skip
RECORD = {"attempt": pl.String, "sequence": pl.Int64, "observed_at": pl.Float64}
ORIGINAL_EVENTS = RECORD | {
    "event_type": pl.String, "time_stamp": pl.Float64, "time_origin": pl.Float64, "time": TIME,
    "is_trusted": pl.Boolean, "key": pl.String, "code": pl.String, "location": pl.Int64, "repeat": pl.Boolean,
    "input_type": pl.String, "data": pl.String, "is_composing": pl.Boolean, "modifiers": JSON,
    "press_sequence": pl.Int64, "json": JSON,
}  # fmt: skip
PROCESSED_EVENTS = RECORD | {
    "original_sequence": pl.Int64, "synthetic": pl.Boolean, "event_type": pl.String, "time_stamp": pl.Float64,
    "key": pl.String, "code": pl.String, "modifiers": JSON, "input_type": pl.String, "code_point": pl.Int64,
    "char": pl.String, "time_to_type": pl.Float64, "json": JSON,
}  # fmt: skip
STATES = RECORD | {
    "processed_sequence": pl.Int64, "effect": pl.String, "feedback": pl.Int64, "cursor_before": pl.Int64,
    "cursor_after": pl.Int64, "before": JSON, "after": JSON, "accepted": JSON, "pending": JSON, "json": JSON,
}  # fmt: skip


class RecordingError(Exception):
    """The file cannot be read as keybr recordings. The message says why."""


class NewerRecordings(RecordingError):
    """The file has a newer database version than this typokiller reads."""


class Recording(NamedTuple):
    """The tables of one file of keybr recordings. Every table also has the columns source
    ("keybr"), schema_version (the record contract version) and file (the file's path). Each record
    table keeps the record's own JSON in its `json` column. Each table is sorted on its
    first columns: attempt and sequence for the record tables."""

    path: Path
    database_version: int  # PRAGMA user_version
    keyboards: pl.DataFrame
    attempts: pl.DataFrame
    original_events: pl.DataFrame
    processed_events: pl.DataFrame
    states: pl.DataFrame


def wall_clock(origin: float, stamp: float) -> datetime:
    """The UTC time of a browser event: its time origin and its timestamp are in ms."""
    return EPOCH + timedelta(milliseconds=origin + stamp)


def checked_version(db: sqlite3.Connection, path: Path) -> int:
    """The database version of the recordings in `db`, after the checks of its versions and tables."""
    try:
        (version,) = db.execute("PRAGMA user_version").fetchone()
        tables = {name for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.DatabaseError as e:
        raise RecordingError(f"{path} is not an SQLite database: {e}") from e
    if version > max(DATABASE_VERSIONS):
        raise NewerRecordings(f"{path} has database version {version}, which is newer than this typokiller reads. Update typokiller.")
    if version not in DATABASE_VERSIONS:
        raise RecordingError(f"{path} has database version {version}. Only versions 1 and 2 can be read.")
    for table, columns in (COLUMNS_V2 if version == 2 else COLUMNS).items():
        if table not in tables:
            raise RecordingError(f"{path} has no table {table}.")
        have = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if missing := [c for c in columns if c not in have]:
            raise RecordingError(f"{path}: the table {table} has no column {', '.join(missing)}.")
    found = db.execute("SELECT value FROM metadata WHERE key = 'schemaVersion'").fetchone()
    if found is None or found[0] != str(CONTRACT_VERSION):
        raise RecordingError(
            f"{path} has record schemaVersion {found and found[0]}. Only version {CONTRACT_VERSION} can be read."
        )
    return version


def read_recordings(path: Path | str) -> Recording:
    """The tables of the keybr recordings at `path`. Raises RecordingError when the file is
    missing, is not SQLite, has an unsupported database or contract version (NewerRecordings
    for a newer database version), lacks a table or column, or has a record whose JSON does not
    parse or whose schema version is not 1.

    keybr may write to the file at the same time. The file is opened read-only, and the checks
    and all the reads are in one transaction, so they see one state of the file (#75)."""
    path = Path(path)
    if not path.is_file():
        raise RecordingError(f"There is no file at {path}.")
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, autocommit=True)
    try:
        db.execute("BEGIN")
        version = checked_version(db, path)
        keyboards = read_keyboards(db, version)
        flags = {a: (bool(i), bool(n)) for a, i, n in db.execute("SELECT id, incomplete, interrupted FROM attempts")}
        by_attempt: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for attempt, sequence, schema, text in db.execute(
            "SELECT attempt_id, sequence, schema_version, json FROM records ORDER BY attempt_id, sequence"
        ):
            where = f"the record of Attempt {attempt} with sequence {sequence}"
            try:
                record = json.loads(text)
            except json.JSONDecodeError as e:
                raise RecordingError(f"{path}: {where} is not valid JSON: {e}") from e
            if schema != CONTRACT_VERSION or record.get("schemaVersion") != CONTRACT_VERSION:
                raise RecordingError(
                    f"{path}: {where} has schema version {record.get('schemaVersion', schema)}. Only version {CONTRACT_VERSION} can be read."
                )
            record["json"] = text
            by_attempt[attempt].append(record)
        db.execute("COMMIT")
    finally:
        db.close()
    letters = dict(zip(keyboards["keymap_version"], keyboards["letter_layout"]))
    attempts = [
        attempt_row(attempt, by_attempt.get(attempt, []), *flags.get(attempt, (False, False)), letters)
        for attempt in sorted(set(flags) | set(by_attempt))
    ]
    every = [r for found in by_attempt.values() for r in found]
    labels = {"source": pl.lit(SOURCE), "schema_version": pl.lit(CONTRACT_VERSION), "file": pl.lit(str(path))}

    def table(rows: list[dict[str, Any]], schema: dict[str, Any], *order: str) -> pl.DataFrame:
        return pl.DataFrame(rows, schema=schema, orient="row").with_columns(**labels).sort(*order)

    return Recording(
        path,
        version,
        keyboards.with_columns(**labels).sort("board_id", "keymap_id", "imported_at", "keymap_version", nulls_last=True),
        table(attempts, ATTEMPTS, "started", "attempt"),
        table([original_row(r) for r in every if r["type"] == "original"], ORIGINAL_EVENTS, "attempt", "sequence"),
        table([processed_row(r) for r in every if r["type"] == "processed"], PROCESSED_EVENTS, "attempt", "sequence"),
        table([state_row(r) for r in every if r["type"] == "state"], STATES, "attempt", "sequence"),
    )


def read_keyboards(db: sqlite3.Connection, version: int) -> pl.DataFrame:
    """One row per keymap snapshot, with its board snapshot. A keymap snapshot that is not an
    import from typokiller (such as keybr's test fixtures) has None for what it lacks."""
    boards = {}
    rows = []
    found = list(db.execute("SELECT kind, id, version, json FROM snapshots ORDER BY kind, id, version"))
    for kind, id, v, text in found:
        if kind == "board":
            boards[id, v] = json.loads(text).get("configuration") or {}
    imported = {}
    if version == 2:
        imported = {
            (id, v): datetime.fromisoformat(at)
            for id, v, at in db.execute("SELECT id, version, min(imported_at) FROM keyboard_sources WHERE kind = 'keymap' GROUP BY id, version")
        }
    for kind, id, v, text in found:
        if kind != "keymap":
            continue
        configuration = json.loads(text).get("configuration") or {}
        board = configuration.get("board") or {}
        board_config = boards.get((board.get("id"), board.get("version")), {})
        rows.append({
            "board_id": board.get("id"),
            "board_version": board.get("version"),
            "keymap_id": id,
            "keymap_version": v,
            "letter_layout": configuration.get("letterLayout"),
            "layers": configuration.get("layers"),
            "vil": configuration.get("vil"),
            "vil_hash": configuration.get("vilHash"),
            "vial": board_config.get("vial"),
            "imported_at": imported.get((id, v)),
        })
    return pl.DataFrame(rows, schema=KEYBOARDS, orient="row")


def attempt_row(
    attempt: str, found: list[dict[str, Any]], incomplete: bool, interrupted: bool, letters: dict[str, str]
) -> dict[str, Any]:
    """The row of `attempts` for one Attempt, from its records in sequence order.

    - started: the wall-clock time of its first original event.
    - sequence_gaps: how many sequence numbers from 0 to the last one have no record.
    - broken_links: processed records whose original record is missing, state records whose
      processed record is missing, and original records whose press is missing.
    - discontinuous_states: state records whose `before` is not the `after` of the state before.
    - missing_releases: presses (non-repeat keydowns) with no keyup that names them.
    - status: "unreadable" (no start record, so no text), "interrupted", "incomplete" (the
      incomplete flag, no end record, or a gap, broken link or discontinuous state), "complete"
      (ended as completed) or "ended early" (any other end reason).
    """
    by_sequence = {r["sequence"]: r for r in found}
    start = by_sequence.get(0) if by_sequence.get(0, {}).get("type") == "start" else None
    end = next((r for r in found if r["type"] == "end"), None)
    originals = [r for r in found if r["type"] == "original"]

    def is_type(sequence: int | None, kind: str) -> bool:
        return sequence is not None and by_sequence.get(sequence, {}).get("type") == kind

    gaps = (max(by_sequence) + 1 - len(by_sequence)) if by_sequence else 0
    broken = sum(
        (r["type"] == "processed" and not is_type(r["originalSequence"], "original"))
        or (r["type"] == "state" and not is_type(r["processedSequence"], "processed"))
        or (r["type"] == "original" and r["pressSequence"] is not None and not is_type(r["pressSequence"], "original"))
        for r in found
    )
    states = [r for r in found if r["type"] == "state"]
    jumps = sum(a["before"] != b["after"] for b, a in zip(states, states[1:]))
    released = {r["pressSequence"] for r in originals if r["event"]["type"] == "keyup"}
    missing = sum(
        r["event"]["type"] == "keydown" and not r["event"]["repeat"] and r["sequence"] not in released for r in originals
    )
    if start is None:
        status = "unreadable"
    elif interrupted:
        status = "interrupted"
    elif incomplete or end is None or gaps or broken or jumps:
        status = "incomplete"
    else:
        status = "complete" if end["reason"] == "completed" else "ended early"
    context = start["context"] if start else {}
    board, keymap = context.get("board") or {}, context.get("keymap") or {}
    result = (end or {}).get("result") or {}
    first = originals[0]["event"] if originals else None
    return {
        "attempt": attempt,
        "board_id": board.get("id"),
        "board_version": board.get("version"),
        "keymap_id": keymap.get("id"),
        "keymap_version": keymap.get("version"),
        "letter_layout": letters.get(keymap.get("version", "")),
        "text": context.get("text"),
        "application_revision": context.get("applicationRevision"),
        "keybr_layout": (context.get("settings") or {}).get("layout", {}).get("keyboard.layout"),
        "settings": json.dumps(context["settings"]) if "settings" in context else None,
        "started": wall_clock(first["timeOrigin"], first["timeStamp"]) if first else None,
        "records": len(found),
        "interrupted": interrupted,
        "incomplete": incomplete,
        "has_start": start is not None,
        "has_end": end is not None,
        "end_reason": end and end["reason"],
        "sequence_gaps": gaps,
        "broken_links": broken,
        "discontinuous_states": jumps,
        "missing_releases": missing,
        "status": status,
        "speed": result.get("speed"),
        "errors": result.get("errors"),
        "length": result.get("length"),
        "time": result.get("time"),
        "result_accepted": end and end.get("resultAccepted"),
        "result": json.dumps(end["result"]) if end and end.get("result") else None,
    }


def record_row(r: dict[str, Any]) -> dict[str, Any]:
    return {"attempt": r["attemptId"], "sequence": r["sequence"], "observed_at": r["observedAt"]}


def original_row(r: dict[str, Any]) -> dict[str, Any]:
    e = r["event"]
    return record_row(r) | {
        "event_type": e["type"],
        "time_stamp": e["timeStamp"],
        "time_origin": e["timeOrigin"],
        "time": wall_clock(e["timeOrigin"], e["timeStamp"]),
        "is_trusted": e["isTrusted"],
        "key": e["key"],
        "code": e["code"],
        "location": e["location"],
        "repeat": e["repeat"],
        "input_type": e["inputType"],
        "data": e["data"],
        "is_composing": e["isComposing"],
        "modifiers": json.dumps(e["modifiers"]),
        "press_sequence": r["pressSequence"],
        "json": r["json"],
    }


def processed_row(r: dict[str, Any]) -> dict[str, Any]:
    e = r["event"]
    point = e.get("codePoint")
    return record_row(r) | {
        "original_sequence": r["originalSequence"],
        "synthetic": r["synthetic"],
        "event_type": e["type"],
        "time_stamp": e["timeStamp"],
        "key": e.get("key"),
        "code": e.get("code"),
        "modifiers": json.dumps(e["modifiers"]) if "modifiers" in e else None,
        "input_type": e.get("inputType"),
        "code_point": point,
        # clearChar and clearWord have code point 0, which is no character.
        "char": chr(point) if e.get("inputType") in ("appendChar", "appendLineBreak") else None,
        "time_to_type": e.get("timeToType"),
        "json": r["json"],
    }


def state_row(r: dict[str, Any]) -> dict[str, Any]:
    return record_row(r) | {
        "processed_sequence": r["processedSequence"],
        "effect": r["effect"],
        "feedback": r["feedback"],
        "cursor_before": r["before"]["cursor"],
        "cursor_after": r["after"]["cursor"],
        "before": json.dumps(r["before"]),
        "after": json.dumps(r["after"]),
        "accepted": json.dumps(r["accepted"]),
        "pending": json.dumps(r["pending"]),
        "json": r["json"],
    }
