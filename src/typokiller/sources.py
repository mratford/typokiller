import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

# Characters that NFKD does not turn into ASCII, and the ASCII to type instead.
ASCII_V1 = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "‟": '"', "–": "-", "—": "-"})


def ascii_v1(text: str) -> tuple[str, int]:
    """The `ascii-v1` normaliser: the text with only printable ASCII and newlines, and how many characters it dropped.

    Curly quotes become straight, dashes become `-` and accents are stripped. NFKD
    turns `…` into `...`. Anything else outside printable ASCII is dropped, because
    those are the characters that the Australian keyboard input setting in macOS types.
    """
    text = "".join(c for c in unicodedata.normalize("NFKD", text.translate(ASCII_V1)) if not unicodedata.combining(c))
    kept = "".join(c for c in text if " " <= c <= "~" or c == "\n")
    return kept, len(text) - len(kept)


def gutenberg_paragraphs(text: str) -> list[str]:
    """The paragraphs between the START and END lines of a Project Gutenberg plain text book."""
    body = re.split(r"^\*\*\* *(?:START|END) OF .*$", text, flags=re.M)[1]
    return [p for p in re.split(r"\n\s*\n", body) if p.strip()]


def article_paragraphs(text: str) -> list[str]:
    """The paragraphs of a web page's text as the browser's `innerText` gives it: each block of the
    page is on its own line, so each line is a paragraph. A line that is there more than once, such
    as a menu at the top and the bottom of the page, is dropped."""
    lines = [line.strip() for line in text.splitlines()]
    counts = Counter(lines)
    return [line for line in lines if line and counts[line] == 1]


def keep_passages(normalised: list[tuple[str, int]], max_dropped: float, min_length: int) -> tuple[list[str], int]:
    """The texts that are kept as Passages, and how many were skipped. Each text comes with how many
    characters normalising dropped from it. A text is skipped when normalising dropped more than
    `max_dropped` of its characters or left fewer than `min_length`.
    """
    passages = [
        text for text, dropped in normalised if dropped <= max_dropped * (len(text) + dropped) and len(text) >= min_length
    ]
    return passages, len(normalised) - len(passages)


def prose_passages(paragraphs: list[str], max_dropped: float, min_length: int) -> tuple[list[str], int]:
    """The Passages made from prose paragraphs with `ascii-v1`, and how many paragraphs were skipped.
    Line breaks inside a paragraph become spaces."""
    return keep_passages([ascii_v1(" ".join(p.split())) for p in paragraphs], max_dropped, min_length)


def code_passages(text: str, max_dropped: float, min_length: int) -> tuple[list[str], int]:
    """The Passages made from one code file with `ascii-v1`: one for each function, and how many were skipped.

    The file is split at blank lines. A part that starts indented belongs to the function
    before it, which keeps one blank line there. Tabs become 4 columns. Each line keeps its
    indentation, and the rest of the line has each run of whitespace made one space and no
    trailing whitespace. A function is skipped by the same rule as a prose paragraph.
    """
    lines = [re.sub(r"(?<=\S)\s+", " ", line).rstrip() for line in text.expandtabs(4).splitlines()]
    functions: list[str] = []
    for part in re.split(r"\n\n+", "\n".join(lines)):
        if functions and part.startswith(" "):
            functions[-1] += "\n\n" + part
        elif part:
            functions.append(part)
    return keep_passages([ascii_v1(f) for f in functions], max_dropped, min_length)


def search_catalogue(catalogue: Path, query: str) -> list[dict]:
    """Up to 9 text books in Project Gutenberg's `pg_catalog.csv` whose title and
    authors hold every word of the query, or the book with a pasted number or URL.
    A book newer than the catalogue file is found by its number, with no title."""
    number = re.fullmatch(r"\s*(\d+)\s*", query) or re.search(r"gutenberg\.org/\D*(\d+)", query)
    words = query.lower().split()
    found = []
    with catalogue.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            title = " ".join(row["Title"].split())
            text = f"{title} {row['Authors']}".lower()
            if row["Type"] == "Text" and (row["Text#"] == number[1] if number else all(w in text for w in words)):
                found.append({"number": int(row["Text#"]), "title": title, "authors": row["Authors"]})
                if len(found) == 9:
                    break
    if number and not found:
        found = [{"number": int(number[1]), "title": f"Gutenberg book {number[1]}", "authors": ""}]
    return found
