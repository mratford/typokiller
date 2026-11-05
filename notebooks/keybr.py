import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")

with app.setup:
    import json
    from datetime import date
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import polars as pl

    from typokiller.analysis import WEAKNESS_MODELS, rank_units
    from typokiller.drawing import Heat, draw_layers, layer_name, show_chars
    from typokiller.keybr_analysis import (
        ANALYSIS,
        exclusions,
        first_input_accuracy,
        native_scores,
        observations,
        units,
    )
    from typokiller.recording import RecordingError, read_recordings
    from typokiller.service import recordings_path


@app.cell
def _():
    mo.md("""
    # keybr recordings

    The Attempts that keybr recorded in detail, read once when this cell runs, read only, with the
    analysis method `keybr-input-v1`. The keyboards come from the recordings too. keybr's own scores
    are shown apart, labelled "keybr".
    """)
    return


@app.cell
def _():
    # keybr's live recordings file by default. To open another file, such as a backup:
    # uv run marimo edit notebooks/keybr.py -- --recordings other.sqlite
    # str(): the type of a command-line value is a string, a number, a boolean or a list.
    path = Path(str(mo.cli_args().get("recordings") or recordings_path()))
    print(f"Recordings: {path.resolve()}")
    return (path,)


@app.cell
def _(path):
    mo.stop(
        not path.exists(),
        mo.md(f"""
        There are no keybr recordings at `{path.resolve()}`. keybr writes them when detailed
        recording is on: see `keybr/docs/detailed_recording.md`.
        """),
    )
    try:
        recording = read_recordings(path)
        _error = None
    except RecordingError as e:
        recording, _error = None, str(e)
    mo.stop(recording is None, mo.md(f"The recordings cannot be read: {_error}"))
    assert recording is not None
    observed = observations(recording)
    excluded = exclusions(recording)
    native = native_scores(recording)
    return excluded, native, observed, recording


@app.cell
def _(recording):
    # The filters. A keymap version is one saved .vil with its keyboard and layer names, labelled
    # with the first 8 characters of the .vil's sha256 and the date it was first imported.
    _attempts = recording.attempts
    _boards = sorted(b for b in _attempts["board_id"].unique() if b is not None)
    _letters = sorted(x for x in _attempts["letter_layout"].unique() if x is not None)
    _versions = {}
    for _row in recording.keyboards.iter_rows(named=True):
        if _row["keymap_version"] in set(_attempts["keymap_version"]):
            _imported = _row["imported_at"].date().isoformat() if _row["imported_at"] else "no import date"
            _label = f"{_row['keymap_id']} · {(_row['vil_hash'] or '?')[:8]} · {_imported}"
            _versions[_label] = _row["keymap_version"]
    _days = [d for d in _attempts["started"].dt.date() if d is not None] or [date.today()]
    board = mo.ui.dropdown({"every keyboard": None} | {b: b for b in _boards}, value="every keyboard", label="Board")
    letter_layout = mo.ui.dropdown({"every layout": None} | {x: x for x in _letters}, value="every layout", label="Letter layout")
    keymap_version = mo.ui.dropdown({"every version": None} | _versions, value="every version", label="Keymap version")
    days = mo.ui.date_range(start=min(_days), stop=max(_days), value=(min(_days), max(_days)), label="Days")
    mo.hstack([board, letter_layout, keymap_version, days], justify="start")
    return board, days, keymap_version, letter_layout


@app.cell
def _(board, days, excluded, keymap_version, letter_layout, native, observed, recording):
    # The Attempts that the filters keep, and their rows of each table.
    _start, _stop = days.value
    _keep = pl.col("started").dt.date().is_between(_start, _stop) | pl.col("started").is_null()
    for _column, _choice in [("board_id", board), ("letter_layout", letter_layout), ("keymap_version", keymap_version)]:
        if _choice.value is not None:
            _keep = _keep & (pl.col(_column) == _choice.value)
    chosen = recording.attempts.filter(_keep)
    _ids = chosen["attempt"].implode()
    chosen_observed = observed.filter(pl.col("attempt").is_in(_ids))
    chosen_native = native.filter(pl.col("attempt").is_in(_ids))
    chosen_excluded = excluded.filter(pl.col("attempt").is_in(_ids))
    mo.md(f"{chosen.height} of {recording.attempts.height} Attempts, with {chosen_observed.height} observations.")
    return chosen, chosen_excluded, chosen_native, chosen_observed


