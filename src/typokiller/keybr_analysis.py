"""The analysis method keybr-input-v1: character observations from keybr recordings.

keybr's typing rules are not typokiller's. keybr can forgive a wrong character, skip a word,
recover by itself and stop on an error, and it records what its engine accepted. So this method
does not replay key events with `analysis.apply_key` and `analysis.first_error_v1`. It reads the
recorded input outcomes and state changes instead (see docs/adr/0003-keybr-input-v1.md). Its numbers
must not be pooled with those of first-error-v1.

A real input is a processed appendChar or appendLineBreak input that has a state record. Its time
is the timeStamp of its original event. The order of cause of the inputs is their sequence order.

The final reading of each input comes from the steps that the state records put in. A step keeps
the timestamp of the input that put it in, so:

- An accepted step at position p whose (timeStamp, codePoint) is a real input's makes that input
  correct at p. This covers keybr's recovery, which accepts earlier inputs later.
- A step whose timestamp is that of an input that typed another character makes that input wrong
  at p, unless the same splice makes it correct somewhere else. This is the replaced character.
- Any other step is automatic: keybr put it in without a real input.
- A rejected input that no later splice reads again is wrong at its state's cursor.

Per position, the first input is correct or an Error charged to the intended character. Later
wrong inputs are off-track. The first correct input after the Error is the Fix. A position that
keybr accepted without a correct input after an Error is recovered, and its fix time stays None.
A position with only automatic steps is skipped and is no observation.
"""

import json
from collections import defaultdict
from typing import Any, NamedTuple

import polars as pl

from typokiller.analysis import NO_BOARD, Event, attempt_keystrokes
from typokiller.keymap import Keymap, read_keymap
from typokiller.recording import TIME, Recording

ANALYSIS = "keybr-input-v1"
APPEND = ("appendChar", "appendLineBreak")

OBSERVATIONS = {
    "attempt": pl.String, "board_id": pl.String, "keymap_id": pl.String, "keymap_version": pl.String,
    "letter_layout": pl.String, "started": TIME, "attempt_status": pl.String, "position": pl.Int64,
    "char": pl.String, "status": pl.String, "first_time_correct": pl.Boolean, "fix_ms": pl.Float64,
    "time": pl.Float64, "dwell": pl.Float64, "flight": pl.Float64, "timing_source": pl.String,
    "inferred_kind": pl.String, "inferred_layer": pl.Int64, "inferred_key": pl.String, "inferred_event": pl.String,
    "pair": pl.String, "time_stamp": pl.Float64,
}  # fmt: skip
EXCLUSIONS = {
    "attempt": pl.String, "attempt_status": pl.String, "inputs": pl.Int64, "skipped": pl.Int64,
    "recovered": pl.Int64, "off_track": pl.Int64, "ignored": pl.Int64, "ambiguous": pl.Int64,
    "composed": pl.Int64, "missing_releases": pl.Int64, "not_timed": pl.Int64,
}  # fmt: skip
NATIVE = {
    "attempt": pl.String, "board_id": pl.String, "keymap_version": pl.String, "letter_layout": pl.String,
    "keybr_layout": pl.String, "started": TIME, "length": pl.Int64, "time": pl.Float64, "errors": pl.Int64,
    "complexity": pl.Int64, "speed": pl.Float64, "wpm": pl.Float64, "accuracy": pl.Float64, "score": pl.Float64,
    "result_accepted": pl.Boolean,
}  # fmt: skip


class Input(NamedTuple):
    order: int  # its place in the order of cause
    sequence: int  # of the processed record
    original: int  # the sequence of its original record
    t: float  # the timeStamp of its original event (ms)
    step_t: float  # the timeStamp of the processed event, which its steps keep
    char: str
    synthetic: bool  # put in by forward emulation, from a keydown
    composed: bool  # from a composition
    state: dict[str, Any]


