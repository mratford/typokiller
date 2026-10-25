import sqlite3

import pytest
from fastapi.testclient import TestClient

from typokiller.app import create_app


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


def rows(db_path, sql):
    with sqlite3.connect(db_path) as db:
        return db.execute(sql).fetchall()


def test_batch_stores_key_events_and_ignores_a_resend(client, db_path):
    session = client.post("/api/sessions").json()["session"]
    batch = {"events": [key_event(0), key_event(1, type="keyup")], "settings": {0: SETTINGS}}

    response = client.post(f"/api/sessions/{session}/batch", json=batch)
    client.post(f"/api/sessions/{session}/batch", json=batch)

    assert response.status_code == 204
    assert rows(db_path, "SELECT * FROM key_event ORDER BY seq") == [
        (session, 0, 0, 1000.5, "keydown", "KeyA", "a", 0, 0, 0, 0, 0),
        (session, 1, 0, 1001.5, "keyup", "KeyA", "a", 0, 0, 0, 0, 0),
    ]


def test_attempt_is_abandoned_unless_a_batch_finishes_it(client, db_path):
    session = client.post("/api/sessions").json()["session"]
    url = f"/api/sessions/{session}/batch"
    typed = {"events": [key_event(0, attempt=0), key_event(1, attempt=1)], "settings": {0: SETTINGS, 1: SETTINGS}}

    client.post(url, json=typed)
    client.post(url, json={"finished": [0]})
    client.post(url, json=typed)  # a late resend must not undo the finish

    assert rows(db_path, "SELECT ord, finished FROM attempt ORDER BY ord") == [(0, 1), (1, 0)]


def test_attempt_records_the_settings_it_was_typed_with(client, db_path):
    session = client.post("/api/sessions").json()["session"]
    locked = {"typing": {"wrong_key_mode": "locked until fixed"}}

    client.post(f"/api/sessions/{session}/batch", json={"events": [key_event(0)], "settings": {0: locked}})

    assert rows(db_path, "SELECT settings ->> '$.typing.wrong_key_mode' FROM attempt") == [("locked until fixed",)]


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
