import pytest
import polars as pl

from typokiller.analysis import rank_units
from typokiller.keybr_analysis import ANALYSIS, exclusions, native_scores, observations, units
from typokiller.recording import read_snapshot

from keybr_snapshot import all_scenarios_snapshot, build_snapshot, scenario_snapshot, scenarios, typing_records

E, C = "error", "correct"

# The expected (position, char, status, fix_ms, time) of each observation of each fixture scenario,
# worked out by hand from the records in v1.json and the rules of keybr-input-v1.
EXPECTED = {
    "ordinary": [(0, "a", C, None, None)] + [(p, c, C, None, 200.0) for p, c in enumerate("abc abc abc") if p],
    # x and y are rejected at position 0, then deleted; a is accepted (and forgiven) at 900.
    "multiple-wrong-and-backspace": [(0, "a", E, 800.0, None), (1, "b", C, None, 200.0), (2, "c", C, None, 200.0)],
    # a and b are deleted with the word and typed again: no new first inputs.
    "clear-word": [(0, "a", C, None, None)] + [(p, c, C, None, 200.0) for p, c in enumerate("abc def") if p],
    "stop-on-error": [(0, "a", E, 400.0, None), (1, "b", C, None, 200.0), (2, "c", C, None, 200.0)],
    "forgiveness": [(0, "a", E, 200.0, None), (1, "b", C, None, 200.0), (2, "c", C, None, 200.0)],
    # The space skips b and c, which are no observations; the space itself follows a skip.
    "skip-word": [(0, "a", C, None, None), (3, " ", C, None, None), (4, "d", C, None, 200.0), (5, "e", C, None, 200.0), (6, "f", C, None, 200.0)],
    # x is wrong at 0, and keybr puts a in its place: the Error stays unresolved. b, c, d become correct.
    "replaced-character-recovery": [
        (0, "a", E, None, None), (1, "b", C, None, None), (2, "c", C, None, 200.0), (3, "d", C, None, 200.0), (4, "e", C, None, 200.0),
    ],  # fmt: skip
    # keybr skips a (no real input), and b and c become correct at 1 and 2. d's press brings the skip, so d is not timed.
    "skipped-character-recovery": [(1, "b", C, None, None), (2, "c", C, None, 200.0), (3, "d", C, None, None), (4, "e", C, None, 200.0)],
    "unicode": [(0, "🍬", C, None, None), (1, "🍭", C, None, 200.0)],
    "forward-emulation-and-repeat": [(0, "o", C, None, None)],
    "reverse-emulation-and-repeat": [(0, "o", C, None, None)],
    "composition": [(0, "á", C, None, None)],
    "held-key-crossing-exercises": [(0, "a", C, None, None), (0, "b", C, None, None)],
    "release-after-navigation": [],
    "empty-focus-resets": [],
    **{f"end-{reason}": [(0, "a", C, None, None)] for reason in ["reset", "skipped", "inactivity", "focus-loss", "settings-change", "keyboard-change", "navigation"]},
}

# The expected (skipped, recovered, off_track, composed, missing_releases) of each scenario, summed over its Attempts.
EXCLUDED = {
    "multiple-wrong-and-backspace": (0, 0, 1, 0, 0),
    "stop-on-error": (0, 0, 1, 0, 0),
    "skip-word": (2, 0, 0, 0, 0),
    "replaced-character-recovery": (0, 1, 0, 0, 0),
    "skipped-character-recovery": (1, 0, 0, 0, 0),
    "composition": (0, 0, 0, 1, 0),
    **{f"end-{reason}": (0, 0, 0, 0, 1) for reason in ["reset", "skipped", "inactivity", "focus-loss", "settings-change", "keyboard-change", "navigation"]},
}

OUTCOME = ["position", "char", "status", "fix_ms", "time"]


def observed(path, columns=OUTCOME):
    return observations(read_snapshot(path)).sort("started", "attempt", "position").select(columns).rows()


def test_every_scenario_has_its_expected_table():
    assert set(EXPECTED) == set(scenarios())


