# PROTOTYPE data generator for issue #80: real keyboard pictures from the test fixtures.
import json, random, sys
from pathlib import Path
from typokiller.drawing import draw_layers, Heat
from typokiller.keymap import keymap_letters

root = Path("tests/fixtures")
random.seed(4)
out = []
for board, vial_dir, vils, names in [
    ("Sweep", "sweep", ["ferris_sweep_freerange.vil", "ferris_sweep_qwerty.vil"], ["Base", "Sym", "Nav", "Num"]),
    ("Cheapino", "cheapino", ["cheapino.vil"], []),
    ("Q4", "q4", ["q4.vil"], []),
]:
    vial = (root / "boards" / vial_dir / "vial.json").read_text()
    for vil_name in vils:
        vil = (root / "vil" / vil_name).read_text()
        letters = keymap_letters(vil, vial)
        chars = "abcdefghijklmnopqrstuvwxyz,.;'/-"
        costs = {c: random.uniform(140, 420) for c in chars}
        weakest = sorted(costs, key=lambda c: -costs[c])[:10]
        pairs = [random.choice("etaoinshr") + random.choice("etaoinshrdl") for _ in range(10)]
        heat = Heat(costs, {c: 60 for c in chars}, (150.0, 400.0, 50.0))
        plain = draw_layers(vil, vial, names)
        hot = draw_layers(vil, vial, names, heat, pairs)
        out.append({
            "board": board, "layout": letters, "file": vil_name,
            "layers": [n for n, _ in plain], "plain": [s for _, s in plain], "heat": [s for _, s in hot],
            "chars": [[c, round(costs[c]), random.randint(25, 400)] for c in weakest],
            "pairs": [[p, random.randint(250, 600), random.randint(20, 150)] for p in pairs],
        })
sys.stdout.write("const DATA = " + json.dumps(out) + ";\n")
