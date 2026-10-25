import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from typokiller.app import create_app
from typokiller.keymap import qmk_settings


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def settings_path(tmp_path):
    return tmp_path / "typokiller.toml"


@pytest.fixture
def client(db_path, settings_path):
    return TestClient(create_app(db_path, settings_path))


SETTINGS = {"typing": {"wrong_key_mode": "keep typing"}}


# The sweep-layouts repo is in the same folder as this repo, or as the repo that holds this worktree.
SWEEP_LAYOUTS = next(p / "sweep-layouts" for p in Path(__file__).parents if (p / "sweep-layouts").exists())


def add_board(client, name, vil, vial):
    vil_text = (SWEEP_LAYOUTS / "vil" / vil).read_text()
    vial_text = (SWEEP_LAYOUTS / "boards" / vial / "vial.json").read_text()
    return client.post("/api/boards", json={"name": name, "vil": vil_text, "vial": vial_text})


def key_event(seq, attempt=0, type="keydown"):
    return {
        "seq": seq,
        "attempt": attempt,
        "t": 1000.5 + seq,
        "type": type,
        "code": "KeyA",
        "key": "a",
        "shift": False,
        "ctrl": False,
        "alt": False,
        "meta": False,
        "repeat": False,
    }


def start_session(client, keymap_version="abc"):
    return client.post("/api/sessions", json={"keymap_version": keymap_version}).json()["session"]


def rows(db_path, sql):
    with sqlite3.connect(db_path) as db:
        return db.execute(sql).fetchall()


def test_batch_stores_key_events_and_the_attempt_settings_and_ignores_a_resend(client, db_path):
    session = start_session(client)
    batch = {"events": [key_event(0), key_event(1, type="keyup")], "settings": {0: SETTINGS}}

    response = client.post(f"/api/sessions/{session}/batch", json=batch)
    client.post(f"/api/sessions/{session}/batch", json=batch)

    assert response.status_code == 204
    assert rows(db_path, "SELECT * FROM key_event ORDER BY seq") == [
        (session, 0, 0, 1000.5, "keydown", "KeyA", "a", 0, 0, 0, 0, 0),
        (session, 1, 0, 1001.5, "keyup", "KeyA", "a", 0, 0, 0, 0, 0),
    ]
    assert rows(db_path, "SELECT settings ->> '$.typing.wrong_key_mode' FROM attempt") == [("keep typing",)]


def test_attempt_is_abandoned_unless_a_batch_finishes_it(client, db_path):
    session = start_session(client)
    url = f"/api/sessions/{session}/batch"
    typed = {"events": [key_event(0, attempt=0), key_event(1, attempt=1)], "settings": {0: SETTINGS, 1: SETTINGS}}

    client.post(url, json=typed)
    client.post(url, json={"finished": [0]})
    client.post(url, json=typed)  # a late resend must not undo the finish

    assert rows(db_path, "SELECT ord, finished FROM attempt ORDER BY ord") == [(0, 1), (1, 0)]


def test_a_missing_settings_file_is_created_with_defaults_and_comments(client, settings_path):
    settings = client.get("/api/settings").json()

    assert settings == {"typing": {"wrong_key_mode": "keep typing"}}
    assert "# " in settings_path.read_text()


def test_settings_are_read_again_after_the_file_is_edited(client, settings_path):
    client.get("/api/settings")
    settings_path.write_text('[typing]\nwrong_key_mode = "locked until fixed"\n')

    assert client.get("/api/settings").json() == {"typing": {"wrong_key_mode": "locked until fixed"}}


def test_saving_settings_keeps_comments_and_formatting(client, settings_path):
    settings_path.write_text('# My notes\n\n[typing]\n# a comment\nwrong_key_mode   =  "keep typing"  # why\n')

    response = client.put("/api/settings", json={"typing": {"wrong_key_mode": "locked until fixed"}})

    assert response.status_code == 204
    assert settings_path.read_text() == (
        '# My notes\n\n[typing]\n# a comment\nwrong_key_mode   =  "locked until fixed"  # why\n'
    )


def test_a_vil_is_stored_whole_by_hash_and_a_reimport_does_nothing(client, db_path):
    vil = (SWEEP_LAYOUTS / "vil" / "ferris_sweep_qwerty.vil").read_text()

    add_board(client, "Sweep", "ferris_sweep_qwerty.vil", "sweep")
    add_board(client, "Sweep", "ferris_sweep_qwerty.vil", "sweep")

    assert rows(db_path, "SELECT hash, vil FROM keymap_version") == [(hashlib.sha256(vil.encode()).hexdigest(), vil)]


def test_qmk_settings_come_from_the_vil_with_qmk_defaults_when_absent():
    vil = json.loads((SWEEP_LAYOUTS / "vil" / "ferris_sweep_qwerty.vil").read_text())

    assert qmk_settings(vil) == {"tapping_term": 200, "combo_term": 40}
    del vil["settings"]
    assert qmk_settings(vil) == {"tapping_term": 200, "combo_term": 50}


def test_each_keymap_has_its_letter_layout_and_a_session_puts_it_first(client, db_path):
    add_board(client, "Sofle", "sofle.vil", "sofle")
    sweep = add_board(client, "Sweep", "ferris_sweep_qwerty.vil", "sweep").json()["board"]
    add_board(client, "Sweep", "ferris_sweep_freerange.vil", "sweep")
    add_board(client, "Q4", "q4.vil", "q4")

    boards = client.get("/api/boards").json()["boards"]
    assert [(b["name"], [k["letter_layout"] for k in b["keymaps"]]) for b in boards] == [
        ("Sofle", ["free-range"]),
        ("Sweep", ["QWERTY", "free-range"]),
        ("Q4", ["QWERTY"]),
    ]

    free_range = boards[1]["keymaps"][1]["version"]
    start_session(client, free_range)

    assert rows(db_path, "SELECT keymap_version FROM session") == [(free_range,)]
    listed = client.get("/api/boards").json()
    assert listed["last"] == sweep
    assert [k["letter_layout"] for k in listed["boards"][1]["keymaps"]] == ["free-range", "QWERTY"]
