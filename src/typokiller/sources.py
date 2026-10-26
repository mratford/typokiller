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
    passages = [text for text, dropped in normalised if kept(text, dropped, max_dropped, min_length)]
    return passages, len(normalised) - len(passages)


def kept(text: str, dropped: int, max_dropped: float, min_length: int) -> bool:
    """Whether a normalised text is kept as a Passage, by the rule of `keep_passages`."""
    return dropped <= max_dropped * (len(text) + dropped) and len(text) >= min_length


def prose_passages(paragraphs: list[str], max_dropped: float, min_length: int) -> tuple[list[str], int]:
    """The Passages made from prose paragraphs with `ascii-v1`, and how many paragraphs were skipped.
    Line breaks inside a paragraph become spaces."""
    return keep_passages([prose(p) for p in paragraphs], max_dropped, min_length)


def prose(paragraph: str) -> tuple[str, int]:
    """A prose paragraph normalised with `ascii-v1`, with its line breaks made spaces, and how
    many characters were dropped."""
    return ascii_v1(" ".join(paragraph.split()))


def code_passages(text: str, max_dropped: float, min_length: int) -> tuple[list[str], int]:
    """The Passages made from one code file with `ascii-v1`: one for each function, and how many were skipped.

    The file is tidied with `tidy_code` and split into `top_level_parts`. A function is skipped by
    the same rule as a prose paragraph.
    """
    return keep_passages([ascii_v1(f) for f in top_level_parts(tidy_code(text))], max_dropped, min_length)


def top_level_parts(code: str) -> list[str]:
    """Tidied code split at blank lines before unindented lines: the functions, classes and
    other top-level parts, in written order. Runs of blank lines become one blank line."""
    return [part for part in re.split(r"\n\n(?=\S)", re.sub(r"\n\n+", "\n\n", code.strip("\n"))) if part]


def tidy_code(text: str) -> str:
    """Code with tabs made 4 columns, and each line with its indentation, each run of whitespace
    after it made one space, and no trailing whitespace."""
    return "\n".join(re.sub(r"(?<=\S)\s+", " ", line).rstrip() for line in text.expandtabs(4).splitlines())


FENCE = re.compile(r"\s*(```|~~~)")


def lesson_passages(
    markdown: str, split_lines: int, max_dropped: float, min_length: int
) -> tuple[list[tuple[str | None, str]], int]:
    """The Passages of a Lesson written in Markdown, each with the heading above it, and how
    many paragraphs and code blocks were skipped (spec §9).

    Headings are not typed. Each paragraph and each list item is a prose Passage, with inline
    markup removed: code spans keep their text without the backticks, and bold, italics and
    links keep their words. A table is dropped, and counts as skipped. Each fenced code block is
    a code Passage, tidied like a code file with runs of blank lines made one. A block over
    `split_lines` lines is split at blank lines before unindented lines, with as many whole
    parts in each Passage as fit in `split_lines`. Then each Passage is normalised with
    `ascii-v1` and skipped by the rule of `keep_passages`.
    """
    heading = None
    normalised: list[tuple[str | None, str, int]] = []  # (heading, text, characters dropped)
    paragraph: list[str] = []
    code: list[str] | None = None  # the lines of the open code block

    def end_paragraph():
        if paragraph and paragraph[0].lstrip().startswith("|"):
            normalised.append((heading, "", 0))  # a table: never long enough to keep
        elif paragraph:
            normalised.append((heading, *prose(plain(" ".join(paragraph)))))
        paragraph.clear()

    for line in markdown.splitlines():
        if code is not None:
            if FENCE.match(line):
                normalised += [(heading, *ascii_v1(c)) for c in split_code(tidy_code("\n".join(code)), split_lines)]
                code = None
            else:
                code.append(line)
            continue
        if FENCE.match(line):
            end_paragraph()
            code = []
        elif not line.strip():
            end_paragraph()
        elif title := re.match(r"#+\s+(.*)", line):
            end_paragraph()
            heading = plain(title[1].strip("# "))
        elif item := re.match(r"\s*(?:[-*+]|\d+[.)])\s+(.*)", line):
            end_paragraph()
            paragraph.append(item[1])
        else:
            paragraph.append(line)
    end_paragraph()
    parts = [(h, text) for h, text, dropped in normalised if kept(text, dropped, max_dropped, min_length)]
    return parts, len(normalised) - len(parts)


def plain(text: str) -> str:
    """Markdown text without inline markup. Code spans keep their text exactly."""
    pieces = re.split(r"`([^`]*)`", text)  # odd pieces are the text of code spans
    for i in range(0, len(pieces), 2):
        words = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", pieces[i])  # links and images
        words = re.sub(r"(\*\*|__)(.+?)\1", r"\2", words)  # bold
        pieces[i] = re.sub(r"(?<!\w)([*_])(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", words)  # italics
    return "".join(pieces)


def split_code(code: str, split_lines: int) -> list[str]:
    """A tidied code block as `top_level_parts` put together, split as `lesson_passages` says."""
    parts = top_level_parts(code)
    if (whole := "\n\n".join(parts)).count("\n") < split_lines:
        return [whole]
    chunks: list[str] = []
    for part in parts:
        # The lines of the last chunk, a blank line and the lines of this part.
        if chunks and chunks[-1].count("\n") + 1 + 1 + part.count("\n") + 1 <= split_lines:
            chunks[-1] += "\n\n" + part
        else:
            chunks.append(part)
    return chunks


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
