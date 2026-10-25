# typokiller

A personal typing trainer that records detailed data on every keystroke, uses it to target practice at weaknesses, and feeds it back into keyboard and editor design.

## Language

### Keyboards

**Board**:
A physical keyboard, such as the Ferris Sweep, Sofle or Q2.
_Avoid_: keyboard (when a specific device is meant), device

**Letter layout**:
Which letters sit on the 30 main keys, such as QWERTY or free-range.
_Avoid_: layout, alphas

**Keymap**:
Every layer of keys on one Board, imported from its `.vil`; it includes exactly one Letter layout.
_Avoid_: layout, vil

### Practice

**Session**:
One sitting at one Board, from choosing the Board until stopping.
_Avoid_: run, sitting

**Source**:
Somewhere text comes from: a Gutenberg book, a code repo or folder, an article sent from the browser, or a Lesson.
_Avoid_: content, material, feed

**Lesson**:
A Source the LLM writes on request about a programming topic in one language, such as "async with examples", mixing explanation with examples that have been checked to run.
_Avoid_: using "lesson" for typing practice in general

**Passage**:
One chunk of text meant to be typed in one go: a paragraph or function taken from a Source, or a Drill. The same Passage can be typed many times.
_Avoid_: exercise, snippet, text

**Attempt**:
One typing of a Passage within a Session, finished or abandoned; every keystroke belongs to exactly one Attempt.
_Avoid_: try, run, rep

**Drill**:
A Passage that typokiller generates around chosen Targets rather than taking from a Source; used to practise weaknesses, gather data, or simply practise.
_Avoid_: exercise, lesson

**Target**:
A character or pair of characters that a Drill focuses on, because it is measured as weak or has not been measured enough yet.
_Avoid_: weak spot, focus

**Unlocked keys**:
The keys of a Letter layout that Drills may use while that layout is being learned; the set only ever grows.
_Avoid_: unlocked letters (punctuation keys count too), level

**Introduction Drill**:
A Drill built around a key that has just been unlocked.
_Avoid_: intro, warm-up

### Analysis

**Weakness model**:
A named, swappable method that ranks a Board's characters and pairs by cost, so different methods can be compared.
_Avoid_: scorer, algorithm

**Error**:
The first keystroke in a run that doesn't match the Passage at the cursor; it is charged to the character that should have been typed.
_Avoid_: typo, mispress, mistake (when the counted thing is meant)

**Off-track**:
A keystroke typed after an Error and before it is fixed; it counts neither as an Error nor towards timings.
_Avoid_: error (for these keystrokes)

**Fix**:
Getting from an Error back to the right character in its place; its duration is the fix time.
_Avoid_: correction
