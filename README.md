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

The server tests read real `.vil` and `vial.json` files from the `sweep-layouts` repo, which must be in the same folder as this repo.
