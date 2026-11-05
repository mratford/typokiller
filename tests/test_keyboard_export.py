import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from typokiller.app import SCHEMA
from typokiller.keyboard_export import export_keyboards, main, open_read_only, read_settings_file

from keybr_recordings import KEYBR_FIXTURES

SWEEP_LAYOUTS = Path(__file__).parent / "fixtures"  # the Board fixtures of test_app.py

SETTINGS = """\
[keymaps.Sweep.QWERTY]
layers = ["Base", "Sym", "Nav", "Stack", "Num"]

[keymaps.Q4.QWERTY]
layers = ["Base", "Fn"]
"""


def fixture_text(*parts):
    return SWEEP_LAYOUTS.joinpath(*parts).read_text()


def keybr_export(name):
    return json.loads((KEYBR_FIXTURES / "keyboards" / name).read_text())


def add_vil(db, board, vil):
    db.execute("INSERT INTO keymap_version VALUES (?, ?, ?)", (hashlib.sha256(vil.encode()).hexdigest(), board, vil))


@pytest.fixture
def db_path(tmp_path):
    """A typokiller database with the Boards of keybr's import fixture: the Sweep (QWERTY, then
    free-range), the Sofle and the Q4. It is written with direct INSERTs, as the server would
    store them, so that the export does not need the server."""
    path = tmp_path / "typokiller.db"
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        for id, name, vial in [(1, "Sweep", "sweep"), (2, "Sofle", "sofle"), (3, "Q4", "q4")]:
            db.execute("INSERT INTO board VALUES (?, ?, ?)", (id, name, fixture_text("boards", vial, "vial.json")))
        for board, vil in [(1, "ferris_sweep_qwerty.vil"), (1, "ferris_sweep_freerange.vil"), (2, "sofle.vil"), (3, "q4.vil")]:
            add_vil(db, board, fixture_text("vil", vil))
    db.close()
    return path


@pytest.fixture
def settings_path(db_path):
    path = db_path.with_name("typokiller.toml")
    path.write_text(SETTINGS)
    return path


def exported(db_path, settings_path):
    db = open_read_only(db_path)
    try:
        return export_keyboards(db, read_settings_file(settings_path))
    finally:
        db.close()


def without_time(export):
    return {name: value for name, value in export.items() if name != "exportedAt"}


def test_the_export_matches_keybrs_initial_import_fixture(db_path, settings_path):
    export = exported(db_path, settings_path)

    assert without_time(export) == without_time(keybr_export("initial.json"))
    assert datetime.fromisoformat(export["exportedAt"]).utcoffset() == timedelta(0)
    assert export["exportedAt"].endswith("Z")
    for board in export["boards"]:
        for keymap in board["keymaps"]:
            assert hashlib.sha256(keymap["vil"].encode()).hexdigest() == keymap["sourceHash"]


def test_after_a_new_vial_json_a_new_vil_and_new_layer_names_the_export_matches_keybrs_updated_fixture(db_path, settings_path):
    updated = keybr_export("updated.json")
    sweep = updated["boards"][0]
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE board SET vial = ? WHERE name = 'Sweep'", (sweep["vial"],))
        add_vil(db, 1, sweep["keymaps"][2]["vil"])
    db.close()
    settings_path.write_text(SETTINGS.replace('"Sym"', '"Symbols"'))

    assert without_time(exported(db_path, settings_path)) == without_time(updated)


def test_the_vil_and_vial_texts_are_exported_exactly_as_stored(db_path, settings_path):
    # A .vil uid can be larger than JavaScript's safe integers, so the text must not be parsed and written again.
    odd = fixture_text("vil", "sofle.vil").replace('{"version": 1,', '{ "version":   1,')
    assert '"uid": 13865123068767927988' in odd
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE keymap_version SET vil = ? WHERE board = 2", (odd,))
    db.close()
    sofle = exported(db_path, settings_path)["boards"][1]
    assert sofle["vial"] == fixture_text("boards", "sofle", "vial.json")
    assert sofle["keymaps"][0]["vil"] == odd


def test_the_command_writes_the_file_and_changes_neither_the_database_nor_the_settings(db_path, settings_path, capsys):
    before = db_path.read_bytes(), settings_path.read_bytes()
    output = db_path.with_name("keyboards.json")

    main([str(output), "--db", str(db_path)])

    assert without_time(json.loads(output.read_text())) == without_time(keybr_export("initial.json"))
    assert (db_path.read_bytes(), settings_path.read_bytes()) == before
    assert sorted(p.name for p in db_path.parent.iterdir()) == ["keyboards.json", "typokiller.db", "typokiller.toml"]
    assert "3 keyboards" in capsys.readouterr().out


def test_with_no_settings_file_there_are_no_layer_names_and_no_file_is_made(db_path, tmp_path):
    output = tmp_path / "keyboards.json"

    main([str(output), "--db", str(db_path)])

    assert not db_path.with_name("typokiller.toml").exists()
    export = json.loads(output.read_text())
    assert [k["layers"] for b in export["boards"] for k in b["keymaps"]] == [[], [], [], []]


def test_the_settings_can_be_given_with_settings(db_path, tmp_path):
    other = tmp_path / "other.toml"
    other.write_text(SETTINGS)
    output = tmp_path / "keyboards.json"

    main([str(output), "--db", str(db_path), "--settings", str(other)])

    assert json.loads(output.read_text())["boards"][0]["keymaps"][0]["layers"] == ["Base", "Sym", "Nav", "Stack", "Num"]


def test_the_command_does_not_overwrite_a_file(db_path, settings_path, capsys):
    output = db_path.with_name("keyboards.json")
    output.write_text("mine")

    with pytest.raises(SystemExit) as stopped:
        main([str(output), "--db", str(db_path)])

    assert stopped.value.code != 0
    assert output.read_text() == "mine"
    assert "already exists" in capsys.readouterr().err


def test_a_database_with_no_keyboards_gives_a_message_and_no_file(tmp_path, capsys):
    db_path = tmp_path / "typokiller.db"
    with sqlite3.connect(db_path) as db:
        db.executescript(SCHEMA)
    db.close()
    output = tmp_path / "keyboards.json"

    with pytest.raises(SystemExit) as stopped:
        main([str(output), "--db", str(db_path)])

    assert stopped.value.code != 0
    assert not output.exists()
    assert "no keyboards" in capsys.readouterr().err


def test_a_missing_database_gives_a_message_and_no_file(tmp_path, capsys):
    output = tmp_path / "keyboards.json"

    with pytest.raises(SystemExit):
        main([str(output), "--db", str(tmp_path / "missing.db")])

    assert not output.exists()
    assert not (tmp_path / "missing.db").exists()
    assert "no database" in capsys.readouterr().err.lower()


def test_with_no_db_the_command_reads_the_service_database(db_path, settings_path, tmp_path, monkeypatch):
    monkeypatch.setattr("typokiller.service.data_folder", lambda: db_path.parent)
    output = tmp_path / "out" / "keyboards.json"
    output.parent.mkdir()

    main([str(output)])

    assert len(json.loads(output.read_text())["boards"]) == 3
