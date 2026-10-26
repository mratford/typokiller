"""The numbers computed from the stored key events. The app uses this module, and the
marimo notebooks (a later ticket) are to use it too, so both compute the same numbers.

Polars 2 does not keep the order of rows, so every table is sorted on explicit columns.
"""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import groupby
from typing import Any, NamedTuple

import polars as pl

from typokiller.keymap import Key, Keymap, keymap_letters, read_keymap

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

    - cursor: the number of characters typed before the key.
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
        row = {"cursor": cursor, "position": None, "status": "ignored", "first": False, "fix_ms": None}
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
    cursor, position, status, first and fix_ms as `first_error_v1` gives them, and alignment.
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
    alignment = {
        "cursor": pl.Int64, "position": pl.Int64, "status": pl.String, "first": pl.Boolean, "fix_ms": pl.Float64,
    }  # fmt: skip
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


MODIFIERS = {"Shift", "Control", "Alt", "Meta", "CapsLock"}  # the `key` of modifier keys
MACRO_GAP_MS = 5  # a macro types its characters about 1 ms apart, faster than any finger
KEY_SCHEMA = pl.Struct({"layer": pl.Int64, "key": pl.String, "kind": pl.String})
NO_KEYMAP = Keymap({}, {}, {}, [])  # for Sessions from before Boards


class Event(NamedTuple):
    seq: int
    t: float
    type: str
    code: str
    key: str
    repeat: bool


def keystrokes(db: sqlite3.Connection, since: datetime = datetime.min) -> pl.DataFrame:
    """One row per intended character in the Sessions started at `since` or later: each
    keydown that `keydowns` gives a position, and each combo misfire. Sorted on session and seq.

    - session, ord (of the Attempt), seq, t: the keydown's.
    - board, letter_layout: of the Session's Keymap; None for Sessions from before Boards.
    - position, status, fix_ms: as `keydowns` gives them. char: the Passage's character at
      the position. typed: the keydown's `key`.
    - event: "typed", or "mod-tap misfire", "combo misfire" or "macro misfire". A misfire is
      a firmware result that the typist did not want, so it has no first_time_correct.
      - A mod-tap misfire is a key at a position whose character is the tap of a mod-tap,
        after that mod-tap's modifier went down: the mod-tap was held too long. With Shift
        this is a wrong capital. Ctrl and GUI make the next key do nothing, so the key
        marked is usually the mod-tap's own character, typed again.
      - A combo misfire is the key a combo sends where the Passage has the combo's
        characters next: they were pressed too close together. Its position is the cursor's.
      - A macro misfire is a macro's text whose first character is an Error.
    - candidates: the keys that type the typed character (see `read_keymap`). The picked
      key is the first one on the layer of the Passage character's own first candidate,
      or else the first one. For a correct key, this is the first one.
      For a misfire, the candidates are the key that misfired.
      Capitals, Caps Word, the Shift + _ key override and Shift held on a mod-tap all
      come from the keys of plain typing; macro text from its macro key.
    - layer, key, kind: the picked key's.
    - dwell: from the keydown to its keyup with the same `code`. None when the keyup was
      lost, and for mod-tap and layer-tap keys, which send both at the key's release.
    - flight: from the previous keystroke's keyup to this keydown, when only modifier keys
      came between them. Around a run of mod-tap or layer-tap keys, every pair gets the
      time from the keyup before the run to the keydown after it.
    - time: from the previous keystroke's keydown to this keydown, under the same rules as
      flight, but a lost keyup does not matter. Around a run of mod-tap or layer-tap keys,
      whose keydowns come at their release, every pair gets an equal share of the time from the keydown
      before the run to the keydown after it.
      Dwell, flight and time are None for keys that are not finger presses: macros, combo
      outputs, auto-repeat, misfires and off-track keys. Shift from Caps Word or from a shifted
      keycode is a modifier key, so it does not count either.
    - first_time_correct: for the first keystroke at a position, whether it was correct
      (True) or an Error (False). None for later keystrokes, off-track keys and misfires.
    - alignment: the alignment step that gave the positions.
    """
    aligned: dict[int, dict[int, dict[str, Any]]] = {}  # the keydowns rows, by session and seq
    for r in keydowns(db, since).iter_rows(named=True):
        aligned.setdefault(r["session"], {})[r["seq"]] = r
    found = db.execute(
        "SELECT a.session, a.ord, p.text, b.name, k.vil, b.vial FROM attempt a JOIN passage p ON p.id = a.passage"
        " JOIN session s ON s.id = a.session LEFT JOIN keymap_version k ON k.hash = s.keymap_version"
        " LEFT JOIN board b ON b.id = k.board WHERE s.started >= ?",
        (since.isoformat(),),
    )
    attempt_info = {
        (session, ord): (
            text,
            board,
            keymap_letters(vil, vial) if vil else None,
            read_keymap(vil) if vil else NO_KEYMAP,
        )
        for session, ord, text, board, vil, vial in found
    }
    # A keyup belongs to the Attempt of its keydown, so it can come after the next Attempt's first keydown.
    events = db.execute(
        "SELECT e.session, attempt, seq, t, type, code, key, repeat FROM key_event e JOIN session s ON s.id = e.session"
        " WHERE s.started >= ? ORDER BY e.session, attempt, seq",
        (since.isoformat(),),
    )
    rows = []
    for (session, ord), group in groupby(events, lambda e: e[:2]):
        passage, board, letters, keymap = attempt_info[session, ord]
        group = [Event(seq, t, type, code, key, bool(repeat)) for _, _, seq, t, type, code, key, repeat in group]
        for row in attempt_keystrokes(passage, keymap, group, aligned[session]):
            rows.append({"session": session, "ord": ord, "board": board, "letter_layout": letters, **row})
    schema = {
        "session": pl.Int64, "ord": pl.Int64, "seq": pl.Int64, "t": pl.Float64, "board": pl.String,
        "letter_layout": pl.String, "position": pl.Int64, "char": pl.String, "typed": pl.String,
        "status": pl.String, "event": pl.String, "layer": pl.Int64, "key": pl.String, "kind": pl.String,
        "candidates": pl.List(KEY_SCHEMA), "dwell": pl.Float64, "flight": pl.Float64, "time": pl.Float64,
        "first_time_correct": pl.Boolean, "fix_ms": pl.Float64,
    }  # fmt: skip
    return (
        pl.DataFrame([{name: row[name] for name in schema} for row in rows], schema=schema)
        .with_columns(alignment=pl.lit(ALIGNMENT))
        .sort("session", "seq")
    )


