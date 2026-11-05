"""The analysis code that keybr_analysis.py and the keybr notebook use: the keystroke rows of one
Attempt (`attempt_keystrokes`) and the Weakness models.

Polars 2 does not keep the order of rows, so every table is sorted on explicit columns.
"""

from collections.abc import Callable
from typing import Any, NamedTuple

import polars as pl

from typokiller.keymap import Key, Keymap

MODIFIERS = {"Shift", "Control", "Alt", "Meta", "CapsLock"}  # the `key` of modifier keys
MACRO_GAP_MS = 5  # a macro types its characters about 1 ms apart, faster than any finger
NO_BOARD = Keymap({}, {}, {}, [])  # the Keymap of an Attempt with no Board


class Event(NamedTuple):
    seq: int
    t: float
    type: str
    code: str
    key: str
    repeat: bool


def attempt_keystrokes(
    passage: str, keymap: Keymap, events: list[Event], aligned: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """One row per intended character of one Attempt: each keydown that `aligned` gives a
    position, and each combo misfire. `events` are its key events in seq order. `aligned`
    holds, for each keydown by seq, what the analysis method found: cursor (the number of
    characters typed before the key), position (of the character the key was meant to type,
    or None), status ("correct", "error", "off-track" or "ignored"), first (whether no earlier
    keystroke was at this position) and fix_ms (on an Error, the time to its Fix).

    - seq, t: the keydown's.
    - position, status, fix_ms: as `aligned` gives them. char: the text's character at the
      position. typed: the keydown's `key`.
    - event: "typed", or "mod-tap misfire", "combo misfire" or "macro misfire". A misfire is
      a firmware result that the typist did not want, so it has no first_time_correct.
      - A mod-tap misfire is a key at a position whose character is the tap of a mod-tap,
        after that mod-tap's modifier went down: the mod-tap was held too long. With Shift
        this is a wrong capital. Ctrl and GUI make the next key do nothing, so the key
        marked is usually the mod-tap's own character, typed again.
      - A combo misfire is the key a combo sends where the text has the combo's
        characters next: they were pressed too close together. Its position is the cursor's.
      - A macro misfire is a macro's text whose first character is an Error.
    - candidates: the keys that type the typed character (see `read_keymap`). The picked
      key is the first one on the layer of the text character's own first candidate,
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
      whose keydowns come at their release, every pair gets an equal share of the time from
      the keydown before the run to the keydown after it.
      Dwell, flight and time are None for keys that are not finger presses: macros, combo
      outputs, misfires and off-track keys. Shift from Caps Word or from a shifted
      keycode is a modifier key, so it does not count either.
    - first_time_correct: for the first keystroke at a position, whether it was correct
      (True) or an Error (False). None for later keystrokes, off-track keys and misfires.
    """

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
        row |= {"presses": presses}
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
        r["timed"] = r["event"] == "typed" and r["kind"] not in ("macro", "combo") and r["status"] != "off-track"
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
    # (rows of keybr_analysis.units, the settings) -> one row per character and pair of those
    # rows, with at least the columns unit, cost and seen. The caller picks the rows.
    rank: Callable[[pl.DataFrame, dict[str, Any]], pl.DataFrame]
    scale: tuple[float, float, float]  # the fixed colour scale of Keymap drawings: low, high and tick costs in ms


def recent_cost_v1(units: pl.DataFrame, settings: dict[str, Any]) -> pl.DataFrame:
    """The cost of each character and pair in rows of keybr_analysis.units, abandoned Attempts too.
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


# The Weakness models, by name.
WEAKNESS_MODELS = {"recent-cost-v1": WeaknessModel(recent_cost_v1, (150, 600, 400))}


def rank_units(rows: pl.DataFrame, settings: dict[str, Any]) -> pl.DataFrame:
    """The ranking of rows of keybr_analysis.units by the Weakness model named settings["model"].
    Columns: unit, cost (ms), seen, the model's own columns, and model (its name). Sorted on
    cost, the highest first, then on unit."""
    name = settings["model"]
    return (
        WEAKNESS_MODELS[name]
        .rank(rows, settings)
        .with_columns(model=pl.lit(name))
        .sort(["cost", "unit"], descending=[True, False])
    )

