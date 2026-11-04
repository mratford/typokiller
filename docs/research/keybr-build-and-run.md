# How is the keybr fork built and run outside development?

Resolves issue #74 (part of map #73). Researched 2026-11-04.

**Question.** How is the keybr fork built and run outside development, so that a launchd service can run it all
the time with recording turned on? Which commands, settings, data folder, tests, Node version, and what does a
server that runs from a git worktree need?

**Sources.** The keybr fork at commit `c1e1c8d5` (`~/src/keybr.com`): `package.json`, `.env.example`,
`AGENTS.md`, `docs/getting_started.md`, `docs/detailed_recording.md`, `build.sh`, `Dockerfile`,
`.github/workflows/ci.yml`, `root/` and the server code named below. typokiller at commit `8212c2a`:
`docs/adr/0002-local-service.md` and `src/typokiller/service.py`. The `.env` file of the checkout was not read.

**Tests.** The checkout was not changed. All commands ran in a separate clone of the fork in a temporary folder,
with Node 24.22.0 and npm 11.19.1 on this Mac. The npm download cache (`~/.npm`) was already full, so the install
time is the time with a warm cache. A first install on a new Mac downloads about 490 MB more. Claims marked
**(test)** come from these runs. Claims marked **(inference)** follow from the sources but are not stated in them.

## Short answer

1. **Commands and timings (test).** From the repo folder:

   | Step | Command | Time | Needed to run? |
   |---|---|---|---|
   | Install packages | `npm ci` | 31 s | yes |
   | Type check | `npm run compile` | 30 s | no, a check only |
   | Build | `npm run build` | 15 s | yes |
   | Tests | `env DATABASE_CLIENT=sqlite npm test` | 63 to 70 s | for `update` |
   | Start | `node --enable-source-maps root/index.js` | under 1 s | yes |

   `npm run build` and the tests work without `npm run compile` first **(test)**. The whole `install, build, test`
   takes about 2 minutes. The upstream CI runs `npm ci`, `compile`, `lint`, `stylelint`, `build`, `test`.
2. **Settings.** keybr reads `.env` from the **current working folder**, like typokiller. The settings for a local
   service with recording:

   ```sh
   APP_URL=http://localhost:3000/
   COOKIE_DOMAIN=localhost
   COOKIE_SECURE=false
   DATA_DIR=~/.local/state/keybr
   DATABASE_CLIENT=sqlite
   DATABASE_FILENAME=~/.local/state/keybr/database.sqlite
   DETAILED_RECORDING=true
   # optional: SERVER_PORT (default 3000), SERVER_PORT_WS (default 3001), APPLICATION_REVISION (default "local")
   ```

   No secret is needed. Mail, Google, Microsoft, Facebook and Paddle keys are read only when those pages are used.
3. **Data.** Recordings are in `DATA_DIR/recordings.sqlite` (with `-wal` and `-shm` files). The server creates the
   folder and the file on the first request **(test)**. Other files in `DATA_DIR` are for accounts only:
   `database.sqlite`, `sessions/`, `user_settings/`, `user_stats/`. keybr's own typing history (results without
   login) is in the browser, in the IndexedDB of the page's address, not on the server.
4. **Node.** The docs and CI ask for **Node 26**. `package.json` has no `engines` field, and there is no `.nvmrc`.
   This Mac has only Node 24 (24.15.0 and 24.22.0, through nvm, default `24`). With Node 24.22.0 all 61 test
   packages pass, and the server runs and records **(test)**. nvm is loaded only by `~/.zshrc`. There is no
   `node` in `/opt/homebrew/bin` or `/usr/local/bin`. So launchd cannot find `node` by itself: the service must
   give the full path to the `node` program, or a `PATH` that contains it.
5. **A worktree service needs (inference from the tests):**
   - its own `node_modules/` from `npm ci` (about 490 MB), then `npm run build`, which writes `root/lib/` (31 MB)
     and `root/public/assets/` (34 MB). The checkout's `node_modules` and build cannot be shared.
   - a working folder outside the worktree with the `.env` above. The launchd agent runs
     `<node> --enable-source-maps <worktree>/root/index.js` with that folder as `WorkingDirectory`.
   - `npm ci` deletes and reinstalls `node_modules` on each `update`. When the tests fail, going back to the old
     commit means `npm ci` and `npm run build` again (about 45 s), unlike `uv sync`.
   - Stopping: SIGTERM to the main process stops all 5 processes within about 1 s **(test)**.

