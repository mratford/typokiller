from pathlib import Path

from typokiller.analysis import MODIFIERS, Event, attempt_keystrokes
from typokiller.keymap import read_keymap

VIL = Path(__file__).parent / "fixtures" / "vil"
E, C = "error", "correct"


def down(t, key, code=None, repeat=False):
    return {"t": t, "type": "keydown", "key": key, "code": code or f"Key{key}", "repeat": repeat}


def up(t, key, code=None):
    return {"t": t, "type": "keyup", "key": key, "code": code or f"Key{key}"}


def tap(t, key, code=None, dwell=80.0):
    return [down(t, key, code), up(t + dwell, key, code)]


def correct(*positions):
    """The alignment of keys that are each right the first time, at these positions."""
    return [(p, p, C, True, None) for p in positions]


def keystrokes(vil, text, aligned, *events):
    """The rows of `attempt_keystrokes` for one Attempt at `text` with the .vil from the fixtures.
    `aligned` holds (cursor, position, status, first, fix_ms) for each keydown that is not a
    modifier, in time order. Each item of `events` is an event or a list of them, in any order.
    keybr's own path to these rows, with its alignment, is tested in test_keybr_analysis.py."""
    flat = sorted((e for item in events for e in (item if isinstance(item, list) else [item])), key=lambda e: e["t"])
    found = [Event(seq, e["t"], e["type"], e["code"], e["key"], e.get("repeat", False)) for seq, e in enumerate(flat)]
    keys = [e.seq for e in found if e.type == "keydown" and e.key not in MODIFIERS]
    columns = ["cursor", "position", "status", "first", "fix_ms"]
    by_seq = {seq: dict(zip(columns, a)) for seq, a in zip(keys, aligned, strict=True)}
    return attempt_keystrokes(text, read_keymap((VIL / vil).read_text()), found, by_seq)


def select(rows, *columns):
    return [tuple(r[c] for c in columns) for r in rows]


def test_each_keystroke_is_attributed_to_its_candidate_keys_and_one_pick_guided_by_the_text():
    rows = keystrokes(
        "ferris_sweep_qwerty.vil", "A(78",
        [*correct(0, 1, 2), (3, 3, E, True, 400.0), (4, None, "off-track", False, None), (3, 3, C, False, None)],
        down(0, "Shift", "ShiftRight"), tap(10, "A"), up(100, "Shift", "ShiftRight"),
        down(200, "Shift", "ShiftLeft"), tap(201, "(", "Digit9"), up(290, "Shift", "ShiftLeft"),
        tap(400, "7"),
        tap(600, "*"),  # an Error: the * on Num is picked, as 8 is on Num
        tap(800, "Backspace"),
        tap(1000, "8"),
    )  # fmt: skip

    columns = ["position", "char", "typed", "status", "layer", "key", "kind", "first_time_correct", "fix_ms", "event"]
    assert select(rows, *columns) == [
        (0, "A", "A", "correct", 0, "1,0", "plain", True, None, "typed"),
        (1, "(", "(", "correct", 1, "5,2", "plain", True, None, "typed"),
        (2, "7", "7", "correct", 4, "4,1", "plain", True, None, "typed"),
        (3, "8", "*", "error", 4, "4,4", "plain", False, 400.0, "typed"),
        (3, "8", "8", "correct", 4, "4,2", "plain", None, None, "typed"),
    ]
    # Shift between two keys does not stop their flight; Backspace does.
    assert [r["flight"] for r in rows] == [None, 111.0, 119.0, 120.0, None]
    assert rows[1]["candidates"] == [
        {"layer": 1, "key": "5,2", "kind": "plain"},
        {"layer": 4, "key": "1,2", "kind": "plain"},
        {"layer": 4, "key": "4,3", "kind": "plain"},
    ]
    assert select(rows[:1], "seq", "t", "dwell", "flight") == [(1, 10.0, 80.0, None)]


