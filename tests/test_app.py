import hashlib
import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from typokiller.app import DEFAULT_SETTINGS, create_app, options
from typokiller.drawing import Heat, draw_keymap
from typokiller.keymap import qmk_settings, read_keymap

from keybr_recordings import ORIGIN, build_recordings, change, keyboard_export, keymap_snapshot, attempt


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def settings_path(tmp_path):
    return tmp_path / "typokiller.toml"


@pytest.fixture
def recordings(tmp_path):
    return tmp_path / "recordings.sqlite"


@pytest.fixture
def client(db_path, settings_path, recordings):
    return TestClient(create_app(db_path, settings_path, recordings))


# Real .vil and vial.json files from the sweep-layouts repo, as of its commit 67c9332 (2026-10-25).
# They are copies, so that a change to a keyboard there does not change the tests.
SWEEP_LAYOUTS = Path(__file__).parent / "fixtures"


def add_board(client, name, vil, vial):
    vil_text = (SWEEP_LAYOUTS / "vil" / vil).read_text()
    vial_text = (SWEEP_LAYOUTS / "boards" / vial / "vial.json").read_text()
    return client.post("/api/boards", json={"name": name, "vil": vil_text, "vial": vial_text})


def rows(db_path, sql):
    with sqlite3.connect(db_path) as db:
        return db.execute(sql).fetchall()


# The tables of a database from before keybr was the typing app, each with one row. The columns
# are fewer than they were: only the table names matter.
PRACTICE_SCHEMA = """
CREATE TABLE board (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, vial TEXT NOT NULL);
CREATE TABLE keymap_version (hash TEXT PRIMARY KEY, board INTEGER NOT NULL, vil TEXT NOT NULL);
CREATE TABLE session (id INTEGER PRIMARY KEY, started TEXT NOT NULL, keymap_version TEXT);
CREATE TABLE source (id INTEGER PRIMARY KEY, title TEXT NOT NULL);
CREATE TABLE passage (id INTEGER PRIMARY KEY, text TEXT NOT NULL);
CREATE TABLE drill (passage INTEGER PRIMARY KEY);
CREATE TABLE unlock (letter_layout TEXT NOT NULL, key TEXT NOT NULL);
CREATE TABLE lesson (id INTEGER PRIMARY KEY, topic TEXT NOT NULL);
CREATE TABLE spend (lesson INTEGER NOT NULL, dollars REAL NOT NULL);
CREATE INDEX passage_source ON passage (text);
CREATE TABLE attempt (session INTEGER NOT NULL, ord INTEGER NOT NULL, PRIMARY KEY (session, ord)) WITHOUT ROWID;
CREATE TABLE key_event (session INTEGER NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (session, seq)) WITHOUT ROWID;
CREATE INDEX key_event_attempt ON key_event (session);
INSERT INTO board VALUES (1, 'Sweep', '{}');
INSERT INTO keymap_version VALUES ('abc', 1, '{}');
INSERT INTO session VALUES (1, '2026-11-01', 'abc');
INSERT INTO source VALUES (1, 'A book');
INSERT INTO passage VALUES (1, 'It is a truth');
INSERT INTO drill VALUES (1);
INSERT INTO unlock VALUES ('free-range', 'a');
INSERT INTO lesson VALUES (1, 'decorators');
INSERT INTO spend VALUES (1, 0.002);
INSERT INTO attempt VALUES (1, 0);
INSERT INTO key_event VALUES (1, 0);
"""


def test_the_first_start_deletes_every_table_but_the_boards_and_keymap_versions_and_keeps_their_rows(
    db_path, settings_path, recordings
):
    with sqlite3.connect(db_path) as db:
        db.executescript(PRACTICE_SCHEMA)

    create_app(db_path, settings_path, recordings)

    assert rows(db_path, "SELECT type, name FROM sqlite_schema ORDER BY name") == [
        ("table", "board"),
        ("table", "keymap_version"),
        ("index", "sqlite_autoindex_board_1"),
        ("index", "sqlite_autoindex_keymap_version_1"),
    ]
    assert rows(db_path, "SELECT * FROM board") == [(1, "Sweep", "{}")]
    assert rows(db_path, "SELECT * FROM keymap_version") == [("abc", 1, "{}")]


def test_a_missing_settings_file_is_created_with_defaults_and_comments(client, settings_path):
    assert settings_path.read_text() == DEFAULT_SETTINGS
    assert "# " in DEFAULT_SETTINGS


# The settings file of the last typokiller with a typing page, with changed [lists] and [keymaps].
OLD_SETTINGS_FILE = """\
# typokiller settings. Edit this file, or press , in the app's Escape menu.

[typing]
# What a wrong key does.
wrong_key_mode = "keep typing"

[passages]
max_dropped = 0.05

[weakness]
model = "recent-cost-v1"

[drills]
generator = "density-v1"

[symbols]
weak = 2

[unlocking]
letter_layout = "free-range"

[lists]
# The letters that label the items of a list.
letters = "asdf"  # my letters

[keymaps]
# The layer names in Keymap drawings.

[keymaps.Sweep.QWERTY]
layers = ["Base", "Sym"]  # my names

[lessons]
cap = 5.0
"""


