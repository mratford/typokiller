"""Lesson bake-off: which models write Gleam and Python Lessons whose code compiles and runs?

Throwaway harness for issue #11 (map #1). Standard library only.

    python3 trial.py generate --env-file ../../../.env   # call OpenRouter, save lessons/
    python3 trial.py check --gleam-template DIR          # compile and run every code block
    python3 trial.py report                              # print the summary tables

Every step is resumable: existing lessons and checks are skipped.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
LESSONS = HERE / "lessons"
RESULTS = HERE / "results"

MODELS = [
    "anthropic/claude-haiku-5.5",
    "anthropic/claude-sonnet-5.5",
    "openai/gpt-6-luna",
    "openai/gpt-6.1-sol",
]

TOPICS = {
    "pattern-matching": "pattern matching",
    "error-handling": "error handling",
    "lists-and-recursion": "working with lists and recursion",
    "custom-types": "defining and using your own data types",
    "string-processing": "string processing",
    "concurrency": "concurrency",
}

LANGS = {
    "gleam": (
        "Gleam",
        "Gleam 1.18 on the Erlang target. Each example is a complete module with its own "
        "imports and a `pub fn main() -> Nil`. Use only gleam_stdlib 1.0, gleam_erlang 1.3 "
        "and gleam_otp 1.3.",
    ),
    "python": (
        "Python",
        "Python 3.14. Each example is a complete script using only the standard library.",
    ),
}

SYSTEM = """You write Lessons for a touch-typing trainer. The learner reads and types the whole \
Lesson, code included, so it should be accurate and idiomatic.

