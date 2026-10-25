import csv
import re
import unicodedata
from pathlib import Path

# Characters that NFKD does not turn into ASCII, and the ASCII to type instead.
ASCII_V1 = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "‟": '"', "–": "-", "—": "-"})


def ascii_v1(text: str) -> tuple[str, int]:
    """The `ascii-v1` normaliser: the text with only printable ASCII, and how many characters it dropped.

    Curly quotes become straight, dashes become `-` and accents are stripped. NFKD
    turns `…` into `...`. Anything else outside printable ASCII is dropped, because
    those are the characters that the Australian keyboard input setting in macOS types.
    """
    text = "".join(c for c in unicodedata.normalize("NFKD", text.translate(ASCII_V1)) if not unicodedata.combining(c))
    kept = "".join(c for c in text if " " <= c <= "~")
    return kept, len(text) - len(kept)


def gutenberg_paragraphs(text: str) -> list[str]:
    """The paragraphs between the START and END lines of a Project Gutenberg plain text book."""
    body = re.split(r"^\*\*\* *(?:START|END) OF .*$", text, flags=re.M)[1]
    return [p for p in re.split(r"\n\s*\n", body) if p.strip()]


def prose_passages(paragraphs: list[str], max_dropped: float, min_length: int) -> tuple[list[str], int]:
    """The Passages made from prose paragraphs with `ascii-v1`, and how many paragraphs were skipped.

    Line breaks inside a paragraph become spaces. A paragraph is skipped when normalising dropped more
    than `max_dropped` of its characters or left fewer than `min_length`.
    """
    passages = []
    for paragraph in paragraphs:
        text, dropped = ascii_v1(" ".join(paragraph.split()))
        if dropped <= max_dropped * (len(text) + dropped) and len(text) >= min_length:
            passages.append(text)
    return passages, len(paragraphs) - len(passages)


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