def test_at_start_the_settings_of_the_typing_page_are_removed_and_lists_and_keymaps_keep_their_values_and_comments(
    db_path, settings_path, recordings
):
    settings_path.write_text(OLD_SETTINGS_FILE)

    create_app(db_path, settings_path, recordings)

    assert settings_path.read_text() == """\
# typokiller settings. Edit this file, or press , in the app's Escape menu.

[lists]
# The letters that label the items of a list.
letters = "asdf"  # my letters

[keymaps]
# The layer names in Keymap drawings.

[keymaps.Sweep.QWERTY]
layers = ["Base", "Sym"]  # my names

"""


def test_a_settings_file_with_a_missing_table_gets_it_with_its_comments(db_path, settings_path, recordings):
    settings_path.write_text('[keymaps.Sweep.QWERTY]\nlayers = ["Base"]\n')

    create_app(db_path, settings_path, recordings)

    text = settings_path.read_text()
    assert 'letters = "sadflewcmpgh"' in text and "# The letters that label" in text
    assert 'layers = ["Base"]' in text


def test_the_first_page_says_that_typing_has_moved_and_links_to_the_typing_page(client):
    page = client.get("/").text

    assert re.findall(r"<p>(.*)</p>", page) == ['Typing has moved to <a id="typing" href="http://localhost:3100/">the typing page</a>.']
    assert "document.getElementById('typing').hostname = location.hostname;" in page


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
    """The Keymap drawing of a .vil from the fixtures as an XML tree. `change` may edit the .vil first."""
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



def test_each_keymap_has_its_letter_layout_and_version(client):
    add_board(client, "Sofle", "sofle.vil", "sofle")
    add_board(client, "Sweep", "ferris_sweep_qwerty.vil", "sweep")
    add_board(client, "Sweep", "ferris_sweep_freerange.vil", "sweep")
    add_board(client, "Q4", "q4.vil", "q4")

    boards = client.get("/api/boards").json()["boards"]
    assert [(b["name"], [k["letter_layout"] for k in b["keymaps"]]) for b in boards] == [
        ("Sofle", ["free-range"]),
        ("Sweep", ["QWERTY", "free-range"]),
        ("Q4", ["QWERTY"]),
    ]
    vil = (SWEEP_LAYOUTS / "vil" / "ferris_sweep_freerange.vil").read_text()
    assert boards[1]["keymaps"][1]["version"] == hashlib.sha256(vil.encode()).hexdigest()


# The keyboard export, which keybr reads each time its typing page loads. The Boards are those of
# keybr's import fixture: the Sweep (QWERTY, then free-range), the Sofle and the Q4.
EXPORT_SETTINGS = """\
[keymaps.Sweep.QWERTY]
layers = ["Base", "Sym", "Nav", "Stack", "Num"]

[keymaps.Q4.QWERTY]
layers = ["Base", "Fn"]
"""


@pytest.fixture
def exporting(client, settings_path):
    settings_path.write_text(EXPORT_SETTINGS)
    add_board(client, "Sweep", "ferris_sweep_qwerty.vil", "sweep")
    add_board(client, "Sweep", "ferris_sweep_freerange.vil", "sweep")
    add_board(client, "Sofle", "sofle.vil", "sofle")
    add_board(client, "Q4", "q4.vil", "q4")
    return client


def without_time(export):
    return {name: value for name, value in export.items() if name != "exportedAt"}


def test_the_keyboard_export_matches_keybrs_initial_import_fixture(exporting):
    export = exporting.get("/api/keyboards/export").json()

    assert without_time(export) == without_time(keyboard_export("initial.json"))
    assert datetime.fromisoformat(export["exportedAt"]).utcoffset() == timedelta(0)
    assert export["exportedAt"].endswith("Z")


def test_after_a_new_vial_json_a_new_vil_and_new_layer_names_the_export_matches_keybrs_updated_fixture(
    exporting, settings_path
):
    updated = keyboard_export("updated.json")
    sweep = updated["boards"][0]
    exporting.post("/api/boards", json={"name": "Sweep", "vial": sweep["vial"], "vil": sweep["keymaps"][2]["vil"]})
    # The settings file is read again for each export.
    settings_path.write_text(EXPORT_SETTINGS.replace('"Sym"', '"Symbols"'))

    assert without_time(exporting.get("/api/keyboards/export").json()) == without_time(updated)


