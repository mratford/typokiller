"""Keymap drawings as SVG (spec §10). The app and the marimo notebooks both use draw_keymap,
so the practice screen, the progress page and the notebooks draw a Keymap the same way.

Sizes are in key widths, as in the vial.json. Colours come from the page's CSS variables
(--bg, --fg, --dim, --faint, --panel, --next), with defaults for a notebook, which has none.
"""

import json
import math
import re
from collections.abc import Sequence
from html import escape
from typing import Any, NamedTuple

from typokiller.keymap import combo_keys, key_char, macro_text

# Legends for keycodes that do not type a character, and for ⌥3, which types £ on a Mac.
NAMED = {
    "KC_SPC": "Space", "KC_ENT": "⏎", "KC_BSPC": "⌫", "KC_DEL": "Del", "KC_ESC": "Esc", "KC_TAB": "Tab",
    "KC_LEFT": "←", "KC_RGHT": "→", "KC_UP": "↑", "KC_DOWN": "↓", "KC_HOME": "Home", "KC_END": "End",
    "KC_PGUP": "PgUp", "KC_PGDN": "PgDn", "KC_VOLD": "Vol−", "KC_VOLU": "Vol+", "KC_MUTE": "Mute",
    "KC_MPLY": "Play", "KC_MPRV": "Prev", "KC_MNXT": "Next", "KC_BRID": "Bri−", "KC_BRIU": "Bri+",
    "QK_BOOT": "Boot", "QK_LAYER_LOCK": "Lock", "QK_CAPS_WORD_TOGGLE": "CapsW", "KC_PSCR": "PrtSc",
    "KC_INS": "Ins", "KC_CAPS": "Caps", "KC_APP": "Menu", "NK_TOGG": "NKRO", "LGUI(KC_Z)": "Undo",
    "SGUI(KC_Z)": "Redo", "LGUI(KC_C)": "Copy", "LGUI(KC_V)": "Paste", "LGUI(KC_X)": "Cut",
    "LALT(KC_3)": "£", "KC_TRNS": "", "KC_NO": "",
}  # fmt: skip
MODS = {"GUI": "⌘", "WIN": "⌘", "ALT": "⌥", "CTL": "⌃", "SFT": "⇧", "SGUI": "⇧⌘", "MEH": "Meh ", "HYPR": "Hyper "}
OPENS = r"(LT|MO|TG|TT|OSL)\((\d+)(?:,\s*(.+))?\)"  # a key that opens a layer: the layer, and the tap of LT

STYLE = """
.keymap text { text-anchor: middle; dominant-baseline: central; font-family: -apple-system, system-ui, sans-serif; }
.keymap .key rect { fill: var(--panel, #fff); stroke: var(--fg, #23221f); stroke-width: 0.03; }
.keymap .trns rect { fill: none; stroke: var(--dim, #a29e94); stroke-dasharray: 0.08 0.06; }
.keymap .none rect { fill: none; stroke: var(--faint, #d9d5cc); }
.keymap .held rect { fill: var(--faint, #d9d5cc); stroke-width: 0.08; }
.keymap .tap { fill: var(--fg, #23221f); font-weight: 600; }
.keymap .hold { fill: var(--dim, #a29e94); font-weight: 500; }
.keymap .combo rect { fill: var(--fg, #23221f); }
.keymap .combo text { fill: var(--bg, #fbfaf7); font-weight: 700; }
.keymap .next rect { stroke: var(--next, #2456a6); stroke-width: 0.1; }
"""


class Place(NamedTuple):
    """Where a key is drawn: its top left corner and size before rotation, and its
    rotation in degrees about (rx, ry)."""

    x: float
    y: float
    w: float = 1
    h: float = 1
    r: float = 0
    rx: float = 0
    ry: float = 0

    def turn(self, x: float, y: float) -> tuple[float, float]:
        """The point (x, y) of the key, rotated with it."""
        a = math.radians(self.r)
        dx, dy = x - self.rx, y - self.ry
        return self.rx + dx * math.cos(a) - dy * math.sin(a), self.ry + dx * math.sin(a) + dy * math.cos(a)

    def centre(self) -> tuple[float, float]:
        return self.turn(self.x + self.w / 2, self.y + self.h / 2)


