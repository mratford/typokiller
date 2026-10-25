# Mapping typed characters back to keys from a .vil

Resolves issue #2 (part of #1). Question: given a Board's Vial `.vil` (plus its `vial.json` for geometry), how can each character the browser receives be mapped back to the physical key(s), layer and modifiers that produced it, and where is that mapping ambiguous?

## Short answer

- The browser never sees the physical key or the layer. It sees what the keyboard's USB report said: a `code` (a HID usage, i.e. a QMK *basic* keycode), a `key` (that usage run through the OS input source), and modifier state. The `.vil` gives the other half: for every (layer, matrix position) the QMK keycode that position sends. So the mapping is a **forward model that you invert**: `.vil` -> set of "recipes" (layer stack, key, hold/tap, modifiers) -> `(code, modifiers)` -> char under the OS input source. Typed event -> candidate recipes.
- Most letters are unambiguous. Symbols and digits often are not, because the layout deliberately repeats them across layers, and several features (shifted keycodes, Caps Word, macros, mod-tap Shift, the key override) emit events that are indistinguishable from a person pressing the "plain" keys. Ambiguity cannot be removed from the event stream; handle it by (a) keeping the raw events, (b) attributing to a candidate *set* with a deterministic tie-break, and (c) using the known target text (the Passage) to pick the recipe the typist most plausibly meant.
- The OS input source only changes `key` (the char), not `code`. Key on `code` + modifiers, and derive the char table per Board from the input source. macOS Australian and ABC give identical characters to US on the keys the layout uses (checked, below). The Q3 Max's UK-Windows layout differs on six keys, and the existing `.vil` already compensates for those on the keycode side but **not in the `|>` text macro** (probable bug, below).

Worked example throughout: `/Users/mike/src/sweep-layouts` (`layout.py`, `render.py`, `boards.py`, `vil/*.vil`, `boards/*/vial.json`). Source snapshots used: vial-gui `aef8222` (main), vial-qmk `dd43959` (branch `vial`), qmk_firmware `180f394` (master), all fetched 2026-10-25. Links below are permalinks to those commits.

## 1. What each side actually knows

| | Knows | Does not know |
| --- | --- | --- |
| Browser `keydown`/`keyup` | `code` (physical position, layout-independent), `key` (layout- and modifier-dependent), `shiftKey`/`ctrlKey`/`altKey`/`metaKey`, `getModifierState()`, `location` (left/right), `repeat`, timestamp | Which matrix key, which layer, whether a modifier came from a mod-tap, Caps Word, a macro or a real key |
| `.vil` + `vial.json` | Every layer's keycode per matrix position; combos, key overrides, macros, QMK settings; each position's x/y geometry | What the OS does with the keycodes; which layers were active at a given moment |

