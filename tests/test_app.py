import hashlib
import importlib.util
import json
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from typokiller.analysis import WEAKNESS_MODELS, attempts, keystrokes, progress, weakness
from typokiller.app import create_app
from typokiller.drawing import Heat, draw_keymap
from typokiller.drills import WORDS, pool
from typokiller.keymap import qmk_settings, read_keymap
from typokiller.lessons import GLEAM_PROJECT, Reply, run_code
from typokiller.sources import ascii_v1, code_passages, lesson_passages


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def settings_path(tmp_path):
    return tmp_path / "typokiller.toml"


class FakeProvider:
    """Answers each call with the next of `texts`, and with `text` when none are left, or
    raises `error`, and records each call. It answers only while `going` is set. Its prices are
    Haiku 5.5's on OpenRouter: $0.10 and $0.50 per million tokens."""

    def __init__(self):
        self.text = LESSON
        self.texts: list[str] = []
        self.error: Exception | None = None
        self.calls = []
        self.going = threading.Event()
        self.going.set()

    def prices(self, model):
        return 0.1e-6, 0.5e-6

    def write(self, model, messages, max_tokens, reasoning):
        self.calls.append({"model": model, "messages": messages, "max_tokens": max_tokens, "reasoning": reasoning})
        self.going.wait(5)
        if self.error:
            raise self.error
        text = self.texts.pop(0) if self.texts else self.text
        return Reply(text, {"prompt_tokens": 200, "completion_tokens": 3000}, 0.0015)


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def client(db_path, settings_path, provider):
    return TestClient(create_app(db_path, settings_path, provider))


WEAKNESS = {"model": "recent-cost-v1", "weeks": 4, "min_seen": 20}
UNLOCKING = {
    "letter_layout": "free-range",
    "start": "u n t s m , r e a _",
    "order": "o i l h d c w f g y p b v . k ' j x q z",
    "threshold": 400,
    "last": 50,
    "min_seen": 20,
}
LESSONS = {
    "prompt": "lesson-prompt-v1",
    "python_model": "anthropic/claude-haiku-5.5",
    "gleam_model": "anthropic/claude-sonnet-5.5",
    "reasoning": "low",
    "max_tokens": 8000,
    "words": 1300,
    "level": "intermediate",
    "split_lines": 40,
    "timeout": 10,
    "repairs": 2,
    "repair_tokens": 4000,
    "drop_share": 0.34,
    "cap": 5.0,
    "dollars_per_pound": 1.337,
}
SETTINGS = {
    "typing": {"wrong_key_mode": "keep typing", "show_keymap": False},
    "passages": {"max_dropped": 0.05, "min_length": 20},
    "weakness": WEAKNESS,
    "drills": {"generator": "density-v1", "weak": 2, "under_measured": 1, "min_seen": 20, "words": 40},
    "unlocking": UNLOCKING,
    "lessons": LESSONS,
    "keymaps": {},
}
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
    # The settings it was typed with include whether the Keymap was drawn under the Passage.
    assert rows(
        db_path, "SELECT passage, settings ->> '$.typing.wrong_key_mode', settings ->> '$.typing.show_keymap' FROM attempt"
    ) == [(1, "keep typing", 0)]


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


def test_settings_are_read_again_after_the_file_is_edited_and_missing_tables_and_settings_are_added(
    client, settings_path
):
    client.get("/api/settings")
    settings_path.write_text('[typing]\nwrong_key_mode = "locked until fixed"\n')

    typing = {"wrong_key_mode": "locked until fixed", "show_keymap": False}
    assert client.get("/api/settings").json() == {**SETTINGS, "typing": typing}
    assert "min_length = 20" in settings_path.read_text()


