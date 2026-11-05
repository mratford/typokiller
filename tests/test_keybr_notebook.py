import importlib.util
import sys
from pathlib import Path

from typokiller.service import recordings_path

from keybr_recordings import all_scenarios_recordings

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


def test_the_notebook_runs_on_recordings_without_typokiller_and_leaves_the_file_unchanged(tmp_path, monkeypatch):
    # No typokiller database anywhere: the notebook must not need one.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("typokiller.service.data_folder", lambda: tmp_path / "no-service")
    path = all_scenarios_recordings(tmp_path / "keybr-recordings.sqlite")
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


def test_the_notebook_opens_the_file_given_with_recordings_otherwise_keybrs_live_recordings(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # The file does not exist, so the notebook stops after the cell that sets `path` and says so.
    monkeypatch.setattr(sys, "argv", ["keybr.py", "--recordings", str(tmp_path / "backup.sqlite")])
    outputs, defs = run_notebook()
    assert defs["path"] == tmp_path / "backup.sqlite"

    monkeypatch.setattr(sys, "argv", ["keybr.py"])
    outputs, defs = run_notebook()
    assert defs["path"] == recordings_path() == tmp_path / ".local/share/keybr/data/recordings.sqlite"
    assert "There are no keybr recordings" in text_of(outputs)
