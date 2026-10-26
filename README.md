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

On free-range (the `[unlocking]` settings name the Letter layout being learned), Drills use only the Unlocked keys. The status line shows the progress, such as `10/30 keys · next o`. After each finished Attempt, the next key unlocks when each Unlocked key is fast enough; `u` in the Escape menu unlocks it at once. After an unlock, the next Drills are Introduction Drills of the new key. Keymap drawings show locked keys dashed and faint, with a ring on the next one.

Press `l` in the Escape menu for a new Lesson: type a topic, such as `decorators`, then Enter. The form shows what Lessons cost this month. A model writes the Lesson through OpenRouter in the background (Python: Claude Haiku 5.5, about $0.002 a Lesson), and a notice says when it is ready. It is then first in the list of Sources (`o`). The API key is `OPENROUTER_API_KEY`, from the environment or from a `.env` file in the folder that the server runs in (it is gitignored), for example `OPENROUTER_API_KEY=sk-or-...`. The `[lessons]` settings hold the model, the length and level, and the monthly cap (£5); a request that could make the month's cost more than the cap is refused. The code in a Lesson is not checked yet.

The server tests read real `.vil` and `vial.json` files from the `sweep-layouts` repo, which must be in the same folder as this repo.
