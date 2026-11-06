# typokiller

typokiller's typing page is a changed copy of [keybr.com](https://www.keybr.com/) by Aliaksandr Radzivanovich ([aradzie/keybr.com](https://github.com/aradzie/keybr.com)), under the AGPL 3.0.
The code in `keybr/` is under the AGPL 3.0 (see `keybr/LICENSE` and `keybr/NOTICE`). The rest of this repo is also under the AGPL 3.0 (see `LICENSE`).

## Running

typokiller and keybr run all the time on this Mac as two launchd services: typokiller on port 8000 (the analysis page), keybr on port 3100 (the typing page). Other computers on the home network use the name of this Mac, for example http://marge.local:3100/. Both run from their own copy of this repo, a clone of GitHub in `~/.local/share/typokiller/app`, which changes only when you update it. typokiller's database, settings and backups are in `~/.local/share/typokiller/data`, and keybr's recorded lessons, settings and backups in `~/.local/share/keybr/data`. The logs are `~/Library/Logs/typokiller.log` and `~/Library/Logs/keybr.log`. The reasons are in `docs/adr/0006-service-runs-both-apps-from-a-github-clone.md`.

Install it once, with `git`, `uv` and `node` 24 or newer (`brew install uv node`). No checkout is needed:

```sh
uvx --from git+https://github.com/mratford/typokiller typokiller-service install
```

After that, `typokiller-service` is in `~/.local/bin`. Each command acts on both apps:

```sh
typokiller-service update      # go to the latest commit of main on GitHub
typokiller-service update abc1234        # go to another commit, also an older one
typokiller-service update origin/branch  # go to a branch that is pushed to GitHub
typokiller-service status      # running or not, the commit, the addresses, the newest backups
typokiller-service logs        # the end of both logs, as they grow (Ctrl-C stops)
typokiller-service stop        # stop both until the next login
typokiller-service start
typokiller-service restore     # list the backups, newest first
typokiller-service restore recordings-2026-11-01-093015.sqlite
typokiller-service uninstall   # remove both, but keep the data and the logs
```

`update` gets the code from GitHub. It installs the packages of both apps, builds keybr and runs the tests of both. If a step fails, it goes back to the old commit and both apps continue with the old code. If all pass, it backs up `typokiller.db` and keybr's `recordings.sqlite` to `backups/` in their data folders, and restarts keybr, then typokiller. typokiller also backs up both files when it starts and every 24 hours. The 10 newest backups of each file are kept.

To go back to a backup, list them with `restore`, then give one file name. Both apps stop, the file is backed up first (so you can undo the restore with the same command), the chosen backup takes its place, and both apps start again. The code does not change.

For development, run a server from this folder on another port. It uses `typokiller.db` and `typokiller.toml` in this folder, not the service's data:

```sh
uv run typokiller --port 8001
uv run pytest              # server tests
node --test tests/*.test.js   # page tests
uv run pyright             # type check
```

The database is `typokiller.db` in the folder that the server runs in. The settings are in `typokiller.toml` next to it, created with defaults and comments on first use. Edit it in any editor.

`/` opens the analysis page. On it, `b` opens the keyboards panel and `t` opens the typing page. The panel has one line for each keyboard and layout. Type a line's label, or move with `j`/`k` and press `Enter`, to see the analysis of that layout. In the panel, `n` adds a keyboard (choose its `vial.json`, give it a name, then choose a `.vil`), `v` saves a `.vil` on the selected keyboard (the same letters as a saved layout make a new version of it, other letters make a new layout), and `r` sets the layer names of the selected layout, separated by spaces. `Esc` stops a form. `Esc` or `b` closes the panel. The typing page has a link "analysis" back to this page.

The keyboard pictures name the layers of a layout with the names in `[keymaps]` in `typokiller.toml` (the `r` key in the panel writes them there), for example:

```toml
[keymaps.Sweep.QWERTY]
layers = ["Base", "Sym", "Nav", "Stack", "Num"]
```

### Typing in keybr

keybr (in `keybr/`) records in detail everything that you type there, for the keyboard and layout that you choose there. The notebook `notebooks/keybr.py` reads these recordings. keybr has its own typing rules, so its numbers are measured in a way of their own (`keybr-input-v1`). keybr's own speed and accuracy are shown apart, labelled "keybr". See [keybr/docs/detailed_recording.md](keybr/docs/detailed_recording.md) for how to turn recording on.

1. Give keybr the address of typokiller, in `keybr/.env`:

   ```sh
   TYPOKILLER_URL=http://127.0.0.1:8000
   ```

   Each time the typing page loads, keybr then gets the keyboards and their saved layouts from typokiller, with the layer names in `typokiller.toml`. It gets only the keyboards and layouts: no typing history, no API keys. After you add a layout to a keyboard in typokiller, or change its layer names, reload the typing page. Choose the keyboard and layout there. It also gets the keyboard picture of each layout, which it shows under the text in place of its own picture, with the layer of the next character. When typokiller does not answer, the typing page uses the keyboards that it got the last time, shows its own keyboard picture, and says that keyboards can be missing.

2. After typing in keybr, open the notebook, in this folder:

   ```sh
   uv run marimo edit notebooks/keybr.py
   ```

   It reads keybr's recorded lessons in `~/.local/share/keybr/data/recordings.sqlite` once, read only, while keybr runs. To open another file, such as a backup, add `-- --recordings /path/to/recordings.sqlite`. It never opens the typokiller database. It has filters for the keyboard, the layout, the saved version of the layout and the days. It shows keybr's own progress, the first-input accuracy, the weakest characters and pairs, fix times, timings, the keyboard picture with heat, and how complete the recordings are.

The server tests read copies of real `.vil` and `vial.json` files, kept in `tests/fixtures/`. They come from the `sweep-layouts` repo (commit 67c9332), which the tests do not need. They do not follow that repo. To refresh them, copy the files that a test needs from `sweep-layouts`, then change the commit in this line and in `tests/test_app.py`.

### From another computer

keybr and typokiller can also be opened from another computer on the home network, with the name of this Mac, for example `http://marge.local:8000/` for the analysis page. On this Mac, use `localhost`. Both apps (keybr when it records) answer only when the address is `localhost`, an IP address or a name that ends in `.local`. Each computer has its own keybr progress. See [keybr/docs/detailed_recording.md](keybr/docs/detailed_recording.md#opening-keybr-from-another-computer).
