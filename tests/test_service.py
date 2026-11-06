import os
import plistlib
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from typokiller import service

OLD, NEW = "a" * 40, "b" * 40
NODE = "/Users/me/.nvm/versions/node/v24.22.0/bin/node"


class FakeRun:
    """Stands in for service.run: records each command and the folder it runs in, and answers it
    with the (returncode, output) of the first entry in `results` that the command starts with,
    or with (0, "")."""

    def __init__(self, results: dict[tuple, tuple[int, str]]):
        self.results = results
        self.calls: list[tuple[str, ...]] = []
        self.folders: dict[tuple[str, ...], str] = {}

    def __call__(self, *args, cwd=None):
        args = tuple(str(arg) for arg in args)
        self.calls.append(args)
        self.folders[args] = str(cwd)
        for start, (code, output) in self.results.items():
            if args[: len(start)] == tuple(str(word) for word in start):
                return subprocess.CompletedProcess(args, code, output)
        return subprocess.CompletedProcess(args, 0, "")

    def ran(self, *start) -> bool:
        return any(call[: len(start)] == start for call in self.calls)

    def launchctl(self) -> list[tuple[str, str]]:
        """The launchctl commands, each with the label it acts on."""
        return [(call[1], call[-1].split("/")[-1].removesuffix(".plist")) for call in self.calls if call[0] == "launchctl"]


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def tools(monkeypatch) -> dict[str, str]:
    """The programs that shutil.which finds. A test can delete some."""
    found = {"git": "/usr/bin/git", "uv": "/opt/homebrew/bin/uv", "node": NODE}
    monkeypatch.setattr(service.shutil, "which", found.get)
    return found


@pytest.fixture
def fake(home, tools, monkeypatch) -> FakeRun:
    """This Mac is named marge, node is version 24, and both servers answer at once."""
    fake = FakeRun({("scutil", "--get", "LocalHostName"): (0, "marge\n"), ("node", "--version"): (0, "v24.22.0\n")})
    monkeypatch.setattr(service, "run", fake)
    monkeypatch.setattr(service, "get", lambda url: "<html>")
    return fake


def test_install_stops_with_one_line_for_each_missing_program(fake, tools):
    del tools["git"], tools["node"]
    with pytest.raises(SystemExit) as stopped:
        service.main(["install"])
    assert stopped.value.code == "git is missing. Install it with: brew install git\nnode is missing. Install it with: brew install node"
    assert fake.calls == []


def test_install_stops_when_node_is_older_than_24(fake):
    fake.results[("node", "--version")] = (0, "v22.11.0\n")
    with pytest.raises(SystemExit, match="node is older than version 24. Update it with: brew upgrade node"):
        service.main(["install"])
    assert not fake.ran("git")


def test_install_clones_builds_and_tests_then_starts_both_apps(home, fake, capsys):
    clone = home / ".local/share/typokiller/app"
    fake.results[("git", "-C", clone, "rev-parse", "HEAD")] = (0, NEW + "\n")
    service.main(["install"])
    assert fake.calls[1:] == [
        ("git", "clone", "--quiet", "https://github.com/mratford/typokiller", str(clone)),
        ("git", "-C", str(clone), "rev-parse", "HEAD"),
        ("git", "-C", str(clone), "checkout", "--quiet", "--detach", NEW),
        ("uv", "sync", "--locked"),
        ("uv", "run", "pytest", "-q"),
        ("node", "--test", "tests/*.test.js"),
        ("npm", "ci"),
        ("npm", "run", "build"),
        ("env", "DATABASE_CLIENT=sqlite", "npm", "test"),
        ("launchctl", "bootstrap", f"gui/{os.getuid()}", str(home / "Library/LaunchAgents/local.keybr.plist")),
        ("launchctl", "bootstrap", f"gui/{os.getuid()}", str(home / "Library/LaunchAgents/local.typokiller.plist")),
        ("scutil", "--get", "LocalHostName"),
    ]
    assert fake.folders[("uv", "run", "pytest", "-q")] == str(clone)
    assert fake.folders[("npm", "ci")] == str(clone / "keybr")
    assert (home / ".local/bin/typokiller-service").readlink() == clone / ".venv/bin/typokiller-service"
    out = capsys.readouterr().out
    assert "downloads about 490 MB and takes about 3 minutes" in out
    assert "http://localhost:3100/ on this Mac, and at http://marge.local:3100/ on other computers" in out