@app.cell
def _(chosen_native, chosen_observed):
    # Native progress: keybr's own speed and accuracy of completed Attempts. First-input accuracy
    # (keybr-input-v1) is shown in its own chart, over every Attempt that has observations.
    def by_day(rows, columns):
        return (
            rows.with_columns(day=pl.col("started").dt.date())
            .group_by("day")
            .agg(*[pl.col(c).median() for c in columns], attempts=pl.len())
            .sort("day")
        )

    _native = by_day(chosen_native, ["wpm", "accuracy"])
    _first = by_day(first_input_accuracy(chosen_observed), ["accuracy"])
    _base = alt.Chart().mark_line(point=True).encode(x=alt.X("day:T", title=None)).properties(width=300, height=140)
    mo.vstack([
        mo.md("""
        ### Progress

        **keybr's own** speed (WPM, from keybr's characters per minute / 5) and accuracy: the median
        of each day's completed Attempts. Then the **first-input accuracy (keybr-input-v1)**: the
        median of each day's share of positions whose first input was correct, abandoned Attempts too.
        """),
        alt.hconcat(
            _base.encode(y=alt.Y("wpm:Q", title="keybr WPM", scale=alt.Scale(zero=False))).properties(data=_native),
            _base.encode(y=alt.Y("accuracy:Q", title="keybr accuracy", axis=alt.Axis(format=".0%"))).properties(data=_native),
            _base.encode(
                y=alt.Y("accuracy:Q", title="first-input accuracy (keybr-input-v1)", axis=alt.Axis(format=".0%"))
            ).properties(data=_first),
        ).configure(background="transparent"),
        mo.ui.table(_native, selection=None, label="keybr, by day"),
    ])
    return


@app.cell
def _():
    min_seen = mo.ui.number(start=1, stop=1000, value=5, label="Seen at least (times)")
    mo.hstack([min_seen], justify="start")
    return (min_seen,)


@app.cell
def _(chosen_observed, min_seen):
    # The Weakness model of typokiller, run on the keybr-input-v1 observations.
    model = "recent-cost-v1"
    typed = units(chosen_observed)
    ranking = rank_units(typed, {"model": model, "min_seen": min_seen.value})
    _length = pl.col("unit").str.len_chars()
    _weakest = ["unit", "cost", "time", "error_rate", "fix_ms", "seen"]
    _fixes = (
        chosen_observed.filter(pl.col("status") == "error")
        .group_by("char")
        .agg(errors=pl.len(), fixed=pl.col("fix_ms").count(), median_fix_ms=pl.col("fix_ms").median())
        .with_columns(unresolved=pl.col("errors") - pl.col("fixed"))
        .sort(["errors", "char"], descending=[True, False])
    )
    mo.vstack([
        mo.md(f"""
        ### Weakest characters and pairs

        `{model}` costs in ms, from the `{ANALYSIS}` observations. Unresolved Errors have no fix time.
        """),
        mo.hstack(
            [
                mo.ui.table(ranking.filter(_length == 1).select(_weakest), selection=None, label="characters"),
                mo.ui.table(ranking.filter(_length == 2).select(_weakest), selection=None, label="pairs"),
            ],
            widths="equal",
        ),
        mo.md("### Correction times\n\nThe median fix time of each character's Errors, and how many were never fixed by a correct input."),
        mo.ui.table(_fixes, selection=None),
    ])
    return model, ranking, typed


@app.cell
def _(chosen_observed):
    # Timing distributions. Each measure has its own rules for when it is known; see keybr_analysis.observations.
    _long = chosen_observed.unpivot(["time", "dwell", "flight"], index=["char", "timing_source"]).drop_nulls("value")
    mo.vstack([
        mo.md(f"### Timing distributions\n\n{_long.height} timed values (ms), from `{ANALYSIS}`."),
        alt.Chart(_long)
        .mark_bar()
        .encode(
            x=alt.X("value:Q", bin=alt.Bin(maxbins=40), title="ms"),
            y=alt.Y("count():Q", title=None),
            color=alt.Color("timing_source:N", title="timed from"),
        )
        .properties(width=220, height=120)
        .facet(column=alt.Column("variable:N", title=None))
        .configure(background="transparent"),
    ])
    return


