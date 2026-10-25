# typokiller

## Running

```sh
uv run typokiller          # serves http://<this Mac>:8000 on the LAN
uv run pytest              # server tests
node --test tests/*.test.js   # typing rules tests
uv run pyright src tests   # type check
```

The database is `typokiller.db` in the current directory. The settings are in `typokiller.toml` next to it, created with defaults and comments on first use. Edit it in any editor, or press `,` in the Escape menu.