class Reading(NamedTuple):
    """What the state records of one Attempt say about its inputs."""

    inputs: list[Input]
    final: dict[int, tuple[int, bool]]  # the final (position, correct) of each input that has one, by index
    automatic: set[int]  # the positions where keybr put in a step with no real input
    stepped: set[int]  # the positions where a step was put in that is not a correct input
    brought: set[int]  # the inputs whose own state put in an automatic step
    ignored: int  # inputs that were neither accepted nor rejected, such as an ignored space


def read_inputs(text: str, found: list[dict[str, Any]]) -> Reading:
    """The final reading of each real input of one Attempt, from its records in sequence order."""
    by_sequence = {r["sequence"]: r for r in found}
    states = {r["processedSequence"]: r for r in found if r["type"] == "state"}
    inputs = []
    for r in found:
        e = r["event"] if r["type"] == "processed" else {}
        if e.get("type") != "input" or e["inputType"] not in APPEND or r["sequence"] not in states:
            continue
        original = by_sequence.get(r["originalSequence"], {}).get("event") or e
        char = "\n" if e["inputType"] == "appendLineBreak" else chr(e["codePoint"])
        inputs.append(Input(
            len(inputs), r["sequence"], r["originalSequence"], original["timeStamp"], e["timeStamp"], char,
            r["synthetic"], original["type"] == "compositionend", states[r["sequence"]],
        ))  # fmt: skip
    final: dict[int, tuple[int, bool]] = {}
    automatic, stepped, brought = set(), set(), set()
    ignored = 0
    by_step: dict[tuple[float, int], int] = {}  # the latest input so far with each (timeStamp, codePoint)
    by_time: dict[float, list[int]] = defaultdict(list)  # the inputs so far with each timeStamp
    for j, i in enumerate(inputs):
        by_step[i.step_t, ord(i.char)] = j
        by_time[i.step_t].append(j)
        splice = i.state["accepted"]
        correct_here, rest = set(), []
        for k, step in enumerate(splice["inserted"]):
            p = splice["from"] + k
            if (m := by_step.get((step["timeStamp"], step["codePoint"]))) is not None:
                correct_here.add(m)
                final[m] = (p, True)
            else:
                rest.append((p, step))
        for p, step in rest:
            stepped.add(p)
            typed = [e for e in by_time.get(step["timeStamp"], []) if e not in correct_here]
            if typed:
                final[typed[-1]] = (p, False)
            else:
                automatic.add(p)
                brought.add(j)
        if not splice["inserted"]:
            if i.state["effect"] == "rejected":
                final[j] = (i.state["before"]["cursor"], False)
            else:
                ignored += 1
    return Reading(inputs, final, automatic, stepped, brought, ignored)


class Press(NamedTuple):
    keydown: int | None  # the sequence of the processed keydown that caused the input
    ambiguous: bool


def presses(found: list[dict[str, Any]], inputs: list[Input]) -> dict[int, Press]:
    """The key press that caused each input, by input index. A synthetic input comes from its own
    keydown. Another input comes from the one earlier unmatched non-repeat keydown with the same
    key since the input before; with none, or with more than one, the match is ambiguous.
    Composed input has no press, and neither has input in an Attempt with no keydowns."""
    by_sequence = {r["sequence"]: r for r in found}
    downs = [
        r for r in found
        if r["type"] == "processed" and r["event"]["type"] == "keydown"
        and not by_sequence.get(r["originalSequence"], {}).get("event", {}).get("repeat")
    ]  # fmt: skip
    if not downs:
        return {i.order: Press(None, False) for i in inputs}
    matched: set[int] = set()
    found_presses = {}
    after = -1  # the original sequence of the input before
    for i in inputs:
        if i.composed:
            found_presses[i.order] = Press(None, False)
        elif i.synthetic:
            down = next((d["sequence"] for d in downs if d["originalSequence"] == i.original), None)
            found_presses[i.order] = Press(down, down is None)
        else:
            key = "Enter" if i.char == "\n" else i.char
            candidates = [
                d["sequence"] for d in downs
                if after < d["sequence"] < i.original and d["event"]["key"] == key and d["sequence"] not in matched
            ]  # fmt: skip
            one = candidates[0] if len(candidates) == 1 else None
            found_presses[i.order] = Press(one, one is None)
        if (down := found_presses[i.order].keydown) is not None:
            matched.add(down)
        after = i.original
    return found_presses


