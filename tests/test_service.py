import os
import plistlib
import re
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from typokiller import service


class FakeRun:
    """Stands in for service.run: records each command, and answers it with the (returncode,
    output) of the first entry in `results` that the command starts with, or with (0, "")."""

    def __init__(self, results: dict[tuple, tuple[int, str]]):
        self.results = results
        self.calls: list[tuple[str, ...]] = []
        self.asked: list[str] = []  # the paths asked of the server

    def __call__(self, *args, cwd=None):
        args = tuple(str(arg) for arg in args)
        self.calls.append(args)
        for start, (code, output) in self.results.items():
            if args[: len(start)] == tuple(str(word) for word in start):
                return subprocess.CompletedProcess(args, code, output)
        return subprocess.CompletedProcess(args, 0, "")

    def ran(self, *start) -> bool:
        return any(call[: len(start)] == start for call in self.calls)


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def checkout(tmp_path) -> Path:
    (tmp_path / "checkout").mkdir()
    return tmp_path / "checkout"


@pytest.fixture
def fake(home, checkout, monkeypatch) -> FakeRun:
    """The checkout is found with git rev-parse. The server does not answer, and the commands
    do not wait for it to start."""
    fake = FakeRun({("git", "rev-parse", "--path-format=absolute", "--git-common-dir"): (0, f"{checkout}/.git\n")})
    monkeypatch.setattr(service, "run", fake)
    monkeypatch.setattr(service, "get", lambda path: fake.asked.append(path))
    monkeypatch.setattr(service, "wait_for_server", lambda: None)
    return fake


def test_install_writes_the_plist_for_launchd(home, fake):
    service.main(["install"])
    plist = plistlib.loads((home / "Library/LaunchAgents/local.typokiller.plist").read_bytes())
    assert plist["Label"] == "local.typokiller"
    assert plist["ProgramArguments"] == [f"{home}/.local/share/typokiller/app/.venv/bin/typokiller", "--no-access-log"]
    assert plist["WorkingDirectory"] == f"{home}/.local/share/typokiller/data"
    assert plist["EnvironmentVariables"] == {
        "PYTHONUNBUFFERED": "1",
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    }
    assert plist["RunAtLoad"] and plist["KeepAlive"] and plist["ThrottleInterval"] == 10
    assert plist["StandardOutPath"] == plist["StandardErrorPath"] == f"{home}/Library/Logs/typokiller.log"


def test_install_moves_the_database_and_copies_only_the_settings(home, checkout, fake):
    for name in ["typokiller.db", "typokiller.toml", ".env", "pg_catalog.csv"]:
        (checkout / name).write_text(name)
    service.main(["install"])
    data = home / ".local/share/typokiller/data"
    assert not (checkout / "typokiller.db").exists()
    assert sorted(path.name for path in data.iterdir()) == ["backups", "typokiller.db", "typokiller.toml"]
    assert (data / "typokiller.db").read_text() == "typokiller.db"
    assert (data / "typokiller.toml").read_text() == (checkout / "typokiller.toml").read_text() == "typokiller.toml"


def test_install_keeps_a_database_already_in_the_data_folder(home, checkout, fake):
    data = home / ".local/share/typokiller/data"
    data.mkdir(parents=True)
    (data / "typokiller.db").write_text("kept")
    (data / "typokiller.toml").write_text("kept")
    (checkout / "typokiller.db").write_text("development")
    (checkout / "typokiller.toml").write_text("development")
    service.main(["install"])
    assert (data / "typokiller.db").read_text() == (data / "typokiller.toml").read_text() == "kept"
    assert (checkout / "typokiller.db").read_text() == "development"


def test_install_refuses_when_the_plist_exists(home, fake):
    (home / "Library/LaunchAgents").mkdir(parents=True)
    (home / "Library/LaunchAgents/local.typokiller.plist").write_text("old")
    with pytest.raises(SystemExit, match="installed already"):
        service.main(["install"])
    assert fake.calls == []


def test_install_refuses_when_something_answers_on_port_8000(home, fake, monkeypatch):
    monkeypatch.setattr(service, "get", lambda path: "<html>")
    with pytest.raises(SystemExit, match="port 8000"):
        service.main(["install"])
    assert fake.calls == []


@pytest.fixture
def installed(home, fake) -> Path:
    """An installed service whose worktree is at commit `aaaa…` while main is at `bbbb…`, with a
    database that holds one row. Returns the data folder."""
    app = home / ".local/share/typokiller/app"
    fake.results[("git", "-C", app, "rev-parse", "HEAD")] = (0, "a" * 40 + "\n")
    fake.results[("git", "-C", app, "rev-parse", "main^{commit}")] = (0, "b" * 40 + "\n")
    data = home / ".local/share/typokiller/data"
    (data / "backups").mkdir(parents=True)
    with closing(sqlite3.connect(data / "typokiller.db")) as db:
        db.execute("CREATE TABLE t (x)")
        db.execute("INSERT INTO t VALUES ('now')")
        db.commit()
    return data