def test_saving_settings_keeps_comments_and_formatting(client, settings_path):
    rest = '\n[passages]\nmax_dropped = 0.05\nmin_length = 20\n\n[weakness]\nmodel = "recent-cost-v1"\nweeks = 4\nmin_seen = 20\n'
    rest += '\n[drills]\ngenerator = "density-v1"\nweak = 2\nunder_measured = 1\nmin_seen = 20\nwords = 40\n'
    rest += '\n[unlocking]\nletter_layout = "free-range"\nstart = "u n t s m , r e a _"\n'
    rest += 'order = "o i l h d c w f g y p b v . k \' j x q z"\nthreshold = 400\nlast = 50\nmin_seen = 20\n'
    rest += '\n[lessons]\n' + "".join(f"{k} = {json.dumps(v)}\n" for k, v in LESSONS.items())
    rest += '\n[keymaps.Sweep.QWERTY]\nlayers = ["Base", "Sym"]\n'
    rest = 'show_keymap = false\n' + rest
    settings_path.write_text('# My notes\n\n[typing]\n# a comment\nwrong_key_mode   =  "keep typing"  # why\n' + rest)

    response = client.put("/api/settings", json={"typing": {"wrong_key_mode": "locked until fixed"}})

    assert response.status_code == 204
    assert settings_path.read_text() == (
        '# My notes\n\n[typing]\n# a comment\nwrong_key_mode   =  "locked until fixed"  # why\n' + rest
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


def keys_for(vil, char):
    """(layer, key, kind) of each candidate key for a character, best first."""
    return [tuple(k) for k in read_keymap((SWEEP_LAYOUTS / "vil" / vil).read_text()).keys[char]]


def test_each_character_has_its_candidate_keys_from_the_keymap_best_first():
    sweep, cheapino = "ferris_sweep_qwerty.vil", "cheapino.vil"
    # A symbol with several recipes: on Sym, on Num, and Shift with 9 on Num.
    assert keys_for(sweep, "(") == [(1, "5,2", "plain"), (4, "1,2", "plain"), (4, "4,3", "plain")]
    assert keys_for(cheapino, "(") == [(1, "1,2", "plain"), (4, "5,8", "plain"), (4, "0,3", "plain")]
    # Capitals are Shift with the letter's key, which can be a mod-tap.
    assert keys_for(sweep, "A") == [(0, "1,0", "plain")]
    assert keys_for(cheapino, "V") == [(0, "6,7", "mod-tap")]
    assert keys_for(sweep, " ") == [(0, "7,0", "layer-tap")]
    # Shift with the _ key gives - by the key override.
    assert keys_for(sweep, "-") == [(1, "4,3", "plain"), (4, "5,0", "plain"), (0, "5,4", "plain")]
    # Enter is the J+L combo or the key on Nav.
    assert keys_for(sweep, "\n") == [(0, "5,1+5,3", "combo"), (2, "7,1", "plain")]


def drawing(vil, vial, layer, names=(), change=lambda vil: None, heat=None, pairs=()):
    """The Keymap drawing of a .vil from sweep-layouts as an XML tree. `change` may edit the .vil first."""
    data = json.loads((SWEEP_LAYOUTS / "vil" / vil).read_text())
    change(data)
    vial_text = (SWEEP_LAYOUTS / "boards" / vial / "vial.json").read_text() if vial else None
    return ET.fromstring(draw_keymap(json.dumps(data), vial_text, layer, names, heat, pairs))


def drawn(svg, key):
    """The class and the texts of a key or combo in a drawing, or None if it is not drawn."""
    found = svg.find(f".//*[@id='k{key}']")
    return None if found is None else (found.get("class"), list(found.itertext()))


def rect(svg, key):
    """The x and y of a key's rectangle, and its rotation."""
    found = svg.find(f".//*[@id='k{key}']")
    box = next(found.iter("{http://www.w3.org/2000/svg}rect"))
    return float(box.get("x")), float(box.get("y")), found.get("transform")


NAMES = ["Base", "Sym", "Nav", "Stack", "Num"]


def test_a_keymap_drawing_shows_tap_and_hold_legends_layer_keys_and_combos():
    base = drawing("ferris_sweep_qwerty.vil", "sweep", 0, NAMES)

    assert drawn(base, "2,0") == ("key", ["z", "⌘"])  # a mod-tap: the tap legend, then the hold legend
    assert drawn(base, "7,0") == ("key", ["Space", "Sym"])  # a layer-tap
    assert drawn(base, "3,1") == ("key", ["Nav"])  # MO(2)
    assert drawn(base, "5,4") == ("key", ["_"])
    assert drawn(base, "5,1+5,2") == ("combo", ["Esc"])  # J+K
    assert drawn(base, "5,1+5,3") == ("combo", ["⏎"])  # J+L

    sym = drawing("ferris_sweep_qwerty.vil", "sweep", 1, NAMES)

    assert drawn(sym, "7,0") == ("key held", ["held"])  # the key held for Sym
    assert drawn(sym, "3,0") == ("key trns", [])
    assert drawn(sym, "5,2") == ("key", ["("])
    # J and K type = and ( on Sym, so their combo is not drawn there; when they are
    # transparent on Sym, it is.
    assert drawn(sym, "5,1+5,2") is None

    def transparent_j_and_k(vil):
        vil["layout"][1][5][1:3] = ["KC_TRNS", "KC_TRNS"]

    sym = drawing("ferris_sweep_qwerty.vil", "sweep", 1, NAMES, transparent_j_and_k)

    assert drawn(sym, "5,1+5,2") == ("combo", ["Esc"])


def test_macros_show_their_text_else_their_taps_else_their_number_and_kc_no_is_faint():
    def change(vil):
        vil["macro"][2] = []
        vil["layout"][3][0][0] = "KC_NO"

    sym = drawing("ferris_sweep_qwerty.vil", "sweep", 1, NAMES)
    stack = drawing("ferris_sweep_qwerty.vil", "sweep", 3, NAMES, change)

    assert drawn(sym, "2,0") == ("key", ["|>"])  # M0 types text
    assert drawn(stack, "1,0") == ("key", ["b c"])  # M4 holds Ctrl, so it shows the keys it taps
    assert drawn(stack, "1,2") == ("key", ["M2"])  # an empty macro
    assert drawn(stack, "0,0") == ("key none", [])


def test_layers_with_no_name_are_named_after_the_key_that_opens_them():
    base = drawing("ferris_sweep_qwerty.vil", "sweep", 0)

    assert drawn(base, "7,1") == ("key", ["Tab", "Tab"])  # LT(3,KC_TAB)
    assert drawn(base, "3,1") == ("key", ["L2"])  # MO(2) has no tap legend


def test_key_positions_come_from_the_vial_json_with_rotation_and_without_encoders_or_a_plain_grid():
    cheapino = drawing("cheapino.vil", "cheapino", 0)

    assert rect(cheapino, "4,11")[2] == "rotate(18 5.4 5)"
    # 0,0 is also the matrix position of an encoder, which is not drawn.
    assert rect(cheapino, "0,0") == (11.05, 1.3, None)

    grid = drawing("cheapino.vil", None, 0)

    assert rect(grid, "4,11") == (11.05, 4.05, None)


def test_a_session_gets_a_drawing_of_each_layer_with_names_from_the_settings_and_the_key_for_each_character(
    client, settings_path
):
    add_board(client, "Sweep", "ferris_sweep_qwerty.vil", "sweep")
    session = start_session(client, client.get("/api/boards").json()["boards"][0]["keymaps"][0]["version"])
    client.get("/api/settings")
    with settings_path.open("a") as settings:
        settings.write('\n[keymaps.Sweep.QWERTY]\nlayers = ["Base", "Sym"]\n')

    keymap = client.get(f"/api/sessions/{session}/keymap").json()

    assert len(keymap["layers"]) == 5  # the other 11 layers of the .vil are empty
    assert drawn(ET.fromstring(keymap["layers"][0]), "7,0") == ("key", ["Space", "Sym"])
    # Each character's key is its first candidate, which key attribution picks for a correct keystroke.
    assert keymap["keys"]["("] == {"layer": 1, "key": "5,2"}
    assert keymap["keys"]["\n"] == {"layer": 0, "key": "5,1+5,3"}
    assert keymap["keys"]["A"] == {"layer": 0, "key": "1,0"}


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


def test_each_function_in_a_code_file_is_a_passage_with_code_normalising():
    code = (
        "import os\n\n\n"
        "def área(x):\t \n"
        "\tif  x:\t\treturn   1  \n\n"
        "\treturn 2\n\n"
        "class A:\n    pass\n"
    )

    assert code_passages(code, 0.05, 10) == (
        ["def area(x):\n    if x: return 1\n\n    return 2", "class A:\n    pass"],
        1,  # "import os" is too short
    )


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A git repo with two tracked code files, a tracked binary file and an untracked file."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "a.py").write_text("def first_function():\n    return 1\n\n\ndef second_function():\n    return 2\n")
    (repo / "b.js").write_text("function third() {\n  return 3;\n}\n")
    (repo / "image.png").write_bytes(b"\x89PNG\x00\x00 not text, not text at all")
    git("init", cwd=repo)
    git("add", ".", cwd=repo)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "x", cwd=repo)
    (repo / "untracked.py").write_text("def untracked_function():\n    return 4\n")
    return repo


@pytest.fixture
def running(db_path, settings_path, provider):
    """A client whose server keeps running between requests, so background work can finish."""
    db_path.with_name("pg_catalog.csv").write_text(CATALOGUE)  # so nothing is downloaded
    with TestClient(create_app(db_path, settings_path, provider)) as client:
        yield client


def wait_for_notice(client, n=1):
    for _ in range(100):
        if len(notices := client.get("/api/notices").json()) >= n:
            return notices
        time.sleep(0.05)
    raise AssertionError("no notice")


def test_a_git_repo_is_cloned_in_the_background_and_each_function_of_its_tracked_text_files_is_a_passage(
    running, db_path, repo
):
    response = running.post("/api/code", json={"url": str(repo)})

    assert response.status_code == 202
    assert wait_for_notice(running) == ["Imported myrepo: 3 Passages, 0 functions skipped."]
    [(source, title)] = rows(db_path, "SELECT id, title FROM source")
    assert title == "myrepo"
    passages = [text for (text,) in rows(db_path, f"SELECT text FROM passage WHERE source = {source} ORDER BY ord")]
    a = ["def first_function():\n    return 1", "def second_function():\n    return 2"]
    b = ["function third() {\n  return 3;\n}"]
    assert passages in (a + b, b + a)  # the files in either order, each file's functions in written order


def test_a_clone_that_fails_is_reported(running, tmp_path):
    running.post("/api/code", json={"url": str(tmp_path / "missing")})

    [notice] = wait_for_notice(running)
    assert notice.startswith(f"Could not clone {tmp_path / 'missing'}:")


# What `innerText` gives for a news page: each block on its own line, menu text at the top and the bottom.
ARTICLE = (
    "Sign up for the morning newsletter to get our best stories\n"
    "Share\n\n"
    "Ministers met on Monday to discuss the “new” rules for the city’s harbour.\n"
    "\n   The plan, they said, would take three years — and cost more than expected.  \n"
    "Ἐν ἀρχῇ ἦν ὁ λόγος, said the vicar of the harbour church.\n"
    "Subscribe\n"
    "Sign up for the morning newsletter to get our best stories\n"
)


