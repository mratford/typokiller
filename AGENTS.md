# AGENTS.md

## Writing style

In all messages to the user, documentation and code comments, use plain technical English. Do not use idioms, slang or tech-industry jargon. Assume the reader speaks English as a second language: use short sentences and common words, and describe the concrete thing instead of naming a pattern.

## Words on screen

The glossary terms in `CONTEXT.md` are for the code, the files in `docs/`, the comments in `typokiller.toml` and tickets. Screen text (the page, the server notices and error messages, the settings page labels) and the README use these plain words, never the capitalised glossary terms. A test in `tests/typing.test.js` checks the page files.

| Glossary term | On screen | Example |
|---|---|---|
| Board | keyboard | "change keyboard", "add a keyboard" |
| Letter layout / Keymap | layout | "Sweep · free-range", "choose a layout" |
| Keymap drawing (`m`) | keyboard picture | "keyboard picture on/off" |
| Session | not named | "stop", "Stopped. Reload the page to start again." |
| Source | text | "open a text", "add a text", "My book · part 3 of 40" |
| Passage | part | "skip this part", "restart this part" |
| Built-in Passage | sample text | "No text open: typing the sample text." |
| Attempt | not named | "Settings saved. They apply from the next part you start." |
| Lesson | lesson (lowercase) | "new lesson (written by the AI)" |
| Drill | drill (lowercase) | "drill your weakest keys" |
| Target | not named, or "practising" | status line: "drill · practising: e th ;" |
| Symbol Drill | symbol drill | "symbol drills: lines of code with numbers and symbols" |
| Introduction Drill | new key drill | "Unlocked e. Next come drills for e." |
| symbol docs | Python, Gleam and shell docs | "add the Python, Gleam and shell docs (code for symbol drills)" |

Labels describe the action where they can, so that most of them need no noun.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `mratford/typokiller`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` plus `docs/adr/` at the repo root. See `docs/agents/domain.md`.
