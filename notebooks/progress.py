import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")

with app.setup:
    import json
    import sqlite3
    from datetime import UTC, datetime, timedelta
    from pathlib import Path

    import marimo as mo
    import polars as pl

    from typokiller.analysis import ALIGNMENT, TREND_WEEKS, progress, rank_units, trend_chart, units, unlocking
    from typokiller.app import layer_names, read_settings
    from typokiller.drawing import draw_layers, layer_name, show_chars
    from typokiller.keymap import keymap_letters
    from typokiller.service import data_folder, notebook_db


@app.cell
def _():
    mo.md("""
    # Progress

    The progress page of one Board × Letter layout, made with the same functions as the
    app, so the numbers are the same. Then the Weakness costs split by layer.
    """)
    return


@app.cell
def _():
    # To use another database: uv run marimo edit notebooks/progress.py -- --db other.db
    # The settings are typokiller.toml next to it, as for the server.
    path = Path(mo.cli_args().get("db") or notebook_db(data_folder()))
    print(f"Database: {path.resolve()}")
    return (path,)


@app.cell
def _(path):
    mo.stop(not path.exists(), mo.md(f"There is no database at `{path.resolve()}`."))
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)  # read only
    settings = read_settings(path.with_name("typokiller.toml")).unwrap()
    return db, settings


@app.cell
def _(db):
    # Each Board × Letter layout with its newest Keymap version, as on the progress page.
    # The one of the last Session is chosen first.
    keymaps, _last_session = {}, {}
    for _board, _vil, _vial, _last in db.execute(
        "SELECT b.name, k.vil, b.vial, (SELECT max(id) FROM session WHERE keymap_version = k.hash)"
        " FROM keymap_version k JOIN board b ON b.id = k.board ORDER BY k.rowid"  # oldest version first
    ):
        _letters = keymap_letters(_vil, _vial)
        _label = f"{_board} · {_letters}"
        keymaps[_label] = (_board, _letters, _vil, _vial)
        _last_session[_label] = max(_last or 0, _last_session.get(_label, 0))
    mo.stop(not keymaps, mo.md("The database has no Boards yet."))
    keymap = mo.ui.dropdown(keymaps, value=max(_last_session, key=lambda label: _last_session[label]), label="Board · Letter layout")
    keymap
    return (keymap,)


@app.cell
def _(db, keymap, settings):
    board, letters, vil, vial = keymap.value
    found = progress(db, board, letters, settings["weakness"])
    model = settings["weakness"]["model"]
    names = layer_names(settings, board, letters)
    state = unlocking(db, letters, settings["unlocking"])
    locked = state.locked if state else ""
    mo.md(f"""
    ## {board} · {letters}

    Alignment: `{ALIGNMENT}` · Weakness model: `{model}`, over the last {settings["weakness"]["weeks"]} weeks
    """)
    return board, found, letters, locked, model, names, vial, vil


@app.cell
def _(found):
    mo.vstack([
        mo.md(f"""
        ### Trend

        WPM and first-time accuracy: the median of each day's finished Attempts over the
        last {TREND_WEEKS} weeks ({found.trend.height} days).
        """),
        trend_chart(found.trend),
    ])
    return


@app.cell
def _(found):
    weakest = ["unit", "cost", "seen", "model"]
    mo.hstack(
        [
            mo.vstack([mo.md("### Weakest characters"), mo.ui.table(found.chars.select(weakest), selection=None)]),
            mo.vstack([mo.md("### Weakest pairs"), mo.ui.table(found.pairs.select(weakest), selection=None)]),
        ],
        widths="equal",
    )
    return


@app.cell
def _(found):
    pair = mo.ui.dropdown(
        {show_chars(p): p for p in found.pairs["unit"]},
        value=found.pairs["unit"].first(),
        label="Pair drawn as an arc",
    )
    pair
    return (pair,)


@app.cell
def _(found, locked, names, pair, vial, vil):
    layers = draw_layers(vil, vial, names, found.heat, [pair.value] if pair.value else [], locked)
    mo.vstack([
        mo.md("### Keymap heat drawing"),
        mo.ui.tabs({
            f"{layer} {name}": mo.Html(f'<div style="max-width: 46rem">{svg}</div>')
            for layer, (name, svg) in enumerate(layers)
        }),
    ])
    return


@app.cell
def _(board, db, letters, model, names, settings, vil):
    # The split: the Weakness model ranks the keystrokes of each layer on their own, from
    # the same rows of `units` that `weakness` ranks together. A keystroke's layer is the
    # layer of the key picked for it, so a pair is on the layer of its second character.
    # Characters that no key types have no layer and are left out.
    since = datetime.now(UTC) - timedelta(weeks=settings["weakness"]["weeks"])
    typed = units(db, board, letters, since).drop_nulls("layer")
    mo.stop(typed.is_empty(), mo.md("No keystrokes on this Keymap in the Weakness model's weeks."))
    parsed = json.loads(vil)
    split = (
        pl.concat([
            rank_units(rows, settings["weakness"]).with_columns(
                layer=pl.lit(layer, pl.Int64), name=pl.lit(layer_name(parsed, layer, names))
            )
            for (layer,), rows in typed.partition_by("layer", as_dict=True).items()
        ])
        .sort(["layer", "cost", "unit"], descending=[False, True, False])
        .select("layer", "name", pl.exclude("layer", "name"))
    )
    by_layer = (
        split.group_by("layer", "name")
        .agg(
            units=pl.len(),
            median_cost=pl.col("cost").median(),
            weakest=pl.col("unit").sort_by(["cost", "unit"], descending=[True, False]).head(5),
        )
        .sort("layer")
    )
    mo.vstack([
        mo.md(f"""
        ### Weakness by layer

        `{model}` costs in ms, ranked within each layer.
        """),
        mo.ui.table(by_layer, selection=None),
        mo.ui.table(split, selection=None),
    ])
    return (split,)


if __name__ == "__main__":
    app.run()