def test_each_kept_line_of_an_article_is_a_passage_and_the_article_is_first_in_the_sources(client, db_path, gutenberg):
    book = import_book(client)["source"]

    response = client.post("/api/articles", json={"title": "Harbour rules", "text": ARTICLE})

    assert response.status_code == 200
    article = response.json()["source"]
    assert rows(db_path, f"SELECT title, text FROM source WHERE id = {article}") == [("Harbour rules", ARTICLE)]
    assert rows(db_path, f"SELECT text, normaliser FROM passage WHERE source = {article} ORDER BY ord") == [
        ('Ministers met on Monday to discuss the "new" rules for the city\'s harbour.', "ascii-v1"),
        ("The plan, they said, would take three years - and cost more than expected.", "ascii-v1"),
    ]
    assert client.get("/api/notices").json() == [
        "Imported article Harbour rules: 2 Passages, 3 paragraphs skipped. It is first in the list of Sources (o)."
    ]
    assert [s["id"] for s in client.get("/api/sources").json()] == [article, book]


def test_an_article_with_nothing_long_enough_to_type_is_not_saved(client, db_path):
    response = client.post("/api/articles", json={"title": "Menu", "text": "Share\nSubscribe\n"})

    assert response.status_code == 422
    assert rows(db_path, "SELECT * FROM source") == []


def test_the_send_page_that_the_bookmarklet_opens_is_served_at_send(client):
    response = client.get("/send")

    assert response.status_code == 200
    assert "/api/articles" in response.text


def key_presses(keys, attempt, seq, gap=1000):
    """A keydown every `gap` ms for each key, each with its keyup 100 ms later."""
    events = []
    for i, k in enumerate(keys):
        for type, t in [("keydown", gap * i), ("keyup", gap * i + 100)]:
            events.append(key_event(seq + len(events), attempt, type) | {"t": t, "key": k, "code": f"Key{k}"})
    return events


CODE = {"passage": 2, "settings": SETTINGS}  # "ab\n  cd": its 2 spaces of indentation are not typed
TYPE_CODE = ["a", "b", "Enter", "c", "d"]  # 5 characters in 4.1 s, all right first time


def sweep_versions(client, db_path):
    """The QWERTY and the free-range Keymap versions of a Sweep. Also adds the code Passage."""
    add_board(client, "Sweep", "ferris_sweep_qwerty.vil", "sweep")
    add_board(client, "Sweep", "ferris_sweep_freerange.vil", "sweep")
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO passage (id, source, ord, text, normaliser) VALUES (2, NULL, 0, ?, 'ascii-v1')", ("ab\n  cd",))
    keymaps = client.get("/api/boards").json()["boards"][0]["keymaps"]
    return [k["version"] for k in keymaps]


def typed_session(client, version, *attempts, finished, attempt=CODE, gap=1000):
    """A Session on `version` with one Attempt at the code Passage (or `attempt`) for each list
    of keys, a key every `gap` ms. `finished` holds the ords of the Attempts that finished."""
    session = start_session(client, version)
    events = [e for ord, keys in enumerate(attempts) for e in key_presses(keys, ord, 100 * ord, gap)]
    batch = {"events": events, "attempts": {ord: attempt for ord in range(len(attempts))}, "finished": finished}
    client.post(f"/api/sessions/{session}/batch", json=batch)
    return session


def test_the_attempts_table_has_wpm_from_typed_characters_and_first_time_accuracy(client, db_path):
    qwerty, _ = sweep_versions(client, db_path)
    session = typed_session(client, qwerty, TYPE_CODE, ["a", "x"], finished=[0])

    table = attempts(sqlite3.connect(db_path))

    assert table.drop("started").to_dicts() == [
        {"session": session, "ord": 0, "board": "Sweep", "letter_layout": "QWERTY", "passage": 2, "finished": True,
         "wpm": 60 / 4.1, "accuracy": 1.0, "alignment": "first-error-v1"},
        {"session": session, "ord": 1, "board": "Sweep", "letter_layout": "QWERTY", "passage": 2, "finished": False,
         "wpm": None, "accuracy": 0.5, "alignment": "first-error-v1"},
    ]  # fmt: skip


def test_the_summary_of_an_attempt_has_the_medians_of_this_keymaps_finished_attempts_in_the_last_4_weeks(
    client, db_path
):
    qwerty, free_range = sweep_versions(client, db_path)
    typed_session(client, qwerty, TYPE_CODE, finished=[0])
    old = typed_session(client, qwerty, TYPE_CODE, finished=[0])
    with sqlite3.connect(db_path) as db:
        db.execute(f"UPDATE session SET started = '2026-01-01T00:00:00+00:00' WHERE id = {old}")
    typed_session(client, free_range, TYPE_CODE, finished=[0])
    one_error = ["a", "x", "Backspace", "b", "Enter", "c", "d"]  # in 6.1 s, 4 of 5 right first time
    session = typed_session(client, qwerty, ["a"], one_error, finished=[1])
    client.put("/api/settings", json={"weakness": {"min_seen": 1}})

    summary = client.get(f"/api/sessions/{session}/attempts/1/summary").json()

    assert summary.pop("unlocking") is None  # QWERTY has no locked keys
    # Of this Passage's pairs, only ab has a cost: the others follow the Enter combo or the c mod-tap.
    assert summary.pop("slowest_pairs") == ["ab"]
    assert summary == pytest.approx(
        {"wpm": 60 / 6.1, "accuracy": 0.8, "median_wpm": (60 / 4.1 + 60 / 6.1) / 2, "median_accuracy": 0.9}
    )


def test_the_weakness_ranking_has_the_cost_of_each_character_and_pair_on_one_keymap_in_the_window(client, db_path):
    qwerty, free_range = sweep_versions(client, db_path)
    typed_session(client, qwerty, TYPE_CODE, ["a", "x", "Backspace", "b"], finished=[0])  # the second is abandoned
    old = typed_session(client, qwerty, TYPE_CODE, finished=[0])
    with sqlite3.connect(db_path) as db:
        db.execute(f"UPDATE session SET started = '2026-01-01T00:00:00+00:00' WHERE id = {old}")
    typed_session(client, free_range, TYPE_CODE, finished=[0])

    ranking = weakness(sqlite3.connect(db_path), "Sweep", "QWERTY", WEAKNESS | {"min_seen": 2})

    # b took 1000 ms once, and was an Error once that took 2000 ms to fix; so was the pair ab.
    # a was seen twice but never timed, as it starts each Attempt. The rest were seen once.
    model = {"time": 1000.0, "error_rate": 0.5, "fix_ms": 2000.0, "seen": 2, "model": "recent-cost-v1"}
    assert ranking.to_dicts() == [{"unit": "ab", "cost": 2000.0, **model}, {"unit": "b", "cost": 2000.0, **model}]
    assert WEAKNESS_MODELS["recent-cost-v1"].scale == (150, 600, 400)


def down(t, key, code=None, repeat=False):
    return {"t": t, "type": "keydown", "key": key, "code": code or f"Key{key}", "repeat": repeat}


def up(t, key, code=None):
    return {"t": t, "type": "keyup", "key": key, "code": code or f"Key{key}"}


def tap(t, key, code=None, dwell=80.0):
    return [down(t, key, code), up(t + dwell, key, code)]


