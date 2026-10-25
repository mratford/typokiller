import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from typokiller.app import create_app
from typokiller.keymap import qmk_settings
from typokiller.sources import ascii_v1


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def settings_path(tmp_path):
    return tmp_path / "typokiller.toml"


@pytest.fixture
def client(db_path, settings_path):
    return TestClient(create_app(db_path, settings_path))


SETTINGS = {"typing": {"wrong_key_mode": "keep typing"}, "passages": {"max_dropped": 0.05, "min_length": 20}}
ATTEMPT = {"passage": 1, "settings": SETTINGS}  # the built-in Passage


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


def test_batch_stores_key_events_and_the_attempt_passage_and_settings_and_ignores_a_resend(client, db_path):
    session = start_session(client)
    batch = {"events": [key_event(0), key_event(1, type="keyup")], "attempts": {0: ATTEMPT}}

    response = client.post(f"/api/sessions/{session}/batch", json=batch)
    client.post(f"/api/sessions/{session}/batch", json=batch)

    assert response.status_code == 204
    assert rows(db_path, "SELECT * FROM key_event ORDER BY seq") == [
        (session, 0, 0, 1000.5, "keydown", "KeyA", "a", 0, 0, 0, 0, 0),
        (session, 1, 0, 1001.5, "keyup", "KeyA", "a", 0, 0, 0, 0, 0),
    ]
    assert rows(db_path, "SELECT passage, settings ->> '$.typing.wrong_key_mode' FROM attempt") == [(1, "keep typing")]


def test_attempt_is_abandoned_unless_a_batch_finishes_it(client, db_path):
    session = start_session(client)
    url = f"/api/sessions/{session}/batch"
    typed = {"events": [key_event(0, attempt=0), key_event(1, attempt=1)], "attempts": {0: ATTEMPT, 1: ATTEMPT}}

    client.post(url, json=typed)
    client.post(url, json={"finished": [0]})
    client.post(url, json=typed)  # a late resend must not undo the finish

    assert rows(db_path, "SELECT ord, finished FROM attempt ORDER BY ord") == [(0, 1), (1, 0)]


def test_a_missing_settings_file_is_created_with_defaults_and_comments(client, settings_path):
    settings = client.get("/api/settings").json()

    assert settings == SETTINGS
    assert "# " in settings_path.read_text()


def test_settings_are_read_again_after_the_file_is_edited_and_missing_tables_are_added(client, settings_path):
    client.get("/api/settings")
    settings_path.write_text('[typing]\nwrong_key_mode = "locked until fixed"\n')

    assert client.get("/api/settings").json() == {**SETTINGS, "typing": {"wrong_key_mode": "locked until fixed"}}
    assert "min_length = 20" in settings_path.read_text()


