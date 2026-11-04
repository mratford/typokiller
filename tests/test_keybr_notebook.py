import importlib.util
import sys
from pathlib import Path

from keybr_snapshot import all_scenarios_snapshot

NOTEBOOK = Path(__file__).parents[1] / "notebooks" / "keybr.py"


def run_notebook(**defs):
    """Runs every cell of the keybr notebook, top to bottom, with `defs` set in place of the cells
    that define them. Raises if a cell fails. (A copy of run_notebook in test_app.py.)"""
    spec = importlib.util.spec_from_file_location("keybr_notebook", NOTEBOOK)
    assert spec and spec.loader
    notebook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notebook)
    return notebook.app.run(defs=defs)


def text_of(outputs):
    return " ".join(str(getattr(output, "text", "")) for output in outputs)


def test_the_notebook_runs_on_a_snapshot_without_typokiller_and_leaves_the_file_unchanged(tmp_path, monkeypatch):
    # No typokiller database anywhere: the notebook must not need one.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("typokiller.service.data_folder", lambda: tmp_path / "no-service")
    path = all_scenarios_snapshot(tmp_path / "keybr-recordings.sqlite")
    before = path.read_bytes()

    outputs, defs = run_notebook(path=path)

    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keybr-recordings.sqlite"]
    text = text_of(outputs)
    assert "keybr-input-v1" in text and "first-input accuracy" in text and "keybr's own" in text
    # Every Attempt of the fixtures is on the free-range Sweep, and the filters start with all of them.
    assert defs["chosen"].height == defs["recording"].attempts.height
    assert defs["completeness"]["attempts"].sum() == defs["recording"].attempts.height
    assert defs["layers"]  # one drawing per layer of the Sweep's saved Keymap


def test_the_notebook_opens_the_snapshot_given_with_snapshot_otherwise_the_one_in_this_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # The file does not exist, so the notebook stops after the cell that sets `path` and says how to make one.
    monkeypatch.setattr(sys, "argv", ["keybr.py", "--snapshot", str(tmp_path / "other.sqlite")])
    outputs, defs = run_notebook()
    assert defs["path"] == tmp_path / "other.sqlite"

    monkeypatch.setattr(sys, "argv", ["keybr.py"])
    outputs, defs = run_notebook()
    assert defs["path"] == Path("keybr-recordings.sqlite")
    assert "recording export" in text_of(outputs)