## Commands

`package.json` (scripts):

- `"build": "env NODE_ENV=production webpack"`, `"build-dev": "env NODE_ENV=development webpack"`.
- `"test": "lage test --no-cache"`, `"compile": "lage compile --no-cache"`, `"clean": "lage clean --no-cache"`.
- `"start": "env NODE_ENV=development node --enable-source-maps ./root/index.js"`.
- `"start-docker"`: runs `initdb.ts`, then `NODE_ENV=production node --enable-source-maps ./root/index.js`.
- `"postinstall": "husky && patch-package"`.

**Install.** `npm ci` installs exactly the versions in `package-lock.json` (the `Dockerfile` and CI use it). It is
the npm command that matches `uv sync --locked` in typokiller's service **(inference)**. `postinstall` then:

- runs `patch-package`, which applies the 3 files in `patches/` (to `debug`, `objection` and `ws`). The fork needs
  these, so do not use `npm ci --ignore-scripts`. In the test, the `ws` patch was applied after `npm ci`.
- runs `husky`, which runs `git config core.hooksPath .husky/_` and writes `.husky/_/`
  (`node_modules/husky/index.js`, version 9.1.7). In a git worktree, `git config` writes the config that all
  worktrees share. The checkout already has the same value (`.husky/_`), and the path is relative, so nothing
  changes. To skip this step, set `HUSKY=0` (the code returns at once when `HUSKY` is `0`).

npm 11 prints a warning that the install script of `fsevents` is not allowed. `fsevents` is an optional macOS file
watcher for development tools, so this does not matter for the service **(inference)**.

**Type check.** `npm run compile` runs `tsc` in each package and writes only type declarations to
`packages/*/.types/` (`AGENTS.md`: "package compilation is declaration-only"). The build does not use them:
webpack uses `ts-loader` with `transpileOnly: true` (`webpack.config.js`). In the test, `npm run clean` then
`npm run build` and `npm test` passed. So `compile` is a type check, useful in `update` only as an extra check.

**Build.** `npm run build` runs webpack with `mode = production`. It writes two bundles:

- the server and the CLI to `root/lib/` (`index.js`, `keybr.js` and message files);
- the browser page to `root/public/assets/` (`clean: true`, so old files are deleted).

webpack fixes `process.env.NODE_ENV` in the bundle when it builds. In the built `root/lib/index.js` the line is
`const env = "production" || 0;` **(test)**. So `NODE_ENV` at start time does not change a built server, and
`npm start` (which sets `NODE_ENV=development`) runs a production build as a production build. To run the built
server, the plain `node --enable-source-maps root/index.js` is enough.

The build also reads `packages/thirdparties/lib/config-env` (if it exists) for analytics and payment IDs, and
otherwise `config-env.example`, where all are `0` (`packages/thirdparties/webpack-env.js`). The fork has no
`config-env`, so no analytics code is active.

**`root/` is self-contained.** `AGENTS.md` says `root/` "has no external dependency on the rest of the repo or on
`node_modules` outside itself". In the test, a copy of `root/` in another folder, with no `node_modules`, served
the page and recorded, and its `keybr.js recording export` worked **(test)**. The webpack `externals` are
`sqlite3`, `bufferutil` and `utf-8-validate`, but keybr uses Node's built-in `node:sqlite`
(`packages/keybr-config/lib/knex/node-sqlite.ts`, `packages/keybr-recording-store/lib/index.ts`), and the `ws`
patch removes the `bufferutil` lookup. So the service could also run a copy of `root/`, not the worktree
**(inference)**.

**Start.** `root/index.js` loads `root/_config.js`, which sets `PUBLIC_DIR` to `root/public`, then
`root/lib/index.js`. The main process (`packages/server/lib/main.ts`) reads the `.env` files and starts 5 worker
processes: 4 HTTP workers on `SERVER_PORT` and 1 game (multiplayer) worker on `SERVER_PORT_WS`. When a worker
exits, the main process starts a new one at once. In the test the server answered within about 0.3 s of the
start, and `GET /` took 35 ms.

The CLI is `node root/keybr.js` (for example `recording import-keyboards <file>` and `recording export <file>`).
It reads the same `.env` from its working folder. In the test, keyboards imported while the server ran appeared in
`GET /_/recording/config` at once, with no restart.

