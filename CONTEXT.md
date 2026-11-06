# typokiller

Two apps that work together. keybr is where you type, and it records every keystroke in detail. typokiller holds the keyboards and their layouts and analyses keybr's recordings, so that the results can feed back into keyboard and editor design.

## Language

These terms are for the code, the files in `docs/`, the settings file and tickets. The app's screen and the README's user part use plain words instead; `AGENTS.md` lists them.

### The apps

**keybr**:
The typing app in `keybr/`, a changed copy of keybr.com.
_Avoid_: the keybr fork, keybr.com (the name keybr.com means only the original)

**typokiller**:
Only the Python app: the keyboards, the analysis page and the drawing. For both apps together, say "both apps" or "the repo".
_Avoid_: partner app, server (when the app is meant)

### Keyboards

**Board**:
A physical keyboard, such as the Ferris Sweep, Sofle or Q2.
_Avoid_: keyboard (when a specific device is meant), device

**Letter layout**:
Which letters sit on the 30 main keys, such as QWERTY or free-range.
_Avoid_: layout, alphas, keybr layout

**Keymap**:
Every layer of keys on one Board, imported from its `.vil`; it includes exactly one Letter layout.
_Avoid_: layout, vil

**Keymap drawing**:
A picture of one layer of one Keymap version, drawn by typokiller. Heat colours, the weakest-pair arc and the next-key outline are things a drawing can show. They are not separate terms.

**Keyboard export**:
The Boards, their Keymap versions and their Keymap drawings that typokiller gives keybr when keybr's typing page loads. keybr keeps the last one it got, so its copy can be older than typokiller's keyboards.
_Avoid_: sync, import file, export file

### Analysis

**Attempt**:
One keybr lesson, finished or abandoned. Every keystroke belongs to exactly one Attempt.
_Avoid_: try, run, rep

**keybr recordings**:
The SQLite database in which keybr keeps detailed records of every Attempt. Each Attempt names a Board and a Keymap version. typokiller reads it while keybr runs, and never writes it.
_Avoid_: snapshot, keybr history, recordings.sqlite (the file name)

**Weakness model**:
A named, swappable method that ranks the characters and pairs typed on one Board with one Letter layout by cost, so different methods can be compared.
_Avoid_: scorer, algorithm

**Error**:
The first keystroke in a run that does not match the Attempt's text at the cursor. It is charged to the character that should have been typed.
_Avoid_: typo, mispress, mistake (when the counted thing is meant)

**Off-track**:
A keystroke typed after an Error and before it is fixed; it counts neither as an Error nor towards timings.
_Avoid_: error (for these keystrokes)

**Fix**:
Getting from an Error back to the right character in its place; its duration is the fix time.
_Avoid_: correction

**Analysis method**:
The named rules that turn recorded typing into positions, Errors, Fixes and timings. There is one so far: `keybr-input-v1` for keybr recordings. Each table says which one made it. The metrics of different methods must not be pooled.
_Avoid_: alignment (for keybr-input-v1), scorer