@pytest.mark.parametrize("name", list(EXPECTED))
def test_each_fixture_scenario_gives_its_expected_positions_outcomes_fix_times_and_timing(tmp_path, name):
    assert observed(scenario_snapshot(tmp_path, name)) == EXPECTED[name]


@pytest.mark.parametrize("name", list(EXPECTED))
def test_each_fixture_scenario_gives_its_expected_exclusions(tmp_path, name):
    found = exclusions(read_snapshot(scenario_snapshot(tmp_path, name)))
    counts = ["skipped", "recovered", "off_track", "composed", "missing_releases"]
    assert tuple(found[c].sum() for c in counts) == EXCLUDED.get(name, (0, 0, 0, 0, 0))


def test_every_observation_names_the_analysis_method_and_first_time_correct_matches_the_status(tmp_path):
    found = observations(read_snapshot(scenario_snapshot(tmp_path, "forgiveness")))

    assert set(found["analysis"]) == {ANALYSIS} == {"keybr-input-v1"}
    assert found["first_time_correct"].to_list() == [False, True, True]


def test_attempts_with_only_input_events_are_timed_from_the_inputs(tmp_path):
    found = observations(read_snapshot(scenario_snapshot(tmp_path, "ordinary")))

    assert set(found["timing_source"]) == {"input"}
    assert found["dwell"].null_count() == found.height


def test_the_press_of_each_input_gives_its_dwell(tmp_path):
    # forward emulation: the synthetic input comes from its own keydown; reverse: from the keydown before the input.
    for name in ["forward-emulation-and-repeat", "reverse-emulation-and-repeat"]:
        assert observed(scenario_snapshot(tmp_path, name), ["timing_source", "dwell"]) == [("key press", 100.0)]
    # A release after the end of the Attempt still counts; a release that never came gives no dwell.
    # keymap=None keeps keybr's fixture keyboard, which has no .vil: on the free-range Sweep, b is
    # a mod-tap, which has no dwell.
    assert observed(scenario_snapshot(tmp_path, "held-key-crossing-exercises", keymap=None), ["dwell"]) == [(150.0,), (200.0,)]
    assert observed(scenario_snapshot(tmp_path, "held-key-crossing-exercises"), ["inferred_kind", "dwell"]) == [
        ("plain", 150.0),
        ("mod-tap", None),
    ]
    assert observed(scenario_snapshot(tmp_path, "end-reset"), ["dwell"]) == [(None,)]


def test_composed_input_is_counted_but_never_timed(tmp_path):
    path = scenario_snapshot(tmp_path, "composition")
    assert observed(path, ["dwell", "time"]) == [(None, None)]


def hand_built(tmp_path, text, actions, keymap=("Sweep", "free-range")):
    return build_snapshot(tmp_path / "typed.sqlite", typing_records(text, actions), keymap=keymap)


def test_key_presses_give_dwell_flight_and_time(tmp_path):
    path = hand_built(tmp_path, "ea", [
        ("down", "e", "KeyE", 0), ("input", "e", 0), ("up", "KeyE", 80),
        ("down", "a", "KeyA", 200), ("input", "a", 200), ("up", "KeyA", 260),
    ])  # fmt: skip

    assert observed(path, ["char", "time", "dwell", "flight", "timing_source", "pair"]) == [
        ("e", None, 80.0, None, "key press", None),
        ("a", 200.0, 60.0, 120.0, "key press", "ea"),
    ]


def test_an_input_whose_press_is_not_clear_is_counted_as_ambiguous_and_not_timed(tmp_path):
    # Two keys that type a are down before the first a; the second a has no keydown of its own.
    path = hand_built(tmp_path, "eaa", [
        ("down", "e", "KeyE", 0), ("input", "e", 0), ("up", "KeyE", 50),
        ("down", "a", "KeyA", 200), ("down", "a", "KeyQ", 210), ("input", "a", 220), ("up", "KeyA", 260), ("up", "KeyQ", 270),
        ("input", "a", 400),
    ])  # fmt: skip

    assert observed(path, ["char", "status", "time", "dwell"]) == [("e", C, None, 50.0), ("a", C, None, None), ("a", C, None, None)]
    assert exclusions(read_snapshot(path))["ambiguous"].to_list() == [2]