def test_install_writes_the_settings_of_keybr_and_the_plists_of_both(home, fake):
    clone = home / ".local/share/typokiller/app"
    fake.results[("git", "-C", clone, "rev-parse", "HEAD")] = (0, NEW + "\n")
    service.main(["install"])
    keybr = home / ".local/share/keybr/data"
    assert (keybr / ".env").read_text().splitlines() == [
        "DETAILED_RECORDING=true",
        "DATABASE_CLIENT=sqlite",
        f"DATABASE_FILENAME={keybr}/database.sqlite",
        f"DATA_DIR={keybr}",
        "SERVER_PORT=3100",
        "SERVER_PORT_WS=3101",
        "APP_URL=http://localhost:3100/",
        "COOKIE_DOMAIN=localhost",
        "COOKIE_SECURE=false",
        "TYPOKILLER_URL=http://127.0.0.1:8000",
        f"APPLICATION_REVISION={NEW}",
    ]
    assert (home / ".local/share/typokiller/data/.env").read_text() == "KEYBR_PORT=3100\n"
    plists = {app: plistlib.loads((home / f"Library/LaunchAgents/local.{app}.plist").read_bytes()) for app in ["typokiller", "keybr"]}
    assert plists["typokiller"]["ProgramArguments"] == [f"{clone}/.venv/bin/typokiller", "--no-access-log"]
    assert plists["typokiller"]["EnvironmentVariables"] == {"PYTHONUNBUFFERED": "1", "PATH": service.PATH}
    assert plists["keybr"]["ProgramArguments"] == [NODE, "--enable-source-maps", f"{clone}/keybr/root/index.js"]
    for app, plist in plists.items():
        assert plist["Label"] == f"local.{app}"
        assert plist["WorkingDirectory"] == f"{home}/.local/share/{app}/data"
        assert plist["RunAtLoad"] and plist["KeepAlive"] and plist["ThrottleInterval"] == 10
        assert plist["StandardOutPath"] == plist["StandardErrorPath"] == f"{home}/Library/Logs/{app}.log"


def test_install_refuses_when_a_plist_exists(home, fake):
    (home / "Library/LaunchAgents").mkdir(parents=True)
    (home / "Library/LaunchAgents/local.keybr.plist").write_text("old")
    with pytest.raises(SystemExit, match="installed already"):
        service.main(["install"])
    assert fake.calls == []


