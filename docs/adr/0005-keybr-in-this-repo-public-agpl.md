# keybr's code is in this repo, and the repo is public under the AGPL

keybr is the typing app and typokiller is its partner (ADR 0004). Many changes need code in both: keybr reads the keyboards and the keyboard picture from typokiller, and typokiller reads keybr's recordings. With two repos, each such change was two PRs that had to be merged in the right order, and the service had to find a matching commit of each. So keybr's code (from `mratford/keybr.com`) is now in this repo, in `keybr/`, added with `git subtree add` so that its history is kept. Each commit holds a matching pair of both apps. The decision is in the ticket "How does one command install and update both apps?" (#82) of the map #73.

keybr is under the AGPL 3.0. Our changed copy runs as a web server, and the AGPL network clause asks that its users can get its source. So the repo is public, and typokiller's own code is also under the AGPL 3.0. `keybr/` keeps its `LICENSE`, and `keybr/NOTICE` says since which upstream commit it was changed. The README credits keybr at the top. keybr's page carries the typokiller name and logo, says that it is a changed copy of keybr.com, and links to this repo. It no longer shows keybr.com's terms of service or privacy policy, because they are about keybr.com's own service.

## Considered options

- **Put typokiller into the keybr repo.** keybr's tooling would stay at the root of the repo. It was rejected because the map, the tickets and the docs are all in this repo and would have to move, and the Python project would sit inside a large JavaScript repo.
- **Keep two repos, with typokiller pinning a keybr commit (for example as a git submodule).** Nothing would move. It was rejected because every change to both apps would still be two PRs plus a change to the pin.
- **Keep this repo private.** It was rejected because anyone else who used the changed keybr could then not get its source, as the AGPL requires.

## Consequences

- `mratford/keybr.com` is archived, and `~/src/keybr.com` is no longer used.
- keybr's tooling (husky hooks, `npm` scripts) runs from `keybr/`. keybr's tests are run with `env DATABASE_CLIENT=sqlite npm test` in that folder.
- To take later changes from upstream keybr.com, use `git subtree pull --prefix=keybr`. This is not planned.
