# AGENTS.md

## Writing style

In all messages to the user, documentation and code comments, use plain technical English. Do not use idioms, slang or tech-industry jargon. Assume the reader speaks English as a second language: use short sentences and common words, and describe the concrete thing instead of naming a pattern.

## Words on screen

The glossary terms in `CONTEXT.md` are for the code, the files in `docs/`, the comments in `typokiller.toml` and tickets. Screen text (the pages and the server's error messages) and the README use these plain words, never the capitalised glossary terms. A test in `tests/pages.test.js` checks the page files.

| Glossary term | On screen | Example |
|---|---|---|
| keybr | typing page | "Type on the typing page, then reload this page." |
| typokiller | analysis page (and "typokiller" as the name on both apps) | `t` opens the typing page |
| Board | keyboard | "change keyboard", "add a keyboard" |
| Letter layout / Keymap | layout | "Sweep · free-range", "choose a layout" |
| Keymap drawing | keyboard picture | keybr's "change view" turns the keyboard picture off (in place of `m`) |
| Attempt | lesson | "No lessons recorded yet." |
| keybr recordings | recorded lessons | "The recorded lessons are newer than this version of typokiller." |
| Keyboard export | not named; "keyboards" | "keyboards added since it last ran are missing" |

The name "keybr" appears on screen only in the credit (the footer and the README). The terminal output of `typokiller-service` still says "keybr", because the service labels and the log files use that name.

Labels describe the action where they can, so that most of them need no noun.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `mratford/typokiller`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` plus `docs/adr/` at the repo root. See `docs/agents/domain.md`.
