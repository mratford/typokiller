"""The numbers computed from the stored key events. The app uses this module, and the
marimo notebooks (notebooks/) use it too, so both compute the same numbers.

Polars 2 does not keep the order of rows, so every table is sorted on explicit columns.
"""

import math
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple

import polars as pl

from typokiller.drawing import Heat
from typokiller.keymap import Key, Keymap, keymap_letters, read_keymap

if TYPE_CHECKING:
    import altair as alt

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
    found = [pl.DataFrame(schema=KEYDOWNS), *(r.keydowns for r in replayed(db, since).values())]
    return pl.concat(found).with_columns(alignment=pl.lit(ALIGNMENT)).sort("session", "seq")


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
    boards = keymaps(db)
    found = replayed(db, since)
    rows = []
    for session, ord, started, version, passage, text, finished in db.execute(
        "SELECT a.session, a.ord, s.started, s.keymap_version, a.passage, p.text, a.finished"
        " FROM attempt a JOIN session s ON s.id = a.session JOIN passage p ON p.id = a.passage WHERE s.started >= ?",
        (since.isoformat(),),
    ):
        r = found[session, ord]  # an Attempt is stored with its first key event
        wpm = None
        if finished:
            typed = len(text) - sum(len(indent_at(text, i + 1)) for i, c in enumerate(text) if c == "\n")
            wpm = typed / 5 / (r.wpm_ms / 60000)
        rows.append((
            session, ord, datetime.fromisoformat(started), *boards.get(version, NO_BOARD)[:2], passage,
            bool(finished), wpm, r.accuracy,
        ))  # fmt: skip
    schema = {
        "session": pl.Int64, "ord": pl.Int64, "started": pl.Datetime("us", "UTC"), "board": pl.String,
        "letter_layout": pl.String, "passage": pl.Int64, "finished": pl.Boolean, "wpm": pl.Float64,
        "accuracy": pl.Float64,
    }  # fmt: skip
    return (
        pl.DataFrame(rows, schema=schema, orient="row").with_columns(alignment=pl.lit(ALIGNMENT)).sort("session", "ord")
    )


MODIFIERS = {"Shift", "Control", "Alt", "Meta", "CapsLock"}  # the `key` of modifier keys
MACRO_GAP_MS = 5  # a macro types its characters about 1 ms apart, faster than any finger
KEY_SCHEMA = pl.Struct({"layer": pl.Int64, "key": pl.String, "kind": pl.String})
NO_BOARD = (None, None, Keymap({}, {}, {}, []))  # the Board, Letter layout and Keymap of Sessions from before Boards
KEYDOWNS = {
    "session": pl.Int64, "ord": pl.Int64, "seq": pl.Int64, "t": pl.Float64, "key": pl.String,
    "cursor": pl.Int64, "position": pl.Int64, "status": pl.String, "first": pl.Boolean, "fix_ms": pl.Float64,
}  # fmt: skip
KEYSTROKES = {
    "session": pl.Int64, "ord": pl.Int64, "seq": pl.Int64, "t": pl.Float64, "board": pl.String,
    "letter_layout": pl.String, "position": pl.Int64, "char": pl.String, "typed": pl.String,
    "status": pl.String, "event": pl.String, "layer": pl.Int64, "key": pl.String, "kind": pl.String,
    "candidates": pl.List(KEY_SCHEMA), "dwell": pl.Float64, "flight": pl.Float64, "time": pl.Float64,
    "first_time_correct": pl.Boolean, "fix_ms": pl.Float64,
}  # fmt: skip
REPLAYED = {name: schema for name, schema in KEYSTROKES.items() if name not in ("board", "letter_layout")}


class Event(NamedTuple):
    seq: int
    t: float
    type: str
    code: str
    key: str
    ctrl: bool
    meta: bool
    repeat: bool


class Replay(NamedTuple):
    """What replaying the key events of one Attempt gives."""

    events: int  # its number of key events
    keydowns: pl.DataFrame  # its rows of `keydowns`, with no alignment column
    keystrokes: pl.DataFrame  # its rows of `keystrokes`, without board, letter_layout and alignment
    wpm_ms: float  # the time that its WPM counts (see `attempts`)
    accuracy: float | None  # its first-time accuracy (see `attempts`)


# The Replay of each Attempt, by (database file, session, ord). An Attempt's Passage,
# settings and Session (so its Keymap version) never change, but it can still get key
# events: a late keyup, or a batch sent again. So it is replayed again when its number of
# key events changes. Nothing is kept for an in-memory database.
replay_cache: dict[tuple[str, int, int], Replay] = {}


