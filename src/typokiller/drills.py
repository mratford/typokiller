"""Drills: Passages that typokiller makes around chosen Targets (spec §7).

A Drill generator is a named, swappable step (spec §12). It picks the Targets and the
words of a Drill. The settings file names the one in use, and each Drill records it.
"""

import random
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

import polars as pl

from typokiller.analysis import seen_counts, weakness

# Common English words. They join the pool while the Sources give fewer than SMALL_POOL
# different words, so the first Drills have enough words to choose from.
WORDS = """
the of and to a in is it you that he was for on are with as I his they be at one have this
from or had by not word but what some we can out other were all there when up use your how
said an each she which do their time if will way about many then them write would like so
these her long make thing see him two has look more day could go come did number sound no
most people my over know water than call first who may down side been now find any new work
part take get place made live where after back little only round man year came show every
good me give our under name very through just form sentence great think say help low line
differ turn cause much mean before move right boy old too same tell does set three want air
well also play small end put home read hand port large spell add even land here must big
high such follow act why ask men change went light kind off need house picture try us again
animal point mother world near build self earth father head stand own page should country
found answer school grow study still learn plant cover food sun four between state keep eye
never last let thought city tree cross farm hard start might story saw far sea draw left late
run don't while press close night real life few north open seem together next white children
begin got walk example ease paper group always music those both mark often letter until mile
river car feet care second book carry took science eat room friend began idea fish mountain
stop once base hear horse cut sure watch colour face wood main enough plain girl usual young
ready above ever red list though feel talk bird soon body dog family direct pose leave song
measure door product black short numeral class wind question happen complete ship area half
rock order fire south problem piece told knew pass since top whole king space heard best hour
better true during hundred five remember step early hold west ground interest reach fast verb
sing listen six table travel less morning ten simple several vowel toward war lay against
pattern slow centre love person money serve appear road map rain rule govern pull cold notice
voice unit power town fine certain fly fall lead cry dark machine note wait plan figure star
box noun field rest correct able pound done beauty drive stood contain front teach week final
gave green oh quick develop ocean warm free minute strong special mind behind clear tail
produce fact street inch multiply nothing course stay wheel full force blue object decide
surface deep moon island foot system busy test record boat common gold possible plane stead
dry wonder laugh thousand ago ran check game shape equate hot miss brought heat snow tire
bring yes distant fill east paint language among
""".split()
SMALL_POOL = 1000


class Drill(NamedTuple):
    # Each Target: unit (a character or pair), reason ("weak" or "under-measured"), cost
    # (ms, from the Weakness model; None when the model does not rank it) and seen (times).
    targets: list[dict[str, Any]]
    text: str


def pool(db: sqlite3.Connection, unlocked: set[str] | None) -> Counter[str]:
    """The words a Drill can use, with how often each is in the Sources: the text of every
    Source's Passages split at whitespace, plus WORDS while there are fewer than SMALL_POOL
    different words. With `unlocked`, only words made of those characters."""
    words = Counter(w for (text,) in db.execute("SELECT text FROM passage WHERE source IS NOT NULL") for w in text.split())
    if len(words) < SMALL_POOL:
        words.update(WORDS)
    if unlocked is not None:
        words = Counter({w: n for w, n in words.items() if set(w) <= unlocked})
    return words


def unit_counts(words: Counter[str]) -> Counter[str]:
    """How often each character and pair is in the pool, with a space after each word."""
    counts = Counter()
    for word, n in words.items():
        spaced = f" {word} "
        for unit in [*spaced[1:], *(spaced[i : i + 2] for i in range(len(spaced) - 1))]:
            counts[unit] += n
    return counts


def density_v1(
    db: sqlite3.Connection,
    board: str | None,
    letter_layout: str | None,
    settings: dict[str, Any],
    unlocked: set[str] | None,
) -> Drill:
    """The Targets and text of a Drill. `settings` holds every table of the settings file.

    Targets: first the `weak` units (of the [drills] settings) that the Weakness model ranks
    highest. Then the most common units of the pool that were seen fewer than `min_seen`
    times on this Board and Letter layout, in the Weakness model's `weeks`. These are the
    under-measured units, and there are `under_measured` of them. With no ranking yet, all
    the Targets are under-measured. With too few under-measured units, more weak units fill
    in. A Target must be a unit that the pool's words hold.

    Text: `words` words of the pool. Word i holds Target i modulo the number of Targets. It
    is picked at random, with a weight of its number of Targets per character. So short
    words with many Targets come up most."""
    drills = settings["drills"]
    words = pool(db, unlocked)
    counts = unit_counts(words)
    since = datetime.now(UTC) - timedelta(weeks=settings["weakness"]["weeks"])
    counted = seen_counts(db, board, letter_layout, since)
    seen = dict(zip(counted["unit"], counted["seen"]))
    ranked = weakness(db, board, letter_layout, settings["weakness"]).filter(pl.col("unit").is_in(list(counts)))
    cost = dict(zip(ranked["unit"], ranked["cost"]))
    weak = [{"unit": u, "reason": "weak", "cost": cost[u], "seen": seen[u]} for u in ranked["unit"]]
    under_measured = [
        {"unit": u, "reason": "under-measured", "cost": cost.get(u), "seen": seen.get(u, 0)}
        for u in sorted(counts, key=lambda u: (-counts[u], u))
        if seen.get(u, 0) < drills["min_seen"]
    ]
    n = drills["weak"]
    targets = weak[:n]
    chosen = {t["unit"] for t in targets}
    rest = [t for t in under_measured + weak[n:] if t["unit"] not in chosen]
    targets += rest[: n + drills["under_measured"] - len(targets)]
    target_units = [t["unit"] for t in targets]

    def density(word: str) -> float:
        return sum(f" {word} ".count(u) for u in target_units) / len(word)

    weights = {w: density(w) for w in words}
    holding = {u: [w for w in words if u in f" {w} "] for u in target_units}  # the pool's words that hold each Target
    text = []
    for i in range(drills["words"]):
        candidates = holding[target_units[i % len(target_units)]]
        text += random.choices(candidates, [weights[w] for w in candidates])
    return Drill(targets, " ".join(text))


# The Drill generators, by name (spec §12). The settings file names the one in use. Each
# takes (db, board, letter_layout, the settings, the Unlocked keys or None for every key).
# #30 adds "introduction", for the Drills that follow an unlock.
DRILL_GENERATORS = {"density-v1": density_v1}