def key_events(found: list[dict[str, Any]]) -> list[Event]:
    """The key events of one Attempt for `analysis.attempt_keystrokes`: each processed keydown, with
    its original event's timeStamp and the processed key and code, and each original keyup that
    names its press, with the code of that press's processed keydown. Sorted on sequence."""
    by_sequence = {r["sequence"]: r for r in found}
    processed_down = {
        r["originalSequence"]: r for r in found if r["type"] == "processed" and r["event"]["type"] == "keydown"
    }
    events = []
    for r in found:
        if r["type"] == "processed" and r["event"]["type"] == "keydown":
            original = by_sequence.get(r["originalSequence"], {}).get("event") or r["event"]
            e, mods = r["event"], r["event"]["modifiers"]
            repeat = bool(original.get("repeat"))
            events.append(Event(r["sequence"], original["timeStamp"], "keydown", e["code"], e["key"], "Control" in mods, "Meta" in mods, repeat))
        elif r["type"] == "original" and r["event"]["type"] == "keyup" and r["pressSequence"] is not None:
            press = processed_down.get(r["pressSequence"])
            code = press["event"]["code"] if press else r["event"]["code"]
            events.append(Event(r["sequence"], r["event"]["timeStamp"], "keyup", code, r["event"]["key"] or "", False, False, False))
    return sorted(events, key=lambda e: e.seq)


class AttemptResult(NamedTuple):
    observations: list[dict[str, Any]]
    exclusions: dict[str, Any]


def analyse_attempt(attempt: dict[str, Any], found: list[dict[str, Any]], keymap: Keymap) -> AttemptResult:
    """The observations and exclusion counts of one Attempt. `attempt` is its row of `attempts`."""
    text = attempt["text"]
    reading = read_inputs(text, found)
    inputs, final = reading.inputs, reading.final
    readings: dict[int, list[tuple[int, bool]]] = defaultdict(list)
    for index, (p, ok) in sorted(final.items()):
        readings[p].append((index, ok))
    pressed = presses(found, inputs)
    events = key_events(found)
    by_key = any(e.type == "keydown" for e in events)

    outcomes = {}  # position -> (first input, correct, fix_ms)
    skipped = recovered = off_track = 0
    for p in sorted(set(readings) | reading.automatic):
        if p not in readings:
            skipped += 1
            continue
        (first, ok), *later = readings[p]
        fix = next((i for i, good in later if good), None) if not ok else None
        fix_ms = inputs[fix].t - inputs[first].t if fix is not None else None
        recovered += not ok and fix is None and p in reading.stepped
        off_track += sum(not good for _, good in later)
        outcomes[p] = (first, ok, fix_ms)

    # The rows of analysis.attempt_keystrokes, keyed by keydown, built from the outcomes above.
    of_keydown = {press.keydown: index for index, press in pressed.items() if press.keydown is not None}
    # A keydown with no input has the cursor of the last state before it, for the combo misfires.
    aligned, cursor = {}, 0
    states = sorted((r["sequence"], r["after"]["cursor"]) for r in found if r["type"] == "state")
    for e in events:
        if e.type != "keydown":
            continue
        while states and states[0][0] < e.seq:
            cursor = states.pop(0)[1]
        row = {"cursor": cursor, "position": None, "status": "ignored", "first": False, "fix_ms": None}
        if (index := of_keydown.get(e.seq)) is not None and index in final:
            p, ok = final[index]
            first, _, fix_ms = outcomes[p]
            if first == index:
                row |= {"position": p, "status": "correct" if ok else "error", "first": True, "fix_ms": fix_ms}
            else:
                row |= {"position": p, "status": "correct" if ok else "off-track"}
        aligned[e.seq] = row
    keystrokes = {r["seq"]: r for r in attempt_keystrokes(text, keymap, events, aligned)} if by_key else {}

    rows = []
    for p, (j, ok, fix_ms) in sorted(outcomes.items()):
        i = inputs[j]
        linked = j > 0 and final.get(j - 1) == (p - 1, True) and j not in reading.brought
        press, before = pressed[j], pressed.get(j - 1)
        timed = ok and linked and not i.composed and not inputs[j - 1].composed
        key = keystrokes.get(press.keydown) if press.keydown is not None else None
        time = flight = None
        if by_key:
            timed = timed and key is not None and before is not None and before.keydown is not None
            if timed and key is not None:
                time, flight = key["time"], key["flight"]
        elif timed:
            time = i.t - inputs[j - 1].t
        rows.append({
            "attempt": attempt["attempt"],
            "board_id": attempt["board_id"],
            "keymap_id": attempt["keymap_id"],
            "keymap_version": attempt["keymap_version"],
            "letter_layout": attempt["letter_layout"],
            "started": attempt["started"],
            "attempt_status": attempt["status"],
            "position": p,
            "char": text[p],
            "status": "correct" if ok else "error",
            "first_time_correct": ok,
            "fix_ms": fix_ms,
            "time": time,
            "dwell": key["dwell"] if key else None,
            "flight": flight,
            "timing_source": "key press" if by_key else "input",
            "inferred_kind": key and key["kind"],
            "inferred_layer": key and key["layer"],
            "inferred_key": key and key["key"],
            "inferred_event": key and key["event"],
            "pair": text[p - 1] + text[p] if linked else None,
            "time_stamp": i.t,
        })
    excluded = {
        "attempt": attempt["attempt"],
        "attempt_status": attempt["status"],
        "inputs": len(inputs),
        "skipped": skipped,
        "recovered": recovered,
        "off_track": off_track,
        "ignored": reading.ignored,
        "ambiguous": sum(p.ambiguous for p in pressed.values()),
        "composed": sum(i.composed for i in inputs),
        "missing_releases": attempt["missing_releases"],
        "not_timed": sum(r["status"] == "correct" and r["time"] is None for r in rows),
    }
    return AttemptResult(rows, excluded)


