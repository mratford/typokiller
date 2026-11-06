"""typokiller-service: runs typokiller and keybr all the time as two launchd agents, from one clone
of the GitHub repo, with their data outside the clone (ADR 0006). Its messages are screen text, so
they use plain words."""

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

REPO = "https://github.com/mratford/typokiller"
# The two apps, in the order that they restart. Each app has the launchd label local.<app>
# (local.keybr, local.typokiller), the log ~/Library/Logs/<app>.log and the data folder
# ~/.local/share/<app>/data, which is its working folder.
APPS = ["keybr", "typokiller"]
TYPOKILLER_PORT = 8000
KEYBR_PORT = 3100
KEYBR_PORT_WS = 3101
DOMAIN = f"gui/{os.getuid()}"
# The PATH of the typokiller server: launchd gives a much shorter one.
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# The steps of an update, in order: the app, and the command, which runs in that app's folder.
STEPS = [
    ("typokiller", ("uv", "sync", "--locked")),
    ("typokiller", ("uv", "run", "pytest", "-q")),
    ("typokiller", ("node", "--test", "tests/*.test.js")),
    ("keybr", ("npm", "ci")),
    ("keybr", ("npm", "run", "build")),
    ("keybr", ("env", "DATABASE_CLIENT=sqlite", "npm", "test")),
]
# The commands of the steps that install the packages and build. They run again after going back
# to the old commit.
BUILD = [("uv", "sync", "--locked"), ("npm", "ci"), ("npm", "run", "build")]


def data_folder(app: str) -> Path:
    return Path.home() / f".local/share/{app}/data"


def log_path(app: str) -> Path:
    return Path.home() / f"Library/Logs/{app}.log"


def plist_path(app: str) -> Path:
    return Path.home() / f"Library/LaunchAgents/local.{app}.plist"


def target(app: str) -> str:
    return f"{DOMAIN}/local.{app}"


def app_folder() -> Path:
    """The clone that both apps run from, with one commit checked out and no branch."""
    return Path.home() / ".local/share/typokiller/app"


def link_path() -> Path:
    return Path.home() / ".local/bin/typokiller-service"


def recordings_path() -> Path:
    """The keybr recordings, which keybr writes in its own data folder."""
    return data_folder("keybr") / "recordings.sqlite"


def databases() -> list[Path]:
    """The database files that are backed up. keybr's own database holds almost nothing."""
    return [data_folder("typokiller") / "typokiller.db", recordings_path()]


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


def get(url: str) -> str | None:
    """The body of GET `url`, or None when the server does not answer. Tests replace it."""
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.read().decode()
    except OSError:
        return None


def check_tools():
    """Stops with one line for each program that is missing: git, uv, and node 24 or newer."""
    missing = [f"{tool} is missing. Install it with: brew install {tool}" for tool in ["git", "uv", "node"] if not shutil.which(tool)]
    if not missing and int(must("node", "--version").lstrip("v").split(".")[0]) < 24:
        missing.append("node is older than version 24. Update it with: brew upgrade node")
    if missing:
        sys.exit("\n".join(missing))


def plist(app: str, program: list[str], environment: dict[str, str]) -> bytes:
    log = str(log_path(app))
    return plistlib.dumps({
        "Label": f"local.{app}",
        "ProgramArguments": program,
        "WorkingDirectory": str(data_folder(app)),
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": log,
        "StandardErrorPath": log,
    })