def make_db(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE t (x)")
        db.execute("INSERT INTO t VALUES (?)", (value,))
        db.commit()


@pytest.fixture
def installed(home, fake) -> list[Path]:
    """Installed apps whose clone is at OLD while origin/main is at NEW, with the two databases.
    Returns the two databases."""
    clone = home / ".local/share/typokiller/app"
    fake.results[("git", "-C", clone, "rev-parse", "HEAD")] = (0, OLD + "\n")
    fake.results[("git", "-C", clone, "rev-parse", "origin/main^{commit}")] = (0, NEW + "\n")
    databases = [home / ".local/share/typokiller/data/typokiller.db", home / ".local/share/keybr/data/recordings.sqlite"]
    for db in databases:
        make_db(db, "now")
        (db.parent / "backups").mkdir()
    return databases


def checkouts(fake: FakeRun) -> list[str]:
    return [call[-1] for call in fake.calls if call[3:4] == ("checkout",)]


def test_update_where_the_typokiller_tests_fail_runs_no_keybr_step_and_restarts_nothing(installed, fake, capsys):
    fake.results[("uv", "run", "pytest")] = (1, "1 failed")
    with pytest.raises(SystemExit, match=f"A step of typokiller failed, so both apps still run {OLD[:7]}"):
        service.main(["update"])
    assert checkouts(fake) == [NEW, OLD]
    assert fake.calls[-3][:2] == ("uv", "run") and fake.calls[-1] == ("uv", "sync", "--locked")
    assert not fake.ran("npm") and fake.launchctl() == []
    assert "1 failed" in capsys.readouterr().out
    assert [list((db.parent / "backups").iterdir()) for db in installed] == [[], []]


def test_update_where_the_keybr_tests_fail_builds_both_apps_of_the_old_commit_again(installed, fake, capsys):
    fake.results[("env", "DATABASE_CLIENT=sqlite", "npm", "test")] = (1, "@keybr/server test failed")
    with pytest.raises(SystemExit, match=f"A step of keybr failed, so both apps still run {OLD[:7]}"):
        service.main(["update"])
    assert checkouts(fake) == [NEW, OLD]
    assert fake.calls[-4][-1] == OLD
    assert fake.calls[-3:] == [("uv", "sync", "--locked"), ("npm", "ci"), ("npm", "run", "build")]
    assert fake.launchctl() == []
    assert "@keybr/server test failed" in capsys.readouterr().out


def test_update_fetches_backs_up_both_databases_then_restarts_keybr_then_typokiller(home, installed, fake, capsys):
    service.main(["update"])
    assert fake.calls[0] == ("git", "-C", str(home / ".local/share/typokiller/app"), "fetch", "--quiet")
    assert checkouts(fake) == [NEW]
    for db in installed:
        (backup,) = (db.parent / "backups").iterdir()
        assert backup.name.startswith(db.stem + "-") and backup.suffix == db.suffix
        with closing(sqlite3.connect(backup)) as copy:
            assert copy.execute("SELECT x FROM t").fetchall() == [("now",)]
    assert fake.launchctl() == [("bootout", "local.keybr"), ("bootout", "local.typokiller"), ("bootstrap", "local.keybr"), ("bootstrap", "local.typokiller")]
    assert f"APPLICATION_REVISION={NEW}" in (home / ".local/share/keybr/data/.env").read_text()
    assert "http://marge.local:3100/" in capsys.readouterr().out


def test_update_keeps_the_other_lines_of_typokillers_env(home, installed, fake):
    env = home / ".local/share/typokiller/data/.env"
    env.write_text("OTHER=1\nKEYBR_PORT=3000\n")
    service.main(["update"])
    assert env.read_text() == "OTHER=1\nKEYBR_PORT=3100\n"


def test_update_to_a_branch_on_github(home, installed, fake):
    fake.results[("git", "-C", home / ".local/share/typokiller/app", "rev-parse", "origin/try^{commit}")] = (0, "c" * 40)
    service.main(["update", "origin/try"])
    assert checkouts(fake) == ["c" * 40]


def test_update_to_the_commit_already_running_changes_nothing(home, installed, fake, capsys):
    fake.results[("git", "-C", home / ".local/share/typokiller/app", "rev-parse", "aaaa^{commit}")] = (0, OLD)
    service.main(["update", "aaaa"])
    assert "already" in capsys.readouterr().out
    assert checkouts(fake) == [] and fake.launchctl() == []


def test_status_shows_each_app_then_the_code_addresses_data_and_newest_backups(home, installed, fake, capsys):
    clone = home / ".local/share/typokiller/app"
    fake.results[("launchctl", "print", f"gui/{os.getuid()}/local.keybr")] = (0, "\tstate = running\n\tpid = 4321\n")
    fake.results[("git", "-C", clone, "rev-list", "--count", "HEAD..origin/main")] = (0, "3\n")
    fake.results[("git", "-C", clone, "log", "-1")] = (0, "aaaaaaa Add a thing\n")
    (installed[1].parent / "backups/recordings-2026-11-01-120000.sqlite").write_text("old")
    service.main(["status"])
    assert fake.calls[2] == ("git", "-C", str(clone), "fetch", "--quiet")
    assert capsys.readouterr().out.splitlines() == [
        "keybr: running, process 4321.",
        "typokiller: not running.",
        "Code: aaaaaaa Add a thing (GitHub has 3 newer commits)",
        "The typing page is at http://localhost:3100/ on this Mac, and at http://marge.local:3100/ on other computers.",
        f"Data: {home}/.local/share/typokiller/data and {home}/.local/share/keybr/data",
        "Newest backup of typokiller.db: none",
        "Newest backup of recordings.sqlite: recordings-2026-11-01-120000.sqlite",
    ]


def test_restore_lists_the_backups_of_both_newest_first(installed, fake, capsys):
    names = ["typokiller-2026-01-01-120000-1234567.db", "typokiller-2026-01-03-120000.db", "recordings-2026-01-02-120000.sqlite"]
    for name in names:
        (installed[0 if name.startswith("typokiller") else 1].parent / "backups" / name).write_text("old")
    service.main(["restore"])
    assert capsys.readouterr().out.split() == [names[1], names[0], names[2]]


def test_restore_of_the_recordings_backs_them_up_puts_the_backup_in_place_and_deletes_the_wal_files(installed, fake):
    """The chosen backup is the oldest of 10, so the new backup makes it the 11th."""
    recordings = installed[1]
    backups = recordings.parent / "backups"
    for day in range(1, 11):
        make_db(backups / f"recordings-2026-01-{day:02}-120000.sqlite", f"day {day}")
    for suffix in ["-wal", "-shm"]:
        Path(f"{recordings}{suffix}").write_text("stale")
    service.main(["restore", "recordings-2026-01-01-120000.sqlite"])
    with closing(sqlite3.connect(recordings)) as db:
        assert db.execute("SELECT x FROM t").fetchall() == [("day 1",)]
    assert not Path(f"{recordings}-wal").exists() and not Path(f"{recordings}-shm").exists()
    (new,) = [path for path in backups.iterdir() if not path.name.startswith("recordings-2026-01-")]
    with closing(sqlite3.connect(new)) as db:
        assert db.execute("SELECT x FROM t").fetchall() == [("now",)]
    assert len(list(backups.iterdir())) == 10
    assert fake.launchctl() == [("bootout", "local.keybr"), ("bootout", "local.typokiller"), ("bootstrap", "local.keybr"), ("bootstrap", "local.typokiller")]


def test_each_database_keeps_its_10_newest_backups(installed):
    for db in installed:
        for day in range(1, 12):
            (db.parent / "backups" / f"{db.stem}-2026-01-{day:02}-120000{db.suffix}").write_text("old")
        service.back_up(db)
        backups = sorted(path.name for path in (db.parent / "backups").iterdir())
        assert len(backups) == 10 and backups[0] == f"{db.stem}-2026-01-03-120000{db.suffix}"


def test_uninstall_removes_both_plists_the_clone_and_the_link_and_keeps_the_data_and_logs(home, installed, fake, capsys):
    clone = home / ".local/share/typokiller/app"
    clone.mkdir()
    (home / "Library/LaunchAgents").mkdir(parents=True)
    for app in ["typokiller", "keybr"]:
        (home / f"Library/LaunchAgents/local.{app}.plist").write_text("plist")
    (home / ".local/bin").mkdir(parents=True)
    (home / ".local/bin/typokiller-service").symlink_to(clone / ".venv/bin/typokiller-service")
    service.main(["uninstall"])
    assert list((home / "Library/LaunchAgents").iterdir()) == []
    assert not clone.exists() and not (home / ".local/bin/typokiller-service").is_symlink()
    assert fake.launchctl() == [("bootout", "local.keybr"), ("bootout", "local.typokiller")]
    assert all(db.exists() for db in installed)
    out = capsys.readouterr().out
    assert str(installed[0].parent) in out and str(installed[1].parent) in out and "keybr.log" in out
