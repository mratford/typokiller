import re
from typing import Any

# Letter layouts with a name, written as the 30 main keys row by row, left to right.
LETTER_LAYOUTS = {
    "qwertyuiopasdfghjkl_zxcvbnm,.'": "QWERTY",
    "xpdgvklio'untsm,rea_zwbcfjhy.q": "free-range",
}
PUNCTUATION = {"KC_COMM": ",", "KC_DOT": ".", "KC_QUOT": "'", "KC_UNDS": "_", "KC_SCLN": ";", "KC_SLSH": "/"}

# Each QMK setting's id in the .vil `settings` block (from Vial's qmk_settings.json)
# and QMK's default, which applies when the block does not have it.
QMK_SETTINGS = {"tapping_term": ("7", 200), "combo_term": ("2", 50)}


def qmk_settings(vil: dict[str, Any]) -> dict[str, int]:
    settings = vil.get("settings", {})
    return {name: settings.get(id, default) for name, (id, default) in QMK_SETTINGS.items()}


def tapped(keycode: Any) -> str:
    """The character a key types when tapped, or "": `LSFT_T(KC_C)` and `KC_C` give `c`."""
    code = str(keycode).split("(")[-1].rstrip(")").split(",")[-1]
    if re.fullmatch("KC_[A-Z]", code):
        return code[-1].lower()
    return PUNCTUATION.get(code, "")


def key_x(vial: dict[str, Any]) -> dict[tuple[int, int], float]:
    """The x position of each matrix key (row, col) in the KLE layout of a vial.json.

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

    This rule works for split boards such as the Sweep and the Sofle, where the
    left half has the first half of the matrix rows. The main keys are the keys in
    a matrix row that has a letter and in a matrix column (of the same half) that
    has a letter. This drops number rows, thumb rows and outer columns such as Tab.
    Rows are matched across the halves in matrix order, and keys in a row are put
    in order by their x position in the vial.json.
    """
    base = vil["layout"][0]
    half = len(base) // 2
    letters = [(r, c) for r, row in enumerate(base) for c, keycode in enumerate(row) if tapped(keycode).isalpha()]
    rows = sorted({r for r, _ in letters})
    cols = {(r < half, c) for r, c in letters}
    xs = key_x(vial)
    keys = sorted(
        (rows.index(r) % (len(rows) // 2), xs[r, c], tapped(base[r][c]))
        for r in rows
        for c in range(len(base[r]))
        if (r < half, c) in cols
    )
    text = "".join(char for _, _, char in keys)
    return LETTER_LAYOUTS.get(text, text)