def write_settings(commit: str):
    """Writes keybr's .env and both plists again, and the KEYBR_PORT line of typokiller's .env."""
    keybr = data_folder("keybr")
    keybr.mkdir(parents=True, exist_ok=True)
    (keybr / ".env").write_text(
        "DETAILED_RECORDING=true\n"
        "DATABASE_CLIENT=sqlite\n"
        f"DATABASE_FILENAME={keybr}/database.sqlite\n"
        f"DATA_DIR={keybr}\n"
        f"SERVER_PORT={KEYBR_PORT}\n"
        f"SERVER_PORT_WS={KEYBR_PORT_WS}\n"
        f"APP_URL=http://localhost:{KEYBR_PORT}/\n"
        # Recording does not use the session cookie, so other addresses work too (keybr/.env.example).
        "COOKIE_DOMAIN=localhost\n"
        "COOKIE_SECURE=false\n"
        f"TYPOKILLER_URL=http://127.0.0.1:{TYPOKILLER_PORT}\n"
        f"APPLICATION_REVISION={commit}\n"
    )
    env = data_folder("typokiller") / ".env"
    env.parent.mkdir(parents=True, exist_ok=True)
    lines = [line for line in (env.read_text().splitlines() if env.exists() else []) if not line.startswith("KEYBR_PORT=")]
    env.write_text("\n".join([*lines, f"KEYBR_PORT={KEYBR_PORT}"]) + "\n")
    app = app_folder()
    plist_path("keybr").parent.mkdir(parents=True, exist_ok=True)
    plist_path("typokiller").write_bytes(plist(
        "typokiller",
        [str(app / ".venv/bin/typokiller"), "--no-access-log"],
        {"PYTHONUNBUFFERED": "1", "PATH": PATH},
    ))
    # launchd does not know the PATH of the shell, so keybr's agent names node with its full path.
    node = shutil.which("node") or "node"
    plist_path("keybr").write_bytes(plist("keybr", [node, "--enable-source-maps", str(app / "keybr/root/index.js")], {}))


def run_steps(steps: list[tuple[str, tuple[str, ...]]]) -> tuple[str, tuple[str, ...]] | None:
    """Runs the steps in the clone, in order, until one fails. Prints the output of the step that
    fails, and returns it. Returns None when all pass."""
    for step in steps:
        app, command = step
        result = run(*command, cwd=app_folder() / "keybr" if app == "keybr" else app_folder())
        if result.returncode:
            print(result.stdout)
            return step
    return None


def back_up(db: Path):
    """Copies the database file `db`, when it exists, into backups/ next to it, named with the time,
    and keeps the 10 newest backups. It opens `db` read-only, because keybr writes the recordings."""
    if not db.is_file():
        return
    (db.parent / "backups").mkdir(exist_ok=True)
    name = f"{db.stem}-{datetime.now():%Y-%m-%d-%H%M%S}{db.suffix}"
    with closing(sqlite3.connect(f"{db.absolute().as_uri()}?mode=ro", uri=True)) as source:
        source.execute("VACUUM INTO ?", (str(db.parent / "backups" / name),))
    for old in backups(db)[10:]:
        old.unlink()


def backups(db: Path) -> list[Path]:
    """The backups of `db`, newest first. Their names start with the time, so they sort by time."""
    return sorted((db.parent / "backups").glob(f"{db.stem}-*{db.suffix}"), reverse=True)


def addresses() -> str:
    name = must("scutil", "--get", "LocalHostName")
    return f"The typing page is at http://localhost:{KEYBR_PORT}/ on this Mac, and at http://{name}.local:{KEYBR_PORT}/ on other computers."


def wait_for_servers():
    """Waits until both apps answer, for 10 s at most, then prints the addresses."""
    for _ in range(20):
        if get(f"http://127.0.0.1:{KEYBR_PORT}/") is not None and get(f"http://127.0.0.1:{TYPOKILLER_PORT}/") is not None:
            break
        time.sleep(0.5)
    else:
        print("The apps did not answer within 10 s. See the logs with: typokiller-service logs")
    print(addresses())


def start():
    for app in APPS:
        must("launchctl", "bootstrap", DOMAIN, plist_path(app))
    wait_for_servers()


def stop():
    for app in APPS:
        run("launchctl", "bootout", target(app))