def key_places(vial: dict[str, Any]) -> dict[tuple[int, int], Place]:
    """Where each matrix key (row, col) is drawn, from the KLE layout of a vial.json. Its
    labels are "row,col". Encoders (a last label line "e") and decals are skipped, and of
    each layout option only the first choice is drawn."""
    places = {}
    x = y = r = rx = ry = 0.0
    w = h = 1.0
    decal = False
    for kle_row in vial["layouts"]["keymap"]:
        for item in kle_row:
            if isinstance(item, dict):
                r = item.get("r", r)
                if "rx" in item or "ry" in item:  # a new rotation centre starts a new block of keys
                    x, y = rx, ry = item.get("rx", rx), item.get("ry", ry)
                x, y = x + item.get("x", 0), y + item.get("y", 0)
                w, h, decal = item.get("w", w), item.get("h", h), item.get("d", decal)
                continue
            lines = item.split("\n")
            option = lines[3] if len(lines) > 3 else ""
            if lines[-1] != "e" and not decal and option.split(",")[-1] in ("", "0"):
                row, col = lines[0].split(",")
                places[int(row), int(col)] = Place(x, y, w, h, r, rx, ry)
            x += w
            w, h, decal = 1.0, 1.0, False
        x, y = rx, y + 1
    return places


def drawn_layers(vil_text: str) -> int:
    """The number of layers to draw: up to the last layer with a key that is not KC_TRNS or KC_NO."""
    layers = json.loads(vil_text)["layout"]
    used = [i for i, rows in enumerate(layers) if any(k not in ("KC_TRNS", "KC_NO", -1) for row in rows for k in row)]
    return max(used, default=0) + 1


def legend(keycode: Any, vil: dict[str, Any], names: Sequence[str]) -> tuple[str, str]:
    """The tap legend and the hold legend of a keycode. `names` are the layer names."""
    k = str(keycode)
    if k in NAMED:
        return NAMED[k], ""
    if m := re.fullmatch(r"[LR]?(GUI|ALT|CTL|SFT|MEH|HYPR)_T\((.+)\)", k):  # a mod-tap
        return legend(m[2], vil, names)[0], MODS[m[1]].strip()
    if m := re.fullmatch(OPENS, k):
        name = layer_name(vil, int(m[2]), names)
        if m[3]:  # LT: the tapped key, held for the layer
            return legend(m[3], vil, names)[0], name
        return name + ("" if m[1] == "MO" else f" {m[1].lower()}"), ""
    if m := re.fullmatch(r"M(\d+)", k):  # a macro: its text, else the keys it taps, else its number
        actions = vil["macro"][int(m[1])]
        taps = " ".join(legend(arg, vil, names)[0] for action, arg in actions if action == "tap")
        return macro_text(actions) or taps or k, ""
    if char := key_char(k):
        return char, ""
    if m := re.fullmatch(r"OSM\(MOD_(\w+)\)", k):
        return f"1×{m[1].lower()}", ""
    if m := re.fullmatch(r"[LR]?(GUI|ALT|CTL|SFT|SGUI|MEH|HYPR)\((.+)\)", k):  # a key with modifiers
        return MODS[m[1]] + legend(m[2], vil, names)[0], ""
    if m := re.fullmatch(r"KC_[LR](GUI|WIN|ALT|CTL|SFT)", k):
        return MODS[m[1]], ""
    if m := re.fullmatch(r"USER0*(\d+)", k):
        return f"U{m[1]}", ""
    if re.match(r"(RGB|RM|UG)_", k):
        return "RGB", ""
    return re.sub(r"^(KC|QK)_", "", k)[:5], ""


def opener(vil: dict[str, Any], layer: int) -> tuple[tuple[int, int] | None, str | None]:
    """The matrix position of the key on the base layer that opens a layer, if there is one,
    and the keycode it taps, if it is a layer-tap."""
    for r, row in enumerate(vil["layout"][0]):
        for c, keycode in enumerate(row):
            if (m := re.fullmatch(OPENS, str(keycode))) and int(m[2]) == layer:
                return (r, c), m[3]
    return None, None


def layer_name(vil: dict[str, Any], layer: int, names: Sequence[str]) -> str:
    """The layer's name from the settings, else the tap legend of the key that opens it, else L<n>."""
    if layer < len(names) and names[layer]:
        return names[layer]
    _, tap = opener(vil, layer)
    return legend(tap, vil, names)[0] if tap else f"L{layer}"


def font_size(text: str, width: float) -> float:
    """A smaller font for a longer legend, so it fits on the key."""
    n = len(text)
    size = 0.42 if n <= 1 else 0.34 if n <= 2 else 0.25 if n <= 4 else 0.19 if n <= 6 else 0.15
    return min(0.42, size * max(1, width * 0.8))


