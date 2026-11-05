import json
import sqlite3
from datetime import UTC, datetime

import polars as pl
import pytest

from typokiller.recording import NewerRecordings, RecordingError, read_recordings

from keybr_recordings import (
    build_recordings,
    change,
    keyboard_export,
    keymap_snapshot,
    records,
    scenario_recordings,
    scenarios,
    sha256,
)

STATUS = ["attempt", "status", "end_reason", "has_start", "has_end", "missing_releases"]


def attempt_rows(path, columns=STATUS):
    return read_recordings(path).attempts.sort("attempt").select(columns).rows()


@pytest.mark.parametrize("name", list(scenarios()))
def test_every_fixture_scenario_reads_with_one_row_per_record(tmp_path, name):
    found = read_recordings(scenario_recordings(tmp_path, name))

    expected = records(name)
    for table, kind in [(found.original_events, "original"), (found.processed_events, "processed"), (found.states, "state")]:
        assert table.height == sum(r["type"] == kind for r in expected)
    assert found.attempts.height == len({r["attemptId"] for r in expected})
    assert set(found.attempts["status"]) <= {"complete", "ended early"}


def test_a_completed_attempt_is_complete_and_keeps_keybrs_result(tmp_path):
    found = read_recordings(scenario_recordings(tmp_path, "ordinary")).attempts.row(0, named=True)

    assert found["status"] == "complete" and found["end_reason"] == "completed"
    assert found["text"] == "abc abc abc"
    assert (found["speed"], found["errors"], found["length"], found["time"], found["result_accepted"]) == (330, 0, 11, 2000, True)
    # The wall-clock time of the first original event: timeOrigin 1700000000000 + timeStamp 100.
    assert found["started"] == datetime(2023, 11, 14, 22, 13, 20, 100000, tzinfo=UTC)
    assert found["keybr_layout"] == "en-us"
    assert (found["source"], found["schema_version"]) == ("keybr", 1)


def test_an_attempt_names_its_imported_keyboard_and_layout(tmp_path):
    path = scenario_recordings(tmp_path, "ordinary", keymap=("Sweep", "QWERTY"))
    found = read_recordings(path)

    sweep = keymap_snapshot(keyboard_export(), "Sweep", "QWERTY")
    attempt = found.attempts.row(0, named=True)
    assert (attempt["board_id"], attempt["keymap_id"], attempt["keymap_version"]) == ("Sweep", "Sweep/QWERTY", sweep["version"])
    assert attempt["letter_layout"] == "QWERTY"
    keyboard = found.keyboards.filter(pl.col("keymap_version") == sweep["version"]).row(0, named=True)
    assert keyboard["vil"] == sweep["configuration"]["vil"]
    assert keyboard["vil_hash"] == sha256(keyboard["vil"])
    assert keyboard["layers"] == ["Base", "Sym", "Nav", "Stack", "Num"]
    assert keyboard["vial"] == keyboard_export()["boards"][0]["vial"]
    assert keyboard["imported_at"] == datetime(2026, 11, 1, 9, 30, tzinfo=UTC)
    # Every keymap snapshot of the import: 2 on the Sweep, 1 on the Sofle and 1 on the Q4.
    assert found.keyboards.height == 4


def test_a_key_held_across_two_exercises_gives_its_late_release_to_its_own_attempt(tmp_path):
    path = scenario_recordings(tmp_path, "held-key-crossing-exercises")
    found = read_recordings(path)

    assert attempt_rows(path) == [
        ("00000000-0000-4000-8000-000000000001", "complete", "completed", True, True, 0),
        ("00000000-0000-4000-8000-000000000002", "complete", "completed", True, True, 0),
    ]
    ups = found.original_events.filter(pl.col("event_type") == "keyup").sort("attempt")
    assert ups.select("attempt", "code", "press_sequence").rows() == [
        ("00000000-0000-4000-8000-000000000001", "KeyA", 1),
        ("00000000-0000-4000-8000-000000000002", "KeyB", 1),
    ]


