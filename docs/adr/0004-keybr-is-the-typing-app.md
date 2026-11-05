# keybr is the typing app; typokiller keeps only keyboards and analysis

The user wants to practise and see a good analysis without using a terminal. With two typing apps, everything had to work twice, and a keybr session needed four commands between the apps. So the keybr fork (`mratford/keybr.com`) is now the only place to type, and typokiller no longer has a typing page. typokiller keeps only the keyboards and their saved layouts (the `board` and `keymap_version` tables), the analysis of keybr's recordings, and the code that draws a keyboard picture. The decisions are in the map "one easy setup with keybr for typing and typokiller for analysis" (#73) and its ticket "What stays in typokiller, and what is removed?" (#76).

## Considered options

- Keep both apps, with no commands between them. This was rejected because every part would still have to be built and kept working twice.
- Keep typokiller and drop keybr. This was rejected because the user types in keybr.

## Consequences

- Texts (books, articles, code from git repos), AI lessons, symbol lessons, symbol drills and typokiller's free-range unlocking and drills were removed. Bringing one of them back means building it in keybr.
- The earlier practice in typokiller's database (sessions, attempts and key events) was deleted, with the tables that held it. Only the backups that `typokiller-service update` made before the change still hold it, until newer backups replace them.
- All numbers now come from keybr's recordings, measured with `keybr-input-v1` (ADR 0003).
- With no background work, typokiller has no job runner (ADR 0001) and the service has no busy check (ADR 0002).