def analysed(recording: Recording) -> list[AttemptResult]:
    """The result of every Attempt that can be read: every one but those with status "unreadable"."""
    keymaps = {v: read_keymap(vil) for v, vil in recording.keyboards.select("keymap_version", "vil").iter_rows() if vil}
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table in (recording.original_events, recording.processed_events, recording.states):
        for attempt, text in table.select("attempt", "json").iter_rows():
            found[attempt].append(json.loads(text))
    results = []
    for attempt in recording.attempts.filter(pl.col("status") != "unreadable").iter_rows(named=True):
        records = sorted(found.get(attempt["attempt"], []), key=lambda r: r["sequence"])
        results.append(analyse_attempt(attempt, records, keymaps.get(attempt["keymap_version"], NO_BOARD[2])))
    return results


def observations(recording: Recording) -> pl.DataFrame:
    """One row per position with a real first input, in every Attempt that can be read, abandoned
    ones too. Sorted on started, attempt and position.

    - attempt, board_id, keymap_id, keymap_version, letter_layout, started, attempt_status: the Attempt's.
    - position (in code points), char: the intended character.
    - status: "correct", or "error" for an Error charged to char. first_time_correct: the same as a boolean.
    - fix_ms: the time from the Error to its Fix. None when it was not fixed by a correct input,
      also when keybr recovered the position by itself.
    - time: from the previous input to this one, kept only when this is a correct first input, the
      previous real input was the correct input at position - 1, this input's own state put in
      no automatic step, neither input was composed, and (with key presses) both presses are
      known. With key presses it is the time of `analysis.attempt_keystrokes`, with its rules for
      mod-taps, layer-taps, combos and macros; with input events only, the difference of their timestamps.
    - dwell, flight: of `analysis.attempt_keystrokes`, from the input's press and its release.
      None without a known press or release; flight only when time is kept.
    - timing_source: "key press", or "input" for an Attempt with no keydowns.
    - inferred_kind, inferred_layer, inferred_key, inferred_event: the key that the saved Keymap
      says typed the character, and "typed" or a misfire. They are inferred from the firmware's
      .vil, not measured.
    - pair: the character before and this one, when the previous real input was the correct
      input at position - 1 and this input's state put in no automatic step.
    - time_stamp: the timeStamp of the first input (ms). analysis: "keybr-input-v1".
    """
    rows = [r for result in analysed(recording) for r in result.observations]
    return (
        pl.DataFrame(rows, schema=OBSERVATIONS, orient="row")
        .with_columns(analysis=pl.lit(ANALYSIS))
        .sort("started", "attempt", "position")
    )