def test_mod_tap_combo_and_macro_misfires_are_their_own_event_types():
    rows = keystrokes(
        "cheapino.vil", "ve kl->xy",
        [
            (0, 0, E, True, 250.0), (1, None, "off-track", False, None), (0, 0, C, False, None), *correct(1, 2),
            (3, None, "ignored", False, None), (2, 2, C, False, None), *correct(3, 4, 5, 6),
            (7, 7, E, True, None), (8, 8, "off-track", True, None),
        ],
        down(0, "Shift", "ShiftLeft"), tap(250, "E"), up(300, "Shift", "ShiftLeft"),  # v held too long
        tap(400, "Backspace"), tap(500, "v"), tap(600, "e"), tap(700, " ", "Space"),
        tap(800, "Backspace"),  # K+L together send Backspace
        tap(900, " ", "Space"), tap(1000, "k"), tap(1100, "l"),
        tap(1200, "-", "Minus", 0.2), tap(1201, ">", "Period", 0.2),  # the -> macro
        tap(1400, "|", "Backslash", 0.2), tap(1401, ">", "Period", 0.2),  # the |> macro, where x was wanted
    )  # fmt: skip

    assert select(rows, "position", "typed", "status", "event", "layer", "key", "kind") == [
        (0, "E", "error", "mod-tap misfire", 0, "6,7", "mod-tap"),
        (0, "v", "correct", "typed", 0, "6,7", "mod-tap"),
        (1, "e", "correct", "typed", 0, "4,8", "plain"),
        (2, " ", "correct", "typed", 0, "1,5", "layer-tap"),
        (3, "Backspace", "ignored", "combo misfire", 0, "1,2+1,3", "combo"),
        (2, " ", "correct", "typed", 0, "1,5", "layer-tap"),
        (3, "k", "correct", "typed", 0, "1,2", "plain"),
        (4, "l", "correct", "typed", 0, "1,3", "plain"),
        (5, "-", "correct", "typed", 1, "6,7", "macro"),
        (6, ">", "correct", "typed", 1, "6,7", "macro"),
        (7, "|", "error", "macro misfire", 1, "6,10", "macro"),
        (8, ">", "off-track", "macro misfire", 1, "6,10", "macro"),
    ]
    # Misfires are not counted as Errors.
    assert [r["first_time_correct"] for r in rows[:5]] == [None, None, True, True, None]


def test_dwell_and_flight_come_from_finger_events_with_summed_time_around_tap_hold_keys():
    rows = keystrokes(
        "ferris_sweep_qwerty.vil", "ab e-d->f\ng",
        [*correct(*range(9)), (9, None, "ignored", False, None), *correct(9, 10)],
        tap(0, "a"), tap(200, "b"),
        tap(500, " ", "Space", 0.3),  # a tapped layer-tap arrives at its release
        tap(600, "e"),
        down(800, "-", "Minus"), up(880, "_", "Minus"),  # a keyup's key can differ from its keydown's
        down(1000, "d"),  # its keyup was lost
        tap(1200, "-", "Minus", 0.2), tap(1201, ">", "Period", 0.2),  # the -> macro
        down(1400, "f"), down(1900, "f", repeat=True), up(1950, "f"),
        tap(2100, "Enter", "Enter"),  # the J+L combo
        tap(2300, "g"),
    )  # fmt: skip

    # time runs from keydown to keydown; across the layer-tap, the two pairs share it equally.
    assert select(rows, "char", "kind", "dwell", "flight", "time") == [
        ("a", "plain", 80.0, None, None),
        ("b", "plain", 80.0, 120.0, 200.0),
        (" ", "layer-tap", None, 320.0, 200.0),  # from b's keyup to e's keydown, for both pairs
        ("e", "plain", 80.0, 320.0, 200.0),
        ("-", "plain", 80.0, 120.0, 200.0),
        ("d", "plain", None, 120.0, 200.0),
        ("-", "macro", None, None, None),
        (">", "macro", None, None, None),
        ("f", "plain", 550.0, None, None),  # its keyup came after the auto-repeat, which has no row
        ("\n", "combo", None, None, None),
        ("g", "plain", 80.0, None, None),
    ]
