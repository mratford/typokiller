# PROTOTYPE data generator for issue #81: the Sweep free-range pictures, drawn by drawing.py.
import re
import json, sys
from typokiller.drawing import draw_layers
from typokiller.keymap import read_keymap
d = json.load(open('/Users/mike/src/keybr.com/packages/keybr-recording/fixtures/keyboards/initial.json'))
sweep = d['boards'][0]
fr = [k for k in sweep['keymaps'] if k['letterLayout'] == 'free-range'][0]
vil, vial = fr['vil'], sweep['vial']
names = ["Base", "Sym", "Nav", "Stack", "Num"]
layers = draw_layers(vil, vial, names)
keys = {c: {"layer": ks[0].layer, "key": ks[0].key} for c, ks in read_keymap(vil).keys.items()}
# keycode of each key on each layer, to map the browser's `code` to the drawn key
v = json.loads(vil)
codes = {}
for r, row in enumerate(v['layout'][0]):
    for c, k in enumerate(row):
        m = re.search(r'KC_([A-Z0-9])\b|KC_(SPC|COMM|DOT|SLSH|SCLN|QUOT|MINS)\b', str(k))
        if m:
            name = m.group(1) or m.group(2)
            code = {'SPC':'Space','COMM':'Comma','DOT':'Period','SLSH':'Slash','SCLN':'Semicolon','QUOT':'Quote','MINS':'Minus'}.get(name) or (('Digit' if name.isdigit() else 'Key') + name)
            codes.setdefault(code, f"{r},{c}")
json.dump({"names": [n for n, _ in layers], "layers": [s for _, s in layers], "keys": keys, "codes": codes}, sys.stdout)
