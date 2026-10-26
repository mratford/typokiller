"""The numbers computed from the stored key events. The app uses this module, and the
marimo notebooks (a later ticket) are to use it too, so both compute the same numbers.

Polars 2 does not keep the order of rows, so every table is sorted on explicit columns.
"""

import sqlite3
from datetime import datetime
from itertools import groupby
from typing import Any, NamedTuple

import polars as pl

from typokiller.keymap import keymap_letters

# The name of the alignment step (spec §12), given in the tables made with it.
ALIGNMENT = "first-error-v1"


class Keydown(NamedTuple):
    t: float  # ms
    key: str
    ctrl: bool = False
    meta: bool = False


def indent_at(passage: str, i: int) -> str:
    """The spaces at the start of the line that begins at position i of the Passage."""
    line = passage[i:]
    return " " * (len(line) - len(line.lstrip(" ")))


def typed_char(passage: str, typed: str, k: Keydown) -> str | None:
    """The character that a key puts at the cursor, if it is put in: the key's character,
    or a newline for Enter where the Passage has one. None for other keys, for keys with
    Ctrl or Meta, and after the end of the Passage."""
    at = passage[len(typed) : len(typed) + 1]
    if k.ctrl or k.meta or not at:
        return None
    if k.key == "Enter":
        return "\n" if at == "\n" else None
    return k.key if len(k.key) == 1 else None


def apply_key(passage: str, typed: str, k: Keydown, mode: str | None) -> str:
    """What has been typed in the Attempt after one more key.

    These are the rules of `applyKey` in static/typing.js, which the page uses. The two
    must change together, or the alignment no longer sees what the page showed.
    """
    if k.key == "Backspace" and not (k.ctrl or k.meta):
        # Backspace after filled-in indentation removes it together with the newline.
        newline = typed.rfind("\n")
        if newline >= 0 and typed[newline + 1 :] == indent_at(passage, newline + 1):
            return typed[:newline]
        return typed[:-1]
    char = typed_char(passage, typed, k)
    if char is None or (mode == "locked until fixed" and char != passage[len(typed)]):
        return typed
    # After a newline, the next line's indentation is filled in without typing it.
    return typed + char + (indent_at(passage, len(typed) + 1) if char == "\n" else "")


def first_error_v1(passage: str, mode: str | None, keydowns: list[Keydown]) -> list[dict[str, Any]]:
    """Lines up an Attempt's keydowns with its Passage. Returns one row per keydown:

    - position: the position in the Passage of the character the key was meant to type,
      or None for a key that types nothing (Backspace, Shift, Enter where there is no newline).
    - status: "correct", "error", "off-track" or "ignored". With no Error open, a key that
      types a character is correct when it is the Passage's character, else it is an Error.
      After an Error, every key that types or deletes is off-track, until the typed text
      is all correct and longer than the Error's position: that key ends the Fix, and is correct.
      Backspace with no Error open and keys that type nothing are ignored.
    - first: whether no earlier keystroke of the Attempt was at this position.
    - fix_ms: on an Error, the time from it to its Fix; None if it was never fixed.

    `mode` is the wrong-key mode; None (Attempts from before the setting) is "keep typing".
    """
    rows = []
    typed = ""
    error = None  # the index of the open Error in rows and keydowns
    seen = set()  # positions typed at so far
    for k in keydowns:
        cursor = len(typed)
        char = typed_char(passage, typed, k)
        row = {"position": None, "status": "ignored", "first": False, "fix_ms": None}
        if char is not None:
            row |= {"position": cursor, "first": cursor not in seen}
            seen.add(cursor)
        typed = apply_key(passage, typed, k, mode)
        if error is not None and (char is not None or (k.key == "Backspace" and not (k.ctrl or k.meta))):
            if passage.startswith(typed) and len(typed) > rows[error]["position"]:
                row["status"] = "correct"
                rows[error]["fix_ms"] = k.t - keydowns[error].t
                error = None
            else:
                row["status"] = "off-track"
        elif char is not None:
            row["status"] = "correct" if char == passage[cursor] else "error"
            if row["status"] == "error":
                error = len(rows)
        rows.append(row)
    return rows