def attempt_keystrokes(
    passage: str, keymap: Keymap, events: list[Event], aligned: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """The rows of `keystrokes` for one Attempt, without its session, ord, board and Letter
    layout. `events` are its key events in seq order; `aligned` holds the rows of `keydowns`
    of its Session, by seq."""

    def candidates(char: str) -> list[Key]:
        return keymap.keys.get("\n" if char == "Enter" else char, [])

    up_at, held = {}, {}  # the keyup time of each keydown; the keydown of each code that is still down
    for e in events:
        if e.type == "keydown":
            if not e.repeat:  # the keyup ends the first press, not an auto-repeat
                held[e.code] = e.seq
        elif e.code in held:
            up_at[held.pop(e.code)] = e.t
    rows = []
    mods = set()  # the codes of the modifier keys pressed since the last row
    presses = 0  # the keys other than modifiers pressed so far
    for e in (e for e in events if e.type == "keydown"):
        if e.key in MODIFIERS:
            mods.add(e.code)
            continue
        presses += 1
        a = aligned[e.seq]
        row = {"seq": e.seq, "t": e.t, "position": a["position"], "typed": e.key, "status": a["status"]}
        row |= {"event": "typed", "candidates": candidates(e.key), "fix_ms": a["fix_ms"], "first": a["first"]}
        row |= {"presses": presses, "repeat": e.repeat}
        if a["position"] is not None:
            char = passage[a["position"]]
            misfired = next((keymap.holds[m, char] for m in mods if (m, char) in keymap.holds), None)
            if misfired and a["status"] != "off-track":
                row |= {"event": "mod-tap misfire", "candidates": [misfired]}
        else:
            cursor = a["cursor"]
            misfired = next(
                (k for sent, chars, k in keymap.combos
                 if sent == e.key and sorted(passage[cursor : cursor + len(chars)]) == sorted(chars)),
                None,
            )  # fmt: skip
            if not misfired:
                continue
            row |= {"position": cursor, "event": "combo misfire", "candidates": [misfired]}
        row["char"] = passage[row["position"]]
        rows.append(row)
        mods = set()
    # A macro's text comes as one fast burst of keys.
    for i in range(len(rows)):
        for text, key in keymap.macros.items():
            burst = rows[i : i + len(text)]
            if "".join(r["typed"] for r in burst) == text and all(
                b["t"] - a["t"] <= MACRO_GAP_MS for a, b in zip(burst, burst[1:])
            ):
                event = "macro misfire" if burst[0]["status"] == "error" else "typed"
                for r in burst:
                    r |= {"event": event, "candidates": [key]}
    for r in rows:
        own = candidates(r["char"])
        pick = next((k for k in r["candidates"] if own and k.layer == own[0].layer), None)
        pick = pick or next(iter(r["candidates"]), None)
        r |= {"layer": pick and pick.layer, "key": pick and pick.key, "kind": pick and pick.kind}
        r["timed"] = (
            r["event"] == "typed"
            and r["kind"] not in ("macro", "combo")
            and not r["repeat"]
            and r["status"] != "off-track"
        )
        r["tap_hold"] = r["kind"] in ("mod-tap", "layer-tap")
        counted = r["first"] and r["event"] == "typed" and r["status"] in ("correct", "error")
        r["first_time_correct"] = r["status"] == "correct" if counted else None
        up = up_at.get(r["seq"])
        r["dwell"] = up - r["t"] if r["timed"] and not r["tap_hold"] and up is not None else None
        r["candidates"] = [k._asdict() for k in r["candidates"]]

    def linked(i: int) -> bool:
        """Whether rows i - 1 and i are finger presses with only modifier keys between them."""
        return (
            0 < i < len(rows)
            and rows[i - 1]["timed"]
            and rows[i]["timed"]
            and (rows[i]["presses"] == rows[i - 1]["presses"] + 1)
        )

    for i, r in enumerate(rows):
        start, end = i - 1, i  # the pair, made longer over tap-hold keys at either end
        while start >= 0 and rows[start]["tap_hold"] and linked(start):
            start -= 1
        while rows[end]["tap_hold"] and linked(end + 1):
            end += 1
        r["flight"] = r["time"] = None
        if linked(i) and not (rows[start]["tap_hold"] or rows[end]["tap_hold"]):
            r["time"] = (rows[end]["t"] - rows[start]["t"]) / (end - start)
            if rows[start]["seq"] in up_at:
                r["flight"] = rows[end]["t"] - up_at[rows[start]["seq"]]
    return rows


class WeaknessModel(NamedTuple):
    # (db, board, letter_layout, the [weakness] settings) -> one row per character and pair
    # with at least the columns unit, cost and seen
    rank: Callable[[sqlite3.Connection, str | None, str | None, dict[str, Any]], pl.DataFrame]
    scale: tuple[float, float, float]  # the fixed colour scale of Keymap drawings: low, high and tick costs in ms


def units(db: sqlite3.Connection, board: str | None, letter_layout: str | None, since: datetime) -> pl.DataFrame:
    """The keystrokes typed on the Board with the Letter layout in the Sessions started at
    `since` or later, with one row for each unit of each keystroke: its character, and the
    pair of the character before and this one when the keystroke before was correct.
    The columns of `keystrokes`, and unit. Only correct keystrokes and Errors of the
    "typed" event count: misfires and off-track keys do not."""

    def before(column: str) -> pl.Expr:
        """The column's value in the keystroke before, in the same Attempt."""
        return pl.col(column).shift().over("session", "ord", order_by="seq")

    return (
        keystrokes(db, since)
        .filter(pl.col("board").eq_missing(board), pl.col("letter_layout").eq_missing(letter_layout))
        .with_columns(pair=pl.when(before("status") == "correct").then(before("char") + pl.col("char")))
        .filter(pl.col("event") == "typed", pl.col("status").is_in(["correct", "error"]))
        .with_columns(unit=pl.concat_list("char", "pair"))
        .explode("unit")
        .drop_nulls("unit")
    )


def recent_cost_v1(
    db: sqlite3.Connection, board: str | None, letter_layout: str | None, settings: dict[str, Any]
) -> pl.DataFrame:
    """The cost of each character and pair typed on the Board with the Letter layout in
    the Sessions of the last settings["weeks"] weeks, abandoned Attempts too. Characters and
    pairs seen fewer than settings["min_seen"] times, or never timed, are left out.

    - unit: as `units` gives it.
    - time: the median `time` of the unit's correct keystrokes.
    - error_rate: the share of Errors among its first keystrokes at a position.
    - fix_ms: the median fix time of its Errors.
    - cost (ms) = time + error_rate × fix_ms.
    - seen: its number of first keystrokes at a position.
    """
    return (
        units(db, board, letter_layout, datetime.now(UTC) - timedelta(weeks=settings["weeks"]))
        .group_by("unit")
        .agg(
            time=pl.col("time").filter(pl.col("status") == "correct").median(),
            error_rate=pl.col("first_time_correct").not_().mean(),
            fix_ms=pl.col("fix_ms").median(),
            seen=pl.col("first_time_correct").count(),
        )
        .filter(pl.col("seen") >= settings["min_seen"])
        .drop_nulls("time")
        .with_columns(cost=pl.col("time") + pl.col("error_rate") * pl.col("fix_ms").fill_null(0))
    )


# The Weakness models, by name (spec §12). The settings file names the one in use.
WEAKNESS_MODELS = {"recent-cost-v1": WeaknessModel(recent_cost_v1, (150, 600, 400))}


def weakness(
    db: sqlite3.Connection, board: str | None, letter_layout: str | None, settings: dict[str, Any]
) -> pl.DataFrame:
    """The ranking of the characters and pairs typed on the Board with the Letter layout,
    by the Weakness model named settings["model"]. `settings` is the [weakness] table of the
    settings file. Columns: unit, cost (ms), seen, the model's own columns, and model (its
    name). Sorted on cost, the highest first, then on unit."""
    name = settings["model"]
    return (
        WEAKNESS_MODELS[name]
        .rank(db, board, letter_layout, settings)
        .with_columns(model=pl.lit(name))
        .sort(["cost", "unit"], descending=[True, False])
    )
