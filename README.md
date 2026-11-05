# typokiller

## Running

typokiller runs all the time on this Mac as a launchd service, on port 8000 (http://<this Mac>:8000 on the LAN). The service does not run the code in this folder. It runs its own copy, a git worktree in `~/.local/share/typokiller/app`, which changes only when you update it. Its database, settings and backups are in `~/.local/share/typokiller/data`. Its log is `~/Library/Logs/typokiller.log`. The reasons are in `docs/adr/0002-local-service.md`.

```sh
uv run typokiller-service install     # set it up and start it
uv run typokiller-service update      # go to the latest local main
uv run typokiller-service update abc1234   # go to another commit, also an older one
uv run typokiller-service status      # running or not, its commit, its newest backup
uv run typokiller-service logs        # the end of the log, as it grows (Ctrl-C stops)
uv run typokiller-service stop        # stop it until the next login
uv run typokiller-service start
uv run typokiller-service restore     # list the backups, newest first
uv run typokiller-service restore typokiller-2026-11-01-093015-abc1234.db
uv run typokiller-service uninstall   # remove it, but keep the data and the log
```

`install` runs the tests in the new worktree, moves `typokiller.db` from this folder to the data folder, and copies `typokiller.toml` there. It refuses while something answers on port 8000, so stop a server that runs from this folder first. After an `uninstall`, `install` keeps the database that is in the data folder already.

`update` moves the worktree to the commit, installs its packages and runs the tests. If they fail, it goes back to the old commit and the service continues with the old code. If they pass, it backs up the database to `backups/` in the data folder, keeps the 10 newest backups, and restarts the service.

To go back to a backup, list them with `restore`, then give one file name. The service stops, the database is backed up first (so you can undo the restore with the same command), the chosen backup becomes the database, and the service starts again. The code does not change.

For development, run a server from this folder on another port. It uses `typokiller.db` and `typokiller.toml` in this folder, not the service's data:

```sh
uv run typokiller --port 8001
uv run pytest              # server tests
node --test tests/*.test.js   # page tests
uv run pyright             # type check
```

The database is `typokiller.db` in the folder that the server runs in. The settings are in `typokiller.toml` next to it, created with defaults and comments on first use. Edit it in any editor.

The keyboard pictures name the layers of a layout with the names in `[keymaps]` in `typokiller.toml`, for example:

```toml
[keymaps.Sweep.QWERTY]
layers = ["Base", "Sym", "Nav", "Stack", "Num"]
```

### Typing in keybr

keybr (github.com/mratford/keybr.com) records in detail everything that you type there, for the keyboard and layout that you choose there. The notebook `notebooks/keybr.py` reads these recordings. keybr has its own typing rules, so its numbers are measured in a way of their own (`keybr-input-v1`). keybr's own speed and accuracy are shown apart, labelled "keybr". See keybr's [docs/detailed_recording.md](https://github.com/mratford/keybr.com/blob/master/docs/detailed_recording.md) for how to turn recording on.

1. Write your keyboards and their saved layouts to a file, here in this folder:

   ```sh
   uv run typokiller-export-keyboards keyboards.json
   ```

   It reads the service's database (or `typokiller.db` in this folder), or the one given with `--db`, and the layer names from `typokiller.toml` next to it (or the file given with `--settings`). It opens the database read only and changes neither file, and it does not need the server. It writes only the keyboards and layouts: no typing history, no API keys. It does not overwrite a file.

2. Import the file in the keybr folder. Importing the same file again adds nothing:

   ```sh
   node root/keybr.js recording import-keyboards /path/to/keyboards.json
   ```

   Do this again after you add a layout to a keyboard in typokiller, or change its layer names. Then reload keybr's practice page, and choose the keyboard and layout there.

3. After typing in keybr, write a snapshot of the recordings, in the keybr folder. Use a new file name:

   ```sh
   node root/keybr.js recording export /path/to/keybr-recordings.sqlite
   ```

4. Open the notebook on the snapshot, in this folder:

   ```sh
   uv run marimo edit notebooks/keybr.py -- --snapshot /path/to/keybr-recordings.sqlite
   ```

   With no `--snapshot`, it opens `keybr-recordings.sqlite` in this folder. It opens the snapshot read only and never opens the typokiller database. It has filters for the keyboard, the layout, the saved version of the layout and the days. It shows keybr's own progress, the first-input accuracy, the weakest characters and pairs, fix times, timings, the keyboard picture with heat, and how complete the recordings are.

The server tests read copies of real `.vil` and `vial.json` files, kept in `tests/fixtures/`. They come from the `sweep-layouts` repo (commit 67c9332), which the tests do not need. They do not follow that repo. To refresh them, copy the files that a test needs from `sweep-layouts`, then change the commit in this line and in `tests/test_app.py`.