def keydowns(db: sqlite3.Connection, since: datetime = datetime.min) -> pl.DataFrame:
    """One row per keydown in the Sessions started at `since` or later, lined up with its
    Passage by `first_error_v1`. Columns: session, ord (of the Attempt), seq, t, key, and
    position, status, first and fix_ms as `first_error_v1` gives them, and alignment.
    Sorted on session and seq."""
    passage_and_mode = {
        (session, ord): (text, mode)
        for session, ord, text, mode in db.execute(
            "SELECT a.session, a.ord, p.text, a.settings ->> '$.typing.wrong_key_mode'"
            " FROM attempt a JOIN passage p ON p.id = a.passage JOIN session s ON s.id = a.session"
            " WHERE s.started >= ?",
            (since.isoformat(),),
        )
    }
    # An Attempt's keydowns come one after another in seq: the next Attempt starts after them.
    found = db.execute(
        "SELECT e.session, attempt, seq, t, key, ctrl, meta FROM key_event e JOIN session s ON s.id = e.session"
        " WHERE type = 'keydown' AND s.started >= ? ORDER BY e.session, seq",
        (since.isoformat(),),
    )
    events, aligned = [], []
    for attempt, group in groupby(found, lambda e: e[:2]):
        group = list(group)
        events += [e[:5] for e in group]
        aligned += first_error_v1(*passage_and_mode[attempt], [Keydown(*e[3:]) for e in group])
    columns = {"session": pl.Int64, "ord": pl.Int64, "seq": pl.Int64, "t": pl.Float64, "key": pl.String}
    alignment = {"position": pl.Int64, "status": pl.String, "first": pl.Boolean, "fix_ms": pl.Float64}
    return (
        pl.DataFrame(events, schema=columns, orient="row")
        .hstack(pl.DataFrame(aligned, schema=alignment))
        .with_columns(alignment=pl.lit(ALIGNMENT))
        .sort("session", "seq")
    )


def attempts(db: sqlite3.Connection, since: datetime = datetime.min) -> pl.DataFrame:
    """One row per Attempt in the Sessions started at `since` or later, sorted on session and ord.

    - started: the start of the Attempt's Session.
    - board (its name), letter_layout: None for Sessions from before Boards.
    - passage: its id.
    - finished: True when finished, False when abandoned.
    - wpm: for a finished Attempt, its typed characters / 5 per minute, from the first
      keydown to the last keyup (or the last keydown when no keyup came). Indentation
      filled in after Enter is not typed, so it does not count. None when abandoned.
    - accuracy: first-time accuracy, the share of correct keys among the first keystrokes
      at each position that are correct or an Error. Off-track keys and retyped
      characters do not count.
    - alignment: the alignment step that gave the accuracy.
    """
    rows = []
    for session, ord, started, board, vil, vial, passage, text, finished, start, end in db.execute(
        "SELECT a.session, a.ord, s.started, b.name, k.vil, b.vial, a.passage, p.text, a.finished,"
        " min(e.t) FILTER (WHERE e.type = 'keydown'), coalesce(max(e.t) FILTER (WHERE e.type = 'keyup'), max(e.t))"
        " FROM attempt a JOIN session s ON s.id = a.session JOIN passage p ON p.id = a.passage"
        " LEFT JOIN keymap_version k ON k.hash = s.keymap_version LEFT JOIN board b ON b.id = k.board"
        " LEFT JOIN key_event e ON (e.session, e.attempt) = (a.session, a.ord)"
        " WHERE s.started >= ? GROUP BY a.session, a.ord",
        (since.isoformat(),),
    ):
        wpm = None
        if finished:
            typed = len(text) - sum(len(indent_at(text, i + 1)) for i, c in enumerate(text) if c == "\n")
            wpm = typed / 5 / ((end - start) / 60000)
        rows.append((
            session, ord, datetime.fromisoformat(started), board, keymap_letters(vil, vial) if vil else None,
            passage, bool(finished), wpm,
        ))  # fmt: skip
    schema = {
        "session": pl.Int64, "ord": pl.Int64, "started": pl.Datetime("us", "UTC"), "board": pl.String,
        "letter_layout": pl.String, "passage": pl.Int64, "finished": pl.Boolean, "wpm": pl.Float64,
    }  # fmt: skip
    counted = pl.col("first") & pl.col("status").is_in(["correct", "error"])
    accuracy = (
        keydowns(db, since)
        .group_by("session", "ord")
        .agg(accuracy=(counted & (pl.col("status") == "correct")).sum() / counted.sum())
        .with_columns(pl.col("accuracy").fill_nan(None))
    )
    return (
        pl.DataFrame(rows, schema=schema, orient="row")
        .join(accuracy, on=["session", "ord"], how="left")
        .with_columns(alignment=pl.lit(ALIGNMENT))
        .sort("session", "ord")
    )
