# typokiller

## Running

```sh
uv run typokiller          # serves http://<this Mac>:8000 on the LAN
uv run pytest              # server tests
node --test tests/*.test.js   # typing rules tests
uv run pyright src tests   # type check
```

The database is `typokiller.db` in the current directory. The Gutenberg catalogue, `pg_catalog.csv`, is downloaded next to it in the background when the server starts, and again when it is a week old. The settings are in `typokiller.toml` next to it, created with defaults and comments on first use. Edit it in any editor, or press `,` in the Escape menu.

In a list, such as the list of keyboards or the list of texts (`o`), type an item's label of one or two letters to choose it, or select it with `j`/`k` and press Enter. After the first letter of a two-letter label, Esc or Backspace removes it. The letters are the `[lists]` setting `letters`.

Code from a git repo (`i` then `c` in the Escape menu) is cloned with the `git` command, so it uses the Mac's own git credentials and private repos work. git must not need to ask for a password.

Articles (`i` then `a` in the Escape menu) are sent with a bookmarklet. Drag the link in that panel to the bookmarks bar. The link opens `/send` on the address that typokiller was loaded from. So open typokiller at the address that the reading browser uses to reach this Mac, and drag the link from there.

Press `m` in the Escape menu to show a faint picture of the keyboard's layout under the text. Layer names come from `[keymaps]` in `typokiller.toml`, for example:

```toml
[keymaps.Sweep.QWERTY]
layers = ["Base", "Sym", "Nav", "Stack", "Num"]
```

Press `p` in the Escape menu for the progress page of the keyboard and layout that you are typing on. `h` and `l` show the previous and next keyboard and layout, a number shows that layer of the layout, and `j`/`k` select one of the weakest pairs, which is drawn as an arc. Esc goes back. The page loads `vega-embed` from cdn.jsdelivr.net to draw the trend chart, so the chart needs the internet; the rest of the page does not.

The notebook `notebooks/progress.py`, shows the progress page again, made with the same functions as the app, so the numbers are the same. It also ranks your weakest keys in each layer, with the keystrokes of each layer on their own. Open it in marimo from this folder:

```sh
uv run marimo edit notebooks/progress.py                     # typokiller.db in this folder
uv run marimo edit notebooks/progress.py -- --db other.db    # another database
uv run python notebooks/progress.py --db other.db            # run every cell once, with no browser
```

Like the server, it reads the settings in `typokiller.toml` next to the database, and adds any missing settings to that file. It opens the database read only, so the server can run at the same time. A new notebook can import the same functions from `typokiller.analysis` and `typokiller.drawing`.

On free-range (the `[unlocking]` settings name the layout being learned), only four keys are unlocked at the start (`t s r e`), and drills use only the unlocked keys. Their words come from a fixed list of common British English words (SCOWL, size 35, in `src/typokiller/words.txt`), not from your texts. While the list has fewer than `min_words` (200) words for the unlocked keys, made-up words fill it up. A made-up word is not a real word, but its letter pairs are common in the word list. The status line shows the progress, such as `4/30 keys · next a`. After each finished part, the next key unlocks when each unlocked key is fast enough; `u` in the Escape menu unlocks it at once. After an unlock, the next drills are new key drills of the new key. Keyboard pictures show locked keys dashed and faint, with a ring on the next one.

Press `d` in the Escape menu for one drill of your weakest keys, `e` for endless drills, and `y` for endless symbol drills. Symbol drills practise only symbols (the digits and ``!"#$%&()*+-/:;<=>?@[\]^`{|}~``) and symbol pairs (pairs with a symbol and no space or newline), and their text is whole lines of code from the code texts and the code of lessons. They may use every key, locked or not, and no new key drill breaks into them. The `[symbols]` settings hold how many symbols and lines each one has.

Press `i` then `s` in the Escape menu to add the Python and Gleam docs. This clones the Python and Gleam documentation from GitHub in the background (it needs the internet) and makes four code texts from their examples: the Python tutorial and library (the branch is the `[symbols]` setting `python_branch`), the Gleam language tour and the Gleam standard library. A notice says when they are imported. Their text is kept only in the database. Adding them again adds four new texts from the newer docs. After that, each symbol that fewer than `min_lines` (50) lines of code for symbol drills hold gets a symbol lesson: a Python lesson (see `l` below) on a topic that the AI chooses because it uses that symbol, titled "Symbol ^: <topic>". The notice lists the rarest symbols and the symbol lessons queued. When a symbol lesson is written, the lines that hold its symbol are counted again, and the symbol gets one more symbol lesson while it is still in fewer than `min_lines` lines, up to `max_lessons` (3) for each symbol. Each is checked against the monthly cap like any lesson. Add the docs again only for a new `python_branch`. The symbol lessons and the Python and Gleam docs give lines of code to symbol drills and, once all keys are unlocked, words to drills, but they are not in the list of texts (`o`), and typokiller does not go on with them when it starts.

Press `l` in the Escape menu for a new lesson, written by the AI: type a topic, such as `decorators`, then Enter. The form shows what lessons cost this month. First press `p` for Python or `g` for Gleam; Enter chooses the language used last. A model writes the lesson through OpenRouter in the background (Python: Claude Haiku 5.5, about $0.002 a lesson; Gleam: Claude Sonnet 5.5, about $0.05 a lesson), and a notice says when it is ready. It is then first in the list of texts (`o`). The API key is `OPENROUTER_API_KEY`, from the environment or from a `.env` file in the folder that the server runs in (it is gitignored), for example `OPENROUTER_API_KEY=sk-or-...`. The `[lessons]` settings hold the model, the length and level, and the monthly cap (£5); a request that could make the month's cost more than the cap is refused. Each code example is run on this Mac under `sandbox-exec`, in a new temp folder, with no network and no writes outside that folder. An example that fails is sent back to the model for a repair, at most twice, and is then dropped. A lesson with too many dropped examples is written once again, and then rejected.

Gleam examples need `gleam` and Erlang on this Mac. Each one is built and run in a copy of the pre-made project in `src/typokiller/gleam/`, where `manifest.toml` pins the library versions. When you ask for a Gleam lesson, typokiller first runs `gleam build` there. The first time, this downloads the libraries (it needs the internet) and compiles them into `src/typokiller/gleam/build/`; after that it does nothing. If it fails, the request is refused with gleam's error, and nothing is sent to the model. To make that folder again, delete it; the next Gleam lesson request makes it. The Gleam tests are skipped while the folder is missing, because tests do not use the network. To make it at once:

```sh
rm -rf src/typokiller/gleam/build && (cd src/typokiller/gleam && gleam build)
```

The server tests read copies of real `.vil` and `vial.json` files, kept in `tests/fixtures/`. They come from the `sweep-layouts` repo (commit 67c9332), which the tests do not need. They do not follow that repo. To refresh them, copy the files that a test needs from `sweep-layouts`, then change the commit in this line and in `tests/test_app.py`.