Write about 1,200 to 1,500 words of Markdown: short explanations with 3 to 5 code examples. \
Every code example is a fenced block tagged with the language. {rules} Every example must \
compile and run on its own, without input, and finish within a few seconds. Use plain ASCII."""

USER = "Write a {lang} Lesson on {topic}."

MAX_TOKENS = 8000
REASONING_EFFORT = "low"
FENCE = re.compile(r"^```[ \t]*(\w+)[^\n]*\n(.*?)^```[ \t]*$", re.M | re.S)


def lesson_path(model, lang, topic):
    return LESSONS / model.replace("/", "__") / f"{lang}-{topic}.md"


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def load_key(env_file):
    if key := os.environ.get("OPENROUTER_API_KEY"):
        return key
    for line in Path(env_file).read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "OPENROUTER_API_KEY":
            return value.strip().strip("\"'")
    sys.exit("OPENROUTER_API_KEY not found")


def call(key, model, lang, topic):
    name, rules = LANGS[lang]
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM.format(rules=rules)},
            {"role": "user", "content": USER.format(lang=name, topic=TOPICS[topic])},
        ],
        "max_tokens": MAX_TOKENS,
        "reasoning": {"effort": REASONING_EFFORT},
        "usage": {"include": True},
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    start = time.monotonic()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.load(resp)
    seconds = time.monotonic() - start
    choice = data["choices"][0]
    usage = data.get("usage", {})
    return choice["message"]["content"] or "", {
        "model": model,
        "lang": lang,
        "topic": topic,
        "seconds": round(seconds, 1),
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "cost_usd": usage.get("cost"),
        "provider": data.get("provider"),
    }


def generate(args):
    key = load_key(args.env_file)
    jobs = [
        (m, l, t)
        for m in MODELS
        for l in LANGS
        for t in TOPICS
        if not lesson_path(m, l, t).exists()
    ]
    print(f"{len(jobs)} Lessons to generate")

    def run(job):
        try:
            text, record = call(key, *job)
        except Exception as e:  # keep going; a rerun retries
            print(f"FAIL {job}: {e}")
            return
        path = lesson_path(*job)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        append_jsonl(RESULTS / "generations.jsonl", record)
        print(f"ok {job} {record['completion_tokens']} tok ${record['cost_usd']}")

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(run, jobs))


def check_python(code):
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "example.py"
        src.write_text(code)
        r = subprocess.run(
            [sys.executable, "-I", "-m", "py_compile", str(src)], capture_output=True, text=True
        )
        if r.returncode:
            return False, False, r.stderr[-2000:]
        try:
            r = subprocess.run(
                [sys.executable, "-I", str(src)],
                cwd=d,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return True, False, "timeout"
        return True, r.returncode == 0, r.stderr[-2000:]


def check_gleam(code, project):
    src = project / "src"
    for f in src.glob("*.gleam"):
        f.unlink()
    (src / "lesson.gleam").write_text(code)
    r = subprocess.run(
        ["gleam", "build", "--no-print-progress"], cwd=project, capture_output=True, text=True
    )
    if r.returncode:
        return False, False, (r.stdout + r.stderr)[-2000:]
    try:
        r = subprocess.run(
            ["gleam", "run", "--no-print-progress", "-m", "lesson"],
            cwd=project,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return True, False, "timeout"
    return True, r.returncode == 0, (r.stdout + r.stderr)[-2000:]


def check(args):
    done = {(c["model"], c["lang"], c["topic"]) for c in read_jsonl(RESULTS / "checks.jsonl")}
    jobs = [
        (m, l, t)
        for m in MODELS
        for l in LANGS
        for t in TOPICS
        if lesson_path(m, l, t).exists() and (m, l, t) not in done
    ]
    print(f"{len(jobs)} Lessons to check")
    workdir = Path(tempfile.mkdtemp(prefix="lessoncheck-"))
    projects = []
    for i in range(args.workers):
        p = workdir / f"p{i}"
        shutil.copytree(args.gleam_template, p)
        shutil.rmtree(p / "test", ignore_errors=True)
        projects.append(p)

    def run(i):
        project = projects[i]
        for job in jobs[i :: args.workers]:
            text = lesson_path(*job).read_text()
            blocks = [code for tag, code in FENCE.findall(text) if tag.lower() == job[1]]
            other = [tag for tag, _ in FENCE.findall(text) if tag.lower() != job[1]]
            results = []
            for n, code in enumerate(blocks):
                if job[1] == "gleam":
                    compiles, runs, err = check_gleam(code, project)
                else:
                    compiles, runs, err = check_python(code)
                results.append({"block": n, "compiles": compiles, "runs": runs, "error": err})
            m, l, t = job
            append_jsonl(
                RESULTS / "checks.jsonl",
                {"model": m, "lang": l, "topic": t, "other_fences": other, "blocks": results},
            )
            passed = sum(b["compiles"] for b in results)
            print(f"{job}: {passed}/{len(results)} compile")

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(run, range(args.workers)))
    shutil.rmtree(workdir)


def report(args):
    gens = {(g["model"], g["lang"], g["topic"]): g for g in read_jsonl(RESULTS / "generations.jsonl")}
    checks = read_jsonl(RESULTS / "checks.jsonl")
    rows = {}
    for c in checks:
        r = rows.setdefault((c["model"], c["lang"]), dict(
            lessons=0, blocks=0, compiles=0, runs=0, clean=0, tok=0, reason=0, cost=0.0, secs=0.0))
        g = gens.get((c["model"], c["lang"], c["topic"]), {})
        b = c["blocks"]
        r["lessons"] += 1
        r["blocks"] += len(b)
        r["compiles"] += sum(x["compiles"] for x in b)
        r["runs"] += sum(x["runs"] for x in b)
        r["clean"] += bool(b) and all(x["runs"] for x in b)
        r["tok"] += g.get("completion_tokens") or 0
        r["reason"] += g.get("reasoning_tokens") or 0
        r["cost"] += g.get("cost_usd") or 0
        r["secs"] += g.get("seconds") or 0
    print("| Model | Lang | Lessons | Blocks | Compile | Run | Lessons all-pass "
          "| Mean out tok | Mean reasoning tok | Mean cost | Mean secs |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for (m, l), r in sorted(rows.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        n = r["lessons"]
        print(
            f"| {m} | {l} | {n} | {r['blocks']} "
            f"| {r['compiles']}/{r['blocks']} ({r['compiles'] / max(r['blocks'], 1):.0%}) "
            f"| {r['runs']}/{r['blocks']} ({r['runs'] / max(r['blocks'], 1):.0%}) "
            f"| {r['clean']}/{n} | {r['tok'] / n:.0f} | {r['reason'] / n:.0f} "
            f"| ${r['cost'] / n:.4f} | {r['secs'] / n:.0f} |"
        )
    total = sum(g.get("cost_usd") or 0 for g in gens.values())
    print(f"\nTotal spend: ${total:.3f} over {len(gens)} generations")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    g = sub.add_parser("generate")
    g.add_argument("--env-file", default=".env")
    g.add_argument("--workers", type=int, default=6)
    g.set_defaults(fn=generate)
    c = sub.add_parser("check")
    c.add_argument("--gleam-template", required=True)
    c.add_argument("--workers", type=int, default=4)
    c.set_defaults(fn=check)
    r = sub.add_parser("report")
    r.set_defaults(fn=report)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
