# The service runs from its own worktree, with its data outside the repo

typokiller runs all the time as a launchd agent on this Mac (#64). The agent does not run the code in the checkout, and its database is not the one in the checkout. Another session commits to `main` in the checkout while the service is in use. So a half-finished change in the checkout could break the service at its next restart, and testing by hand could write to the real database.

- The code is a git worktree at `~/.local/share/typokiller/app`. It has a fixed commit checked out, with no branch. It changes only when `update` is run.
- The data is in `~/.local/share/typokiller/data`: `typokiller.db`, `typokiller.toml`, `.env`, `pg_catalog.csv` and `backups/`. This folder is the agent's working folder. `main()` reads these files from the working folder, as ADR 0001 says, so the server code does not know about the service.
- The checkout keeps its own `typokiller.db`, which is only for development. `install` moves the real database out of the checkout once, so that it exists in one place only.
- `update` is run by hand. It moves the worktree to a commit (local `main` by default), runs `uv sync`, then the tests. If they fail, it moves the worktree back and does not restart. If they pass, it backs up the database with `VACUUM INTO`, keeps the last 10 backups, and restarts the agent.

## Considered options

- **Run the checkout itself.** Rejected: commits from the parallel session would go live at the next restart, and development would share the real database and port 8000.
- **`uv tool install`.** Rejected: it does not follow `uv.lock`, so the service could run dependency versions that the tests never ran with. Each install also deletes the package folder, together with the Gleam `build/` folder in it.
- **Update after each commit (git hook) or on a timer.** Rejected: the service would restart while typing, and a commit can be one step of a longer change. A failed timer update would show no message.

## Consequences

- To see the real data, open `~/.local/share/typokiller/data/typokiller.db`. The notebooks open it by default when it exists.
- A restart ends all background work (queued Lessons, clones, the Symbol docs import), because that work lives only in the server process (ADR 0001). So `update`, `restore` and `stop` first ask `GET /api/busy`, and refuse without `--force` while work is running.
- The service runs on port 8000, which the article bookmarklet has built in. Development uses another port, with `--port`.
- The service runs with `--no-access-log`, because the page asks for notices every second. Its log, `~/Library/Logs/typokiller.log`, stays small and needs no rotation.
- `restore` changes only the database, not the code. This works because new code adds its missing columns when it starts (ADR 0001), so an older database runs with newer code.
