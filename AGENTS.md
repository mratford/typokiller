# AGENTS.md

## Writing style

In all messages to the user, documentation and code comments, use plain technical English. Do not use idioms, slang or tech-industry jargon. Assume the reader speaks English as a second language: use short sentences and common words, and describe the concrete thing instead of naming a pattern.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `mratford/typokiller`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` plus `docs/adr/` at the repo root. See `docs/agents/domain.md`.
