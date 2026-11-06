import argparse
import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import altair as alt
import polars as pl
import tomlkit
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from typokiller.drawing import draw_layers
from typokiller.keyboard_export import export_keyboards
from typokiller.keybr_analysis import TREND_WEEKS, analysis_page
from typokiller.keymap import keymap_letters
from typokiller.recording import NewerRecordings, read_recordings
from typokiller.service import recordings_path

STATIC = Path(__file__).parent / "static"

SCHEMA = """
CREATE TABLE IF NOT EXISTS board (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, vial TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS keymap_version (hash TEXT PRIMARY KEY, board INTEGER NOT NULL, vil TEXT NOT NULL, saved TEXT);
"""

# The tables of typokiller's own practice, from before keybr was the typing app (ADR 0004).
# A database made then loses them at the first start.
PRACTICE_TABLES = ["session", "source", "passage", "drill", "unlock", "lesson", "spend", "attempt", "key_event"]

# Written to the settings file when it is missing.
DEFAULT_SETTINGS = """\
# typokiller settings. Edit this file in any editor.

[lists]
# The letters that label the items of a list, such as the list of Keymaps in the keyboards
# panel. An item is chosen by typing its label. The first items get one letter, in this order,
# and the others two. j, k, n, v, r and b, the keys of the keyboards panel, are never labels.
letters = "sadflewcmpgh"

[keymaps]
# The layer names in Keymap drawings, for each Board and Letter layout. A layer with no
# name is named after the key that opens it. Put a Board name with spaces in quotes,
# such as [keymaps."Q3 Max".QWERTY]. For example:
# [keymaps.Sweep.QWERTY]
# layers = ["Base", "Sym", "Nav", "Stack", "Num"]
"""

# The settings tables of typokiller's own practice. A file made then loses them.
PRACTICE_SETTINGS = ["typing", "passages", "weakness", "drills", "symbols", "unlocking", "lessons"]


def read_settings(path: Path) -> tomlkit.TOMLDocument:
    if not path.exists():
        path.write_text(DEFAULT_SETTINGS)
    doc = tomlkit.parse(path.read_text())
    # A file made by an older typokiller gets the tables added since, with their comments,
    # and the settings added since to its tables, without their comments. It loses the
    # tables of typokiller's own practice.
    text = tomlkit.dumps(doc)
    for name in PRACTICE_SETTINGS:
        doc.pop(name, None)
    for name, table in tomlkit.parse(DEFAULT_SETTINGS).items():
        if name not in doc:
            doc[name] = table
        doc[name].update({key: value for key, value in table.items() if key not in doc[name]})
    if tomlkit.dumps(doc) != text:
        path.write_text(tomlkit.dumps(doc))
    return doc


# What the analysis page shows in place of the analysis. The link to the typing page gets the
# page's host name.
NO_LESSONS = (
    'No lessons recorded yet. Type on <a class="typing" href="http://localhost:3100/">the typing page</a>,'
    " then reload this page."
)
NEWER = "The recorded lessons are newer than this version of typokiller. Run <code>typokiller-service update</code>."


def trend_chart(trend: pl.DataFrame) -> alt.HConcatChart:
    """The analysis page's chart of a trend of `keybr_analysis.analysis_page`, one point per day:
    WPM, and first-input accuracy beside it. The page gets it as a Vega-Lite spec."""
    base = alt.Chart(trend).mark_line(point=True).encode(x=alt.X("day:T", title=None)).properties(width=360, height=140)
    # Show whole WPM and whole percents. With one day of data, the axis range is very small.
    # tickMinStep keeps the ticks whole, so two ticks do not get the same rounded label.
    return alt.hconcat(
        base.encode(y=alt.Y("wpm:Q", title="WPM", scale=alt.Scale(zero=False), axis=alt.Axis(format="d", tickMinStep=1))),
        base.encode(
            y=alt.Y(
                "accuracy:Q",
                title="first-input accuracy",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(format=".0%", tickMinStep=0.01),
            )
        ),
    ).configure(background="transparent")


class NewBoard(BaseModel):
    name: str
    vil: str  # the text of the .vil file
    vial: str  # the text of the vial.json file


class NewKeymap(BaseModel):
    vil: str  # the text of the .vil file


class LayerNames(BaseModel):
    board: str  # the Board's name
    letter_layout: str
    layers: list[str]