**First start.** `docs/getting_started.md` and `AGENTS.md` say: run `packages/devenv/lib/initdb.ts` once, because
`npm start` does not create the account tables. `initdb.ts` creates the 4 account tables only when they are missing
(`packages/keybr-database/lib/schema.ts`), and adds an example login (`user@localhost`, token `xyz`). In the test,
the practice, profile, account and help pages answered 200 without it, the account database file was not created,
and recording worked. Recording needs no login (`docs/detailed_recording.md`). So the service does not need
`initdb.ts` **(test)**. It needs `node_modules` (it runs through `npx tsnode`), so it cannot run from a `root/` copy.

**Stop.** `Service` handles SIGINT and SIGTERM in each worker: it stops taking new connections and exits within
1 s (`packages/server/lib/server/service.ts`). The main process has no handler and exits at once. In the test,
`kill -TERM <main process>` left no keybr process after about 1 s. Batches are committed in one transaction, and
the browser keeps records until the server confirms them (`docs/detailed_recording.md`), so a restart loses no
records **(inference)**. Unlike typokiller, keybr has no `GET /api/busy`; it has no background work that a restart
would lose **(inference)**.

## Settings

`packages/keybr-config/lib/env.ts` reads these files, and the first value of each setting wins:

1. `<working folder>/.env.<NODE_ENV>` (with a production build: `.env.production`)
2. `<working folder>/.env`
3. `/etc/keybr/env.<NODE_ENV>`
4. `/etc/keybr/env`

