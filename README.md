# typokiller

typokiller's typing page is a changed copy of [keybr.com](https://www.keybr.com/) by Aliaksandr Radzivanovich ([aradzie/keybr.com](https://github.com/aradzie/keybr.com)), under the AGPL 3.0.
The code in `keybr/` is under the AGPL 3.0 (see `keybr/LICENSE` and `keybr/NOTICE`). The rest of this repo is also under the AGPL 3.0 (see `LICENSE`).

Practise typing on your own keyboard, and see which keys and key pairs are slow for you. It runs on your Mac and starts when you log in.

## Set up

Open Terminal and type these two lines. The first is needed only if you do not have `uv` and `node` yet.

```sh
brew install uv node
uvx --from git+https://github.com/mratford/typokiller typokiller-service install
```

The first install downloads about 490 MB and takes about 3 minutes. At the end it prints two addresses.

## Type

Open **http://localhost:3100/** on this Mac.

1. Below the lesson, click **analysis**. Then press `b` and `n` to add your keyboard: choose its `vial.json`, check the name, then choose a `.vil`.
2. Press `t` to go back to the typing page. Below the lesson, choose the keyboard and the layout.
3. Type. Each lesson is recorded.

If your keyboard's firmware already types another layout, such as free-range, also choose that layout in the typing page's settings.

**From another computer** on your home network, open the second address, such as `http://marge.local:3100/`. Each computer keeps its own typing progress, and you choose the keyboard again there. On this Mac, always use `localhost`: another address starts the progress again.

## See your progress

Click **analysis** below the lesson. The line at the bottom of the page lists the keys of the page.

In the keyboards panel (`b`): `n` adds a keyboard, `v` saves a new layout from a `.vil`, `r` names the layers.

## Keep it up to date

```sh
typokiller-service update      # get the newest version; keeps the old one if a step fails
typokiller-service status      # running or not, the addresses, the newest backups
typokiller-service stop        # stop until the next login
typokiller-service start
typokiller-service restore     # list the backups; then give one name to go back to it
typokiller-service uninstall   # remove the apps, keep your data
```

If Terminal says `command not found: typokiller-service`, type `uv tool update-shell` once, then open a new Terminal window.

Your lessons and keyboards are backed up every day and at each update.

## Development

Everything below is for working on the code. Here the two apps are keybr (in `keybr/`) and typokiller (the rest).

### What runs where

`typokiller-service` runs both apps all the time on this Mac as two launchd agents, `local.keybr` and `local.typokiller`: keybr on port 3100 (and 3101 for its WebSocket server), typokiller on port 8000. Both run from one clone of GitHub in `~/.local/share/typokiller/app`, which changes only when you update it. typokiller's database, settings and backups are in `~/.local/share/typokiller/data`. keybr's recorded lessons (`recordings.sqlite`), settings and backups are in `~/.local/share/keybr/data`. The logs are `~/Library/Logs/typokiller.log` and `~/Library/Logs/keybr.log`. The reasons are in `docs/adr/0006-service-runs-both-apps-from-a-github-clone.md`.

Each `install` and `update` writes keybr's `.env` and both plists again, so do not edit them by hand. keybr gets the keyboards, their layouts and their keyboard pictures from typokiller (`TYPOKILLER_URL` in keybr's `.env`) each time the typing page loads. typokiller's `t` key and its links to keybr go to `/typing`, which sends the browser to port `KEYBR_PORT` (in typokiller's `.env`, 3100 when it is missing) on the same host name.