def exclusions(recording: Recording) -> pl.DataFrame:
    """One row per Attempt that can be read, with what its observations leave out or do not time:

    - inputs: its real inputs.
    - skipped: positions keybr put in with no real input. recovered: Errors that keybr accepted
      without a correct input. off_track: wrong inputs after the first at a position. ignored:
      inputs neither accepted nor rejected, such as an ignored space.
    - ambiguous: inputs whose key press is not clear. composed: inputs from a composition.
    - missing_releases: presses with no release. not_timed: correct observations with no time.

    Sorted on attempt. analysis: "keybr-input-v1"."""
    rows = [result.exclusions for result in analysed(recording)]
    return pl.DataFrame(rows, schema=EXCLUSIONS, orient="row").with_columns(analysis=pl.lit(ANALYSIS)).sort("attempt")


def units(observations: pl.DataFrame) -> pl.DataFrame:
    """The observations with one row for each unit: the character, and the pair when there is one.
    The columns of `observations`, and unit. `analysis.rank_units` ranks these rows, as it ranks
    the rows of `analysis.units`; unresolved fix times stay None."""
    return observations.with_columns(unit=pl.concat_list("char", "pair")).explode("unit").drop_nulls("unit")


def first_input_accuracy(observations: pl.DataFrame) -> pl.DataFrame:
    """The first-input accuracy of each Attempt: the share of its observations whose first input
    was correct. Columns: attempt, started, board_id, keymap_version, letter_layout,
    attempt_status, accuracy, observations, analysis. Sorted on started and attempt."""
    keys = ["attempt", "started", "board_id", "keymap_version", "letter_layout", "attempt_status"]
    return (
        observations.group_by(keys)
        .agg(accuracy=pl.col("first_time_correct").mean(), observations=pl.len())
        .with_columns(analysis=pl.lit(ANALYSIS))
        .sort("started", "attempt")
    )


def native_scores(recording: Recording) -> pl.DataFrame:
    """keybr's own scores of each completed Attempt, from its native result, with keybr's formulas
    (packages/keybr-result/lib/result.ts): speed = length / time per minute (characters),
    accuracy = (length - errors) / length, and score = speed × complexity / (errors + 1) × length / 50,
    where complexity is the number of characters in the result's histogram. They are 0 when the
    length, time or complexity is 0. wpm is speed / 5. measure: "keybr", as these are not
    keybr-input-v1 numbers. Sorted on started and attempt."""
    rows = []
    for a in recording.attempts.filter(pl.col("result").is_not_null()).iter_rows(named=True):
        result = json.loads(a["result"])
        length, time, errors = result["length"], result["time"], result["errors"]
        complexity = len(result["histogram"])
        speed = accuracy = score = 0.0
        if length > 0 and time > 0 and complexity > 0:
            speed = length / (time / 1000) * 60
            accuracy = (length - errors) / length
            score = speed * complexity / (errors + 1) * (length / 50)
        rows.append({
            "attempt": a["attempt"], "board_id": a["board_id"], "keymap_version": a["keymap_version"],
            "letter_layout": a["letter_layout"], "keybr_layout": a["keybr_layout"], "started": a["started"],
            "length": length, "time": time, "errors": errors, "complexity": complexity, "speed": speed,
            "wpm": speed / 5, "accuracy": accuracy, "score": score, "result_accepted": a["result_accepted"],
        })  # fmt: skip
    return pl.DataFrame(rows, schema=NATIVE, orient="row").with_columns(measure=pl.lit("keybr")).sort("started", "attempt")
