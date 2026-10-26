import json
import re
from functools import cache
from typing import Any, NamedTuple

# Letter layouts with a name, written as the 30 main keys row by row, left to right.
LETTER_LAYOUTS = {
    "qwertyuiopasdfghjkl_zxcvbnm,.'": "QWERTY",
    "xpdgvklio'untsm,rea_zwbcfjhy.q": "free-range",
}

# The characters of the basic keycodes, without and with Shift, under the Australian
# input source (the same as US on every key used).
UNSHIFTED = "abcdefghijklmnopqrstuvwxyz1234567890-=[]\\;',./`"
SHIFTED = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+{}|:"<>?~'
SHIFT = dict(zip(UNSHIFTED, SHIFTED))
BASIC = [f"KC_{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"] + (
    "KC_MINS KC_EQL KC_LBRC KC_RBRC KC_BSLS KC_SCLN KC_QUOT KC_COMM KC_DOT KC_SLSH KC_GRV".split()
)
# QMK's own names for Shift with a key, in the order of SHIFTED after the capitals.
SHIFTED_NAMES = (
    "KC_EXLM KC_AT KC_HASH KC_DLR KC_PERC KC_CIRC KC_AMPR KC_ASTR KC_LPRN KC_RPRN KC_UNDS KC_PLUS"
    " KC_LCBR KC_RCBR KC_PIPE KC_COLN KC_DQUO KC_LT KC_GT KC_QUES KC_TILD"
).split()
CHARS = dict(zip(BASIC, UNSHIFTED)) | dict(zip(SHIFTED_NAMES, SHIFTED[26:])) | {"KC_SPC": " ", "KC_ENT": "\n"}
# The browser's `key` for the combo outputs that the page records and that type no character there.
KEY_NAMES = {"KC_ENT": "Enter", "KC_BSPC": "Backspace"}
# The browser's `code` for the modifier that a held mod-tap sends: LSFT_T(KC_V) sends ShiftLeft.
HOLDS = {
    f"{side[0]}{mod}": f"{name}{side}"
    for side in ["Left", "Right"]
    for mod, name in [("SFT", "Shift"), ("CTL", "Control"), ("ALT", "Alt"), ("GUI", "Meta")]
}
SHIFT_MODS = 0x22  # either Shift, in the 8-bit modifier masks of a key override


# Each QMK setting's id in the .vil `settings` block (from Vial's qmk_settings.json)
# and QMK's default, which applies when the block does not have it.
QMK_SETTINGS = {"tapping_term": ("7", 200), "combo_term": ("2", 50)}


def qmk_settings(vil: dict[str, Any]) -> dict[str, int]:
    settings = vil.get("settings", {})
    return {name: settings.get(id, default) for name, (id, default) in QMK_SETTINGS.items()}


def tapped(keycode: Any) -> str:
    """The character a key types when tapped, or "": `LSFT_T(KC_C)`, `LT(1,KC_C)` and `KC_C` give `c`."""
    return CHARS.get(str(keycode).split("(")[-1].rstrip(")").split(",")[-1].strip(), "")


def key_x(vial: dict[str, Any]) -> dict[tuple[int, int], float]:
    """The x position of each matrix key (row, col) in the key positions of a vial.json.

    Rotation and key widths are ignored. They change only the thumb keys, and x is
    only used to put the main keys of one row in order. Encoders are skipped.
    """
    xs: dict[tuple[int, int], float] = {}
    for kle_row in vial["layouts"]["keymap"]:
        x = 0.0
        for item in kle_row:
            if isinstance(item, dict):
                x += item.get("x", 0)
                continue
            lines = item.split("\n")
            if lines[-1] != "e":
                row, col = lines[0].split(",")
                xs[int(row), int(col)] = x
            x += 1
    return xs


def letter_layout(vil: dict[str, Any], vial: dict[str, Any]) -> str:
    """The name of the Letter layout on the 30 main keys of the base layer.

    The main keys are on the matrix rows that have a letter: 3 rows, or 6 on a
    split board (3 for each half, and the nth of each half are one row of keys).
    In each of the 3 rows, the keys that type a character are put in order by their
    x position in the vial.json, and the 10 keys from the first letter on are the
    main keys. This drops number rows, thumb rows and outer keys such as Tab.
    """
    base = vil["layout"][0]
    xs = key_x(vial)
    rows = sorted({r for r, c in xs if tapped(base[r][c]).isalpha()})
    by_x = sorted(xs, key=xs.__getitem__)
    text = ""
    for n in range(3):
        chars = [tapped(base[r][c]) for r, c in by_x if r in rows and rows.index(r) % 3 == n]
        chars = [char for char in chars if char]
        first = next(i for i, char in enumerate(chars) if char.isalpha())
        text += "".join(chars[first : first + 10])
    return LETTER_LAYOUTS.get(text, text)