@app.cell
def _(chosen, recording):
    # The saved Keymap to draw: the newest keymap version of the chosen Attempts.
    _versions = chosen.drop_nulls("keymap_version").sort("started")["keymap_version"]
    _found = recording.keyboards.filter(pl.col("keymap_version") == _versions.last()) if _versions.len() else None
    mo.stop(
        _found is None or _found.is_empty() or _found["vil"][0] is None,
        mo.md("No saved Keymap to draw: these Attempts name no imported keyboard."),
    )
    assert _found is not None
    keyboard = _found.row(0, named=True)
    return (keyboard,)


@app.cell
def _(chosen_observed, keyboard, model, ranking, typed):
    names = keyboard["layers"] or []
    _mine = typed.filter(pl.col("keymap_version") == keyboard["keymap_version"])
    _seen = _mine.group_by("unit").agg(seen=pl.col("first_time_correct").count())
    _heat = Heat(dict(zip(ranking["unit"], ranking["cost"])), dict(zip(_seen["unit"], _seen["seen"])), WEAKNESS_MODELS[model].scale)
    _pairs = ranking.filter(pl.col("unit").str.len_chars() == 2)["unit"].head(1).to_list()
    layers = draw_layers(keyboard["vil"], keyboard["vial"], names, _heat, _pairs)
    _parsed = json.loads(keyboard["vil"])
    _kinds = (
        chosen_observed.filter(pl.col("keymap_version") == keyboard["keymap_version"])
        .group_by("inferred_layer", "inferred_kind")
        .agg(
            observations=pl.len(),
            first_input_accuracy=pl.col("first_time_correct").mean(),
            median_time=pl.col("time").median(),
            median_dwell=pl.col("dwell").median(),
        )
        .with_columns(
            layer_name=pl.col("inferred_layer").map_elements(lambda n: layer_name(_parsed, n, names), return_dtype=pl.String)
        )
        .sort("inferred_layer", "inferred_kind", nulls_last=True)
    )
    mo.vstack([
        mo.md(f"""
        ### Layers and key kinds: {keyboard["keymap_id"]} · {(keyboard["vil_hash"] or "")[:8]}

        The heat drawing of the saved Keymap, with `{model}` costs, and the weakest pair
        {", ".join(show_chars(p) for p in _pairs) or "(none)"} as an arc. The layer and key kind of
        each observation are inferred from the .vil, not measured.
        """),
        mo.ui.tabs({
            f"{layer} {name}": mo.Html(f'<div style="max-width: 46rem">{svg}</div>')
            for layer, (name, svg) in enumerate(layers)
        }),
        mo.ui.table(_kinds, selection=None),
    ])
    return (layers,)


@app.cell
def _(chosen, chosen_excluded):
    # Recording completeness: what each Attempt's status is, and what the observations leave out.
    completeness = (
        chosen.group_by("status")
        .agg(
            attempts=pl.len(),
            interrupted=pl.col("interrupted").sum(),
            incomplete_flag=pl.col("incomplete").sum(),
            no_end=(~pl.col("has_end")).sum(),
            sequence_gaps=pl.col("sequence_gaps").sum(),
            broken_links=pl.col("broken_links").sum(),
            discontinuous_states=pl.col("discontinuous_states").sum(),
            missing_releases=pl.col("missing_releases").sum(),
        )
        .sort("status")
    )
    _counts = ["inputs", "skipped", "recovered", "off_track", "ignored", "ambiguous", "composed", "missing_releases", "not_timed"]
    _totals = chosen_excluded.select([pl.col(c).sum() for c in _counts])
    mo.vstack([
        mo.md("""
        ### Recording completeness

        Attempts by status. "unreadable" Attempts (no start record) give no observations.
        Missing releases are never invented: their presses have no dwell.
        """),
        mo.ui.table(completeness, selection=None),
        mo.md(f"""
        What the `{ANALYSIS}` observations leave out or do not time, over these Attempts: skipped
        characters (put in by keybr with no input), recovered Errors (accepted by keybr with no
        correct input), off-track inputs, ignored inputs, ambiguous key presses, composed inputs,
        missing releases and correct observations with no time.
        """),
        mo.ui.table(_totals, selection=None),
        mo.ui.table(chosen.filter(pl.col("status") != "complete").select(
            "attempt", "started", "status", "end_reason", "interrupted", "incomplete", "has_end", "sequence_gaps", "missing_releases"
        ), selection=None, label="Attempts that are not complete"),
    ])
    return (completeness,)


if __name__ == "__main__":
    app.run()