def test_the_vil_and_vial_texts_are_exported_exactly_as_stored(exporting):
    # A .vil uid can be larger than JavaScript's safe integers, so the text must not be parsed and written again.
    odd = (SWEEP_LAYOUTS / "vil" / "sofle.vil").read_text().replace('{"version": 1,', '{ "version":   1,')
    assert '"uid": 13865123068767927988' in odd
    vial = (SWEEP_LAYOUTS / "boards" / "sofle" / "vial.json").read_text()
    exporting.post("/api/boards", json={"name": "Sofle", "vial": vial, "vil": odd})

    sofle = exporting.get("/api/keyboards/export").json()["boards"][1]

    assert sofle["vial"] == vial
    assert sofle["keymaps"][-1]["vil"] == odd


def test_the_options_give_the_port_whether_the_access_log_is_on_and_the_recordings(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert vars(options([])) == {
        "port": 8000,
        "access_log": True,
        "recordings": tmp_path / ".local/share/keybr/data/recordings.sqlite",
    }
    assert vars(options(["--port", "8001", "--no-access-log", "--recordings", "backup.sqlite"])) == {
        "port": 8001,
        "access_log": False,
        "recordings": Path("backup.sqlite"),
    }


def text(html):
    return re.sub(r"<[^>]+>", "", html)


def test_the_analysis_page_is_at_analysis(client):
    page = client.get("/analysis")
    assert page.status_code == 200 and "analysis.js" in page.text


def test_with_no_recordings_or_no_attempts_the_page_says_to_type_on_the_typing_page(client, recordings):
    expected = "No lessons recorded yet. Type on the typing page, then reload this page."
    found = client.get("/api/analysis").json()
    assert text(found["message"]) == expected and 'href="http://localhost:3100/"' in found["message"]
    assert found.keys() == {"message"}

    build_recordings(recordings, [])
    assert text(client.get("/api/analysis").json()["message"]) == expected


def test_with_newer_recordings_the_page_says_to_update_typokiller(client, recordings):
    build_recordings(recordings, attempt(1, 0, "ab"))
    change(recordings, "PRAGMA user_version = 3")

    found = client.get("/api/analysis").json()["message"]

    assert text(found) == "The recorded lessons are newer than this version of typokiller. Run typokiller-service update."


def test_the_page_reads_the_recordings_each_time_and_draws_the_weakest_pair_as_an_arc(client, recordings):
    yesterday = (datetime.now(UTC) - ORIGIN) / timedelta(days=1) - 1
    sweep = keymap_snapshot(keyboard_export(), "Sweep", "QWERTY")
    typed = [attempt(1, yesterday - 1, "ab"), attempt(2, yesterday, "abc" * 20, keymap=sweep, wpm=40)]
    build_recordings(recordings, typed[0], keymap=None)

    assert client.get("/api/analysis").json()["entries"] == ["no keyboard · en-free-range"]
    recordings.unlink()
    build_recordings(recordings, typed[0] + typed[1], keymap=None)
    found = client.get("/api/analysis").json()

    assert found["entries"] == ["Sweep · QWERTY", "no keyboard · en-free-range"] and found["entry"] == "Sweep · QWERTY"
    assert (found["weeks"], found["days"]) == (13, 1)
    assert found["names"] == ["Base", "Sym", "Nav", "Stack", "Num"] and len(found["layers"]) == 5
    assert [p["unit"] for p in found["pairs"]] == ["ab", "bc"] and [c["unit"] for c in found["chars"]] == ["a", "b", "c"]
    assert 'data-pair="ab"' in found["layers"][0] and 'data-pair="bc"' in found["layers"][0]
    assert found["trend"]["$schema"].startswith("https://vega.github.io/schema/vega-lite/")

    # A layout with no keyboard has no picture.
    other = client.get("/api/analysis", params={"entry": "no keyboard · en-free-range"}).json()
    assert other["entry"] == "no keyboard · en-free-range" and other["layers"] == other["names"] == []


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
    pairs = ["ek", "ee", "()", "e(", " e"]
    base = drawing("ferris_sweep_qwerty.vil", "sweep", 0, NAMES, pairs=pairs)
    sym = drawing("ferris_sweep_qwerty.vil", "sweep", 1, NAMES, pairs=pairs)

    arcs = base.findall(".//*[@class='arc']")
    # ( and ) are on Sym, so their arcs are not on the base layer.
    # The keys of e( are on two layers, so it has no arc.
    assert [a.get("data-pair") for a in arcs] == ["ek", "ee", " e"]
    assert "".join(arcs[2].itertext()) == "␣e"
    assert [a.get("data-pair") for a in sym.findall(".//*[@class='arc']")] == ["()"]
    x, y, _, _, x_end, y_end = [float(v) for v in re.findall(r"-?[\d.]+", arcs[0][0].get("d") or "")]
    (x1, y1), (x2, y2) = centre(base, "0,2"), centre(base, "5,2")
    assert (x, y, x_end, y_end) == pytest.approx((x1, y1 - 0.25, x2, y2 - 0.25))