`code` is defined by UI Events as "the unicode character string representing the key that was pressed, ignoring any keyboard modifications such as keyboard layout" ([UI Events, KeyboardEventInit `code`](https://www.w3.org/TR/uievents/)). A caveat that matters here: "the key" is the key *as the USB report names it*, so `code` reports the keycode the firmware sent, not the switch that was pressed. If a SYM-layer key and a base-layer key both send `KC_NUBS`, both arrive as `IntlBackslash`.

`key` is the OS input-source output; the spec for `code` also says the US `\|` key and the UK `#~` key share one code: "`Backslash` ... Used for both the US `\|` (on the 101-key layout) and also for the key located between the `"` and Enter keys on row C of the 102-, 104- and 106-key layouts. Labelled `#~` on a UK (102) keyboard", and `IntlBackslash` is "Located between the left Shift and Z keys. Labelled `\|` on a UK keyboard" ([UI Events Code spec, alphanumeric-section table](https://www.w3.org/TR/uievents-code/)). So QMK's `KC_BSLS` (0x31) and `KC_NUHS` (0x32) are the same `code` in the browser.

## 2. The `.vil` and `vial.json` formats

### `.vil` (a JSON file written by Vial's *Save layout*)

Written by `save_layout()` ([`keyboard_comm.py` L369-L407](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/protocol/keyboard_comm.py#L369-L407)); restored by `restore_layout()` (L409+). Top-level keys: `version`, `uid`, `layout`, `encoder_layout`, `layout_options`, `macro`, `vial_protocol`, `via_protocol`, `tap_dance`, `combo`, `key_override`, `alt_repeat_key`, `settings`.

- `layout[layer][row][col]`: one keycode per **matrix** position, `-1` where `vial.json` declares no key at that position (`save_layout` writes `self.layout.get((l, r, c), -1)`). Rows/cols are the matrix, not the visual grid. On the Sweep, matrix rows 0-3 are the left half and 4-7 the right (`/Users/mike/src/sweep-layouts/boards/sweep/vial.json`); on the Q3 Max they are the visual rows (`boards/q3_max/vial.json`).
- Keycodes are strings. Vial serialises them with `Keycode.serialize` and reads them with `Keycode.deserialize`, which accepts any alias and several syntaxes ([`keycodes.py` L108-L149](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/keycodes/keycodes.py#L108-L149); [`any_keycode.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/any_keycode.py)). **A parser must canonicalise to the 16-bit QMK keycode rather than string-match.** I ran vial-gui's own tables: `KC_UNDS`, `LSFT(KC_MINS)` and `LSFT(KC_MINUS)` all deserialise to `0x022D`, and Vial *saves* it back as `LSFT(KC_MINUS)`; `KC_NUHS` is re-saved as `KC_NONUS_HASH`; `LT(3,KC_ESC)` and `LT3(KC_ESC)` both mean `0x4329`. `sweep-layouts/render.py` writes the friendly forms (`KC_UNDS`, `LT(3,KC_ESC)`, `M0`); a file saved from Vial itself will use the long forms. Use QMK's machine-readable tables (`data/constants/keycodes/*.hjson`, [qmk_firmware](https://github.com/qmk/qmk_firmware/tree/180f394b489c238cb231c2bf8b080262155e03c0/data/constants/keycodes)) or vial-gui's `keycodes_v6.py` for the numeric values and aliases.
- Keycode families that appear in a `.vil` and their bit layout in Vial protocol 6 ([`keycodes_v6.py` L1-L80](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/keycodes/keycodes_v6.py#L1-L80)): `QK_MOD_TAP 0x2000` (mods in bits 8-12, tap key in the low 8 bits), `QK_LAYER_TAP 0x4000` (layer in bits 8-11, tap key low 8 bits), `QK_MOMENTARY 0x5220`, `QK_TOGGLE_LAYER 0x5260`, `QK_ONE_SHOT_MOD 0x52A0`, `QK_MACRO 0x7700`, and `LSFT(kc)` = `0x0200 | kc` etc.
- `macro[n]`: list of actions, each `["text", "..."]`, `["tap"|"down"|"up", "KC_X"]` or `["delay", ms]` ([`macro_action.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/macro/macro_action.py)). A key `M3` in `layout` plays `macro[3]`.
- `combo[i]`: `[in1, in2, in3, in4, output]`, unused inputs `KC_NO` ([`combo.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/protocol/combo.py)). Inputs are **full keycodes**, e.g. `LSFT_T(KC_V)`, not the tap key.
- `key_override[i]`: `trigger, replacement, layers` (bitmask of layers, `0xFFFF` = all), `trigger_mods`, `negative_mod_mask`, `suppressed_mods` (8-bit mod masks: bit0 LCtl, 1 LSft, 2 LAlt, 3 LGui, 4-7 the right-hand versions, so `0x22` = either Shift), `options` bitfield (bit0 activate on trigger down, 1 on required mod down, 2 on negative mod up, 3 one mod suffices, 4 do not re-register trigger, 5 do not unregister on other key down, 7 enabled) ([`key_override.py` L11-L35](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/protocol/key_override.py#L11-L35); firmware struct [`vial.h` L160-L180](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/vial.h#L160-L180)).
- `settings`: `{"<qsid>": value}`. The ones that change what events you see: 2 combo term, 7 tapping term, 18 tap code delay (also the inter-key delay inside macros), 22 permissive hold, 23 hold-on-other-key-press, 24 retro tapping, 25 quick tap term, 26 chordal hold, 27 flow tap ([`qmk_settings.json`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/resources/base/qmk_settings.json)). The sweep-layouts `.vil`s set 2, 5, 6, 7, 22-27 (`layout.py` `SETTINGS`).
- Caps Word, Layer Lock and Repeat are not configured in the `.vil`; they are compiled in and reached only through keycodes (`QK_CAPS_WORD_TOGGLE`, `QK_LAYER_LOCK`) or combos. Whether a board has them is not recorded in the `.vil`.

### `vial.json` (geometry)

A KLE-style description. Vial loads it in `reload_layout` ([`keyboard_comm.py` L114-L195](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/protocol/keyboard_comm.py#L114-L195)): `matrix.rows`/`matrix.cols` size the keymap; `layouts.keymap` is KLE JSON deserialised by `KleSerial`; each key's **first label is `"row,col"`** (the matrix position), label 4 equal to `"e"` marks an encoder (`"idx,dir"`), and label 8 (`"idx,opt"`) selects a layout option (only the Sofle uses `layouts.labels`, across the sweep-layouts boards). Geometry fields are standard KLE: `x`, `y`, `w`, `h`, and rotation `r`, `rx`, `ry` (the Sweep's thumb keys are rotated 15/30 degrees). Keys on the Sweep: `"0,2"` etc. in `boards/sweep/vial.json`.

What `vial.json` gives the trainer: position-to-geometry (for drawing the Board, for hand/finger assignment from x and which half a key is on, and for distance between consecutive keys). It does **not** assign fingers or label legends; the legends come from the keycodes.

## 3. The forward model

For each Board build, once, from the `.vil`:

1. **Layer stack resolution.** QMK scans active layers "from the top down, stopping when it reaches the first active layer that is not set to `KC_TRNS`" ([QMK, Layers](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/feature_layers.md?plain=1#L57)). Layer 0 is the default. A key on a layer-hold position (`MO(n)`, `LT(n,kc)` hold) adds layer *n*. A released key is resolved on the layer it was *pressed* on (`source_layers_cache`, [`action_layer.c` L246-L310](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/action_layer.c#L246-L310)), so releasing the layer key first does not change the key's meaning.
2. **Keycode to emitted usage(s).** See section 4 for each family.
3. **Usage + modifiers to char** through the OS input source (section 5).

Enumerate every (layer stack, position) -> `Recipe { board, layer, matrix(r,c), x/y, kind, tap_or_hold, usages[], mods }`. Index recipes by `(code, modifier set)` and by resulting char.

## 4. Feature by feature

### Layers and layer-taps

- `MO(n)`, `TG`, `OSL` and an `LT` *hold* emit no USB event at all: the layer is invisible to the browser. The layer a character came from must be inferred from the candidate set (section 7), never read.
- An `LT(n, kc)` *tap* sends `kc` as a plain key ([mod_tap.md](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/mod_tap.md) covers Mod-Tap and Layer-Tap together). On the Sweep the thumbs are `LT(NUM,Esc)`, `MO(NAV)`, `LT(SYM,Space)`, `LT(STACK,Tab)`: tapping Space is a plain Space; holding it opens SYM and Space is never sent (retro tapping is off, setting 24 = 0).
- The tap/hold decision uses the tapping term (200 ms here), permissive hold (on) and quick tap term (120 ms) ([`tap_hold.md` L307-L313](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/tap_hold.md?plain=1#L307-L313)). Permissive hold means "press layer key, tap another key, release both inside the term" resolves as hold, so the model must not assume a time threshold alone.
- A *misfire* (user meant a tap, got a hold, or the reverse) is data, not noise: the symptoms are a missing char (the tap was swallowed by a hold) or an unexpected char from the layer (a hold when a tap was intended). The trainer sees the symptom only as "expected `a Space`, got `a symbol`".

### Mod-taps (bottom-row mods)

- Tap sends the tap key; hold sends the modifier. `LSFT_T(KC_V)` tapped is indistinguishable from a plain `KC_V` ([mod_tap.md](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/mod_tap.md)).
- Hold events are modifier `keydown`s with a side: `ShiftLeft`/`ShiftRight`, `ControlLeft`, `AltLeft`, `MetaLeft` etc., plus `location`. So **left vs right is observable, which finger is not** (Alt/Ctrl/Win/Shift sit on different fingers per Board and OS: `MODS` in `layout.py` is `GUI ALT CTL SFT` on Mac and `ALT CTL GUI SFT` on Windows).
- Mod-tap tap keys must be basic keycodes ("the `kc` argument of `MT()` is limited to the Basic Keycode set ... you can't use keycodes like `LCTL()`, `KC_TILD`", [mod_tap.md "Caveats"](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/mod_tap.md)). This is why `layout.py` asserts that `_` is off the bottom row, and why shifted symbols never come from a mod-tap tap. So the tap of any mod-tap yields an unshifted basic char.
- Held Alt/Ctrl/GUI mod-taps while typing text are almost always misfires. Chrome would treat Ctrl+key as a shortcut; the trainer should `preventDefault` where it can and count these as a distinct error class ("hold misfire", with the key it was on identifiable from the modifier `code` side plus the char it swallowed).
- On the Q3 Max the right-pinky mod-tap is `RALT_T(KC_QUOT)`, i.e. a held AltGr on a UK Windows layout; AltGr+letter yields accented chars and AltGr+4 yields the euro sign (UK layout table, [kbdlayout.info/kbduk](https://kbdlayout.info/kbduk/), secondary source). Treat `getModifierState("AltGraph")` as a misfire marker.

### Combos

- A combo is matched on **keycodes of the active layer**: `process_combo` takes the keycode of the pressed position and compares it to the combo's inputs ([`process_combo.c` L597-L606](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/process_keycode/process_combo.c#L597-L606)), so `J+K` fires from any layer where those positions hold `KC_J`/`KC_K`, and a position on another layer that happens to hold the same keycode would join in. Inputs that are mod-taps must be written as the full mod-tap keycode ([combo.md](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/features/combo.md?plain=1#L21-L25)); the `.vil`'s Caps Word combo is `[LSFT_T(KC_V), RSFT_T(KC_M)] -> QK_CAPS_WORD_TOGGLE`.
- Combos run in `pre_process_record_quantum`, before tap-hold resolution ([`quantum.c` L285-L291](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/quantum.c#L285-L291)). While two keys could still form a combo the presses are buffered for the combo term (40 ms here) and then either replaced by the combo's output or released as normal presses ([`process_combo.c` L468-L530](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/process_keycode/process_combo.c#L468-L530)).
- Observable result: the combo output is a single plain key event: `J+K` yields `Escape`, `J+L` yields `Enter`, `K+L` yields `Backspace` and the two constituent letters never reach the browser. Caps Word yields nothing visible by itself. A combo press is indistinguishable from the same key typed on a layer/key that sends it, e.g. `Backspace` from the combo vs the NAV thumb, `Enter` likewise (NAV right thumbs, `layout.py`).
- Combos buffer key presses, so a roll that nearly formed a combo is delayed by up to the combo term. Event timestamps from the browser are the *output* times, so inter-key latency for those keys is inflated by up to 40 ms and should not be read as slowness.
- Failure case worth recording: fast `j k` rolls inside 40 ms on QWERTY will produce `Escape` instead of "jk" (the layout author chose pairs that are rare as bigrams, `layout.py` `COMBO_POS`). This appears in the data as an unexpected `Escape` (or `Enter`/`Backspace`) between expected letters.

### Key overrides (Shift + `_` gives `-`)

- The `.vil` has one override: trigger `KC_UNDS`, replacement `KC_MINS`, `trigger_mods` `0x22` (either Shift), `suppressed_mods` `0x22`, all layers, options `0x8F`. `KC_UNDS` is `LSFT(KC_MINS)`: "They do not have keycodes of their own but are simply shortcuts for `LSFT(kc)`, and as such send a Left Shift with the unshifted keycode" ([US ANSI shifted symbols](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/keycodes_us_ansi_shifted.md?plain=1#L3)). QMK's own docs show exactly this pattern (a shifted-symbol trigger plus a suppressed Shift, "inverts or swaps semicolon and colon", [key_overrides.md L50-L53](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/features/key_overrides.md?plain=1#L50-L53)).
- Matching is by exact keycode equality with the pressed position's keycode (`override->trigger == keycode`, [`process_key_override.c` L278](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/process_keycode/process_key_override.c#L278)) and the current mods ([L114-L145](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/process_keycode/process_key_override.c#L114-L145)). Weak mods do not count unless `KEY_OVERRIDE_INCLUDE_WEAK_MODS` is defined, and nothing in vial-qmk's `quantum/` or `docs/` defines it (individual keyboards' `config.h` were not checked). So **Caps Word's shift does not trigger the override** (Caps Word runs first, `quantum.c` L396-L399, and its shift is a weak mod).
- On activation the trigger is dropped from the report, the suppressed Shift is removed, and the replacement `KC_MINS` is added ([L337-L381](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/process_keycode/process_key_override.c#L337-L381)). When the trigger comes up, the suppressed mods return. Observable: the user holds a Shift (mod-tap hold or real key), taps the `_` key, and the browser gets `Minus` with `shiftKey: false` (inferred from the report; there may be a brief Shift key-up/key-down around it, **to be confirmed by recording real events**).
- Result for `-`: three recipes with identical final events: SYM `-` key, `Shift`-held + `_` key via the override, and (Q3 Max) the number-row `-`. Only the Shift flicker, and the timing of a held Shift, tell the override apart.

### Caps Word

- Toggle by the `V+M` combo (QWERTY; `C+H` on free-range). While on, "letters are capitalized and `-` becomes `_`" and it ends on any key other than `KC_A..KC_Z`, `KC_0..KC_9`, `KC_MINS`, `KC_UNDS`, Delete, Backspace, or after the idle timeout of 5 s ([caps_word.md L7-L14](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/features/caps_word.md?plain=1#L7-L14)). The rule is `caps_word_press_user`: letters and `KC_MINS` get `add_weak_mods(MOD_BIT(KC_LSFT))`; digits, Backspace, Delete and `KC_UNDS` continue unshifted; everything else turns it off ([`process_caps_word.c` L259-L277](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/process_keycode/process_caps_word.c#L259-L277)). A held Shift mod-tap also turns it off by default (L181-L204, no `CAPS_WORD_INVERT_ON_SHIFT`), and layer keys are ignored (L158-L172) so a held SYM does not end the word.
- Shift is a **left** Shift, applied as a weak modifier (cleared on the next key press, `action.c` L98, so it stays in the report across a run of letters). So Caps Word looks like "ShiftLeft held for the whole word, and released at the first digit/non-word key" in the browser. Distinguishing signals: the Shift `keydown` precedes the first letter by about zero ms; digits inside the word arrive **unshifted** while letters stay capital (a held real Shift would give `!@#...`); the word-ending key carries no Shift. A held real Shift is only distinguishable by these patterns and by `ShiftLeft` vs `ShiftRight` (a right-hand Shift mod-tap gives `ShiftRight`).
- `-` while Caps Word is on gives `_`: that is `KC_MINS` (SYM `-`, number-row `-`) plus weak Shift, and also the `_` key itself (already `LSFT(KC_MINS)`). The Shift+`_` override is not involved (weak mods excluded).

### Shift on symbols

- Two distinct mechanisms produce a Shifted symbol:
  1. **Shifted keycode** (`KC_AT`, `KC_UNDS`, `KC_PIPE` ... which is `LSFT(base)`): on press the firmware does `add_weak_mods(mods); send_keyboard_report(); register_code(key)` ([`action.c` L406-L420](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/action.c#L406-L420)), i.e. **Shift goes down in its own report, then the key**; on release the key goes up and then the weak Shift. Left Shift is always the one used. So the browser sees `ShiftLeft` keydown, then the key with `shiftKey: true`, a few ms apart, even though the user pressed one key.
  2. **Real Shift**: a Shift key or Shift mod-tap hold (either side) with an unshifted key.
- These produce the same `(code, shiftKey)`; they differ only by `ShiftLeft` vs `ShiftRight`, by the gap between the Shift and the key, and by key-up order. For the Sweep, SYM holds `& @ + ! \ " : [ ] | < > ~ ^ # / - ` * = ( ) ; % { } ? $` as shifted keycodes and the number row does not exist, so a `(` is by default the SYM key, not Shift+9, but only because there is no other recipe.
- UK Windows adds a wrinkle: `layout.py`'s `UK` table swaps keycodes so the *character* is right, e.g. `"` is sent as `KC_AT` (`LSFT(KC_2)`), since Shift+2 is `"` on a UK layout. The browser therefore sees `Digit2` + Shift for a character the typist thinks of as "the `"` key". Always derive the intended key from the `.vil` side, not the `key` string.

### Macros

- Vial macro playback is in firmware: [`dynamic_keymap_macro_send`](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/dynamic_keymap.c#L245-L331). `text` is sent one ASCII char at a time via `send_string_with_delay(data, DYNAMIC_KEYMAP_MACRO_DELAY)` (L330); `tap/down/up` use the QMK key codes; `delay` waits.
- `text` is converted by `send_char_with_delay`: a lookup table maps ASCII to a keycode and a shift flag; Shift is `register_code(KC_LEFT_SHIFT)` around the tap ([`send_string.c` L216-L256](https://github.com/vial-kb/vial-qmk/blob/dd43959ae5c08d8a28d38a1acf7b04e86b14a344/quantum/send_string/send_string.c#L216-L256)). "By default, Send String assumes your OS keyboard layout is set to US ANSI" ([send_string.md L49-L51](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/features/send_string.md?plain=1#L49-L51)); other layouts need a compile-time `sendstring_*.h` (there is `sendstring_uk.h`), which the generated sweep-layouts `keymap.c` (`render.py` `KEYMAP_C`) does not include. The delay between steps is `DYNAMIC_KEYMAP_MACRO_DELAY` = `TAP_CODE_DELAY` (10 ms by default, setting 18).
- Observable: `->` is `Minus`, then `ShiftLeft`+`Period`; `|>` is `ShiftLeft`+`Backslash`, then `ShiftLeft`+`Period`. Characters arrive at a constant machine cadence (tens of ms apart; each step waits `TAP_CODE_DELAY`, 10 ms by default) from **one** keypress. tmux macros (`Ctrl+B p`, `Ctrl+W h`, `[b`) are `ControlLeft` down, a letter, `ControlLeft` up, a letter, and arrive in the browser as chords, not text.
- Whether a char came from a macro or from typed keys is not in the event, but it is inferable: a macro's text is a fixed string (`->`, `|>`) emitted in a burst with near-constant, sub-human gaps and no preceding key press from a recipe that normally types it.
- **Likely bug in the worked example (to verify on the Q3 Max).** For the Windows-UK board, `layout.py` translates `|` and `\` on the SYM layer (`KC_PIPE -> LSFT(KC_NUBS)`), but macro `M0` (`|>`) is a `text` macro on every board, including `q3_max.vil`. Default send-string emits `|` as `LSFT(KC_BSLS)`, i.e. usage 0x31, which on a UK layout is the `#~` key, so it would type `~>`. UI Events confirms `KC_BSLS`/`KC_NUHS` are the same browser `code` (`Backslash`); the `key` is `~` for Shift under UK ([kbdlayout.info/kbduk](https://kbdlayout.info/kbduk/), secondary). My inversion script shows `M0` -> `~>` on the Q3 Max under the UK table. The fix on the sweep-layouts side would be to emit `M0` as `down LSFT, tap KC_NUBS, up LSFT, text ">"` for `uk` boards.

### One-shot mods, Layer Lock and the rest

`OSM(MOD_MEH)`/`OSM(MOD_HYPR)` (STACK layer) arm a modifier for the next key; the browser sees the modifiers' keydown then the next key. They never produce a char. `QK_LAYER_LOCK` and `TG(n)` change which layer is active without any event, so the *state* of the layer stack can be wrong in the model for long stretches (after a TG or lock) and is only recoverable from the chars that follow. These keys are rare on the base alphabet and the trainer should simply treat sequences it cannot explain as "layer state unknown".

## 5. The OS input source

`code` is layout-independent; `key` is not. Therefore for every Board store `os` + input source, build `(code, shift, altgr/option) -> char` for that source, and invert it. Do not trust `key` alone and do not hard-code US.

### macOS: Australian / ABC

I asked the OS directly, with `UCKeyTranslate` over the installed input sources on this Mac (ANSI keyboard type, no dead-key state). For every key the layout uses (digits 2-4, `-`, `=`, `'`, `` ` ``, `\`, letters, `;`, `/`), **Australian, ABC and US give identical characters** with no modifier, Shift, Option and Shift+Option. For example Digit3 gives `3`, `#`, `£`, `‹`; Digit2 gives `2`, `@`, `™`, `€`; Quote gives `'`, `"`, `æ`, `Æ`; Backquote with Option and Option+E are dead keys. British, in contrast, swaps those: Digit3 gives `3`, `£`, `#`; Digit2 `2`, `@`, `€`. So on the Mac the `£` key (`LALT(KC_3)`, `CHORDS["pound"]` in `layout.py`) is `Digit3` + Option -> `£`, consistent with the README ("macOS input source: Australian or ABC, not British"). I did not find an Apple document stating this; the table above is from running the OS's own layout data (script kept out of the repo).
- Option-based chars arrive with `altKey: true` and `key: "£"`; the ordinary shortcut interpretation of Option+letter by pages is irrelevant for a trainer page that owns the keydown, but dead keys (Option+E, Option+`` ` ``) arrive with `key: "Dead"` and `isComposing`; the trainer should avoid recipes that need them ([UI Events Key spec, `Dead`](https://www.w3.org/TR/uievents-key/)).
- Left GUI/Command held by a mod-tap shows as `metaKey`; Cmd+key is a browser shortcut and may swallow the `keyup` (platform quirk, to be confirmed empirically in the prototype).

### Windows: UK layout (Q3 Max)

Differences from US on the keys that matter here (UK layout, [kbdlayout.info/kbduk](https://kbdlayout.info/kbduk/), a secondary source derived from the Windows layout DLL; for authority verify against the board with `navigator.keyboard.getLayoutMap()` and a keystroke probe):

| Key (`code`) | Unshifted | Shift | AltGr | Notes |
| --- | --- | --- | --- | --- |
| `Digit2` | `2` | `"` | | US `@` |
| `Digit3` | `3` | `£` | | US `#` |
| `Quote` | `'` | `@` | | US `"` |
| `Backslash` (UK `#~`) | `#` | `~` | | US key is `\ \|`; HID 0x31 and 0x32 both land here |
| `IntlBackslash` (UK `\|`) | `\` | `\|` | | The ISO key next to left Shift |
| `Backquote` | `` ` `` | `¬` | `¦` | US `~` |

Everything else the layout uses (`^ & * ( ) _ + : < > ? { }` on their US keys) is unchanged. `sweep-layouts/layout.py` `UK` encodes the six swaps as keycode substitutions so that the SYM layer still types the intended characters, and `CHORDS["pound"]["win"]` is `KC_HASH` (Shift+3 = `£`).
- `navigator.keyboard.getLayoutMap()` ([WICG Keyboard Map](https://wicg.github.io/keyboard-map/)) returns, per `code`, the *unmodified* char of the current layout. It is Chromium-only, needs a secure context, and does not give the shifted layer, so it is a verification aid for the Board's configured input source, not a replacement for a stored table.
- Windows reports AltGr as `AltGraph` modifier state (UI Events Key spec); the right-hand `RALT_T` mod-tap on the Q3 Max triggers it when held.

## 6. Worked example: what the sweep-layouts `.vil`s give

I wrote a small inversion script (kept out of the repo; scratch only) that resolves each `.vil` into recipes by the rules above (held layers stacked on layer 0, transparent fall-through, shifted keycodes, mod-tap/layer-tap taps, text macros through the US send-string table, then the UK or US char table). Results for the distinct characters; tuples are `(layer index, row, col)`.

**Q3 Max (Windows, UK), `vil/q3_max.vil`**, single-character recipes excluding Shift-held paths, Caps Word and the override:
- Letters: one recipe each. `z x c v m , .` are mod-tap taps (bottom row); `Esc`/`'`/`Space` are layer-taps.
- Eight characters have two *identical-event* recipes: `#` (base `KC_NUHS` at (0,3,12), SYM at (2,2,7)), `'` (`LT(4,KC_QUOT)` tap at (0,3,11) and `RALT_T(KC_QUOT)` tap at (0,4,11)), `-` (number row (0,1,11), SYM (2,2,9)), `=`, `[`, `]`, `` ` `` (Hyper-tap on the grave key, SYM), and `\` (physical `KC_NUBS` at (0,4,1), SYM at (2,2,5)). The two `\` recipes are the same `IntlBackslash` event.
- Digits: one recipe each (number row, layer 0).
- Shifted symbols: one SYM recipe each (shifted keycode), plus the generic Shift-held path below.
- Shift sources on this Board: four, all holds of `KC_LSFT`, `KC_RSFT`, `LSFT_T(KC_V)`, `RSFT_T(KC_M)`. So every capital and every Shift symbol has up to 4 Shift paths x (key recipes of the unshifted char).
- Macros: `M1` -> `->` correct; `M0` -> `~>` under UK (see section 4).

**Sweep, QWERTY, Mac (`vil/ferris_sweep_qwerty.vil`)**:
- Letters: one recipe each in layer 0 (`a`...`z`; `z x c v m , . '` as mod-tap taps).
- 14 characters have two recipes with identical events because NUM repeats SYM's punctuation: `$ % ( ) * + , - . / : = [ ]` (e.g. `(` at SYM (1,5,2) and NUM (4,1,2)). Digits live only on NUM (one recipe each).
- `_` is the base-layer key (0,5,4) as a shifted keycode, which makes `_` unambiguous but `-` three-ways ambiguous (SYM, NUM, Shift+`_` override).
- Shift sources: two mod-tap holds (`LSFT_T(KC_V)`, `RSFT_T(KC_M)`), plus the Caps Word combo.

Counts above are for the recipe enumeration only. The generic Shift path multiplies recipes for any letter or shiftable symbol, which is why capitals cannot be attributed to a physical key without a rule (section 7).

## 7. Where the mapping is ambiguous, and how to handle it

### Taxonomy

| Class | Example (this layout) | Identical event? | Resolvable? |
| --- | --- | --- | --- |
| A. Same char, several keys/layers | `-`, `=`, `[`, `]`, `\`, `#`, `'` on the Q3 Max; 14 symbols on the Sweep (SYM vs NUM) | Yes | No, from the event; yes if the Passage target says which was meant |
| B. Same char, tap vs hold route | `'` via `LT` tap vs `RALT_T` tap | Yes | No |
| C. Shifted char, three Shift routes | `A`, `(`: shifted keycode vs Shift mod-tap hold vs real Shift key vs Caps Word | Almost: differ by `ShiftLeft`/`ShiftRight`, gap, key-up order, run length | Partly (heuristics) |
| D. Key override vs base `-` | Shift + `_` key vs SYM `-` | Nearly (Shift flicker) | Partly |
| E. Macro vs typed text | `->`, `|>` | No: burst cadence from one press | Mostly |
| F. Different keycodes, same char | `KC_BSLS` vs `KC_NUHS` on UK layout (both `#`/`~`) | Same `code` | No (and it does not matter) |
| G. Tap/hold misfire | `a`-`z` tapped on a bottom-row mod-tap held too long | Observable as modifier + missing char | Yes, as an error type |
| H. Invisible state | Layer lock, `TG`, one-shot, combo buffering delay | No event | Only by consequence |
| I. Wrong input source / wrong OS | `"` and `@` swap between UK and US | `key` differs from expectation | Yes, by configuration |

### Recommended handling

1. **Store raw events first.** For every `keydown`/`keyup` record `{code, key, location, shiftKey, ctrlKey, altKey, metaKey, AltGraph, repeat, timeStamp}` plus the Session's Board, `.vil` hash (or version), OS and input source. Attribution can then be recomputed when the model improves. This is the single most valuable decision.
2. **Attribute to a candidate set, plus one chosen recipe.** Per typed char produce `candidates: Recipe[]` from the index and a `chosen` recipe by a deterministic rule: prefer the recipe that matches the *expected* char's recipe (the Passage tells us which character was meant; for a correct keystroke the intended recipe is the one the typist was aiming at); otherwise prefer the recipe on the lowest layer, then the one on a home-row/lowest-effort key. Record `ambiguity = candidates.length` and a flag `exact` when `length == 1`.
3. **Use the evidence you do have to narrow the set**, in this order of reliability: (a) `code` and modifier presence (hard); (b) modifier side (`ShiftLeft` vs `ShiftRight`) (hard, excludes the opposite-side mod-tap); (c) Shift timing: Shift `keydown` within a few ms before the key means a shifted keycode, Caps Word or an override, not a human pressing a Shift key first (soft); (d) digits unshifted inside a capitalised run mean Caps Word (strong); (e) inter-key gap under ~15 ms with the same fixed string mean a macro (soft but strong in practice).
4. **For per-key statistics, only use unambiguous or disambiguated samples.** Letters and digits on the alpha layer give clean per-key data. For class A-D chars either count them toward the *char* (not a key) or toward the chosen recipe with `ambiguity > 1` so reports can show "key X, n samples, k of them ambiguous". Drills about a symbol should target the character, and may rotate the recipe the typist is told to use if that is what is being trained.
5. **Treat modifier misfires as first-class errors**, not noise: unexpected non-Shift modifier events with `code` on the home-row side, `AltGraph` on the UK Board, or a letter missing while a modifier is down.
6. **Treat the board+OS as part of the Keymap import.** Importing a `.vil` should also store the input-source choice per Board, and generate the `(code, mods) -> char` table once. If a `key` arriving at runtime disagrees with that table (e.g. `"` where `@` expected) flag a configuration error to the user before collecting data.

## 8. Things I could not settle from primary sources

These need a short recording session on the real boards (cheap, and the prototype can log them):
- Exact browser event order for shifted keycodes and for the key override (Shift down/up around `Minus`), on Chrome/Windows and Chrome/macOS. Derived from QMK source, not observed.
- Whether Windows maps a `KC_BSLS` keystroke and a `KC_NUHS` keystroke to the same char on the UK layout (UI Events says they share one `code`; the UK char table is from a secondary source).
- The `~>` result of `M0` on the Q3 Max under UK Windows. Derived from the send-string source and the default US table; not tested on the hardware.
- Keyup delivery for Command-chords on macOS Chrome and Windows-key behaviour for held GUI mod-taps.
- No Apple document found for "Australian == ABC"; the equality above is from the OS layout data on this Mac only.

## Implications for typokiller

- **Import step (the Keymap).** Parse the `.vil` to canonical 16-bit QMK keycodes (not strings), keep per-layer matrices, macros, combos, overrides and settings; read `vial.json` for geometry. Reject a `.vil` whose `layout` dimensions disagree with `vial.json`'s `matrix`. Store `os` and the input source with the Board; generate the `(code, mods) -> char` table from them rather than from `key` at runtime.
- **Index.** Build `char -> Recipe[]` and `(code, modifier set) -> Recipe[]`. Each Recipe carries Board, layer stack, matrix position, x/y, hand, kind (plain, mod-tap tap, layer-tap tap, shifted keycode, macro text, combo, override), and the Shift/AltGr/Option it needs. Hand comes from geometry (which half), finger from x (and the Board's own mapping), not from the `.vil`.
- **Capture.** Listen to `keydown`/`keyup` (not `input`); log raw events with `performance`-based timestamps; use `event.code` + modifier state as the key identity. Prevent default on keydown where possible (shortcut chords, Tab).
- **Attribution** is "set of candidates + deterministic choice + `ambiguity` count", never a single guessed key. Weak spots to expect in this layout: symbols duplicated across layers, capitals, `-`, and macro output. Letters and digits are essentially exact.
- **Treat these as distinct event types in the stats:** tap, hold-misfire (modifier events from mod-taps, missing char), combo output, macro burst, Caps Word run. Correct "slow key" metrics for combo buffering (up to the 40 ms combo term) and for mod-tap/layer-tap resolution time, otherwise bottom-row and thumb keys look slower than they are.
- **Use the Passage.** Because the expected text is known, the intended char is known; use the candidate set only to explain *which key* a mistyped char came from (the neighbouring-key and finger confusions the Drills are built from), and to decide among equal recipes by plausibility.
- **Config warnings from the data.** A mismatch between the observed `key` and the stored table is a Board configuration problem (wrong input source), not a typo. The Q3 Max `|>` macro is probably a layout-generation bug; worth reporting upstream in sweep-layouts after checking on hardware.
- **Scope check.** Do not try to detect OS-level state the browser cannot see (layer lock, TG layers); mark the layer as "unknown" after such keys until a char proves it.

## Sources

- Vial GUI (vial-kb/vial-gui @ `aef8222`): [`protocol/keyboard_comm.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/protocol/keyboard_comm.py) (save/restore layout, `vial.json` parsing), [`keycodes/keycodes.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/keycodes/keycodes.py), [`keycodes/keycodes_v6.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/keycodes/keycodes_v6.py), [`any_keycode.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/any_keycode.py), [`protocol/combo.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/protocol/combo.py), [`protocol/key_override.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/protocol/key_override.py), [`macro/macro_action.py`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/python/macro/macro_action.py), [`resources/base/qmk_settings.json`](https://github.com/vial-kb/vial-gui/blob/aef8222a2d0429a183b2ed692d5f9efcfd383f08/src/main/resources/base/qmk_settings.json).
- Vial QMK (vial-kb/vial-qmk @ `dd43959`): `quantum/vial.h`, `quantum/dynamic_keymap.c`, `quantum/action.c`, `quantum/action_layer.c`, `quantum/quantum.c`, `quantum/process_keycode/process_combo.c`, `process_key_override.c`, `process_caps_word.c`, `quantum/caps_word.c`, `quantum/send_string/send_string.c`, `quantum/keymap_extras/sendstring_uk.h`.
- QMK docs (qmk/qmk_firmware @ `180f394`): [`mod_tap.md`](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/mod_tap.md), [`tap_hold.md`](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/tap_hold.md), [`feature_layers.md`](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/feature_layers.md), [`features/combo.md`](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/features/combo.md), [`features/key_overrides.md`](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/features/key_overrides.md), [`features/caps_word.md`](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/features/caps_word.md), [`features/send_string.md`](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/features/send_string.md), [`keycodes_us_ansi_shifted.md`](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/keycodes_us_ansi_shifted.md), [`keycodes_basic.md`](https://github.com/qmk/qmk_firmware/blob/180f394b489c238cb231c2bf8b080262155e03c0/docs/keycodes_basic.md), [`data/constants/keycodes/`](https://github.com/qmk/qmk_firmware/tree/180f394b489c238cb231c2bf8b080262155e03c0/data/constants/keycodes).
- W3C: [UI Events](https://www.w3.org/TR/uievents/), [UI Events KeyboardEvent code values](https://www.w3.org/TR/uievents-code/), [UI Events KeyboardEvent key values](https://www.w3.org/TR/uievents-key/); WICG [Keyboard Map](https://wicg.github.io/keyboard-map/).
- UK keyboard layout character table (secondary): [kbdlayout.info/kbduk](https://kbdlayout.info/kbduk/).
- macOS input sources: measured locally via `TISCreateInputSourceList` + `UCKeyTranslate` for `com.apple.keylayout.{Australian,ABC,US,British}` (no Apple document found).
- Worked example (read-only): `/Users/mike/src/sweep-layouts` `README.md`, `layout.py`, `render.py`, `boards.py`, `vil/*.vil`, `boards/*/vial.json`.