def typed_keystrokes(client, db_path, board, passage, *events):
    """The keystrokes table of one Attempt at `passage` on the Sweep with QWERTY or on the
    Cheapino. Each item of `events` is an event or a list of them, in any order."""
    vil = {"sweep": "ferris_sweep_qwerty.vil", "cheapino": "cheapino.vil"}[board]
    add_board(client, board, vil, board)
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO passage (id, source, ord, text, normaliser) VALUES (2, NULL, 0, ?, 'ascii-v1')", (passage,))
    session = start_session(client, client.get("/api/boards").json()["boards"][0]["keymaps"][0]["version"])
    flat = [e for item in events for e in (item if isinstance(item, list) else [item])]
    batch = [key_event(seq) | e for seq, e in enumerate(sorted(flat, key=lambda e: e["t"]))]
    client.post(f"/api/sessions/{session}/batch", json={"events": batch, "attempts": {0: CODE}})
    return keystrokes(sqlite3.connect(db_path))


def test_each_keystroke_is_attributed_to_its_candidate_keys_and_one_pick_guided_by_the_passage(client, db_path):
    table = typed_keystrokes(
        client, db_path, "sweep", "A(78",
        down(0, "Shift", "ShiftRight"), tap(10, "A"), up(100, "Shift", "ShiftRight"),
        down(200, "Shift", "ShiftLeft"), tap(201, "(", "Digit9"), up(290, "Shift", "ShiftLeft"),
        tap(400, "7"),
        tap(600, "*"),  # an Error: the * on Num is picked, as 8 is on Num
        tap(800, "Backspace"),
        tap(1000, "8"),
    )  # fmt: skip

    columns = ["position", "char", "typed", "status", "layer", "key", "kind", "first_time_correct", "fix_ms", "event"]
    assert table.select(columns).rows() == [
        (0, "A", "A", "correct", 0, "1,0", "plain", True, None, "typed"),
        (1, "(", "(", "correct", 1, "5,2", "plain", True, None, "typed"),
        (2, "7", "7", "correct", 4, "4,1", "plain", True, None, "typed"),
        (3, "8", "*", "error", 4, "4,4", "plain", False, 400.0, "typed"),
        (3, "8", "8", "correct", 4, "4,2", "plain", None, None, "typed"),
    ]
    # Shift between two keys does not stop their flight; Backspace does.
    assert table["flight"].to_list() == [None, 111.0, 119.0, 120.0, None]
    assert table["candidates"][1].to_list() == [
        {"layer": 1, "key": "5,2", "kind": "plain"},
        {"layer": 4, "key": "1,2", "kind": "plain"},
        {"layer": 4, "key": "4,3", "kind": "plain"},
    ]
    assert table.select("session", "ord", "seq", "t", "board", "letter_layout", "dwell", "flight", "alignment").row(
        0
    ) == (1, 0, 1, 10.0, "sweep", "QWERTY", 80.0, None, "first-error-v1")