def test_firmware_key_kinds_are_inferred_from_the_attempts_saved_keymap(tmp_path):
    # On the free-range Sweep, c is a mod-tap (Shift when held). The firmware sends its keydown
    # and keyup together at the release, so it has no dwell, and the time is shared out over it.
    path = hand_built(tmp_path, "eca", [
        ("down", "e", "KeyE", 0), ("input", "e", 0), ("up", "KeyE", 60),
        ("down", "c", "KeyC", 250), ("input", "c", 250), ("up", "KeyC", 255),
        ("down", "a", "KeyA", 400), ("input", "a", 400), ("up", "KeyA", 450),
    ])  # fmt: skip

    assert observed(path, ["char", "inferred_kind", "inferred_layer", "inferred_key", "inferred_event", "dwell", "time"]) == [
        ("e", "plain", 0, "5,2", "typed", 60.0, None),
        ("c", "mod-tap", 0, "2,3", "typed", None, 200.0),
        ("a", "plain", 0, "5,3", "typed", 50.0, 200.0),
    ]


def test_a_wrong_input_is_charged_to_the_intended_character_and_later_wrong_inputs_are_off_track(tmp_path):
    path = hand_built(tmp_path, "ea", [("input", "e", 0), ("input", "x", 100), ("input", "y", 200)])

    # The Error has a pair too, so that pairs have error rates.
    assert observed(path, ["position", "char", "status", "fix_ms", "pair"]) == [(0, "e", C, None, None), (1, "a", E, None, "ea")]
    assert exclusions(read_snapshot(path))["off_track"].to_list() == [1]


def test_units_give_each_character_and_pair_for_the_weakness_model(tmp_path):
    found = units(observations(read_snapshot(scenario_snapshot(tmp_path, "forgiveness"))))

    assert found.sort("position", "unit").select("unit", "status", "fix_ms", "time").rows() == [
        ("a", E, 200.0, None),
        ("ab", C, None, 200.0),
        ("b", C, None, 200.0),
        ("bc", C, None, 200.0),
        ("c", C, None, 200.0),
    ]
    ranked = rank_units(found, {"model": "recent-cost-v1", "min_seen": 1})
    assert ranked.select("unit", "cost", "seen").rows() == [("ab", 200.0, 1), ("b", 200.0, 1), ("bc", 200.0, 1), ("c", 200.0, 1)]


def test_an_unresolved_error_keeps_a_missing_fix_time_in_the_units(tmp_path):
    found = units(observations(read_snapshot(scenario_snapshot(tmp_path, "replaced-character-recovery"))))

    assert found.filter(pl.col("unit") == "a").select("status", "fix_ms").rows() == [(E, None)]


def test_native_scores_are_keybrs_own_speed_accuracy_and_score(tmp_path):
    path = all_scenarios_snapshot(tmp_path / "all.sqlite")
    found = native_scores(read_snapshot(path)).sort("attempt")

    expected = [r for s in scenarios().values() for r in s["expected"]["results"]]
    # Only completed Attempts have a native result. The renamed ids keep the scenario order.
    assert found.height == len(expected)
    for row, result in zip(found.iter_rows(named=True), expected):
        assert row["accuracy"] == pytest.approx(result["accuracy"])
        assert row["score"] == pytest.approx(result["score"])
        assert row["speed"] == pytest.approx(result["result"]["speed"])
        assert row["result_accepted"] == result["accepted"]
    assert set(found["measure"]) == {"keybr"}


def test_unreadable_attempts_give_no_observations(tmp_path):
    from keybr_snapshot import records

    path = build_snapshot(tmp_path / "no-start.sqlite", records("ordinary")[1:])
    assert observations(read_snapshot(path)).is_empty()