def test_saving_settings_keeps_comments_and_formatting(client, settings_path):
    passages = "\n[passages]\nmax_dropped = 0.05\nmin_length = 20\n"
    settings_path.write_text('# My notes\n\n[typing]\n# a comment\nwrong_key_mode   =  "keep typing"  # why\n' + passages)

    response = client.put("/api/settings", json={"typing": {"wrong_key_mode": "locked until fixed"}})

    assert response.status_code == 204
    assert settings_path.read_text() == (
        '# My notes\n\n[typing]\n# a comment\nwrong_key_mode   =  "locked until fixed"  # why\n' + passages
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


def test_ascii_v1_makes_typeable_ascii_and_counts_what_it_dropped():
    assert ascii_v1("“Café” – naïve… ‘ok’—fine 😀") == ("\"Cafe\" - naive... 'ok'-fine ", 1)


BOOK = (
    "The Project Gutenberg eBook of Pride and Prejudice\r\n\r\nTitle: Pride and Prejudice\r\n\r\nAuthor: Jane Austen\r\n"
    "\r\n*** START OF THE PROJECT GUTENBERG EBOOK PRIDE AND PREJUDICE ***\r\n\r\n"
    "CHAPTER I.\r\n\r\n"
    "It is a truth universally acknowledged, that a single man in\r\npossession of a good fortune, must be in want of a wife.\r\n\r\n"
    "“My dear Mr. Bennet,” said his lady to him one day, “have you heard\r\nthat Netherfield Park is let at last?”\r\n\r\n"
    "Ἐν ἀρχῇ ἦν ὁ λόγος, said the vicar.\r\n\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK PRIDE AND PREJUDICE ***\r\n\r\nThe licence.\r\n"
)


@pytest.fixture
def gutenberg(monkeypatch):
    """Serves BOOK as book 1342 instead of downloading it, and records the URLs asked for."""
    urls = []

    def fetch(url):
        urls.append(url)
        return BOOK.encode()

    monkeypatch.setattr("typokiller.app.fetch", fetch)
    return urls


def import_book(client):
    return client.post("/api/gutenberg", json={"number": 1342, "title": "Pride and Prejudice"}).json()


def test_a_gutenberg_book_keeps_its_text_and_each_kept_paragraph_is_a_passage(client, db_path, gutenberg):
    imported = import_book(client)

    assert gutenberg == ["https://www.gutenberg.org/cache/epub/1342/pg1342.txt"]
    assert imported == {"source": imported["source"], "passages": 2, "skipped": 2}
    assert rows(db_path, "SELECT title, text FROM source") == [("Pride and Prejudice", BOOK)]
    assert rows(db_path, "SELECT ord, text, normaliser FROM passage WHERE source IS NOT NULL ORDER BY ord") == [
        (0, "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.", "ascii-v1"),
        (1, '"My dear Mr. Bennet," said his lady to him one day, "have you heard that Netherfield Park is let at last?"', "ascii-v1"),
    ]


def bookmark(client, source, at):
    served = client.put(f"/api/sources/{source}/bookmark", json={"at": at}).json()
    return served["source"] and served["source"]["at"], [p["id"] for p in served["passages"]]


def test_passages_are_served_in_order_from_the_bookmark_then_the_built_in_passage(client, gutenberg):
    source = import_book(client)["source"]  # its Passages are 2 and 3; the built-in one is 1

    assert bookmark(client, source, 0) == (0, [2, 3])  # this one and the next
    assert bookmark(client, source, 1) == (1, [3, 1])
    assert bookmark(client, source, 2) == (None, [1])  # finished, so the Source is closed


def test_sources_list_the_last_opened_first_and_finished_ones_last(client, gutenberg):
    a, b, c = (import_book(client)["source"] for _ in range(3))
    bookmark(client, a, 2)  # finished
    bookmark(client, b, 1)

    assert client.get("/api/sources").json() == [
        {"id": b, "title": "Pride and Prejudice", "at": 1, "total": 2},
        {"id": c, "title": "Pride and Prejudice", "at": 0, "total": 2},
        {"id": a, "title": "Pride and Prejudice", "at": 2, "total": 2},
    ]


CATALOGUE = """\
Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves
1342,Text,1998-06-01,Pride and Prejudice,en,"Austen, Jane, 1775-1817",,,
19337,Sound,2006-09-21,Pride and Prejudice,en,"Austen, Jane, 1775-1817",,,
2701,Text,2001-07-01,"Moby Dick; Or,
The Whale",en,"Melville, Herman, 1819-1891",,,
"""


def search(client, q):
    return client.get("/api/gutenberg", params={"q": q})


def test_the_catalogue_is_searched_by_title_and_author_or_by_book_number_or_url(client, db_path):
    db_path.with_name("pg_catalog.csv").write_text(CATALOGUE)
    pride = {"number": 1342, "title": "Pride and Prejudice", "authors": "Austen, Jane, 1775-1817"}

    assert search(client, "austen PRIDE").json() == [pride]  # only books that are text
    assert search(client, "whale").json() == [
        {"number": 2701, "title": "Moby Dick; Or, The Whale", "authors": "Melville, Herman, 1819-1891"}
    ]
    assert search(client, " 1342 ").json() == [pride]
    assert search(client, "https://www.gutenberg.org/ebooks/1342").json() == [pride]
    assert search(client, "99999").json() == [{"number": 99999, "title": "Gutenberg book 99999", "authors": ""}]


def test_searching_before_the_catalogue_is_downloaded_says_so(client):
    assert search(client, "austen").status_code == 503
