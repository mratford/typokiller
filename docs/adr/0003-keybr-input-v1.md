# keybr recordings have their own analysis method, keybr-input-v1

The keybr fork records typing in detail (#71, and keybr issues #2 to #5). We analyse these records in Python, next to typokiller's own history. typokiller's method, `first-error-v1`, replays the keydowns with `apply_key`, which copies the typing rules of typokiller's page. keybr has other rules: it can forgive a wrong character, skip a word with Space, accept a character by itself to recover, stop on an error, and emulate a layout. Replaying keybr's keys with typokiller's rules would put Errors and positions where keybr's page did not have them.

So keybr records get their own method, `keybr-input-v1` (`src/typokiller/keybr_analysis.py`). It reads what keybr's engine recorded instead of replaying keys:

- keybr's state records give, for each input, the steps that were put in or taken out of the accepted text. A step keeps the timestamp of the input that put it in. A step is matched to an input by its (timestamp, code point): this gives the input's final position, also when keybr accepts it later, in a recovery. A step with the timestamp of an input that typed another character makes that input wrong at that position. Any other step is automatic, with no real input.
- The first input at a position gives the first-input outcome, as in `first-error-v1`. Later wrong inputs are off-track, and the first correct input after an Error is the Fix. A position that keybr accepted by itself after an Error has no fix time.
- The key presses are matched to the inputs, and then `analysis.attempt_keystrokes` gives dwell, flight, time and the inferred key from the saved Keymap, with its existing rules for mod-taps, layer-taps, combos and macros.

The tables say which method made them, and the notebook for keybr (`notebooks/keybr.py`) shows only keybr records. keybr's own scores (speed, accuracy, score) are shown apart, labelled "keybr".

## Considered options

- **Turn keybr records into typokiller key events and replay them with `first-error-v1`.** Rejected: the replay would not see keybr's forgiveness, word skips and recoveries, so its positions and Errors would be wrong.
- **Use keybr's native results only.** Rejected: they have no positions, pairs, fix times, dwell or flight, and keybr counts a forgiven character as an error even after it was deleted and typed again.

## Consequences

- typokiller's Weakness model (`recent-cost-v1`) ranks keybr observations unchanged, because `keybr_analysis.units` gives the same columns as `analysis.units`. Its numbers are still not comparable with typokiller's, so the two histories are never pooled.
- A time is kept only when it is clear which input followed which: the previous real input must be the correct input at the position before, and the input's own state must put in no automatic step. So times next to skips and recoveries are left out, and are counted in the notebook.
- An input event is matched to its key press by the processed key, as the one unmatched keydown with that key since the input before. When there is no such keydown, or more than one, the match is ambiguous, and the input is counted but not timed.
- A pair is given for an Error as well as for a correct input, when the input before was correct at the position before. This keeps pair error rates, as `analysis.layout_units` does. The plan for #71 gave pairs only under the full timing rule; with that rule, no pair could ever have an Error.
- When keybr's recording contract changes its version, this method must be checked again against keybr's shared fixtures, which are copied to `tests/fixtures/keybr/`.
