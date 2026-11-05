<!-- PROTOTYPE for "What does the user part of the README say?" (#97). Rough draft to react to. Not the real README. -->

# typokiller

typokiller's typing page is a changed copy of [keybr.com](https://www.keybr.com/) by Aleksei Radzievskii (`aradzie/keybr.com`), under the AGPL 3.0.
The code in `keybr/` is keybr's licence (`keybr/LICENSE`); the rest is typokiller's, also AGPL 3.0 (`LICENSE`).

Practise typing on your own keyboard, and see which keys and key pairs are slow for you. It runs on your Mac and starts when you log in.

## Set up

Open Terminal and type these two lines. The first is needed only if you do not have `uv` and `node` yet.

```sh
brew install uv node
uvx --from git+https://github.com/mratford/typokiller typokiller-service install
```

The first install downloads about 490 MB and takes about 3 minutes. At the end it prints two addresses.

## Type

Open **http://localhost:3100/** on this Mac.

1. Click **analysis** at the top, then press `b` and `n` to add your keyboard: choose its `vial.json`, check the name, then choose a `.vil`.
2. Press `t` to go back to the typing page. Below the lesson, choose the keyboard and the layout.
3. Type. Each lesson is recorded.

If your keyboard types its letters from its own firmware, such as free-range, also choose that layout in the typing page's settings.

**From another computer** on your home network, open the second address, such as `http://marge.local:3100/`. Each computer keeps its own typing progress, and you choose the keyboard again there. On this Mac, always use `localhost`: another address starts the progress again.

## See your progress

Click **analysis** at the top of the typing page. The line at the bottom lists the keys of the page.

In the keyboards panel (`b`): `n` adds a keyboard, `v` saves a new layout from a `.vil`, `r` names the layers.

## Keep it up to date

```sh
typokiller-service update      # get the newest version; keeps the old one if a test fails
typokiller-service status      # running or not, the addresses, the newest backups
typokiller-service stop        # stop until the next login
typokiller-service start
typokiller-service restore     # list the backups; then give one name to go back to it
typokiller-service uninstall   # remove the apps, keep your data
```

Your lessons and keyboards are backed up every day and at each update.

---

## Development

(Everything below is for working on the code. It moves here from the old README, cut to what is still true.)

- What runs where: the clone in `~/.local/share/typokiller/app`, the data folders, the logs, the ports, `logs`. (ADR 0006)
- Moving this Mac over once: the old `uv run typokiller-service uninstall`, then the `uvx` line.
- Trying a pushed branch: `typokiller-service update origin/<branch>`.
- Development servers: typokiller on another port, keybr on 3000/3001 from `keybr/`.
- Tests: `uv run pytest`, `uv run pyright`, `node --test tests/*.test.js`, and `env DATABASE_CLIENT=sqlite npm test` in `keybr/`.
- The notebooks: `notebooks/keybr.py` (`--recordings <path>`) and what they show.
- Layer names in `typokiller.toml` (`[keymaps]`), `[lists] letters`.
- Test fixtures: `tests/fixtures/` from `sweep-layouts`, and the shared ones in `keybr/packages/keybr-recording/fixtures/`.
- keybr's own docs: `keybr/docs/detailed_recording.md`.