def test_mod_tap_combo_and_macro_misfires_are_their_own_event_types(client, db_path):
    table = typed_keystrokes(
        client, db_path, "cheapino", "ve kl->xy",
        down(0, "Shift", "ShiftLeft"), tap(250, "E"), up(300, "Shift", "ShiftLeft"),  # v held too long
        tap(400, "Backspace"), tap(500, "v"), tap(600, "e"), tap(700, " ", "Space"),
        tap(800, "Backspace"),  # K+L together send Backspace
        tap(900, " ", "Space"), tap(1000, "k"), tap(1100, "l"),
        tap(1200, "-", "Minus", 0.2), tap(1201, ">", "Period", 0.2),  # the -> macro
        tap(1400, "|", "Backslash", 0.2), tap(1401, ">", "Period", 0.2),  # the |> macro, where x was wanted
    )  # fmt: skip

    assert table.select("position", "typed", "status", "event", "layer", "key", "kind").rows() == [
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
    assert table["first_time_correct"].to_list()[:5] == [None, None, True, True, None]


def test_dwell_and_flight_come_from_finger_events_with_summed_time_around_tap_hold_keys(client, db_path):
    table = typed_keystrokes(
        client, db_path, "sweep", "ab e-d->ff\ng",
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
    assert table.select("char", "kind", "dwell", "flight", "time").rows() == [
        ("a", "plain", 80.0, None, None),
        ("b", "plain", 80.0, 120.0, 200.0),
        (" ", "layer-tap", None, 320.0, 200.0),  # from b's keyup to e's keydown, for both pairs
        ("e", "plain", 80.0, 320.0, 200.0),
        ("-", "plain", 80.0, 120.0, 200.0),
        ("d", "plain", None, 120.0, 200.0),
        ("-", "macro", None, None, None),
        (">", "macro", None, None, None),
        ("f", "plain", 550.0, None, None),  # its keyup came after the auto-repeat
        ("f", "plain", None, None, None),  # auto-repeat
        ("\n", "combo", None, None, None),
        ("g", "plain", 80.0, None, None),
    ]


def test_an_attempt_is_replayed_again_when_more_of_its_key_events_come(client, db_path):
    table = typed_keystrokes(client, db_path, "sweep", "ab", down(0, "a"), tap(200, "b"))
    late_keyup = key_event(3) | up(150, "a")
    client.post("/api/sessions/1/batch", json={"events": [late_keyup], "attempts": {0: CODE}})

    assert table["dwell"].to_list() == [None, 80.0]
    assert keystrokes(sqlite3.connect(db_path))["dwell"].to_list() == [150.0, 80.0]


def drill(client, session):
    return client.post(f"/api/sessions/{session}/drills").json()


def test_with_no_data_a_drill_has_3_under_measured_targets_the_most_common_in_the_sources_first(
    client, db_path, monkeypatch
):
    monkeypatch.setattr("typokiller.drills.WORDS", [])  # so the pool is only the article's words
    client.post("/api/articles", json={"title": "Tents", "text": "ten ten ten ten ten net net tent"})
    session = start_session(client)

    made = drill(client, session)

    # t is in 9 of the pool's characters; space, e and n in 8 each.
    assert made["targets"] == [
        {"unit": unit, "reason": "under-measured", "cost": None, "seen": 0} for unit in ["t", " ", "e"]
    ]
    words = made["text"].split(" ")
    assert len(words) == 40
    assert set(words) <= {"ten", "net", "tent"}
    # A Drill is a Passage with no Source, and it records how it was made.
    assert rows(db_path, "SELECT p.source, p.text, d.session, d.model, d.generator, d.unlocked"
                " FROM drill d JOIN passage p ON p.id = d.passage") == [
        (None, made["text"], session, "recent-cost-v1", "density-v1", None)
    ]  # fmt: skip
    assert json.loads(rows(db_path, "SELECT targets FROM drill")[0][0]) == made["targets"]


def test_while_the_pool_is_small_the_built_in_word_list_is_in_it(client):
    words = drill(client, start_session(client))["text"].split(" ")

    assert set(words) <= set(WORDS)


def test_a_drill_targets_the_weakest_units_and_the_most_common_under_measured_one_on_this_keymap(
    client, db_path, monkeypatch
):
    monkeypatch.setattr("typokiller.drills.WORDS", [])
    qwerty, free_range = sweep_versions(client, db_path)
    client.post("/api/articles", json={"title": "Abcc", "text": "abcc abcc abcc abcc abcc"})
    session = typed_session(client, qwerty, TYPE_CODE, ["a", "x", "Backspace", "b"], finished=[0])
    typed_session(client, free_range, TYPE_CODE, finished=[0])  # c seen once more, on another Letter layout
    client.put("/api/settings", json={"weakness": {"min_seen": 2}, "drills": {"min_seen": 2}})

    made = drill(client, session)

    # ab and b cost 2000 ms and were seen twice on QWERTY; c, the most common in the pool, only once.
    weak = {"reason": "weak", "cost": 2000.0, "seen": 2}
    assert made["targets"] == [
        {"unit": "ab", **weak},
        {"unit": "b", **weak},
        {"unit": "c", "reason": "under-measured", "cost": None, "seen": 1},
    ]
    assert made["text"] == " ".join(["abcc"] * 40)

    client.put("/api/settings", json={"drills": {"weak": 1, "under_measured": 2, "words": 5}})

    made = drill(client, session)

    assert [(t["unit"], t["reason"]) for t in made["targets"]] == [
        ("ab", "weak"), ("c", "under-measured"), (" ", "under-measured")
    ]
    assert made["text"] == " ".join(["abcc"] * 5)


def test_the_trend_has_the_medians_of_each_days_finished_attempts_on_one_keymap_in_the_last_13_weeks(
    client, db_path
):
    qwerty, free_range = sweep_versions(client, db_path)
    one_error = ["a", "x", "Backspace", "b", "Enter", "c", "d"]  # in 6.1 s, 4 of 5 right first time
    typed_session(client, qwerty, TYPE_CODE, one_error, ["a"], finished=[0, 1])  # the third is abandoned
    days_ago = typed_session(client, qwerty, TYPE_CODE, finished=[0])
    too_old = typed_session(client, qwerty, TYPE_CODE, finished=[0])
    typed_session(client, free_range, TYPE_CODE, finished=[0])
    today = datetime.now(UTC)
    with sqlite3.connect(db_path) as db:
        for session, weeks in [(days_ago, 2), (too_old, 14)]:
            started = (today - timedelta(weeks=weeks)).isoformat()
            db.execute("UPDATE session SET started = ? WHERE id = ?", (started, session))

    trend = progress(sqlite3.connect(db_path), "Sweep", "QWERTY", WEAKNESS).trend

    assert trend.rows() == pytest.approx([
        ((today - timedelta(weeks=2)).astimezone().date(), 60 / 4.1, 1.0, 1),
        (today.astimezone().date(), (60 / 4.1 + 60 / 6.1) / 2, 0.9, 2),
    ])  # fmt: skip


HEAT = Heat(
    costs={"E": 600.0, "e": 150.0, " ": 200.0, "ab": 400.0},
    seen={"E": 25, "e": 40, " ": 50, "z": 3, "ab": 30},
    scale=(150, 600, 400),
)


def fills(svg, key):
    """The fill of each half of a key in a heat drawing: the top half first, if it is split."""
    found = svg.find(f".//*[@id='k{key}']")
    return [e.get("style") for e in found if e.get("class") == "half"]


def test_a_heat_drawing_splits_each_key_with_the_shifted_cost_on_top_and_greys_non_characters():
    base = drawing("ferris_sweep_qwerty.vil", "sweep", 0, NAMES, heat=HEAT)

    assert drawn(base, "0,2") == ("key", ["E", "600", "e", "150"])
    # The fixed colour scale: its low end is the palest colour, its high end the darkest.
    assert fills(base, "0,2") == ["fill:#6e2130", "fill:#fbf1d3"]
    # Halves seen too few times for the Weakness model to rank are hatched, with their count.
    assert drawn(base, "2,0") == ("key", ["Z", "n=0", "z", "n=3"])
    assert fills(base, "2,0") == ["fill:url(#hatch)", "fill:url(#hatch)"]
    assert drawn(base, "7,0") == ("key", ["Space", "200"])  # no Shifted character, so not split
    assert drawn(base, "5,4") == ("key", ["-", "n=0", "_", "n=0"])  # Shift + _ types - by a key override
    assert drawn(base, "3,1") == ("key grey", ["Nav"])
    assert drawn(base, "3,0") == ("key grey", ["Esc", "Num"])
    assert drawn(base, "5,1+5,3") == ("combo grey", ["⏎"])
    assert list(next(e for e in base.iter() if e.get("class") == "scale").itertext())[:3] == ["150", "400", "600 ms"]

    sym = drawing("ferris_sweep_qwerty.vil", "sweep", 1, NAMES, heat=HEAT)

    assert drawn(sym, "2,0") == ("key grey", ["|>"])  # a macro
    assert drawn(sym, "7,0") == ("key held", ["held"])


def centre(svg, key):
    """The centre of a key's rectangle, for a key that is not rotated."""
    x, y, _ = rect(svg, key)
    box = next(svg.find(f".//*[@id='k{key}']").iter("{http://www.w3.org/2000/svg}rect"))
    return x + float(box.get("width")) / 2, y + float(box.get("height")) / 2


def test_each_pair_is_an_arc_from_its_first_characters_key_to_its_seconds_on_the_layer_with_both_keys():
    pairs = ["ek", "ee", "()", "e("]
    base = drawing("ferris_sweep_qwerty.vil", "sweep", 0, NAMES, pairs=pairs)
    sym = drawing("ferris_sweep_qwerty.vil", "sweep", 1, NAMES, pairs=pairs)

    arcs = base.findall(".//*[@class='arc']")
    # ( and ) are on Sym, so their arcs are not on the base layer.
    # The keys of e( are on two layers, so it has no arc.
    assert [a.get("data-pair") for a in arcs] == ["ek", "ee"]
    assert [a.get("data-pair") for a in sym.findall(".//*[@class='arc']")] == ["()"]
    x, y, _, _, x_end, y_end = [float(v) for v in re.findall(r"-?[\d.]+", arcs[0][0].get("d") or "")]
    (x1, y1), (x2, y2) = centre(base, "0,2"), centre(base, "5,2")
    assert (x, y, x_end, y_end) == pytest.approx((x1, y1 - 0.25, x2, y2 - 0.25))


def test_the_progress_page_has_the_trend_chart_the_heat_drawing_and_the_weakest_characters_and_pairs(
    client, db_path
):
    qwerty, _ = sweep_versions(client, db_path)
    typed_session(client, qwerty, TYPE_CODE, ["a", "x", "Backspace", "b"], finished=[0])
    client.put("/api/settings", json={"weakness": {"min_seen": 2}})

    page = client.get(f"/api/keymaps/{qwerty}/progress").json()

    (trend,) = page["trend"]["datasets"].values()
    assert [day["wpm"] for day in trend] == [60 / 4.1]
    assert page["names"] == ["L0", "Space", "L2", "Tab", "Esc"]  # no layer names in the settings
    # b and ab cost 2000 ms and were seen twice; no other unit was seen twice and timed.
    assert page["chars"] == [{"unit": "b", "cost": 2000.0, "seen": 2}]
    assert page["pairs"] == [{"unit": "ab", "cost": 2000.0, "seen": 2}]
    layers = [ET.fromstring(svg) for svg in page["layers"]]
    assert len(layers) == 5
    assert drawn(layers[0], "2,4") == ("key", ["B", "n=0", "b", "2000"])
    assert [a.get("data-pair") for a in layers[0].findall(".//*[@class='arc']")] == ["ab"]


def test_the_notebook_shows_the_progress_pages_numbers_and_splits_the_weakness_costs_by_layer(client, db_path):
    qwerty, _ = sweep_versions(client, db_path)
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO passage (id, source, ord, text, normaliser) VALUES (3, NULL, 0, 'ab(', 'ascii-v1')")
    typed_session(client, qwerty, *[["a", "b", "("]] * 2, finished=[0, 1], attempt={"passage": 3, "settings": SETTINGS})
    client.put("/api/settings", json={"weakness": {"min_seen": 2}})
    spec = importlib.util.spec_from_file_location("progress_notebook", Path(__file__).parents[1] / "notebooks" / "progress.py")
    assert spec and spec.loader
    notebook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notebook)

    outputs, defs = notebook.app.run(defs={"path": db_path})  # runs every cell, top to bottom

    page = client.get(f"/api/keymaps/{qwerty}/progress").json()
    weakest = ["unit", "cost", "seen"]
    assert defs["found"].chars.select(weakest).to_dicts() == page["chars"]
    assert defs["found"].pairs.select(weakest).to_dicts() == page["pairs"]
    # ( is on the layer that Space opens; a pair is on the layer of its second character.
    assert defs["split"].select("layer", "name", *weakest).rows() == [
        (0, "L0", "ab", 1000.0, 2),
        (0, "L0", "b", 1000.0, 2),
        (1, "Space", "(", 1000.0, 2),
        (1, "Space", "b(", 1000.0, 2),
    ]
    text = " ".join(str(getattr(output, "text", "")) for output in outputs)
    assert "first-error-v1" in text and "recent-cost-v1" in text


REA = {"passage": 3, "settings": SETTINGS}  # "rea": plain keys on both free-range Boards


def free_range_boards(client, db_path):
    """The Keymap versions of the Sweep with QWERTY, the Sweep with free-range and the Sofle,
    which has free-range. Also adds the Passage "rea" as Passage 3."""
    qwerty, sweep = sweep_versions(client, db_path)
    add_board(client, "Sofle", "sofle.vil", "sofle")
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO passage (id, source, ord, text, normaliser) VALUES (3, NULL, 0, 'rea', 'ascii-v1')")
    sofle = client.get("/api/boards").json()["boards"][1]["keymaps"][0]["version"]
    return qwerty, sweep, sofle


def unlock_log(db_path):
    return rows(db_path, "SELECT letter_layout, key, how, model FROM unlock ORDER BY rowid")


def test_after_a_finished_attempt_the_next_key_unlocks_when_each_unlocked_character_is_fast_over_its_last_keystrokes_on_every_board_with_the_letter_layout(
    client, db_path
):
    qwerty, sweep, sofle = free_range_boards(client, db_path)
    rule = {"start": "e", "order": "a t", "threshold": 1500, "min_seen": 2}
    client.put("/api/settings", json={"unlocking": rule})
    rea = [["r", "e", "a"]] * 2
    typed_session(client, qwerty, *rea, finished=[0, 1], attempt=REA)  # QWERTY has no locked keys
    typed_session(client, sweep, *rea, finished=[0, 1], attempt=REA, gap=3000)  # e takes 3000 ms
    session = typed_session(client, sofle, *rea, finished=[0, 1], attempt=REA)  # and 1000 ms

    # Over both free-range Boards, the median time of e is 2000 ms.
    assert unlock_log(db_path) == []

    client.put("/api/settings", json={"unlocking": {"last": 2}})
    typed_session(client, sofle, ["r", "e", "a"], finished=[0], attempt=REA)  # finishing another Attempt runs the rule again

    # Over its last 2 keystrokes, on the Sofle, e takes 1000 ms.
    assert unlock_log(db_path) == [("free-range", "a", "rule", "recent-cost-v1")]
    [(settings,)] = rows(db_path, "SELECT settings FROM unlock")
    assert json.loads(settings) == UNLOCKING | rule | {"last": 2}
    state = client.get(f"/api/sessions/{session}/attempts/1/summary").json()["unlocking"]
    assert (state["unlocked"], state["total"], state["next"]) == (2, 3, "t")


def test_a_finished_attempt_sent_again_does_not_unlock_another_key(client, db_path):
    _, sweep, _ = free_range_boards(client, db_path)
    client.put("/api/settings", json={"unlocking": {"start": "e", "order": "a t", "threshold": 1500, "min_seen": 1}})
    session = typed_session(client, sweep, ["r", "e", "a"], finished=[0], attempt=REA)

    client.post(f"/api/sessions/{session}/batch", json={"finished": [0]})  # the page sends the batch again until the server answers

    assert unlock_log(db_path) == [("free-range", "a", "rule", "recent-cost-v1")]


def test_u_unlocks_the_next_key_by_hand_and_drawings_show_the_locked_keys_and_ring_the_next(client, db_path):
    qwerty, sweep, _ = free_range_boards(client, db_path)
    session = start_session(client, sweep)

    keymap = client.get(f"/api/sessions/{session}/keymap").json()

    assert keymap["unlocking"] == {"unlocked": 10, "total": 30, "next": "o", "introducing": None}
    base = ET.fromstring(keymap["layers"][0])
    assert drawn(base, "1,0") == ("key", ["u"])
    assert drawn(base, "0,0") == ("key locked", ["x"])
    assert drawn(base, "4,3") == ("key locked unlock", ["o"])

    unlocked = client.post(f"/api/sessions/{session}/unlocks").json()

    assert unlocked == {"unlocked": 11, "total": 30, "next": "i", "introducing": "o"}
    assert unlock_log(db_path) == [("free-range", "o", "manual", "recent-cost-v1")]
    assert client.get("/api/notices").json() == ["Unlocked o. Introduction Drills come after this Attempt."]
    page = client.get(f"/api/keymaps/{sweep}/progress").json()
    heat = ET.fromstring(page["layers"][0])
    assert drawn(heat, "4,2") == ("key locked unlock", ["I", "n=0", "i", "n=0"])

    for _ in range(19):
        client.post(f"/api/sessions/{session}/unlocks")

    assert client.get(f"/api/sessions/{session}/keymap").json()["unlocking"]["next"] is None
    assert client.post(f"/api/sessions/{session}/unlocks").status_code == 409
    assert client.post(f"/api/sessions/{start_session(client, qwerty)}/unlocks").status_code == 409


def test_drills_use_only_the_unlocked_keys_until_all_30_are_unlocked_and_record_them(client, db_path):
    _, sweep, _ = free_range_boards(client, db_path)
    session = start_session(client, sweep)

    made = drill(client, session)

    assert set(made["text"]) <= set("untsm,rea_ ")  # no capitals either

    client.put("/api/settings", json={"unlocking": {"min_seen": 0}})  # so no Introduction Drills
    for _ in range(20):
        client.post(f"/api/sessions/{session}/unlocks")
    drill(client, session)

    assert rows(db_path, "SELECT generator, unlocked FROM drill ORDER BY passage")[1] == ("density-v1", None)


def test_each_unlock_queues_introduction_drills_of_the_new_key_and_its_two_commonest_pairs_until_it_is_seen_enough(
    client, db_path, monkeypatch
):
    monkeypatch.setattr("typokiller.drills.WORDS", [])  # so the pool is only the article's words
    _, sweep, _ = free_range_boards(client, db_path)
    client.post("/api/articles", json={"title": "Ears", "text": "ear ear ear era era are re at"})
    client.put("/api/settings", json={"unlocking": {"start": "r e", "order": "a t", "min_seen": 2}})
    before = typed_session(client, sweep, ["r", "e", "a"], ["r", "e", "a"], finished=[0, 1], attempt=REA)
    with sqlite3.connect(db_path) as db:
        an_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        db.execute("UPDATE session SET started = ? WHERE id = ?", (an_hour_ago, before))
    session = start_session(client, sweep)
    client.post(f"/api/sessions/{session}/unlocks")  # a

    made = drill(client, session)

    # In the pool's words of r, e and a, ar is in 4 and ea in 3. a was seen twice before its unlock.
    assert made["generator"] == "introduction"
    assert [(t["unit"], t["reason"], t["seen"]) for t in made["targets"]] == [
        ("a", "introduction", 2), ("ar", "introduction", 0), ("ea", "introduction", 2)
    ]  # fmt: skip
    assert set(made["text"].split(" ")) <= {"ear", "era", "are"}
    assert rows(db_path, "SELECT generator, unlocked FROM drill") == [("introduction", '["r", "e", "a"]')]

    later = typed_session(client, sweep, ["r", "e", "a"], finished=[0], attempt=REA)  # a seen once since its unlock

    assert drill(client, later)["generator"] == "introduction"

    typed_session(client, sweep, ["r", "e", "a"], finished=[0], attempt=REA)  # and twice

    asked = client.post(f"/api/sessions/{later}/drills", json={"introduction": True}).json()
    assert asked == {"unlocking": {"unlocked": 3, "total": 4, "next": "t", "introducing": None}}
    assert drill(client, later)["generator"] == "density-v1"


# A Lesson as a model might write it, with the parts that the prompt asks it to leave out.
LESSON = """\
# Pattern Matching in Python

Python's `match` statement compares a **value** against *patterns*,
as [the tutorial](https://docs.python.org/3/tutorial/) shows.

## Literal patterns

- A literal matches an equal value.
- The wildcard `_` matches anything.

| Pattern | Matches |
| --- | --- |
| `1` | one |

```python
import sys

def describe(command):
    match command:

        case "quit":   \t
            return "leaving"



print(describe(sys.argv[0]))
```
"""


def test_a_lesson_is_split_into_paragraphs_and_code_blocks_under_their_headings():
    heading = "Pattern Matching in Python"
    code = 'import sys\n\ndef describe(command):\n    match command:\n\n        case "quit":\n            return "leaving"'

    assert lesson_passages(LESSON, 40, 0.05, 20) == (
        [
            (heading, "Python's match statement compares a value against patterns, as the tutorial shows."),
            ("Literal patterns", "A literal matches an equal value."),
            ("Literal patterns", "The wildcard _ matches anything."),
            ("Literal patterns", code + "\n\nprint(describe(sys.argv[0]))"),
        ],
        1,  # the table
    )
    # A block over split_lines lines (9 > 7) is split at blank lines before unindented lines,
    # with as many whole parts as fit in split_lines.
    assert lesson_passages(LESSON, 7, 0.05, 20)[0][3:] == [
        ("Literal patterns", code),
        ("Literal patterns", "print(describe(sys.argv[0]))"),
    ]


def spend_row(dollars, time):
    return f"INSERT INTO spend (lesson, time, usage, dollars) VALUES (0, '{time}', '{{}}', {dollars})"


def test_a_lesson_is_written_in_the_background_in_the_order_asked_and_recorded_and_first_in_o(
    running, db_path, provider, gutenberg
):
    book = import_book(running)["source"]

    responses = [running.post("/api/lessons", json={"topic": topic}) for topic in ["pattern matching", "decorators"]]

    assert [r.status_code for r in responses] == [202, 202]
    ready = "4 Passages, 1 skipped; 0 of 1 code examples dropped. It is first in the list of Sources (o)."
    assert wait_for_notice(running, 2) == [f"Lesson ready: pattern matching: {ready}", f"Lesson ready: decorators: {ready}"]
    [call, _] = provider.calls
    assert {k: v for k, v in call.items() if k != "messages"} == {
        "model": "anthropic/claude-haiku-5.5", "max_tokens": 8000, "reasoning": "low"
    }  # fmt: skip
    prompt = " ".join(m["content"] for m in call["messages"])
    assert "pattern matching" in prompt and "1300 words" in prompt and "intermediate" in prompt
    sources = running.get("/api/sources").json()
    assert [(s["title"], s["total"]) for s in sources] == [("decorators", 4), ("pattern matching", 4), ("Pride and Prejudice", 2)]
    assert sources[2]["id"] == book
    # Each Passage is served with its heading.
    served = running.put(f"/api/sources/{sources[1]['id']}/bookmark", json={"at": 1}).json()
    assert [p["heading"] for p in served["passages"]] == ["Literal patterns", "Literal patterns"]
    # Each Lesson records how it was made, and each call its usage and cost.
    lessons = rows(db_path, "SELECT topic, language, model, prompt, settings, output, source FROM lesson ORDER BY id")
    assert lessons[0][:4] == ("pattern matching", "python", "anthropic/claude-haiku-5.5", "lesson-prompt-v1")
    assert json.loads(lessons[0][4]) == LESSONS
    assert lessons[0][5:] == (LESSON, sources[1]["id"])
    assert rows(db_path, "SELECT lesson, usage, dollars FROM spend ORDER BY rowid") == [
        (1, '{"prompt_tokens": 200, "completion_tokens": 3000}', 0.0015),
        (2, '{"prompt_tokens": 200, "completion_tokens": 3000}', 0.0015),
    ]
    assert running.get("/api/lessons/spend").json() == {"spent": 0.003 / 1.337, "cap": 5.0, "language": "python"}
    # Lesson text joins the Drill word pool.
    assert pool(sqlite3.connect(db_path), None)["literal"] == 2


def test_a_lesson_that_fails_says_why(running, db_path, provider):
    provider.error = OSError("HTTP Error 500")

    running.post("/api/lessons", json={"topic": "decorators"})

    assert wait_for_notice(running) == ["Lesson decorators failed: HTTP Error 500"]
    assert rows(db_path, "SELECT * FROM source") == []


def test_a_request_whose_worst_case_with_the_waiting_ones_could_pass_the_cap_this_uk_month_is_refused_and_not_sent(
    running, db_path, provider
):
    # A request's worst case is about $0.072: the Lesson (8,000 output tokens at $0.50 per million,
    # and the prompt) and 2 repair calls (4,000 output tokens and a prompt of about 6,500
    # characters) for each of the 6 code blocks that the prompt asks for, and all of that again
    # if the Lesson is written again. $0.1 is left this month, enough for one request but not
    # for two. Without the repairs it would be enough for many.
    london = datetime.now(ZoneInfo("Europe/London"))
    month = london.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with sqlite3.connect(db_path) as db:
        db.execute(spend_row(5 * 1.337 - 0.1, month.astimezone(UTC).isoformat()))
        db.execute(spend_row(100, (month - timedelta(seconds=1)).astimezone(UTC).isoformat()))  # last month
    provider.going.clear()  # so the first Lesson is still being written when the second is asked for

    first = running.post("/api/lessons", json={"topic": "decorators"})
    second = running.post("/api/lessons", json={"topic": "generators"})
    provider.going.set()

    resets = (month + timedelta(days=32)).replace(day=1)
    assert first.status_code == 202
    assert (second.status_code, second.json()["detail"]) == (409, f"Cap reached: resets 1 {resets:%b}")
    wait_for_notice(running)
    assert [call["messages"][1]["content"] for call in provider.calls] == ["Write a Python Lesson on decorators."]
    assert running.get("/api/lessons/spend").json()["spent"] == pytest.approx(5 - (0.1 - 0.0015) / 1.337)


def test_a_python_block_runs_in_a_new_folder_and_cannot_write_outside_it(tmp_path):
    outside = tmp_path / "outside.txt"
    inside = "import tempfile\nopen('here.txt', 'w').write('x')\ntempfile.TemporaryFile().write(b'x')\n"

    assert run_code("python", inside, 10) is None
    assert "PermissionError" in (run_code("python", f"open({str(outside)!r}, 'w')\n", 10) or "")
    assert not outside.exists()


def test_a_python_block_has_no_network():
    with socket.create_server(("127.0.0.1", 0)) as server:
        connect = f"import socket\nsocket.create_connection(('127.0.0.1', {server.getsockname()[1]}), timeout=2)\n"
        subprocess.run([sys.executable, "-c", connect], check=True)  # without the sandbox, it connects

        assert "PermissionError" in (run_code("python", connect, 10) or "")


def test_a_block_passes_on_exit_code_0_within_the_timeout():
    assert run_code("python", "import json\nprint(json.dumps(1))\n", 10) is None
    assert "No module named 'polars'" in (run_code("python", "import polars\n", 10) or "")  # the standard library only
    assert run_code("python", "import sys\nprint('oops', file=sys.stderr)\nsys.exit(3)\n", 10) == (
        "It ended with exit code 3.\noops\n"
    )
    assert run_code("python", "import time\ntime.sleep(10)\n", 0.5) == "It did not finish within 0.5 seconds.\n"


# A Gleam module that uses gleam_stdlib, gleam_erlang and gleam_otp.
GLEAM = """\
import gleam/erlang/process
import gleam/io
import gleam/otp/actor

pub fn main() -> Nil {
  let assert Ok(_) = actor.new(0) |> actor.start
  process.sleep(1)
  io.println("started")
}
"""

# Tests never use the network, so they do not build the pre-made project (README: Lessons).
gleam_built = pytest.mark.skipif(not (GLEAM_PROJECT / "build").exists(), reason="the Gleam project is not built")


@gleam_built
def test_a_gleam_block_builds_and_runs_in_the_pre_made_project_and_fails_without_main():
    assert run_code("gleam", GLEAM, 10) is None  # the dependencies are there, without the network
    without_main = run_code("gleam", GLEAM.replace("pub fn main", "pub fn start"), 10) or ""
    assert without_main.startswith("It ended with exit code 1.") and "does not have a main function" in without_main


@gleam_built
def test_a_gleam_lesson_is_written_by_the_gleam_model_and_its_code_is_checked_with_gleam(running, db_path, provider):
    provider.text = code_lesson(GLEAM, language="gleam")

    running.post("/api/lessons", json={"topic": "actors", "language": "gleam"})

    ready = "2 Passages, 0 skipped; 0 of 1 code examples dropped. It is first in the list of Sources (o)."
    assert wait_for_notice(running) == [f"Lesson ready: actors: {ready}"]
    [call] = provider.calls
    assert call["model"] == "anthropic/claude-sonnet-5.5"
    prompt = " ".join(m["content"] for m in call["messages"])
    assert "Write a Gleam Lesson on actors." in prompt
    assert "pub fn main() -> Nil" in prompt and "gleam_stdlib 1.0, gleam_erlang 1.3 and gleam_otp 1.3" in prompt
    assert rows(db_path, "SELECT language, model FROM lesson") == [("gleam", "anthropic/claude-sonnet-5.5")]
    # The Lesson form chooses the language of the last Lesson at first.
    assert running.get("/api/lessons/spend").json()["language"] == "gleam"


def test_a_gleam_lesson_is_refused_and_not_sent_when_the_gleam_project_does_not_build(
    running, provider, tmp_path, monkeypatch
):
    monkeypatch.setattr("typokiller.lessons.GLEAM_PROJECT", tmp_path)  # no gleam.toml there

    response = running.post("/api/lessons", json={"topic": "actors", "language": "gleam"})

    assert response.status_code == 502 and response.json()["detail"].startswith("Could not build the Gleam project: ")
    assert provider.calls == []


def code_lesson(*blocks, language="python"):
    """A Lesson with a section for each code block."""
    return "".join(f"## Part {i}\n\nA paragraph long enough to type.\n\n```{language}\n{b}\n```\n\n" for i, b in enumerate(blocks))


def fenced(code):
    return f"Here it is fixed:\n\n```python\n{code}\n```\n"


def test_a_failing_block_gets_up_to_2_repair_calls_with_its_error_and_then_is_dropped(running, db_path, provider):
    provider.texts = [
        code_lesson("print('the first block')", "print(two)", "raise SystemExit(1)"),
        fenced("print('the second block')"),  # the second block's first repair passes
        fenced("raise SystemExit(2)"),  # the third block's repairs fail
        fenced("raise SystemExit(3)"),
    ]

    running.post("/api/lessons", json={"topic": "checking"})

    ready = "5 Passages, 0 skipped; 1 of 3 code examples dropped. It is first in the list of Sources (o)."
    assert wait_for_notice(running) == [f"Lesson ready: checking: {ready}"]
    repairs = provider.calls[1:]
    assert [(c["max_tokens"], c["reasoning"]) for c in repairs] == [(4000, "low")] * 3
    asked = [c["messages"][-1]["content"] for c in repairs]
    assert "print(two)" in asked[0] and "NameError: name 'two' is not defined" in asked[0]
    assert "raise SystemExit(1)" in asked[1] and "exit code 1" in asked[1]
    assert "raise SystemExit(2)" in asked[2] and "exit code 2" in asked[2]
    # Each repair call is in the spend ledger with the Lesson.
    assert rows(db_path, "SELECT lesson, dollars FROM spend") == [(1, 0.0015)] * 4
    # The check log has each block's checks, the code of each and its error, None when it passed.
    [(checks, source)] = rows(db_path, "SELECT checks, source FROM lesson")
    log = json.loads(checks)
    assert [[(c["code"], c["error"] is None) for c in block] for block in log] == [
        [("print('the first block')\n", True)],
        [("print(two)\n", False), ("print('the second block')\n", True)],
        [("raise SystemExit(1)\n", False), ("raise SystemExit(2)\n", False), ("raise SystemExit(3)\n", False)],
    ]
    assert log[2][2]["error"] == "It ended with exit code 3.\n"
    # The Source has the repaired block and not the dropped one.
    passages = [p for (p,) in rows(db_path, f"SELECT text FROM passage WHERE source = {source} ORDER BY ord")]
    paragraph = "A paragraph long enough to type."
    assert passages == [paragraph, "print('the first block')", paragraph, "print('the second block')", paragraph]
    assert "SystemExit" not in rows(db_path, f"SELECT text FROM source WHERE id = {source}")[0][0]


def test_a_lesson_with_more_than_a_third_of_its_blocks_dropped_is_written_again_once(running, db_path, provider):
    provider.texts = [code_lesson("print('one')", "raise SystemExit(1)", "raise SystemExit(1)")] + [fenced("1/0")] * 4

    running.post("/api/lessons", json={"topic": "checking"})

    assert wait_for_notice(running)[0].startswith("Lesson ready: checking: 4 Passages")
    assert len(provider.calls) == 1 + 4 + 1
    assert provider.calls[5]["messages"] == provider.calls[0]["messages"]
    # Each time it was written has its own row, with its check log. The first has no Source.
    [first, second] = rows(db_path, "SELECT checks, source FROM lesson ORDER BY id")
    assert len(json.loads(first[0])) == 3 and first[1] is None
    assert len(json.loads(second[0])) == 1 and second[1] is not None
    assert rows(db_path, "SELECT lesson FROM spend ORDER BY rowid") == [(1,)] * 5 + [(2,)]


def test_a_lesson_with_no_code_left_after_it_is_written_again_is_rejected(running, db_path, provider):
    provider.text = "## Prose\n\nOnly prose here, and long enough to type.\n"

    running.post("/api/lessons", json={"topic": "prose"})

    assert wait_for_notice(running) == ["Lesson prose failed: it was written 2 times; the last time, it had no code example."]
    assert len(provider.calls) == 2
    assert rows(db_path, "SELECT checks, source FROM lesson") == [("[]", None), ("[]", None)]
    assert rows(db_path, "SELECT * FROM source") == []