def num(v: float) -> str:
    """A number for the SVG, rounded to 3 decimal places."""
    return f"{round(v, 3):g}"


def draw_keymap(vil_text: str, vial_text: str | None, layer: int, names: Sequence[str] = ()) -> str:
    """An SVG drawing of one layer of a Keymap, from the text of its .vil and of its Board's
    vial.json. Without a vial.json, the matrix is drawn as a plain grid.

    - Each key shows its tap legend large, and its hold legend small underneath. Layer keys
      show the layer's name: names[layer] from the settings, else the tap legend of the key
      on the base layer that opens it, else L<n>.
    - The key held for the layer shown is shaded and reads "held". Transparent keys are
      dashed and empty; KC_NO keys are faint and empty.
    - A macro shows the text it types, else the keys it taps, else M<n>.
    - A combo is a small rounded box between its keys that shows what it sends. It is
      drawn on each layer where its keys are the combo's keycodes or transparent (QMK
      matches combos by keycode).
    - Each key is a <g> with the id "k<row>,<col>", and each combo "k" and its keys' ids
      joined by "+", as `Key.key` in the keystrokes table. The page outlines the key to
      press by adding the class "next".
    """
    vil = json.loads(vil_text)
    keycodes = vil["layout"]
    if vial_text:
        places = key_places(json.loads(vial_text))
    else:
        places = {(r, c): Place(c, r) for r, row in enumerate(keycodes[0]) for c, k in enumerate(row) if k != -1}
    held = opener(vil, layer)[0] if layer else None
    parts = []
    for (r, c), p in places.items():
        keycode = keycodes[layer][r][c]
        tap, hold = legend(keycode, vil, names)
        kind = {"KC_TRNS": " trns", "KC_NO": " none"}.get(str(keycode), "")
        if (r, c) == held:
            kind, tap, hold = " held", "held", ""
        cx, cy = p.x + p.w / 2, p.y + p.h / 2
        texts = ""
        if tap:
            size = font_size(tap, p.w)
            y = cy - 0.1 if hold else cy
            texts += f'<text class="tap" x="{num(cx)}" y="{num(y)}" font-size="{num(size)}">{escape(tap)}</text>'
        if hold:
            texts += f'<text class="hold" x="{num(cx)}" y="{num(p.y + p.h - 0.2)}" font-size="0.18">{escape(hold)}</text>'
        turn = f' transform="rotate({num(p.r)} {num(p.rx)} {num(p.ry)})"' if p.r else ""
        parts.append(
            f'<g id="k{r},{c}" class="key{kind}"{turn}><rect x="{num(p.x + 0.05)}" y="{num(p.y + 0.05)}"'
            f' width="{num(p.w - 0.1)}" height="{num(p.h - 0.1)}" rx="0.12"/>{texts}</g>'
        )
    for inputs, output, at, key in combo_keys(vil):
        drawn = all(a in places and keycodes[layer][a[0]][a[1]] in (i, "KC_TRNS") for i, a in zip(inputs, at))
        if not drawn:
            continue
        centres = [places[a].centre() for a in at]
        x, y = sum(cx for cx, _ in centres) / len(centres), sum(cy for _, cy in centres) / len(centres) + 0.36
        text = legend(output, vil, names)[0]
        w = 0.26 + 0.12 * len(text)
        parts.append(
            f'<g id="k{key}" class="combo">'
            f'<rect x="{num(x - w / 2)}" y="{num(y - 0.13)}" width="{num(w)}" height="0.26" rx="0.13"/>'
            f'<text x="{num(x)}" y="{num(y)}" font-size="0.16">{escape(text)}</text></g>'
        )
    corners = [p.turn(x, y) for p in places.values() for x in (p.x, p.x + p.w) for y in (p.y, p.y + p.h)]
    x0, y0 = min(x for x, _ in corners) - 0.1, min(y for _, y in corners) - 0.1
    x1, y1 = max(x for x, _ in corners) + 0.1, max(y for _, y in corners) + 0.1
    return (
        f'<svg class="keymap" xmlns="http://www.w3.org/2000/svg" viewBox="{num(x0)} {num(y0)} {num(x1 - x0)} {num(y1 - y0)}">'
        f"<style>{STYLE}</style>{''.join(parts)}</svg>"
    )
