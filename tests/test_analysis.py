from typokiller.analysis import Keydown, first_error_v1

BS = "Backspace"


def keys(*pressed):
    """Keydowns 100 ms apart. Each item is a key value, or a Keydown for a key with Ctrl or Meta."""
    return [p._replace(t=100 * i) if isinstance(p, Keydown) else Keydown(100 * i, p) for i, p in enumerate(pressed)]


def aligned(passage, pressed, mode=None):
    """(position, status, first) for each keydown."""
    return [(r["position"], r["status"], r["first"]) for r in first_error_v1(passage, mode, pressed)]


def test_an_error_is_charged_to_the_intended_character_and_its_fix_time_runs_to_the_right_character():
    pressed = keys("Shift", "c", "x", BS, Keydown(0, "a", ctrl=True), "a", "Enter", "t")

    assert aligned("cat", pressed) == [
        (None, "ignored", False),
        (0, "correct", True),
        (1, "error", True),
        (None, "off-track", False),
        (None, "ignored", False),  # Ctrl-a
        (1, "correct", False),  # ends the Fix
        (None, "ignored", False),  # Enter where the Passage has no newline
        (2, "correct", True),
    ]
    assert [r["fix_ms"] for r in first_error_v1("cat", None, pressed)] == [None, None, 300, None, None, None, None, None]


def test_backspace_past_an_error_keeps_the_retyped_characters_off_track_until_the_errors_position_is_right():
    pressed = keys("c", "a", "x", "y", BS, BS, BS, BS, "c", "a", "t", "s")

    assert aligned("cats", pressed) == [
        (0, "correct", True),
        (1, "correct", True),
        (2, "error", True),
        (3, "off-track", True),  # first typed while off-track, so it does not count later
        (None, "off-track", False),
        (None, "off-track", False),
        (None, "off-track", False),
        (None, "off-track", False),  # back over the correct "c" and "a"
        (0, "off-track", False),
        (1, "off-track", False),
        (2, "correct", False),  # ends the Fix
        (3, "correct", False),
    ]
    assert first_error_v1("cats", None, pressed)[2]["fix_ms"] == 800


def test_locked_until_fixed_keeps_the_cursor_at_the_error():
    pressed = keys("c", "x", "y", "a", "t")

    assert aligned("cat", pressed, "locked until fixed") == [
        (0, "correct", True),
        (1, "error", True),
        (1, "off-track", False),
        (1, "correct", False),  # ends the Fix
        (2, "correct", True),
    ]


def test_a_retyped_character_is_not_first():
    assert aligned("cat", keys("c", "a", BS, "a", "t")) == [
        (0, "correct", True),
        (1, "correct", True),
        (None, "ignored", False),  # Backspace with no Error open
        (1, "correct", False),
        (2, "correct", True),
    ]


def test_enter_at_a_newline_is_typed_and_the_filled_in_indentation_is_skipped():
    assert aligned("x:\n  y", keys("x", ":", "Enter", "y")) == [
        (0, "correct", True),
        (1, "correct", True),
        (2, "correct", True),
        (5, "correct", True),
    ]
