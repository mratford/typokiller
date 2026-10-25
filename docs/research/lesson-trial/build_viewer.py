"""Build a side-by-side HTML viewer of the trial Lessons and their check results.

    python3 build_viewer.py OUT.html
"""

import json
import re
import sys

from trial import LANGS, LESSONS, MODELS, RESULTS, TOPICS, lesson_path, read_jsonl

NAMES = {
    "anthropic/claude-haiku-5.5": "Haiku 5.5",
    "anthropic/claude-sonnet-5.5": "Sonnet 5.5",
    "openai/gpt-6-luna": "GPT-6 Luna",
    "openai/gpt-6.1-sol": "GPT-6.1 Sol",
}


def tidy(error):
    error = re.sub(r"\S*/src/lesson\.gleam", "lesson.gleam", error)
    return re.sub(r"\S*/example\.py", "example.py", error).strip()


def main(out):
    gens = {(g["model"], g["lang"], g["topic"]): g for g in read_jsonl(RESULTS / "generations.jsonl")}
    checks = {(c["model"], c["lang"], c["topic"]): c for c in read_jsonl(RESULTS / "checks.jsonl")}
    lessons = []
    for m in MODELS:
        for l in LANGS:
            for t in TOPICS:
                g, c = gens[(m, l, t)], checks[(m, l, t)]
                lessons.append({
                    "model": m, "lang": l, "topic": t,
                    "text": lesson_path(m, l, t).read_text(),
                    "words": len(lesson_path(m, l, t).read_text().split()),
                    "cost": g["cost_usd"], "seconds": g["seconds"], "tokens": g["completion_tokens"],
                    "blocks": [
                        {"compiles": b["compiles"], "runs": b["runs"],
                         "error": "" if b["runs"] else tidy(b["error"])}
                        for b in c["blocks"]
                    ],
                })
    data = {
        "models": [{"id": m, "name": NAMES[m]} for m in MODELS],
        "langs": {k: v[0] for k, v in LANGS.items()},
        "topics": TOPICS,
        "lessons": lessons,
    }
    template = (LESSONS.parent / "viewer.template.html").read_text()
    payload = json.dumps(data).replace("</", "<\\/")
    open(out, "w").write(template.replace("/*DATA*/null", payload))


if __name__ == "__main__":
    main(sys.argv[1])
