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
A Source written by the LLM on request, such as "async with examples".
_Avoid_: using "lesson" for typing practice in general

**Passage**:
One chunk of text meant to be typed in one go: a paragraph or function taken from a Source, or a Drill. The same Passage can be typed many times.
_Avoid_: exercise, snippet, text

**Attempt**:
One typing of a Passage within a Session, finished or abandoned; every keystroke belongs to exactly one Attempt.
_Avoid_: try, run, rep

**Drill**:
A Passage generated from measured weaknesses rather than taken from a Source.
_Avoid_: exercise, lesson
