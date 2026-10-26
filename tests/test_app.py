import hashlib
import json
import sqlite3
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from typokiller.analysis import WEAKNESS_MODELS, attempts, keystrokes, weakness
from typokiller.app import create_app
from typokiller.drawing import draw_keymap
from typokiller.drills import WORDS
from typokiller.keymap import qmk_settings, read_keymap
from typokiller.sources import ascii_v1, code_passages


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def settings_path(tmp_path):
    return tmp_path / "typokiller.toml"


@pytest.fixture
def client(db_path, settings_path):
    return TestClient(create_app(db_path, settings_path))


WEAKNESS = {"model": "recent-cost-v1", "weeks": 4, "min_seen": 20}
SETTINGS = {
    "typing": {"wrong_key_mode": "keep typing", "show_keymap": False},
    "passages": {"max_dropped": 0.05, "min_length": 20},
    "weakness": WEAKNESS,
    "drills": {"generator": "density-v1", "weak": 2, "under_measured": 1, "min_seen": 20, "words": 40},
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


def drawing(vil, vial, layer, names=(), change=lambda vil: None):
    """The Keymap drawing of a .vil from sweep-layouts as an XML tree. `change` may edit the .vil first."""
    data = json.loads((SWEEP_LAYOUTS / "vil" / vil).read_text())
    change(data)
    vial_text = (SWEEP_LAYOUTS / "boards" / vial / "vial.json").read_text() if vial else None
    return ET.fromstring(draw_keymap(json.dumps(data), vial_text, layer, names))


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
def running(db_path, settings_path):
    """A client whose server keeps running between requests, so background work can finish."""
    db_path.with_name("pg_catalog.csv").write_text(CATALOGUE)  # so nothing is downloaded
    with TestClient(create_app(db_path, settings_path)) as client:
        yield client


def wait_for_notice(client):
    for _ in range(100):
        if notices := client.get("/api/notices").json():
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


def key_presses(keys, attempt, seq):
    """A keydown every second for each key, each with its keyup 100 ms later."""
    events = []
    for i, k in enumerate(keys):
        for type, t in [("keydown", 1000 * i), ("keyup", 1000 * i + 100)]:
            events.append(key_event(seq + len(events), attempt, type) | {"t": t, "key": k, "code": f"Key{k}"})
    return events


CODE = {"passage": 2, "settings": SETTINGS}  # "ab\n  cd": its 2 spaces of indentation are not typed
TYPE_CODE = ["a", "b", "Enter", "c", "d"]  # 5 characters in 4.1 s, all right first time


def sweep_versions(client, db_path):
    """The QWERTY and the free-range Keymap versions of a Sweep. Also adds the code Passage."""
    add_board(client, "Sweep", "ferris_sweep_qwerty.vil", "sweep")
    add_board(client, "Sweep", "ferris_sweep_freerange.vil", "sweep")
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO passage VALUES (2, NULL, 0, ?, 'ascii-v1')", ("ab\n  cd",))
    keymaps = client.get("/api/boards").json()["boards"][0]["keymaps"]
    return [k["version"] for k in keymaps]


def typed_session(client, version, *attempts, finished):
    """A Session on `version` with one Attempt at the code Passage for each list of keys.
    `finished` holds the ords of the Attempts that finished."""
    session = start_session(client, version)
    events = [e for ord, keys in enumerate(attempts) for e in key_presses(keys, ord, seq=100 * ord)]
    batch = {"events": events, "attempts": {ord: CODE for ord in range(len(attempts))}, "finished": finished}
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
        db.execute("INSERT INTO passage VALUES (2, NULL, 0, ?, 'ascii-v1')", (passage,))
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
