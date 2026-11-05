"""typokiller-service: runs typokiller all the time as a launchd agent, from its own git worktree,
with its data outside the repo (ADR 0002). Its messages are screen text, so they use plain words."""

import argparse
import os
import plistlib
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
from datetime import datetime
from pathlib import Path

LABEL = "local.typokiller"
DOMAIN = f"gui/{os.getuid()}"
TARGET = f"{DOMAIN}/{LABEL}"
URL = "http://127.0.0.1:8000"
# The PATH of the server: launchd gives a much shorter one.
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def app_folder() -> Path:
    """The worktree that the service runs, with one commit checked out and no branch."""
    return Path.home() / ".local/share/typokiller/app"


def data_folder() -> Path:
    """The service's working folder: its database, settings and backups."""
    return Path.home() / ".local/share/typokiller/data"


def notebook_db(data: Path) -> Path:
    """The database that the notebooks open with no --db: the service's database in `data` when
    it exists, otherwise typokiller.db in the current folder."""
    service_db = data / "typokiller.db"
    return service_db if service_db.exists() else Path("typokiller.db")


def plist_path() -> Path:
    return Path.home() / f"Library/LaunchAgents/{LABEL}.plist"


def log_path() -> Path:
    return Path.home() / "Library/Logs/typokiller.log"


def run(*args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Runs a command and returns its output, stdout and stderr together. Every command that
    changes something goes through here, so tests can replace it."""
    return subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def must(*args: str | Path, cwd: Path | None = None) -> str:
    """Runs a command and returns its output without the last newline, or stops with its output."""
    result = run(*args, cwd=cwd)
    if result.returncode:
        sys.exit(result.stdout)
    return result.stdout.strip()


def get(path: str) -> str | None:
    """The body of GET <URL><path>, or None when the server does not answer. Tests replace it."""
    try:
        with urllib.request.urlopen(URL + path, timeout=2) as response:
            return response.read().decode()
    except OSError:
        return None


def plist() -> bytes:
    log = str(log_path())
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [str(app_folder() / ".venv/bin/typokiller"), "--no-access-log"],
        "WorkingDirectory": str(data_folder()),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1", "PATH": PATH},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": log,
        "StandardErrorPath": log,
    })


def tests_pass() -> bool:
    """Installs the locked packages in the worktree and runs both test suites. Prints the output
    of the first step that fails."""
    print("Running the tests...")
    for step in [("uv", "sync", "--locked"), ("uv", "run", "pytest", "-q"), ("node", "--test", "tests/*.test.js")]:
        result = run(*step, cwd=app_folder())
        if result.returncode:
            print(result.stdout)
            return False
    return True


def backups() -> list[Path]:
    """The backups, newest first. Their names start with the time, so they sort by time."""
    return sorted((data_folder() / "backups").glob("typokiller-*.db"), reverse=True)


def backup(commit: str):
    """Copies the database into backups/, named with the time and `commit`."""
    name = f"typokiller-{datetime.now():%Y-%m-%d-%H%M%S}-{commit[:7]}.db"
    with closing(sqlite3.connect(data_folder() / "typokiller.db")) as db:
        db.execute("VACUUM INTO ?", (str(data_folder() / "backups" / name),))


def prune():
    """Deletes all but the 10 newest backups."""
    for old in backups()[10:]:
        old.unlink()


def start():
    must("launchctl", "bootstrap", DOMAIN, plist_path())
    wait_for_server()


def wait_for_server():
    for _ in range(20):
        if get("/") is not None:
            print(f"The service answers at {URL}/.")
            return
        time.sleep(0.5)
    print(f"The service did not answer within 10 s. See the log: {log_path()}")


def install():
    if plist_path().exists():
        sys.exit(f"The service is installed already: {plist_path()}")
    if get("/") is not None:
        sys.exit("Something answers on port 8000, perhaps a development server. Stop it first, so that the database is not moved while it is in use.")
    # The main working folder of the repo, also when this runs from a worktree.
    checkout = Path(must("git", "rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    must("git", "worktree", "add", "--detach", app_folder(), "main")
    if not tests_pass():
        run("git", "worktree", "remove", "--force", app_folder())
        sys.exit("The tests failed, so the service is not installed.")
    data = data_folder()
    (data / "backups").mkdir(parents=True, exist_ok=True)
    if (checkout / "typokiller.db").exists() and not (data / "typokiller.db").exists():
        shutil.move(checkout / "typokiller.db", data / "typokiller.db")
    if (checkout / "typokiller.toml").exists() and not (data / "typokiller.toml").exists():
        shutil.copy2(checkout / "typokiller.toml", data / "typokiller.toml")
    plist_path().parent.mkdir(parents=True, exist_ok=True)
    plist_path().write_bytes(plist())
    start()


def update(commit: str):
    app = app_folder()
    old = must("git", "-C", app, "rev-parse", "HEAD")
    new = must("git", "-C", app, "rev-parse", f"{commit}^{{commit}}")
    if new == old:
        print(f"The service runs {commit} ({old[:7]}) already.")
        return
    must("git", "-C", app, "checkout", "--detach", new)
    if not tests_pass():
        must("git", "-C", app, "checkout", "--detach", old)
        run("uv", "sync", "--locked", cwd=app)
        sys.exit(f"The tests failed, so the service still runs {old[:7]}.")
    backup(old)
    prune()
    run("launchctl", "kickstart", "-k", TARGET)
    wait_for_server()


def stop():
    must("launchctl", "bootout", TARGET)
    print("Stopped. The service starts again at the next login, or with: uv run typokiller-service start")


def status():
    pid = re.search(r"^\s*pid = (\d+)$", run("launchctl", "print", TARGET).stdout, re.MULTILINE)
    print(f"Running, process {pid[1]}." if pid else "Not running.")
    app = app_folder()
    newer = must("git", "-C", app, "rev-list", "--count", "HEAD..main")
    print(f"Code: {must('git', '-C', app, 'log', '-1', '--format=%h %s')} (main has {newer} newer commits)")
    print(f"Data: {data_folder()}")
    newest = backups()[:1]
    print(f"Newest backup: {newest[0].name if newest else 'none'}")


def restore(name: str | None):
    if name is None:
        for path in backups():
            print(path.name)
        return
    chosen = data_folder() / "backups" / name
    if not chosen.exists():
        sys.exit(f"No backup {chosen}. See the list with: uv run typokiller-service restore")
    run("launchctl", "bootout", TARGET)
    backup(must("git", "-C", app_folder(), "rev-parse", "HEAD"))
    shutil.copy(chosen, data_folder() / "typokiller.db")
    prune()
    start()


def uninstall():
    run("launchctl", "bootout", TARGET)
    plist_path().unlink(missing_ok=True)
    run("git", "worktree", "remove", "--force", app_folder())
    print(f"Uninstalled. The data is still in {data_folder()}, and the log in {log_path()}.")


def main(args: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="typokiller-service", description="Runs typokiller as a service on port 8000. See the README.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["install", "update", "start", "stop", "status", "logs", "restore", "uninstall"]:
        commands.add_parser(name)
    commands.choices["update"].add_argument("commit", nargs="?", default="main")
    commands.choices["restore"].add_argument("backup", nargs="?", help="the file name of a backup; none lists them")
    opts = parser.parse_args(args)
    match opts.command:
        case "install":
            install()
        case "update":
            update(opts.commit)
        case "start":
            start()
        case "stop":
            stop()
        case "status":
            status()
        case "logs":
            os.execvp("tail", ["tail", "-n", "50", "-f", str(log_path())])
        case "restore":
            restore(opts.backup)
        case "uninstall":
            uninstall()
