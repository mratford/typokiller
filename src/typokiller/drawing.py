"""Keymap drawings as SVG, for the pages and the marimo notebooks.

Sizes are in key widths, as in the vial.json. Colours come from the page's CSS variables
(--bg, --fg, --dim, --faint, --line, --panel, --next), with defaults for a notebook, which has none.
"""

import json
import math
import re
from collections.abc import Sequence
from html import escape
from typing import Any, NamedTuple

from typokiller.keymap import SHIFT, combo_keys, key_char, macro_text, read_keymap, shift_overrides, tapped

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
.keymap .grey rect, .keymap .combo.grey rect { fill: var(--line, #e5e1d8); }
.keymap .combo.grey text { fill: var(--dim, #a29e94); }
.keymap .arc { opacity: 0.85; }
.keymap .arc path, .keymap .arc .loop { fill: none; stroke: var(--next, #2456a6); stroke-width: 0.07; stroke-linecap: round; }
.keymap .arc .end, .keymap .arc text { fill: var(--next, #2456a6); font-weight: 700; }
.keymap .scale text { fill: var(--dim, #a29e94); }
.keymap .scale .note { text-anchor: start; }
.keymap .scale line { stroke: var(--fg, #23221f); stroke-width: 0.03; }
.keymap .scale rect { stroke: var(--faint, #d9d5cc); stroke-width: 0.02; }
"""
# The colours of a heat drawing, from the low end of the Weakness model's scale (pale) to
# its high end (dark). Costs outside the scale get the colour of its nearer end.
RAMP = ["#fbf1d3", "#f6cf8a", "#ee9f5e", "#d8663f", "#a83a35", "#6e2130"]
DEFS = (
    '<defs><pattern id="hatch" width="0.18" height="0.18" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
    '<rect width="0.18" height="0.18" style="fill:var(--panel, #fff)"/>'
    '<line x1="0" y1="0" x2="0" y2="0.18" style="stroke:var(--faint, #d9d5cc);stroke-width:0.07"/></pattern>'
    '<linearGradient id="ramp">'
    + "".join(f'<stop offset="{i / (len(RAMP) - 1):.3g}" stop-color="{c}"/>' for i, c in enumerate(RAMP))
    + "</linearGradient></defs>"
)


class Heat(NamedTuple):
    """The Weakness costs that a heat drawing colours its keys by (see `analysis.rank_units`)."""

    costs: dict[str, float]  # the cost (ms) of each unit that the Weakness model ranks
    seen: dict[str, int]  # the times each unit was seen in the Weakness model's weeks
    scale: tuple[float, float, float]  # the Weakness model's colour scale: low, high and tick costs (ms)


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


def key_chars(keycode: Any, overrides: dict[str, str | None]) -> list[str]:
    """The characters a key types, for a heat drawing: [Shifted, unshifted], or one character
    when it has no Shifted character, or none for a key that types no character (layer keys,
    modifiers, navigation keys and macros). A tap-hold key types its tap. `overrides` are
    the .vil's `shift_overrides`, which come before the usual Shifted character."""
    k = str(keycode)
    char = tapped(k) if re.fullmatch(r"(LT|\w+_T)\(.+\)", k) else key_char(k)
    shifted = overrides.get(k) or SHIFT.get(char or "")
    return [shifted, char] if char and shifted else [char] if char else []


def heat_colour(cost: float, scale: tuple[float, float, float]) -> tuple[str, bool]:
    """The colour of a cost on the fixed colour scale (low, high, tick) of a Weakness model,
    and whether it is dark, so that its text is white."""
    low, high, _ = scale
    t = min(max((cost - low) / (high - low), 0), 1) * (len(RAMP) - 1)
    i = min(int(t), len(RAMP) - 2)
    a, b = bytes.fromhex(RAMP[i][1:]), bytes.fromhex(RAMP[i + 1][1:])
    # The last 2 colours of RAMP (and the end of the third last) are dark.
    return "#" + "".join(f"{round(x + (y - x) * (t - i)):02x}" for x, y in zip(a, b)), t > 3


def heat_key(p: Place, chars: list[str], tap: str, heat: Heat) -> tuple[str, str]:
    """The coloured halves and the texts of a key that types characters, in a heat drawing.
    With two characters, the Shifted one is the top half and the unshifted one the bottom.
    Each half shows its cost in ms; a half that the Weakness model does not rank (seen
    too few times) is hatched and shows its seen count as n=<count>."""
    x0, y0, x1, y1 = p.x + 0.05, p.y + 0.05, p.x + p.w - 0.05, p.y + p.h - 0.05
    mid, cx = (y0 + y1) / 2, num(p.x + p.w / 2)
    if len(chars) == 1:
        halves = [(y0, y1, tap, chars[0])]
    else:
        halves = [(y0, mid, escape(chars[0]), chars[0]), (mid, y1, tap, chars[1])]
    fills, labels = [], []
    for top, bottom, text, char in halves:
        rt, rb = 0.12 if top == y0 else 0, 0.12 if bottom == y1 else 0  # round only the key's own corners
        d = (
            f"M{num(x0)} {num(top + rt)}Q{num(x0)} {num(top)} {num(x0 + rt)} {num(top)}H{num(x1 - rt)}"
            f"Q{num(x1)} {num(top)} {num(x1)} {num(top + rt)}V{num(bottom - rb)}Q{num(x1)} {num(bottom)}"
            f" {num(x1 - rb)} {num(bottom)}H{num(x0 + rb)}Q{num(x0)} {num(bottom)} {num(x0)} {num(bottom - rb)}Z"
        )
        colour = ""  # a hatched half has the page's colours
        if char in heat.costs:
            fill, dark = heat_colour(heat.costs[char], heat.scale)
            label = f"{round(heat.costs[char])}"
            colour = f' style="fill:{"#fff" if dark else "#23221f"}"'  # the scale's colours are the same in dark mode
        else:
            fill, label = "url(#hatch)", f"n={heat.seen.get(char, 0)}"
        fills.append(f'<path class="half" d="{d}" style="fill:{fill}"/>')
        h, whole = bottom - top, len(halves) == 1
        size = font_size(text, p.w) if whole else min(0.22, font_size(text, p.w))
        labels.append(
            f'<text class="tap" x="{cx}" y="{num(top + h * 0.38)}" font-size="{num(size)}"{colour}>{text}</text>'
            f'<text class="hold" x="{cx}" y="{num(top + h * 0.8)}" font-size="{0.18 if whole else 0.12}"{colour}>{label}</text>'
        )
    return "".join(fills), "".join(labels)


def scale_legend(scale: tuple[float, float, float], x: float, y: float) -> str:
    """The legend of a heat drawing: the colour scale with its tick, the hatched halves and the grey keys."""
    low, high, tick = scale

    def at(cost: float) -> str:
        return num(x + 3 * (cost - low) / (high - low))

    labels = [(low, num(low)), (tick, num(tick)), (high, f"{num(high)} ms")]
    return (
        f'<g class="scale"><rect x="{num(x)}" y="{num(y)}" width="3" height="0.16" style="fill:url(#ramp)"/>'
        + "".join(f'<text x="{at(c)}" y="{num(y + 0.34)}" font-size="0.14">{t}</text>' for c, t in labels)
        + f'<line x1="{at(tick)}" y1="{num(y - 0.04)}" x2="{at(tick)}" y2="{num(y + 0.2)}"/>'
        f'<rect x="{num(x + 4)}" y="{num(y - 0.04)}" width="0.36" height="0.24" style="fill:url(#hatch)"/>'
        f'<text class="note" x="{num(x + 4.5)}" y="{num(y + 0.08)}" font-size="0.14">seen too few times (n)</text>'
        f'<rect x="{num(x + 6.6)}" y="{num(y - 0.04)}" width="0.36" height="0.24" style="fill:var(--line, #e5e1d8)"/>'
        f'<text class="note" x="{num(x + 7.1)}" y="{num(y + 0.08)}" font-size="0.14">not a character</text></g>'
    )


def show_chars(text: str) -> str:
    """The text with a space shown as ␣ and a newline as ↵, as the page shows them."""
    return text.replace(" ", "␣").replace("\n", "↵")


def arc(pair: str, start: tuple[float, float], end: tuple[float, float]) -> str:
    """A pair drawn as an arc from the centre of its first character's key to its second's,
    with a dot at the end. A pair on one key is a small loop above it."""
    (x1, y1), (x2, y2) = start, end
    label = escape(show_chars(pair))
    if start == end:
        drawn = f'<circle class="loop" cx="{num(x1)}" cy="{num(y1 - 0.62)}" r="0.2"/>'
        lx, ly = x1, y1 - 0.98
    else:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 0.35 - 0.12 * math.hypot(x2 - x1, y2 - y1)
        drawn = (
            f'<path d="M{num(x1)} {num(y1 - 0.25)} Q{num(mx)} {num(my)} {num(x2)} {num(y2 - 0.25)}"/>'
            f'<circle class="end" cx="{num(x2)}" cy="{num(y2 - 0.25)}" r="0.09"/>'
        )
        lx, ly = mx, (y1 + y2 - 0.5 + 2 * my) / 4 - 0.15  # just above the top of the curve
    return (
        f'<g class="arc" data-pair="{escape(pair)}">{drawn}'
        f'<text x="{num(lx)}" y="{num(ly)}" font-size="0.2">{label}</text></g>'
    )


def draw_keymap(
    vil_text: str,
    vial_text: str | None,
    layer: int,
    names: Sequence[str] = (),
    heat: Heat | None = None,
    pairs: Sequence[str] = (),
) -> str:
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
      joined by "+", as `Key.key` in the keystrokes table. A page can outline the key
      to press by adding the class "next".
    - With `heat`, each key is coloured by the Weakness costs (see `heat_key`), and a legend
      of the colour scale is drawn under the keys. Keys that type no character, macros and
      combos are grey (class "grey"); they are not finger presses of one character.
    - Each of `pairs` is an arc (see `arc`), a <g> of class "arc" with the pair in
      data-pair. Its ends are the keys that key attribution picks for a correct keystroke
      (each character's first candidate). It is drawn only when both of these keys are on
      the layer drawn.
    """
    vil = json.loads(vil_text)
    keycodes = vil["layout"]
    if vial_text:
        places = key_places(json.loads(vial_text))
    else:
        places = {(r, c): Place(c, r) for r, row in enumerate(keycodes[0]) for c, k in enumerate(row) if k != -1}

    def centre(key: str) -> tuple[float, float] | None:
        """The centre of a key, or of a combo's box, by its `Key.key`."""
        at = [(int(r), int(c)) for r, c in (k.split(",") for k in key.split("+"))]
        if not all(a in places for a in at):
            return None
        centres = [places[a].centre() for a in at]
        x, y = sum(cx for cx, _ in centres) / len(centres), sum(cy for _, cy in centres) / len(centres)
        return (x, y + 0.36) if len(at) > 1 else (x, y)

    held = opener(vil, layer)[0] if layer else None
    overrides = shift_overrides(vil)
    parts = []
    for (r, c), p in places.items():
        keycode = keycodes[layer][r][c]
        tap, hold = legend(keycode, vil, names)
        kind = {"KC_TRNS": " trns", "KC_NO": " none"}.get(str(keycode), "")
        if (r, c) == held:
            kind, tap, hold = " held", "held", ""
        chars = key_chars(keycode, overrides)
        halves = texts = ""
        if heat and not kind:
            if chars:
                halves, texts = heat_key(p, chars, escape(tap), heat)
            else:
                kind = " grey"
        if not halves:
            cx, cy = p.x + p.w / 2, p.y + p.h / 2
            if tap:
                y, size = cy - 0.1 if hold else cy, font_size(tap, p.w)
                texts += f'<text class="tap" x="{num(cx)}" y="{num(y)}" font-size="{num(size)}">{escape(tap)}</text>'
            if hold:
                y = p.y + p.h - 0.2
                texts += f'<text class="hold" x="{num(cx)}" y="{num(y)}" font-size="0.18">{escape(hold)}</text>'
        turn = f' transform="rotate({num(p.r)} {num(p.rx)} {num(p.ry)})"' if p.r else ""
        outline = ' style="fill:none"' if halves else ""  # drawn over the halves
        parts.append(
            f'<g id="k{r},{c}" class="key{kind}"{turn}>{halves}<rect x="{num(p.x + 0.05)}" y="{num(p.y + 0.05)}"'
            f' width="{num(p.w - 0.1)}" height="{num(p.h - 0.1)}" rx="0.12"{outline}/>{texts}</g>'
        )
    for inputs, output, at, key in combo_keys(vil):
        drawn = all(a in places and keycodes[layer][a[0]][a[1]] in (i, "KC_TRNS") for i, a in zip(inputs, at))
        if not drawn:
            continue
        x, y = centre(key) or (0, 0)
        text = legend(output, vil, names)[0]
        w = 0.26 + 0.12 * len(text)
        parts.append(
            f'<g id="k{key}" class="combo{" grey" if heat else ""}">'
            f'<rect x="{num(x - w / 2)}" y="{num(y - 0.13)}" width="{num(w)}" height="0.26" rx="0.13"/>'
            f'<text x="{num(x)}" y="{num(y)}" font-size="0.16">{escape(text)}</text></g>'
        )
    # The centre of each character's first candidate key, if that key is on this layer.
    here = {char: centre(keys[0].key) for char, keys in read_keymap(vil_text).keys.items() if keys[0].layer == layer}
    for pair in pairs:
        ends = [here.get(char) for char in pair]
        if ends[0] and ends[1]:
            parts.append(arc(pair, ends[0], ends[1]))
    corners = [p.turn(x, y) for p in places.values() for x in (p.x, p.x + p.w) for y in (p.y, p.y + p.h)]
    x0, y0 = min(x for x, _ in corners) - 0.1, min(y for _, y in corners) - 0.1
    x1, y1 = max(x for x, _ in corners) + 0.1, max(y for _, y in corners) + 0.1
    if pairs:
        y0 -= 1  # room for arcs over the top row
    if heat:
        parts.append(scale_legend(heat.scale, x0 + 0.3, y1 + 0.2))
        x1, y1 = max(x1, x0 + 9.3), y1 + 0.7
    return (
        f'<svg class="keymap" xmlns="http://www.w3.org/2000/svg" viewBox="{num(x0)} {num(y0)} {num(x1 - x0)} {num(y1 - y0)}">'
        f"<style>{STYLE}</style>{DEFS if heat else ''}{''.join(parts)}</svg>"
    )


def draw_layers(
    vil_text: str,
    vial_text: str | None,
    names: Sequence[str] = (),
    heat: Heat | None = None,
    pairs: Sequence[str] = (),
) -> list[tuple[str, str]]:
    """The name (see `layer_name`) and the `draw_keymap` drawing of each layer, up to the
    last layer that is not empty (see `drawn_layers`)."""
    vil = json.loads(vil_text)
    return [
        (layer_name(vil, layer, names), draw_keymap(vil_text, vial_text, layer, names, heat, pairs))
        for layer in range(drawn_layers(vil_text))
    ]
