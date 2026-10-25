"""PROTOTYPE, throwaway: builds prototypes/keymap-drawing.html from ../sweep-layouts.

Key positions come from each Board's vial.json (a KLE layout whose labels are "row,col"); the keys on each
layer come from the .vil.  Everything is embedded so the HTML opens by double-click.

    python3 prototypes/keymap_drawing_build.py
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
SL = os.path.join(HERE, "..", "..", "sweep-layouts")

BOARDS = [
    ("Ferris Sweep · QWERTY", "sweep", "ferris_sweep_qwerty.vil", ["Base", "Sym", "Nav", "Stack", "Num"], "us"),
    ("Ferris Sweep · free-range", "sweep", "ferris_sweep_freerange.vil", ["Base", "Sym", "Nav", "Stack", "Num"], "us"),
    ("Keychron Q3 Max · QWERTY", "q3_max", "q3_max.vil", ["Base", "Plain", "Sym", "Nav", "Stack", "Fn"], "uk"),
]

def kle(rows):
    """KLE rows -> [{row, col, x, y, w, h, r, rx, ry}]."""
    out, cur = [], dict(x=0.0, y=0.0, w=1.0, h=1.0, r=0.0, rx=0.0, ry=0.0)
    for row in rows:
        for it in row:
            if isinstance(it, dict):
                if "r" in it: cur["r"] = it["r"]
                if "rx" in it: cur["rx"] = it["rx"]; cur["x"], cur["y"] = cur["rx"], cur["ry"]
                if "ry" in it: cur["ry"] = it["ry"]; cur["x"], cur["y"] = cur["rx"], cur["ry"]
                cur["x"] += it.get("x", 0); cur["y"] += it.get("y", 0)
                if "w" in it: cur["w"] = it["w"]
                if "h" in it: cur["h"] = it["h"]
                continue
            lines = it.split("\n")
            label = lines[0]
            if "," in label and not (len(lines) > 9 and lines[9] == "e"):     # line 10 "e" marks an encoder
                r, c = (int(v) for v in label.split(","))
                out.append(dict(row=r, col=c, x=cur["x"], y=cur["y"], w=cur["w"], h=cur["h"],
                                r=cur["r"], rx=cur["rx"], ry=cur["ry"]))
            cur["x"] += cur["w"]; cur["w"] = cur["h"] = 1.0
        cur["y"] += 1; cur["x"] = cur["rx"]
    return out

def board(title, key, vil, names, host):
    vj = json.load(open(os.path.join(SL, "boards", key, "vial.json")))
    v = json.load(open(os.path.join(SL, "vil", vil)))
    layers = [l for l in v["layout"] if any(k not in ("KC_TRNS", -1, "KC_NO") for r in l for k in r)]
    combos = [c for c in v["combo"] if c[0] != "KC_NO"]
    macros = [" ".join(a[1] if a[0] == "text" else a[1].replace("KC_", "") for a in m if a[0] in ("text", "tap"))
              for m in v["macro"]]
    return dict(title=title, keys=kle(vj["layouts"]["keymap"]), layers=layers, names=names[:len(layers)],
                combos=combos, macros=macros, host=host, freerange="freerange" in vil)

data = [board(*b) for b in BOARDS]
tpl = open(os.path.join(HERE, "keymap-drawing.template.html")).read()
open(os.path.join(HERE, "keymap-drawing.html"), "w").write(tpl.replace("/*DATA*/null", json.dumps(data)))
print("wrote prototypes/keymap-drawing.html:", ", ".join(f"{d['title']} ({len(d['keys'])} keys, {len(d['layers'])} layers)" for d in data))