def test_update_with_failing_tests_goes_back_to_the_old_commit_and_does_not_restart(home, installed, fake, capsys):
    fake.results[("uv", "run", "pytest")] = (1, "1 failed")
    with pytest.raises(SystemExit, match="tests failed"):
        service.main(["update"])
    app = str(home / ".local/share/typokiller/app")
    checkouts = [call for call in fake.calls if call[3:4] == ("checkout",)]
    assert checkouts == [("git", "-C", app, "checkout", "--detach", "b" * 40), ("git", "-C", app, "checkout", "--detach", "a" * 40)]
    assert fake.calls[-1] == ("uv", "sync", "--locked")
    assert not fake.ran("launchctl")
    assert "1 failed" in capsys.readouterr().out
    assert list((installed / "backups").iterdir()) == []


def test_update_backs_up_the_database_keeps_the_10_newest_and_restarts(installed, fake):
    for day in range(1, 12):
        (installed / "backups" / f"typokiller-2026-01-{day:02}-1200-1234567.db").write_text("old")
    service.main(["update"])
    backups = sorted(path.name for path in (installed / "backups").iterdir())
    assert len(backups) == 10
    assert backups[0] == "typokiller-2026-01-03-1200-1234567.db"
    assert re.fullmatch(r"typokiller-\d{4}-\d\d-\d\d-\d{6}-aaaaaaa\.db", backups[-1])
    assert fake.ran("launchctl", "kickstart", "-k", f"gui/{os.getuid()}/local.typokiller")


def test_update_to_the_commit_already_running_changes_nothing(home, installed, fake, capsys):
    fake.results[("git", "-C", home / ".local/share/typokiller/app", "rev-parse", "aaaa^{commit}")] = (0, "a" * 40)
    service.main(["update", "aaaa"])
    assert "already" in capsys.readouterr().out
    assert not fake.ran("launchctl")


@pytest.mark.parametrize("command", ["update", "stop", "restore", "uninstall"])
def test_no_command_asks_the_server_whether_it_is_busy_or_takes_force(installed, fake, command):
    service.main([command])
    assert fake.asked == []
    with pytest.raises(SystemExit):
        service.main([command, "--force"])


def test_restore_lists_the_backups_newest_first(installed, fake, capsys):
    for day in [1, 3, 2]:
        (installed / "backups" / f"typokiller-2026-01-0{day}-1200-1234567.db").write_text("old")
    service.main(["restore"])
    assert capsys.readouterr().out.split() == [f"typokiller-2026-01-0{day}-1200-1234567.db" for day in [3, 2, 1]]


def test_restore_backs_up_the_database_before_it_copies_the_chosen_backup(installed, fake):
    """The chosen backup is the oldest of 10, so the new backup makes it the 11th."""
    for day in range(1, 11):
        (installed / "backups" / f"typokiller-2026-01-{day:02}-1200-1234567.db").write_text(f"day {day}")
    service.main(["restore", "typokiller-2026-01-01-1200-1234567.db"])
    assert (installed / "typokiller.db").read_text() == "day 1"
    (new,) = [path for path in (installed / "backups").iterdir() if not path.name.startswith("typokiller-2026-01-")]
    with closing(sqlite3.connect(new)) as db:
        assert db.execute("SELECT x FROM t").fetchall() == [("now",)]
    launchctl = [call[:2] for call in fake.calls if call[0] == "launchctl"]
    assert launchctl == [("launchctl", "bootout"), ("launchctl", "bootstrap")]


def test_uninstall_removes_the_plist_and_the_worktree_and_keeps_the_data(home, installed, fake, capsys):
    plist = home / "Library/LaunchAgents/local.typokiller.plist"
    plist.parent.mkdir(parents=True)
    plist.write_text("plist")
    service.main(["uninstall"])
    assert not plist.exists()
    assert fake.ran("launchctl", "bootout")
    assert fake.ran("git", "worktree", "remove", "--force", str(home / ".local/share/typokiller/app"))
    assert (installed / "typokiller.db").exists()
    assert str(installed) in capsys.readouterr().out


def test_notebook_db_is_the_service_database_when_it_exists_otherwise_the_local_one(tmp_path):
    assert service.notebook_db(tmp_path) == Path("typokiller.db")
    (tmp_path / "typokiller.db").touch()
    assert service.notebook_db(tmp_path) == tmp_path / "typokiller.db"
