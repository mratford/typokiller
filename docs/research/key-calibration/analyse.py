"""Summarise the calibration logs for ticket #12 (Cheapino, QWERTY keymap).

    python3 analyse.py logs/cheapino-*.json
"""

import json, statistics, sys

MODTAP = {"KeyZ": "z", "KeyX": "x", "KeyC": "c", "KeyV": "v", "KeyM": "m", "Comma": ",", "Period": ".", "Quote": "'"}
LAYERTAP = {"Space", "Escape", "Tab"}
COMBO = {"KeyJ", "KeyK", "KeyL"}
MODS = {"ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft", "AltRight", "MetaLeft", "MetaRight"}
SKIP = {"macros", "combos", "repeat"}  # firmware- or OS-generated, looked at by hand


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def classify(ev, prev):
    if ev["code"] in MODS: return None
    if prev and prev["type"] == "keydown" and prev["code"].startswith("Shift") and ev["t"] - prev["t"] < 3: return "shifted keycode"
    if ev["code"] in MODTAP and ev["key"] == MODTAP[ev["code"]]: return "mod-tap"
    if ev["code"] in LAYERTAP: return "layer-tap"
    if ev["code"] in COMBO: return "combo key"
    if ev["code"].startswith("Key"): return "plain"
    return None


for path in sys.argv[1:]:
    d = json.load(open(path))
    keys = [e for e in d["events"] if e["type"] in ("keydown", "keyup")]
    print(f"\n=== {path}: {d['browser']}, {len(keys)} key events")

    # Dwell per key class: first non-repeat keydown to its keyup, paired by code.
    dwell, down, gaps_after_tap = {}, {}, []
    for i, e in enumerate(keys):
        if e["step"] in SKIP or e["repeat"]: continue
        if e["type"] == "keydown":
            down[e["code"]] = (e, classify(e, keys[i - 1] if i else None))
        elif e["code"] in down:
            d0, cls = down.pop(e["code"])
            if cls: dwell.setdefault(cls, []).append(e["t"] - d0["t"])
            # Gap from a tapped tap-hold key's (late) down+up to the next keydown.
            if cls in ("mod-tap", "layer-tap") and e["t"] - d0["t"] < 2:
                nxt = next((k for k in keys[i + 1:] if k["type"] == "keydown"), None)
                if nxt and nxt["step"] == e["step"]: gaps_after_tap.append(nxt["t"] - e["t"])
    print(f"{'class':<16}{'n':>5}{'p10':>8}{'median':>8}{'p90':>8}{'<2 ms':>8}")
    for cls, xs in sorted(dwell.items()):
        print(f"{cls:<16}{len(xs):>5}{pct(xs, .1):>8.1f}{statistics.median(xs):>8.1f}{pct(xs, .9):>8.1f}{sum(x < 2 for x in xs) / len(xs):>8.0%}")
    if gaps_after_tap:
        print(f"next keydown after a collapsed tap-hold tap: n={len(gaps_after_tap)}, "
              f"<2 ms: {sum(g < 2 for g in gaps_after_tap)}, median {statistics.median(gaps_after_tap):.1f} ms")

    # Clock: resolution and handler lag.
    ts = [e["t"] for e in keys]
    frac = sum(abs(t - round(t)) > 1e-6 for t in ts) / len(ts)
    diffs = sorted({round(b - a, 3) for a, b in zip(ts, ts[1:]) if b > a})
    lag = [e["now"] - e["t"] for e in keys]
    print(f"timestamps with a fractional ms: {frac:.0%}; smallest positive gap {diffs[0]} ms")
    print(f"handler lag (now - timeStamp): median {statistics.median(lag):.1f}, p95 {pct(lag, .95):.1f}, max {max(lag):.1f} ms")
    reps = [e for e in keys if e["repeat"]]
    if reps:
        rgaps = [b["t"] - a["t"] for a, b in zip(reps, reps[1:]) if a["code"] == b["code"] and b["t"] - a["t"] < 100]
        print(f"auto-repeat keydowns: {len(reps)}, spacing median {statistics.median(rgaps):.1f} ms")
