# typokiller

## Running

```sh
uv run typokiller          # serves http://<this Mac>:8000 on the LAN
uv run pytest              # server tests
node --test tests/*.test.js   # typing rules tests
uv run pyright src tests   # type check
```

The database is `typokiller.db` in the current directory. The Gutenberg catalogue, `pg_catalog.csv`, is downloaded next to it in the background when the server starts, and again when it is a week old. The settings are in `typokiller.toml` next to it, created with defaults and comments on first use. Edit it in any editor, or press `,` in the Escape menu.

Code Sources (`i` then `c` in the Escape menu) are cloned with the `git` command, so it uses the Mac's own git credentials and private repos work. git must not need to ask for a password.

Articles (`i` then `a` in the Escape menu) are sent with a bookmarklet. Drag the link in that panel to the bookmarks bar. The link opens `/send` on the address that typokiller was loaded from. So open typokiller at the address that the reading browser uses to reach this Mac, and drag the link from there.

Press `m` in the Escape menu to draw the Board's Keymap faintly under the Passage. Layer names come from `[keymaps]` in `typokiller.toml`, for example:

```toml
[keymaps.Sweep.QWERTY]
layers = ["Base", "Sym", "Nav", "Stack", "Num"]
```

Press `p` in the Escape menu for the progress page of the Session's Board and Letter layout. `h` and `l` show the previous and next Board × Letter layout, a number shows that layer of the Keymap, and `j`/`k` select one of the weakest pairs, which is drawn as an arc. Esc goes back. The page loads `vega-embed` from cdn.jsdelivr.net to draw the trend chart, so the chart needs the internet; the rest of the page does not.

The notebook `notebooks/progress.py`, shows the progress page again, made with the same functions as the app, so the numbers are the same. It adds the Weakness costs of each layer: the Weakness model ranks each layer's keystrokes on their own. Open it in marimo from this folder:

```sh
uv run marimo edit notebooks/progress.py                     # typokiller.db in this folder
uv run marimo edit notebooks/progress.py -- --db other.db    # another database
uv run python notebooks/progress.py --db other.db            # run every cell once, with no browser
```

Like the server, it reads the settings in `typokiller.toml` next to the database, and adds any missing settings to that file. It opens the database read only, so the server can run at the same time. A new notebook can import the same functions from `typokiller.analysis` and `typokiller.drawing`.

On free-range (the `[unlocking]` settings name the Letter layout being learned), Drills use only the Unlocked keys. The status line shows the progress, such as `10/30 keys · next o`. After each finished Attempt, the next key unlocks when each Unlocked key is fast enough; `u` in the Escape menu unlocks it at once. After an unlock, the next Drills are Introduction Drills of the new key. Keymap drawings show locked keys dashed and faint, with a ring on the next one.

Press `e` in the Escape menu for endless Drills, and `y` for endless Symbol Drills. The Targets of Symbol Drills are only Symbols (the digits and ``!"#$%&()*+-/:;<=>?@[\]^`{|}~``) and symbol pairs (pairs with a Symbol and no space or newline), and their text is whole lines of code from the code Sources and the code of Lessons. They may use every key, locked or not, and no Introduction Drill breaks into them. The `[symbols]` settings hold the numbers of Targets and lines.

Press `i` then `s` in the Escape menu to import the symbol docs. This clones the Python and Gleam documentation from GitHub in the background (it needs the internet) and makes four code Sources from their examples: the Python tutorial and library (the branch is the `[symbols]` setting `python_branch`), the Gleam language tour and the Gleam standard library. A notice says when they are imported. Their text is kept only in the database. Importing again adds four new Sources from the newer docs. After an import, each Symbol that fewer than `min_lines` (50) lines of the Symbol Drills' line pool hold gets a Symbol Lesson: a Python Lesson (see `l` below) on a topic that the model chooses because it uses that Symbol, titled "Symbol ^: <topic>". The notice lists the rarest Symbols and the Symbol Lessons queued. When a Symbol Lesson is written, the lines that hold its Symbol are counted again, and the Symbol gets one more Symbol Lesson while it is still in fewer than `min_lines` lines, up to `max_lessons` (3) for each Symbol. Each is checked against the monthly cap like any Lesson. Import again only for a new `python_branch`. The Symbol Lessons and the Sources from the symbol docs are Symbol Sources: they give lines of code to Symbol Drills and words to Drills, but they are not in the list of Sources (`o`), and a new Session does not resume them.

Press `l` in the Escape menu for a new Lesson: type a topic, such as `decorators`, then Enter. The form shows what Lessons cost this month. First press `p` for Python or `g` for Gleam; Enter chooses the language used last. A model writes the Lesson through OpenRouter in the background (Python: Claude Haiku 5.5, about $0.002 a Lesson; Gleam: Claude Sonnet 5.5, about $0.05 a Lesson), and a notice says when it is ready. It is then first in the list of Sources (`o`). The API key is `OPENROUTER_API_KEY`, from the environment or from a `.env` file in the folder that the server runs in (it is gitignored), for example `OPENROUTER_API_KEY=sk-or-...`. The `[lessons]` settings hold the model, the length and level, and the monthly cap (£5); a request that could make the month's cost more than the cap is refused. Each code example is run on this Mac under `sandbox-exec`, in a new temp folder, with no network and no writes outside that folder. An example that fails is sent back to the model for a repair, at most twice, and is then dropped. A Lesson with too many dropped examples is written once again, and then rejected.

Gleam examples need `gleam` and Erlang on this Mac. Each one is built and run in a copy of the pre-made project in `src/typokiller/gleam/`, where `manifest.toml` pins the library versions. When you ask for a Gleam Lesson, typokiller first runs `gleam build` there. The first time, this downloads the libraries (it needs the internet) and compiles them into `src/typokiller/gleam/build/`; after that it does nothing. If it fails, the request is refused with gleam's error, and nothing is sent to the model. To make that folder again, delete it; the next Gleam Lesson request makes it. The Gleam tests are skipped while the folder is missing, because tests do not use the network. To make it at once:

```sh
rm -rf src/typokiller/gleam/build && (cd src/typokiller/gleam && gleam build)
```

The server tests read real `.vil` and `vial.json` files from the `sweep-layouts` repo, which must be in the same folder as this repo.