Both apps answer only when the address is `localhost`, an IP address or a name that ends in `.local`. See [keybr/docs/detailed_recording.md](keybr/docs/detailed_recording.md#opening-keybr-from-another-computer).

The other commands:

```sh
typokiller-service logs                    # the end of both logs, as they grow (Ctrl-C stops)
typokiller-service update abc1234          # go to another commit, also an older one
typokiller-service update origin/<branch>  # go to a branch that is pushed to GitHub
typokiller-service restore recordings-2026-11-01-093015.sqlite
```

`update` gets the code from GitHub (`origin/main` when no commit is given). It installs the packages of both apps, builds keybr and runs the tests of both. If a step fails, it goes back to the old commit and both apps continue with the old code. If all pass, it backs up `typokiller.db` and `recordings.sqlite` to `backups/` in their data folders, and restarts keybr, then typokiller.

The typokiller server also backs up both files when it starts (unless the newest backup is less than 24 hours old) and every 24 hours. The 10 newest backups of each file are kept. Their names are like `typokiller-2026-11-01-093015.db` and `recordings-2026-11-01-093015.sqlite`. `restore` with no name lists typokiller's backups, then the recordings' backups, newest first. With a name, both apps stop, the file is backed up first (so you can undo the restore with the same command), the chosen backup takes its place, and both apps start again. The code does not change.

### Moving this Mac over once

The old service ran only typokiller, from a git worktree. Remove it once, in `~/src/typokiller`, then install the new one:

```sh
uv run typokiller-service uninstall
git worktree prune
uvx --from git+https://github.com/mratford/typokiller typokiller-service install
```

The data folder `~/.local/share/typokiller/data` is kept.

### Development servers

Run typokiller from this folder on another port. It uses `typokiller.db`, `typokiller.toml` and `.env` in this folder, not the service's data. By default it reads the service's keybr recordings; `--recordings <path>` reads another file. It backs up both files as the service does.

```sh
uv run typokiller --port 8001
```

To run keybr from `keybr/` too: copy `keybr/.env.example` to `keybr/.env`, and in it set `DETAILED_RECORDING=true` and `TYPOKILLER_URL=http://127.0.0.1:8001`. Then, in `keybr/`:

```sh
npm ci
npm run build-dev
npm start          # http://localhost:3000/ (and 3001 for the WebSocket server)
npm run watch      # in another terminal: builds again after each change
```

This keybr writes its recordings to `~/.local/state/keybr/recordings.sqlite` (`DATA_DIR` in its `.env`). Give that path to typokiller with `--recordings`, and put `KEYBR_PORT=3000` in `.env` in this folder, so that `t` opens this keybr. See `keybr/docs/getting_started.md` for more.

### Tests

```sh
uv run pytest                 # typokiller's server tests
uv run pyright                # type check
node --test tests/*.test.js   # typokiller's page tests
```

keybr's tests, in `keybr/`, after `npm ci` and `npm run build`:

```sh
env DATABASE_CLIENT=sqlite npm test
```

### The notebook

`notebooks/keybr.py` reads keybr's recordings in `~/.local/share/keybr/data/recordings.sqlite` once, read only, while keybr runs. It never opens the typokiller database. It has filters for the keyboard, the layout, the saved version of the layout and the days. It shows keybr's own progress, the first-input accuracy, the weakest characters and pairs, fix times, timings, the keyboard picture with heat, and how complete the recordings are. keybr has its own typing rules, so its numbers are measured in a way of their own (`keybr-input-v1`), and keybr's own speed and accuracy are shown apart, labelled "keybr".

```sh
uv run marimo edit notebooks/keybr.py
uv run marimo edit notebooks/keybr.py -- --recordings /path/to/recordings.sqlite   # another file, such as a backup
```

### Settings: `typokiller.toml`

typokiller's settings are in `typokiller.toml` next to its database: in `~/.local/share/typokiller/data` for the service, in this folder for a development server. It is created with defaults and comments on first use. Edit it in any editor.

- `[lists] letters`: the letters that label the lines of the keyboards panel.
- `[keymaps]`: the layer names in the keyboard pictures, for each Board and Letter layout. The `r` key in the keyboards panel writes them. For example:

  ```toml
  [keymaps.Sweep.QWERTY]
  layers = ["Base", "Sym", "Nav", "Stack", "Num"]
  ```

### Test fixtures

The server tests read copies of real `.vil` and `vial.json` files, kept in `tests/fixtures/`. They come from the `sweep-layouts` repo (commit 67c9332), which the tests do not need. They do not follow that repo. To refresh them, copy the files that a test needs from `sweep-layouts`, then change the commit in this line and in `tests/test_app.py`.

The tests of both apps also read keybr's own fixtures in `keybr/packages/keybr-recording/fixtures/` (see `tests/keybr_recordings.py`), so a change on one side that breaks the other side fails a test.

### keybr's own docs

[keybr/docs/detailed_recording.md](keybr/docs/detailed_recording.md) describes the recordings, the keyboards that keybr gets from typokiller, the keyboard picture and the free-range layout.