def test_a_release_after_leaving_the_page_is_kept_and_the_attempt_ended_early(tmp_path):
    assert attempt_rows(scenario_recordings(tmp_path, "release-after-navigation")) == [
        ("00000000-0000-4000-8000-000000000001", "ended early", "navigation", True, True, 0),
    ]


@pytest.mark.parametrize(
    "name", ["end-reset", "end-skipped", "end-inactivity", "end-focus-loss", "end-settings-change", "end-keyboard-change", "end-navigation"]
)
def test_every_end_reason_is_kept_and_a_key_never_released_is_a_missing_release(tmp_path, name):
    assert attempt_rows(scenario_recordings(tmp_path, name)) == [
        ("00000000-0000-4000-8000-000000000001", "ended early", name.removeprefix("end-"), True, True, 1),
    ]


def test_resets_with_no_typing_make_no_attempt(tmp_path):
    found = read_recordings(scenario_recordings(tmp_path, "empty-focus-resets"))

    assert found.attempts.is_empty()


def test_an_attempt_with_a_gap_in_its_records_is_incomplete_and_counts_its_gaps(tmp_path):
    found = [r for r in records("ordinary") if r["sequence"] not in (4, 5)]
    path = build_recordings(tmp_path / "gap.sqlite", found)

    (row,) = read_recordings(path).attempts.select("status", "sequence_gaps", "broken_links").rows()
    # Records 4 and 5 are lost, and the state record 6 names the lost processed record 5.
    assert row == ("incomplete", 2, 1)


def test_an_attempt_with_no_end_record_is_incomplete_and_none_is_invented(tmp_path):
    path = build_recordings(tmp_path / "no-end.sqlite", records("ordinary")[:-1])

    (row,) = attempt_rows(path, ["status", "has_end", "end_reason", "speed"])
    assert row == ("incomplete", False, None, None)


def test_an_attempt_with_no_start_record_cannot_be_read(tmp_path):
    path = build_recordings(tmp_path / "no-start.sqlite", records("ordinary")[1:])

    (row,) = attempt_rows(path, ["status", "has_start", "text"])
    assert row == ("unreadable", False, None)


def test_the_interrupted_and_incomplete_flags_are_kept(tmp_path):
    attempt = records("end-reset")[0]["attemptId"]
    interrupted = build_recordings(tmp_path / "a.sqlite", records("end-reset")[:-1], recovery={attempt: {"interrupted": True}})
    incomplete = build_recordings(tmp_path / "b.sqlite", records("ordinary"), recovery={attempt: {"incomplete": True}})

    assert attempt_rows(interrupted, ["status", "interrupted", "incomplete"]) == [("interrupted", True, False)]
    assert attempt_rows(incomplete, ["status", "interrupted", "incomplete"]) == [("incomplete", False, True)]


def test_a_state_that_does_not_follow_the_state_before_is_counted(tmp_path):
    found = records("ordinary")
    state = next(r for r in found if r["type"] == "state" and r["sequence"] == 6)
    state = state | {"before": state["before"] | {"typo": True}}
    path = build_recordings(tmp_path / "jump.sqlite", [state if r["sequence"] == 6 else r for r in found])

    assert attempt_rows(path, ["status", "discontinuous_states"]) == [("incomplete", 1)]


def test_the_record_tables_keep_each_records_fields_and_its_json(tmp_path):
    found = read_recordings(scenario_recordings(tmp_path, "forward-emulation-and-repeat"))

    keydown = found.original_events.filter(pl.col("sequence") == 1).row(0, named=True)
    assert (keydown["event_type"], keydown["key"], keydown["code"], keydown["repeat"], keydown["time_stamp"]) == ("keydown", "s", "KeyS", False, 100)
    synthetic = found.processed_events.filter(pl.col("sequence") == 3).row(0, named=True)
    assert (synthetic["original_sequence"], synthetic["synthetic"], synthetic["input_type"], synthetic["char"]) == (1, True, "appendChar", "o")
    state = found.states.row(0, named=True)
    assert (state["processed_sequence"], state["effect"], state["feedback"], state["cursor_before"], state["cursor_after"]) == (3, "accepted", 0, 0, 1)
    assert json.loads(state["after"])["steps"] == [{"timeStamp": 100, "codePoint": 111, "timeToType": 100, "typo": False}]
    assert json.loads(state["json"]) == next(r for r in records("forward-emulation-and-repeat") if r["sequence"] == 4)
    for table in (found.keyboards, found.attempts, found.original_events, found.processed_events, found.states):
        assert {"source", "schema_version", "file"} <= set(table.columns)
        assert set(table["file"]) <= {str(tmp_path / "forward-emulation-and-repeat.sqlite")}


