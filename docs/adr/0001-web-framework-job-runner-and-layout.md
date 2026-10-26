# Web framework, job runner and project layout

The spec (#17, §2) left three choices to the first build ticket (#18). typokiller has one user on a LAN, so each choice takes the simplest option that will still work when later tickets add Lessons, imports and charts.

## Web framework: FastAPI on uvicorn

FastAPI checks the shape of each batch of key events with Pydantic models, and its test client lets tests call the API without a running server. The page is plain JavaScript served as static files by the same app, so there is no build step. The database is the standard `sqlite3` module with SQL written by hand; there is no ORM. Endpoints are `async`, so all database work runs on one thread and no locking is needed.

## Job runner: tasks inside the server process

Background work (Lesson generation, git clones, the Gutenberg catalogue refresh) runs as `asyncio` tasks in the server process. Lesson generation will read from an `asyncio.Queue` so that requests wait in order. Blocking work runs through `asyncio.to_thread`. There is no separate worker process and no Redis. #21 added the first background work, the Gutenberg catalogue refresh: one task started with the app that checks every hour, so it needs no queue. #22 added git clones without a queue too: each request starts its own task, so several clones can run at the same time.

## Project layout

- `pyproject.toml`, managed with `uv`. `uv run typokiller` starts the server on port 8000 on all interfaces.
- `src/typokiller/app.py`: the schema, the API, the static file mount, the downloads from gutenberg.org with the catalogue refresh, and the git clones.
- `src/typokiller/keymap.py`: reads the QMK settings and the Letter layout from a `.vil` and a `vial.json`.
- `src/typokiller/sources.py`: the `ascii-v1` normaliser, splitting a Gutenberg book or a code file into Passages, and searching the Gutenberg catalogue.
- `src/typokiller/static/`: the page. `typing.js` holds the typing rules and has no DOM code, so Node can test it.
- `tests/`: `pytest` for the API, `node --test` for `typing.js`.
- The database is `typokiller.db` in the working directory. The settings file is `typokiller.toml` next to it; it is created with defaults and comments when it is missing.

## Consequences

- The schema is created with `CREATE TABLE IF NOT EXISTS`. A later ticket that changes a table has to add its own `ALTER TABLE`. #19 added `attempt.settings` and #20 added `session.keymap_version` this way; rows stored before then have NULL there.
- A Board stores its `vial.json` and has one row in `keymap_version` for each distinct `.vil`, keyed by a hash of the file. A Keymap is not stored: it is a Board with one Letter layout, and its versions are the `.vil` files of that Board with that Letter layout. A new Session uses the newest version. Adding a Board with a name that exists adds the `.vil` to that Board and replaces its `vial.json`. The Letter layout is computed on read, so a `.vil` that changes its letters starts a new Keymap.
- A Session has no stored end time. It is computed when the data is read, as `started` plus the `t` of the Session's last key event. `t` counts from page load, which is a little before `started`, so the result is a little late. A stored end time was tried, but it could not be sent reliably when the tab closes. The spec (§5) lists "end" on Session; this is the change.
- The browser keeps key events until the server confirms it has stored them, and sends them again until then. The server ignores events it already has, so batches may overlap. The last batch before the page closes is sent with `keepalive`, which Chrome limits to 64 KB, so only that batch uses it.
- The server stores an Attempt when it receives the Attempt's first key event. The Attempt stays abandoned unless the page reports it as finished. So an Attempt with no key events, such as a restart before typing anything, is not stored.
- #21 added the `source` and `passage` tables and `attempt.passage`. The `PASSAGE` text in `app.py` is Passage 1, which has no Source. It is typed when no Source is open, and every Attempt stored before #21 is linked to it.
- A Source's bookmark is the ord of its next Passage. Paragraphs skipped because of the `[passages]` settings (`max_dropped`, `min_length`) are not stored as Passages, so the ords have no gaps. A Source stores its number of Passages as `total`, and it is finished when its bookmark equals `total`. The last used Source is the one with the latest `opened` time; setting the bookmark updates it.
- The server serves a Passage together with the one after it. After a Source's last Passage, the built-in Passage comes next, so the page always has a next Passage to show at once.
- The Gutenberg catalogue is `pg_catalog.csv` next to the database. It is downloaded when it is missing or a week old, and read again for each search. Downloads use the `truststore` package so that certificates are checked with the macOS keychain: Python's default certificate file lacks the root certificate that gutenberg.org uses.
- The page reads the settings file when an Attempt starts and sends those settings with the Attempt's key events. Attempt stores them as JSON in its `settings` column, so the wrong-key mode is `settings ->> '$.typing.wrong_key_mode'`; there is no separate column for it. Attempts stored before #19 have no settings; they were all typed in "keep typing" mode.
- Attempt does not yet store whether the Keymap was shown (spec §5). The ticket that draws the Keymap under the Passage adds it.
- #22 added code Sources. `POST /api/code` clones the repo with `git clone --depth 1` in a temporary folder, in an `asyncio` task of its own, and returns at once. There is no queue, so clones may run at the same time. The task keeps only the text files that git tracks (valid UTF-8 with no NUL character, not symbolic links), shuffles them once, and splits each file into functions at blank lines. A code Source stores its text as each file's text after a `--- path` line, in the shuffled order; its Passages have the same order. `ascii-v1` keeps `\n`, so code Passages have newlines; prose Passages have none because their line breaks become spaces before normalising.
- Background work reports to the page through notices: `GET /api/notices` returns a list of strings that the server keeps in memory, so it is empty again after a restart. The page reads it every second and shows each notice added since the page loaded on the message line. Later background work (the article bookmarklet, Lessons) appends its notices to the same list.
- Code typing rules (#22, in `typing.js`): Enter goes in only where the Passage has `\n`. The spaces at the start of the next line are then added to the typed text with no key events. Backspace just after those spaces removes them together with the newline. Code that replays key events to find what was typed must follow these rules. Tabs in code become 4 columns when the Passage is made, so a file written for 8-column tabs looks different from the file.