def keymaps(db: sqlite3.Connection) -> dict[str, tuple[str | None, str | None, Keymap]]:
    """The Board name, Letter layout and Keymap of each Keymap version, by its hash."""
    return {
        version: (board, keymap_letters(vil, vial), read_keymap(vil))
        for version, board, vil, vial in db.execute(
            "SELECT k.hash, b.name, k.vil, b.vial FROM keymap_version k JOIN board b ON b.id = k.board"
        )
    }


def replayed(db: sqlite3.Connection, since: datetime) -> dict[tuple[int, int], Replay]:
    """The Replay of each Attempt in the Sessions started at `since` or later, by session and ord."""
    file = db.execute("PRAGMA database_list").fetchone()[2]
    kept = replay_cache if file else {}
    counts = db.execute(
        "SELECT e.session, attempt, count(*) FROM key_event e JOIN session s ON s.id = e.session"
        " WHERE s.started >= ? GROUP BY e.session, attempt",
        (since.isoformat(),),
    ).fetchall()
    known = keymaps(db)
    for session, ord, n in counts:
        if (file, session, ord) in kept and kept[file, session, ord].events == n:
            continue
        text, mode, version = db.execute(
            "SELECT p.text, a.settings ->> '$.typing.wrong_key_mode', s.keymap_version FROM attempt a"
            " JOIN passage p ON p.id = a.passage JOIN session s ON s.id = a.session WHERE (a.session, a.ord) = (?, ?)",
            (session, ord),
        ).fetchone()
        # A keyup belongs to the Attempt of its keydown, so it can come after the next Attempt's first keydown.
        events = db.execute(
            "SELECT seq, t, type, code, key, ctrl, meta, repeat FROM key_event WHERE (session, attempt) = (?, ?)"
            " ORDER BY seq",
            (session, ord),
        )
        keymap = known.get(version, NO_BOARD)[2]
        kept[file, session, ord] = replay(session, ord, text, mode, keymap, [Event(*e) for e in events])
    return {(session, ord): kept[file, session, ord] for session, ord, _ in counts}


def replay(session: int, ord: int, passage: str, mode: str | None, keymap: Keymap, events: list[Event]) -> Replay:
    """Replays the key events of one Attempt, given in seq order."""
    downs = [e for e in events if e.type == "keydown"]
    aligned = first_error_v1(passage, mode, [Keydown(e.t, e.key, e.ctrl, e.meta) for e in downs])
    attempt = {"session": session, "ord": ord}
    rows = attempt_keystrokes(passage, keymap, events, dict(zip((e.seq for e in downs), aligned)))
    counted = [a["status"] == "correct" for a in aligned if a["first"] and a["status"] in ("correct", "error")]
    ups = [e.t for e in events if e.type == "keyup"]
    return Replay(
        len(events),
        pl.DataFrame([attempt | e._asdict() | a for e, a in zip(downs, aligned)], schema=KEYDOWNS),
        pl.DataFrame([attempt | r for r in rows], schema=REPLAYED),
        max(ups or [e.t for e in events]) - min(e.t for e in downs) if downs else 0,
        sum(counted) / len(counted) if counted else None,
    )


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
    boards = keymaps(db)
    sessions = pl.DataFrame(
        [
            (session, *boards.get(version, NO_BOARD)[:2])
            for session, version in db.execute(
                "SELECT id, keymap_version FROM session WHERE started >= ?", (since.isoformat(),)
            )
        ],
        schema={"session": pl.Int64, "board": pl.String, "letter_layout": pl.String},
        orient="row",
    )
    found = [pl.DataFrame(schema=REPLAYED), *(r.keystrokes for r in replayed(db, since).values())]
    return (
        pl.concat(found)
        .join(sessions, on="session", how="left")
        .select(list(KEYSTROKES))
        .with_columns(alignment=pl.lit(ALIGNMENT))
        .sort("session", "seq")
    )