@cache
def keymap_letters(vil: str, vial: str) -> str:
    """The name of the Letter layout of a stored .vil, from the texts of it and its vial.json."""
    return letter_layout(json.loads(vil), json.loads(vial))


def key_char(keycode: str) -> str | None:
    """The character a keycode types: `KC_9` gives 9, and `KC_LPRN` and `LSFT(KC_9)` give (."""
    if shifted := re.fullmatch(r"(?:LSFT|S)\((\w+)\)", keycode):
        return SHIFT.get(CHARS.get(shifted[1], ""))
    return CHARS.get(keycode)


class Key(NamedTuple):
    layer: int
    key: str  # its matrix position, "row,col" as vial.json labels it; a combo's keys joined by "+"
    kind: str  # "plain", "mod-tap", "layer-tap", "combo" or "macro"


class Keymap(NamedTuple):
    keys: dict[str, list[Key]]  # each character's candidate keys, best first
    macros: dict[str, Key]  # the text each macro types, and its key
    holds: dict[tuple[str, str], Key]  # (the modifier's code, the tapped character) of each mod-tap
    combos: list[tuple[str, str, Key]]  # the `key` each combo sends, the characters of its keys, the combo


@cache
def read_keymap(vil_text: str) -> Keymap:
    """Which keys of a .vil type each character, and the macros, mod-taps and combos that
    can misfire. It follows each key's keycode to the character it types. Keys on KC_TRNS fall through to a lower layer, so they are skipped.

    A character's candidates are first the keys that type it, then the keys that type it with
    Shift held (capitals, Caps Word, and the Shift + _ key override). Each group is ordered by
    layer, then by matrix position. A combo is on layer 0 and comes after that layer's keys.
    Macros are not candidates: their characters are found as a fast burst of their text.
    """
    vil = json.loads(vil_text)
    found: list[tuple[bool, str, Key]] = []  # (with Shift, character, key)
    macros, holds, combos = {}, {}, []
    overrides = {
        ko["trigger"]: key_char(ko["replacement"])
        for ko in vil.get("key_override", [])
        if ko["options"] & 0x80 and ko["trigger_mods"] & SHIFT_MODS  # enabled, and triggered by Shift
    }
    base = {}  # the matrix position of each keycode on layer 0, for combos
    for layer, rows in enumerate(vil["layout"]):
        for r, row in enumerate(rows):
            for c, keycode in enumerate(row):
                keycode, char = str(keycode), tapped(keycode)
                if layer == 0:
                    base[keycode] = f"{r},{c}"
                kind = "layer-tap" if keycode.startswith("LT(") else "mod-tap" if "_T(" in keycode else "plain"
                macro = re.fullmatch(r"M(\d+)", keycode)
                kind = "macro" if macro else kind
                key = Key(layer, f"{r},{c}", kind)
                if kind == "plain":
                    char = key_char(keycode)
                elif hold := HOLDS.get(keycode.split("_T(")[0]):
                    holds[hold, char] = key
                if macro and (text := macro_text(vil["macro"][int(macro[1])])):
                    macros[text] = key
                if char:
                    found.append((False, char, key))
                    if char in SHIFT:
                        found.append((True, SHIFT[char], key))
                if replaced := overrides.get(keycode):
                    found.append((True, replaced, key))
    for *inputs, output in vil.get("combo", []):
        inputs = [i for i in inputs if i != "KC_NO"]
        if inputs and all(i in base for i in inputs):
            key = Key(0, "+".join(base[i] for i in inputs), "combo")
            if char := key_char(output):
                found.append((False, char, key))
            if output in KEY_NAMES:
                combos.append((KEY_NAMES[output], "".join(tapped(i) for i in inputs), key))
    keys: dict[str, list[Key]] = {}
    for _, char, key in sorted(found, key=lambda f: (f[0], f[2].layer)):
        keys.setdefault(char, []).append(key)
    return Keymap(keys, macros, holds, combos)


def macro_text(actions: list[list[Any]]) -> str:
    """The text a macro types. A macro that holds a key down types a chord, such as Ctrl-b, so no text."""
    if any(action == "down" for action, *_ in actions):
        return ""
    return "".join(arg if action == "text" else key_char(arg) or "" for action, arg in actions)
