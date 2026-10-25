# Web framework, job runner and project layout

The spec (#17, §2) left three choices to the first build ticket (#18). typokiller has one user on a LAN, so each choice takes the simplest option that will still work when later tickets add Lessons, imports and charts.

## Web framework: FastAPI on uvicorn

FastAPI checks the shape of each batch of key events with Pydantic models, and its test client lets tests call the API without a running server. The page is plain JavaScript served as static files by the same app, so there is no build step. The database is the standard `sqlite3` module with SQL written by hand; there is no ORM. Endpoints are `async`, so all database work runs on one thread and no locking is needed.

## Job runner: tasks inside the server process

Background work (Lesson generation, git clones, the Gutenberg catalogue refresh) will run as `asyncio` tasks in the server process, reading from an `asyncio.Queue` so that requests wait in order. Blocking work runs through `asyncio.to_thread`. There is no separate worker process and no Redis. This is not built yet, because #18 has no background work.

## Project layout

- `pyproject.toml`, managed with `uv`. `uv run typokiller` starts the server on port 8000 on all interfaces.
- `src/typokiller/app.py`: the schema, the API and the static file mount.
- `src/typokiller/static/`: the page. `typing.js` holds the typing rules and has no DOM code, so Node can test it.
- `tests/`: `pytest` for the API, `node --test` for `typing.js`.
- The database is `typokiller.db` in the working directory.

## Consequences

- The schema is created with `CREATE TABLE IF NOT EXISTS`. A later ticket that changes a table has to add its own `ALTER TABLE`.
- A Session has no stored end time. It is computed when the data is read, as `started` plus the `t` of the Session's last key event. `t` counts from page load, which is a little before `started`, so the result is a little late. A stored end time was tried, but it could not be sent reliably when the tab closes. The spec (§5) lists "end" on Session; this is the change.
- The browser keeps key events until the server confirms it has stored them, and sends them again until then. The server ignores events it already has, so batches may overlap. The last batch before the page closes is sent with `keepalive`, which Chrome limits to 64 KB, so only that batch uses it.
- The server stores an Attempt when it receives the Attempt's first key event. The Attempt stays abandoned unless the page reports it as finished. So an Attempt with no key events, such as a restart before typing anything, is not stored.
- There is no Passage table yet. The ticket that imports Sources adds it, and adds a Passage column to Attempt. Every Attempt stored before then typed the `PASSAGE` text in `app.py`, so that ticket links them to it.
- Attempt does not yet store the wrong-key mode, whether the Keymap was shown, or the settings (spec §5). Only one mode exists so far; the tickets that add the other mode, the Keymap and settings add these columns.