It uses `process.loadEnvFile`, which does not replace a variable that is already set. So a variable from the
launchd plist `EnvironmentVariables` wins over all the files **(inference from the comment "First definition
wins")**. Paths may start with `~/` (`Env.asPath`). Values must be valid: for example `DETAILED_RECORDING` must be
exactly `true` or `false`, or the server stops with "Invalid env property".

All settings the server reads (from the `Env.get...` calls in `packages/`):

| Setting | Default in code | For a local service |
|---|---|---|
| `DETAILED_RECORDING` | `false` | `true` |
| `DATA_DIR` | `/var/lib/keybr` | a folder of the user, e.g. `~/.local/state/keybr` (`.env.example`) |
| `DATABASE_CLIENT` | `mysql` | `sqlite` |
| `DATABASE_FILENAME` | `:memory:` | e.g. `~/.local/state/keybr/database.sqlite` |
| `SERVER_PORT` | `3000` | `3000`, or another port |
| `SERVER_PORT_WS` | `3001` | `3001`, or another port |
| `APP_URL` | `https://www.keybr.com/` | `http://localhost:<port>/` (used for links in pages and mails) |
| `COOKIE_DOMAIN` | `.www.keybr.com` | `localhost` |
| `COOKIE_SECURE` | `true` | `false` (the page is plain HTTP) |
| `APPLICATION_REVISION` | `local` | e.g. the commit; it is stored with each recorded Attempt |
| `PUBLIC_DIR` | `/opt/keybr/public` | set by `root/_config.js`; do not set |
| `COOKIE_NAME`, `COOKIE_MAX_AGE`, `COOKIE_PATH`, `COOKIE_HTTP_ONLY` | `session`, 14 days, `/`, `true` | defaults |
| `MAIL_DOMAIN`, `MAIL_KEY`, `MAIL_FROM_*` | none | not needed: read only when a login mail is sent |
| `AUTH_GOOGLE_*`, `AUTH_MICROSOFT_*`, `AUTH_FACEBOOK_*`, `PADDLE_*` | none | not needed: read only for those logins and payments |

`.env.example` has all the needed values except `DETAILED_RECORDING=true` and the ports. In the test, a working
folder with only the settings above was enough, with no mail or login keys **(test)**.

**Recording mode and the network.** With `DETAILED_RECORDING=true`, both ports listen on `127.0.0.1` only, and a
request whose `Host` is not `localhost:<port>`, `127.0.0.1:<port>` or `[::1]:<port>` gets an empty 403
(`packages/server/lib/server/service.ts`, `docs/detailed_recording.md`). In the test, `Host: example.com` got 403
**(test)**. So today keybr cannot record when it is opened from another computer. This is the subject of #79.

**Ports.** The service and a development server cannot both use 3000 and 3001. The browser keeps keybr's typing
history, the queue of records not yet sent, and the keyboard and layout choice per address (origin), so
`localhost:3000` and `localhost:3010` are separate. When the service takes over a port that development used, it
also takes over the data that the browser keeps for that address **(inference)**.

## Data

Under `DATA_DIR` (from `packages/server/lib/app/`, `packages/keybr-config/lib/datadir.ts` and the test):

- `recordings.sqlite`, `recordings.sqlite-wal`, `recordings.sqlite-shm`: the recordings (see #75). Created on the
  first request to `/_/recording/...`.
- `database.sqlite` (from `DATABASE_FILENAME`, which can be anywhere): accounts. Created only when it is used.
- `sessions/`, `user_settings/`, `user_stats/`: login sessions and the data of logged-in users.

The data is not in the repo, so it is safe from worktree changes. For backups, use `VACUUM INTO` (as
`keybr recording export` does), not a copy of the main file alone (`docs/detailed_recording.md`).

## Tests

`npm test` runs each package's `test` script through `lage`, with Node's own test runner (the `tstest` wrapper).
The database tests use MySQL unless `DATABASE_CLIENT=sqlite` is set (`AGENTS.md`, CI). So the command is
`env DATABASE_CLIENT=sqlite npm test`. In the test it took 70 s after `compile` and 63 s without it, and all
61 packages passed with Node 24.22.0 **(test)**. Tests use temporary databases (`docs/detailed_recording.md`), so
they do not touch the service data. They do not need the build. `npm run lint` and `npm run stylelint` are style
checks, not needed for `update`.

## What a git worktree gets

After `npm ci`, `npm run build` (and optionally `npm run compile`), `git status --ignored` lists **(test)**:

| Path | Made by | Size |
|---|---|---|
| `node_modules/`, `packages/keybr-generators/node_modules/`, `packages/keybr-logger/node_modules/` | `npm ci` (downloaded) | 492 MB |
| `.husky/_/` | `npm ci` (husky) | small |
| `root/lib/` | `npm run build` | 31 MB |
| `root/public/assets/` | `npm run build` | 34 MB |
| `packages/*/.types/` | `npm run compile` | small |

The checked-out source is about 90 MB. `packages/keybr-intl/translations/*-merged.json` in the checkout come from
`npm run translate`, a step for translators, and are not needed.

All of these are in `.gitignore`, so `git checkout --detach <commit>` in the worktree keeps them. After a checkout,
run `npm ci` and `npm run build` again: old files in `root/lib/` stay (`clean: false`) but are not used, because
the new `index.js` names its own files **(inference)**.

## Consequences for the service (inference)

A keybr service in the style of ADR 0002 could be:

- **Code:** a git worktree of `~/src/keybr.com` at a fixed commit, with no branch (for example
  `~/.local/share/keybr/app`).
- **Data and settings:** a folder outside the worktree (for example `~/.local/share/keybr/data`) with `.env`.
  `DATA_DIR` can be this same folder or `~/.local/state/keybr`. It is the agent's `WorkingDirectory`.
- **launchd agent:** `ProgramArguments` = `[<full path to node>, "--enable-source-maps",
  "<app>/root/index.js"]`, `KeepAlive`, `RunAtLoad`, a log file. `EnvironmentVariables` can set
  `DETAILED_RECORDING=true` and `APPLICATION_REVISION=<commit>`, so that the plist, not a file, holds the values the
  install command owns.
- **install / update:** `git checkout --detach <commit>`, `HUSKY=0 npm ci`, `npm run build`,
  `env DATABASE_CLIENT=sqlite npm test`; on failure, check out the old commit and run `npm ci` and `npm run build`
  again; on success, back up `recordings.sqlite` with `VACUUM INTO` and restart with `launchctl kickstart -k`.
  About 2 minutes with a warm npm cache. The first install also downloads about 490 MB.
- **Node:** choose one Node program and write its full path into the plist, for example the nvm default
  (`~/.nvm/versions/node/v24.22.0/bin/node`) or a Homebrew `node`. An nvm path changes when Node is updated, so the
  install command should find it again at each `update` (for example `command -v node` in the user's shell). The
  docs ask for Node 26, but Node 24.22.0 passed all tests.
- **Wait for start:** the server answers in under 1 s; `GET /_/recording/config` returns
  `{"enabled":true,...}` when recording is on.