def test_reading_changes_nothing_in_the_file_or_its_folder(tmp_path):
    path = scenario_recordings(tmp_path, "ordinary")
    before = path.read_bytes()

    read_recordings(path)

    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["ordinary.sqlite"]


def test_a_version_1_database_reads_without_import_dates(tmp_path):
    path = scenario_recordings(tmp_path, "ordinary", version=1)

    found = read_recordings(path)

    assert found.attempts["status"].to_list() == ["complete"]
    assert found.keyboards["imported_at"].to_list() == [None] * 4


def raises(path, message):
    with pytest.raises(RecordingError, match=message):
        read_recordings(path)


def test_a_missing_file_or_a_file_that_is_not_sqlite_gives_an_error(tmp_path):
    raises(tmp_path / "missing.sqlite", "no file")
    assert not (tmp_path / "missing.sqlite").exists()
    (tmp_path / "notes.txt").write_text("not a database " * 100)
    raises(tmp_path / "notes.txt", "not an SQLite")


def test_a_newer_database_version_says_to_update_typokiller(tmp_path):
    path = scenario_recordings(tmp_path, "ordinary")
    change(path, "PRAGMA user_version = 3")
    with pytest.raises(NewerRecordings, match="database version 3.*Update typokiller"):
        read_recordings(path)
    change(path, "PRAGMA user_version = 0")
    raises(path, "database version 0")


def test_the_checks_and_every_read_are_in_one_transaction(tmp_path, monkeypatch):
    path = scenario_recordings(tmp_path, "ordinary")
    statements = []
    connect = sqlite3.connect

    def traced(*args, **kwargs):
        db = connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    monkeypatch.setattr(sqlite3, "connect", traced)
    read_recordings(path)

    assert statements[0] == "BEGIN" and statements[1] == "PRAGMA user_version" and statements[-1] == "COMMIT"
    assert any("FROM records" in s for s in statements[1:-1])


def test_while_keybr_writes_the_reader_sees_only_what_keybr_has_committed(tmp_path):
    path = scenario_recordings(tmp_path, "ordinary")
    keybr = sqlite3.connect(path)
    keybr.execute("PRAGMA journal_mode=WAL")
    keybr.execute("BEGIN IMMEDIATE")
    keybr.execute("INSERT INTO attempts (id) VALUES ('00000000-0000-4000-8000-0000000000ff')")

    assert read_recordings(path).attempts.height == 1
    keybr.commit()
    assert read_recordings(path).attempts.height == 2
    keybr.close()


def test_an_unsupported_contract_version_gives_an_error(tmp_path):
    path = scenario_recordings(tmp_path, "ordinary")
    change(path, "UPDATE metadata SET value = '2' WHERE key = 'schemaVersion'")
    raises(path, "schemaVersion 2")


def test_a_record_with_another_schema_version_gives_an_error(tmp_path):
    found = records("ordinary")
    path = build_recordings(tmp_path / "v2.sqlite", [r | {"schemaVersion": 2} if r["sequence"] == 3 else r for r in found])
    raises(path, "schema version 2")


def test_a_missing_table_or_column_gives_an_error(tmp_path):
    path = scenario_recordings(tmp_path, "ordinary")
    change(path, "DROP TABLE keyboard_sources")
    raises(path, "keyboard_sources")
    path = scenario_recordings(tmp_path, "unicode")
    change(path, "ALTER TABLE attempts DROP COLUMN interrupted")
    raises(path, "interrupted")


def test_a_record_whose_json_does_not_parse_gives_an_error(tmp_path):
    path = scenario_recordings(tmp_path, "ordinary")
    change(path, "UPDATE records SET json = '{\"type\": ' WHERE sequence = 2")
    raises(path, "sequence 2")