def install():
    for app in APPS:
        if plist_path(app).exists():
            sys.exit(f"The service is installed already: {plist_path(app)}")
    check_tools()
    print("The first install downloads about 490 MB and takes about 3 minutes.")
    clone = app_folder()
    must("git", "clone", "--quiet", REPO, clone)
    commit = must("git", "-C", clone, "rev-parse", "HEAD")
    must("git", "-C", clone, "checkout", "--quiet", "--detach", commit)
    if failed := run_steps(STEPS):
        shutil.rmtree(clone)
        sys.exit(f"A step of {failed[0]} failed, so nothing is installed.")
    write_settings(commit)
    start()
    link_path().parent.mkdir(parents=True, exist_ok=True)
    link_path().unlink(missing_ok=True)
    link_path().symlink_to(clone / ".venv/bin/typokiller-service")
    print(f"Installed. The command typokiller-service is in {link_path().parent}.")


def update(commit: str):
    clone = app_folder()
    must("git", "-C", clone, "fetch", "--quiet")
    old = must("git", "-C", clone, "rev-parse", "HEAD")
    new = must("git", "-C", clone, "rev-parse", f"{commit}^{{commit}}")
    if new == old:
        print(f"Both apps run {commit} ({old[:7]}) already.")
        return
    must("git", "-C", clone, "checkout", "--quiet", "--detach", new)
    if failed := run_steps(STEPS):
        must("git", "-C", clone, "checkout", "--quiet", "--detach", old)
        run_steps([step for step in STEPS[: STEPS.index(failed) + 1] if step[1] in BUILD])
        sys.exit(f"A step of {failed[0]} failed, so both apps still run {old[:7]}.")
    write_settings(new)
    for db in databases():
        back_up(db)
    stop()
    start()


def status():
    for app in APPS:
        pid = re.search(r"^\s*pid = (\d+)$", run("launchctl", "print", target(app)).stdout, re.MULTILINE)
        print(f"{app}: running, process {pid[1]}." if pid else f"{app}: not running.")
    clone = app_folder()
    run("git", "-C", clone, "fetch", "--quiet")  # without a network, the count is from the last fetch
    newer = must("git", "-C", clone, "rev-list", "--count", "HEAD..origin/main")
    print(f"Code: {must('git', '-C', clone, 'log', '-1', '--format=%h %s')} (GitHub has {newer} newer commits)")
    print(addresses())
    print(f"Data: {data_folder('typokiller')} and {data_folder('keybr')}")
    for db in databases():
        newest = backups(db)[:1]
        print(f"Newest backup of {db.name}: {newest[0].name if newest else 'none'}")


def restore(name: str | None):
    if name is None:
        for db in databases():
            for path in backups(db):
                print(path.name)
        return
    db = next((db for db in databases() if (db.parent / "backups" / name).is_file()), None)
    if db is None:
        sys.exit(f"No backup {name}. See the list with: typokiller-service restore")
    chosen = (db.parent / "backups" / name).read_bytes()  # back_up can delete the oldest backup
    stop()
    back_up(db)
    db.write_bytes(chosen)
    for suffix in ["-wal", "-shm"]:
        Path(f"{db}{suffix}").unlink(missing_ok=True)
    start()


def uninstall():
    for app in APPS:
        run("launchctl", "bootout", target(app))
        plist_path(app).unlink(missing_ok=True)
    shutil.rmtree(app_folder(), ignore_errors=True)
    link_path().unlink(missing_ok=True)
    print(
        f"Uninstalled. The data is still in {data_folder('typokiller')} and {data_folder('keybr')},"
        f" and the logs in {log_path('typokiller')} and {log_path('keybr')}."
    )


def main(args: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="typokiller-service", description="Runs typokiller and keybr as two services. See the README.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["install", "update", "start", "stop", "status", "logs", "restore", "uninstall"]:
        commands.add_parser(name)
    commands.choices["update"].add_argument("commit", nargs="?", default="origin/main", help="a commit or origin/<branch>")
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
            print("Stopped. Both apps start again at the next login, or with: typokiller-service start")
        case "status":
            status()
        case "logs":
            os.execvp("tail", ["tail", "-n", "50", "-f", str(log_path("typokiller")), str(log_path("keybr"))])
        case "restore":
            restore(opts.backup)
        case "uninstall":
            uninstall()