def attempt_keystrokes(
    passage: str, keymap: Keymap, events: list[Event], aligned: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """The rows of `keystrokes` for one Attempt, without its session, ord, board and Letter
    layout. `events` are its key events in seq order; `aligned` holds its rows of
    `first_error_v1`, by seq."""

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
    # (rows of `units`, the [weakness] settings) -> one row per character and pair of those
    # rows, with at least the columns unit, cost and seen. The caller picks the rows:
    # `weakness` gives the last `weeks` weeks on one Board with one Letter layout, and the
    # unlock rule gives each character's last keystrokes on every Board with a Letter layout.
    rank: Callable[[pl.DataFrame, dict[str, Any]], pl.DataFrame]
    scale: tuple[float, float, float]  # the fixed colour scale of Keymap drawings: low, high and tick costs in ms


def units(db: sqlite3.Connection, board: str | None, letter_layout: str | None, since: datetime) -> pl.DataFrame:
    """The keystrokes typed on the Board with the Letter layout in the Sessions started at
    `since` or later, with one row for each unit of each keystroke: its character, and the
    pair of the character before and this one when the keystroke before was correct.
    The columns of `keystrokes`, and unit. Only correct keystrokes and Errors of the
    "typed" event count: misfires and off-track keys do not."""
    return layout_units(db, letter_layout, since).filter(pl.col("board").eq_missing(board))


def layout_units(db: sqlite3.Connection, letter_layout: str | None, since: datetime) -> pl.DataFrame:
    """The rows of `units` on every Board with the Letter layout. The unlock rule counts
    the keystrokes of every Board together (spec §8)."""

    def before(column: str) -> pl.Expr:
        """The column's value in the keystroke before, in the same Attempt."""
        return pl.col(column).shift().over("session", "ord", order_by="seq")

    return (
        keystrokes(db, since)
        .filter(pl.col("letter_layout").eq_missing(letter_layout))
        .with_columns(pair=pl.when(before("status") == "correct").then(before("char") + pl.col("char")))
        .filter(pl.col("event") == "typed", pl.col("status").is_in(["correct", "error"]))
        .with_columns(unit=pl.concat_list("char", "pair"))
        .explode("unit")
        .drop_nulls("unit")
    )


def recent_cost_v1(units: pl.DataFrame, settings: dict[str, Any]) -> pl.DataFrame:
    """The cost of each character and pair in rows of `units`, abandoned Attempts too.
    Characters and pairs seen fewer than settings["min_seen"] times, or never timed, are left out.

    - unit: as `units` gives it.
    - time: the median `time` of the unit's correct keystrokes.
    - error_rate: the share of Errors among its first keystrokes at a position.
    - fix_ms: the median fix time of its Errors.
    - cost (ms) = time + error_rate × fix_ms.
    - seen: its number of first keystrokes at a position.
    """
    return (
        units.group_by("unit")
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
    """The ranking of the characters and pairs typed on the Board with the Letter layout in
    the Sessions of the last settings["weeks"] weeks, by the Weakness model named
    settings["model"]. `settings` is the [weakness] table of the settings file. Columns:
    unit, cost (ms), seen, the model's own columns, and model (its name). Sorted on cost,
    the highest first, then on unit."""
    since = datetime.now(UTC) - timedelta(weeks=settings["weeks"])
    return rank_units(units(db, board, letter_layout, since), settings)


def rank_units(rows: pl.DataFrame, settings: dict[str, Any]) -> pl.DataFrame:
    """The ranking of rows of `units` by the Weakness model named settings["model"], with
    the columns and order of `weakness`. A notebook can rank a part of the rows with it."""
    name = settings["model"]
    return (
        WEAKNESS_MODELS[name]
        .rank(rows, settings)
        .with_columns(model=pl.lit(name))
        .sort(["cost", "unit"], descending=[True, False])
    )


def seen_counts(db: sqlite3.Connection, board: str | None, letter_layout: str | None, since: datetime) -> pl.DataFrame:
    """How many times each character and pair was seen on the Board with the Letter layout
    in the Sessions started at `since` or later: its number of first keystrokes at a
    position, as `recent_cost_v1` counts it. Columns: unit, seen. Sorted on unit."""
    return (
        units(db, board, letter_layout, since)
        .group_by("unit")
        .agg(seen=pl.col("first_time_correct").count())
        .sort("unit")
    )


class Unlocking(NamedTuple):
    """The state of a Letter layout being learned, such as free-range (spec §8). Each key is
    written as the character it types without Shift."""

    unlocked: str  # the Unlocked keys, in unlock order: the starting set, then the unlock log
    locked: str  # the other main keys, in unlock order: the first is the next to unlock
    introducing: str | None  # the newest key of the unlock log, while Introduction Drills are due for it


def unlocking(db: sqlite3.Connection, letter_layout: str | None, settings: dict[str, Any]) -> Unlocking | None:
    """The unlock state of the Letter layout, or None when it is not the one being learned.
    `settings` is the [unlocking] table of the settings file.

    Introduction Drills are due for the newest key of the unlock log until it has been seen
    settings["min_seen"] times since its unlock, on every Board with the Letter layout. Seen
    counts the first keystrokes at a position, as `recent_cost_v1` does. A keystroke's time is
    its Session's start plus its `t`, which is a little late (see the ADR)."""
    if letter_layout != settings["letter_layout"]:
        return None
    log = db.execute("SELECT key, time FROM unlock WHERE letter_layout = ? ORDER BY rowid", (letter_layout,)).fetchall()
    start = "".join(settings["start"].split())
    unlocked = start + "".join(key for key, _ in log if key not in start)
    locked = "".join(key for key in settings["order"].split() if key not in unlocked)
    introducing = None
    if log:
        key, time = log[-1]
        at = datetime.fromisoformat(time)
        # From the start of the Session that was open at the unlock, if there was one.
        (since,) = db.execute("SELECT max(started) FROM session WHERE started <= ?", (time,)).fetchone()
        since = datetime.fromisoformat(since) if since else at
        started = {id: datetime.fromisoformat(s) for id, s in db.execute("SELECT id, started FROM session")}
        typed = (
            layout_units(db, letter_layout, since)
            .filter(pl.col("unit") == key, pl.col("first_time_correct").is_not_null())
            .select("session", "t")
        )
        seen = sum(started[s] + timedelta(milliseconds=t) >= at for s, t in typed.iter_rows())
        introducing = key if seen < settings["min_seen"] else None
    return Unlocking(unlocked, locked, introducing)


def unlock_due(db: sqlite3.Connection, letter_layout: str | None, unlocked: str, settings: dict[str, Any]) -> bool:
    """Whether the next key of the Letter layout being learned unlocks (spec §8): each Unlocked
    key's character costs less than `threshold` ms by the Weakness model in use, over its
    last `last` keystrokes on every Board with the Letter layout, and was seen at least
    `min_seen` times in them. These are settings of the [unlocking] table; `settings` holds
    every table of the settings file."""
    rule, model = settings["unlocking"], settings["weakness"]
    last = (
        layout_units(db, letter_layout, datetime.min)
        .filter(pl.col("unit").is_in(list(unlocked)))
        .filter(pl.int_range(pl.len()).over("unit", order_by=["session", "seq"], descending=True) < rule["last"])
    )
    ranked = WEAKNESS_MODELS[model["model"]].rank(last, model | {"min_seen": rule["min_seen"]})
    cost = dict(zip(ranked["unit"], ranked["cost"]))
    return all(cost.get(key, math.inf) < rule["threshold"] for key in unlocked)


TREND_WEEKS = 13  # the progress page's trend covers about 3 months


class Progress(NamedTuple):
    """What the progress page shows for one Board and Letter layout (spec §11)."""

    trend: pl.DataFrame
    chars: pl.DataFrame
    pairs: pl.DataFrame
    heat: Heat


def progress(
    db: sqlite3.Connection, board: str | None, letter_layout: str | None, settings: dict[str, Any]
) -> Progress:
    """What the progress page shows for the Board with the Letter layout. `settings` is the
    [weakness] table of the settings file.

    - trend: one row per day with a finished Attempt in the last TREND_WEEKS weeks. day:
      the date of the Attempt's Session start, in this computer's time zone. wpm, accuracy: the medians over that
      day's finished Attempts. attempts: their number. Sorted on day.
    - chars, pairs: the 10 weakest characters and the 10 weakest pairs, with the columns
      of `weakness`.
    - heat: the costs of the Weakness ranking, the seen counts of every unit in the
      model's weeks, and the model's colour scale.
    """
    now = datetime.now(UTC)
    finished = attempts(db, now - timedelta(weeks=TREND_WEEKS)).filter(
        pl.col("finished"), pl.col("board").eq_missing(board), pl.col("letter_layout").eq_missing(letter_layout)
    )
    trend = (
        finished.with_columns(day=pl.Series([d.astimezone().date() for d in finished["started"]], dtype=pl.Date))
        .group_by("day")
        .agg(pl.col("wpm").median(), pl.col("accuracy").median(), attempts=pl.len())
        .sort("day")
    )
    ranking = weakness(db, board, letter_layout, settings)
    seen = seen_counts(db, board, letter_layout, now - timedelta(weeks=settings["weeks"]))
    length = pl.col("unit").str.len_chars()
    return Progress(
        trend,
        ranking.filter(length == 1).head(10),
        ranking.filter(length == 2).head(10),
        Heat(
            dict(zip(ranking["unit"], ranking["cost"])),
            dict(zip(seen["unit"], seen["seen"])),
            WEAKNESS_MODELS[settings["model"]].scale,
        ),
    )


def trend_chart(trend: pl.DataFrame) -> alt.HConcatChart:
    """The progress page's chart of a `progress` trend, one point per day: WPM, and first-time
    accuracy beside it. The server sends it as a Vega-Lite spec; a notebook shows it as it is."""
    import altair as alt  # here, as it takes about 0.2 s to import and only this chart needs it

    base = (
        alt.Chart(trend)
        .mark_line(point=True)
        .encode(x=alt.X("day:T", title=None))
        .properties(width=360, height=140)
    )
    # Show whole WPM and whole percents. With one day of data, the axis range is very small.
    # tickMinStep keeps the ticks whole, so two ticks do not get the same rounded label.
    return alt.hconcat(
        base.encode(
            y=alt.Y("wpm:Q", title="WPM", scale=alt.Scale(zero=False), axis=alt.Axis(format="d", tickMinStep=1))
        ),
        base.encode(
            y=alt.Y(
                "accuracy:Q",
                title="first-time accuracy",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(format=".0%", tickMinStep=0.01),
            )
        ),
    ).configure(background="transparent")
