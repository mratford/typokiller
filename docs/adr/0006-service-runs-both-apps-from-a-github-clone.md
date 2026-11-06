# The service runs both apps from a clone of GitHub `main`

This replaces ADR 0002. The aim is now a setup for a user who does not use a terminal day to day: they type in keybr and open typokiller's analysis page, and they use the terminal only to set up and to update. Such a user has no checkout that they commit to, so the service can no longer take its code from the local `main`. And keybr is now in this repo (ADR 0005), so the service runs both apps from one copy of the code. The decision is in the ticket "How does one command install and update both apps?" (#82) of the map #73.

- **Setup.** One line, with no checkout: `uvx --from git+https://github.com/mratford/typokiller typokiller-service install`. It clones the repo into `~/.local/share/typokiller/app` (one commit checked out, no branch), builds and tests both apps, and starts two launchd agents, `local.typokiller` and `local.keybr`. It puts a `typokiller-service` link in `~/.local/bin` that points at the copy in the app folder, so later commands work from any folder and always run the installed code.
- **Data stays outside the code**, as in ADR 0002: `~/.local/share/typokiller/data` and `~/.local/share/keybr/data` (keybr's `DATA_DIR`, with `recordings.sqlite`). These folders, the ports (typokiller 8000, keybr 3100 and 3101) and the labels are constants in `service.py`. keybr's `.env` and plist are written again by each `install` and `update`, so nobody edits them by hand.
- **`update` gets its code from GitHub.** It runs `git fetch`, moves the clone to `origin/main` (or to a given commit), and runs typokiller's tests and then keybr's `npm ci`, `npm run build` and tests. Both apps are updated, or neither: if any step fails, the clone goes back to the old commit and nothing restarts.
- **Every command acts on both apps.** There is no option to act on one app.
- **Backups.** `typokiller.db` and keybr's `recordings.sqlite` are backed up at each `update`. Because the recordings are now all the history, the typokiller server also backs up both files when it starts and every 24 hours. It opens `recordings.sqlite` read-only for this, because keybr writes it.

## Considered options

- **Take the code from the local `main`, as ADR 0002 did.** It was rejected because a user who does not develop would have to run `git pull` in a checkout first.
- **Update each app on its own.** It was rejected because a change to both apps could then arrive in only one of them.
- **A `curl … | sh` script that also installs uv and node.** It was rejected because it is one more file to keep working, and `brew install uv node` is a single line.

## Consequences

- To try unmerged work in the service, push the branch and run `typokiller-service update origin/<branch>`. Local commits that are not pushed cannot be installed.
- A development server uses keybr's ports 3000 and 3001. The browser keeps keybr's history separately for each address, so development typing does not mix with the service's.
- This Mac moves over once, by hand: the old `uninstall` (which removes the worktree), then the new install line. The data folder is kept.