def create_app(db_path: Path, settings_path: Path, recordings: Path) -> FastAPI:
    db = sqlite3.connect(db_path, check_same_thread=False)
    with db:
        for table in PRACTICE_TABLES:
            db.execute(f"DROP TABLE IF EXISTS {table}")
    db.executescript(SCHEMA)
    # A database made before this column has no dates for the .vil files stored then.
    if "saved" not in [column for _, column, *_ in db.execute("PRAGMA table_info(keymap_version)")]:
        db.execute("ALTER TABLE keymap_version ADD COLUMN saved TEXT")
    read_settings(settings_path)

    app = FastAPI()

    # Stores a .vil of a Board, with the date. A .vil that is already stored changes nothing.
    # Its Letter layout tells whether it is a new Keymap or a new version of one.
    def save_vil(board: int, vil: str) -> dict[str, str]:
        with db:
            db.execute(
                "INSERT OR IGNORE INTO keymap_version VALUES (?, ?, ?, ?)",
                (hashlib.sha256(vil.encode()).hexdigest(), board, vil, datetime.now().date().isoformat()),
            )
            (vial,) = db.execute("SELECT vial FROM board WHERE id = ?", (board,)).fetchone()
        return {"letter_layout": keymap_letters(vil, vial)}

    # Adding a Board with a name that exists adds the .vil to that Board and
    # replaces its vial.json.
    @app.post("/api/boards")
    async def add_board(new: NewBoard):
        with db:
            (board,) = db.execute(
                "INSERT INTO board (name, vial) VALUES (?, ?)"
                " ON CONFLICT (name) DO UPDATE SET vial = excluded.vial RETURNING id",
                (new.name, new.vial),
            ).fetchone()
        return save_vil(board, new.vil)

    @app.post("/api/boards/{board}/keymaps")
    async def add_keymap(board: int, new: NewKeymap):
        return save_vil(board, new.vil)

    # What the keyboards panel shows: the Boards of the keyboard export, with their Keymaps in
    # the order they were first added. A Keymap is a Board with one Letter layout; its versions
    # are the .vil files with that Letter layout. Each Keymap has the number of its versions, the
    # date of the newest, and the layer names and plain Keymap drawings of the newest. `names` are
    # the names drawn, and `layer_names` only those in the settings file. `letters` label the list.
    @app.get("/api/boards")
    async def boards():
        settings = read_settings(settings_path)
        saved = dict(db.execute("SELECT hash, saved FROM keymap_version"))
        found = []
        for board in export_keyboards(db, settings)["boards"]:
            versions: dict[str, list[dict]] = {}
            for version in board["keymaps"]:  # oldest first
                versions.setdefault(version["letterLayout"], []).append(version)
            keymaps = []
            for letters, same in versions.items():
                newest = same[-1]
                layers = draw_layers(newest["vil"], board["vial"], newest["layers"])
                keymaps.append({
                    "letter_layout": letters,
                    "versions": len(same),
                    "saved": saved[newest["sourceHash"]],
                    "names": [name for name, _ in layers],
                    "layer_names": newest["layers"],
                    "layers": [svg for _, svg in layers],
                })
            found.append({"id": board["sourceId"], "name": board["name"], "keymaps": keymaps})
        return {"letters": settings["lists"]["letters"], "boards": found}

    # Writes the layer names of a Keymap to the settings file. The other settings and the
    # comments stay.
    @app.put("/api/layers", status_code=204)
    async def save_layers(names: LayerNames):
        doc = read_settings(settings_path)
        board = doc["keymaps"].setdefault(names.board, tomlkit.table(True))
        board.setdefault(names.letter_layout, tomlkit.table())["layers"] = names.layers
        settings_path.write_text(tomlkit.dumps(doc))

    @app.get("/")
    async def first_page():
        return RedirectResponse("/analysis")

    # keybr reads this each time its typing page loads (see `keyboard_export`).
    @app.get("/api/keyboards/export")
    async def keyboards_export():
        return export_keyboards(db, read_settings(settings_path))

    @app.get("/analysis")
    async def analysis_html():
        return FileResponse(STATIC / "analysis.html")

    # The analysis page of one entry (see `keybr_analysis.analysis_page`), or of the first when
    # `entry` is none. It reads the keybr recordings each time. With no analysis to show, only
    # a message. Each layer's keyboard picture has an arc for each of the weakest pairs.
    @app.get("/api/analysis")
    def analysis(entry: str | None = None):
        try:
            page = analysis_page(read_recordings(recordings), entry, datetime.now(UTC)) if recordings.is_file() else None
        except NewerRecordings:
            return {"message": NEWER}
        if page is None:
            return {"message": NO_LESSONS}
        layers = []
        if page.keyboard:
            k = page.keyboard
            layers = draw_layers(k["vil"], k["vial"], k["layers"] or [], page.heat, page.pairs["unit"].to_list())
        weakest = ["unit", "cost", "seen"]
        return {
            "entries": page.entries,
            "entry": page.entry,
            "weeks": TREND_WEEKS,
            "days": page.trend.height,
            "trend": trend_chart(page.trend).to_dict(),
            "names": [name for name, _ in layers],
            "layers": [svg for _, svg in layers],
            "chars": page.chars.select(weakest).to_dicts(),
            "pairs": page.pairs.select(weakest).to_dicts(),
        }

    app.mount("/", StaticFiles(directory=STATIC, html=True))
    return app


def options(args: list[str] | None = None) -> argparse.Namespace:
    """The command-line options: `port`, `access_log` and `recordings`. `args` is sys.argv[1:] when None."""
    parser = argparse.ArgumentParser(prog="typokiller")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--recordings", type=Path, default=recordings_path(), help="the keybr recordings to analyse")
    parser.add_argument("--no-access-log", dest="access_log", action="store_false", help="log only errors and start-up")
    return parser.parse_args(args)


def main():
    opts = options()
    app = create_app(Path("typokiller.db"), Path("typokiller.toml"), opts.recordings)
    uvicorn.run(app, host="0.0.0.0", port=opts.port, access_log=opts.access_log)
