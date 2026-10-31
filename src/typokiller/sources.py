import csv
import os
import re
import sqlite3
import subprocess
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
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


def keep_passages(
    normalised: list[tuple[str, int]], max_dropped: float, min_length: int, limit: int, cut: Callable[[str, int, int], list[str]]
) -> tuple[list[str], int]:
    """The Passages made from texts, and how many texts were skipped. Each text comes with how many
    characters normalising dropped from it. A text is skipped when normalising dropped more than
    `max_dropped` of its characters or left fewer than `min_length`. This is checked on the whole
    text. Each text that is kept is cut into pieces of at most about `limit` characters by `cut`."""
    texts = [text for text, dropped in normalised if kept(text, dropped, max_dropped, min_length)]
    return [piece for text in texts for piece in cut(text, limit, min_length)], len(normalised) - len(texts)


def kept(text: str, dropped: int, max_dropped: float, min_length: int) -> bool:
    """Whether a normalised text is kept as a Passage, by the rule of `keep_passages`."""
    return dropped <= max_dropped * (len(text) + dropped) and len(text) >= min_length


def prose_passages(
    paragraphs: list[str], max_dropped: float, min_length: int, prose_chars: int
) -> tuple[list[str], int]:
    """The Passages made from prose paragraphs with `ascii-v1`, and how many paragraphs were skipped.
    Line breaks inside a paragraph become spaces. A long paragraph is cut by `cut_prose`."""
    return keep_passages([prose(p) for p in paragraphs], max_dropped, min_length, prose_chars, cut_prose)


def prose(paragraph: str) -> tuple[str, int]:
    """A prose paragraph normalised with `ascii-v1`, with its line breaks made spaces, and how
    many characters were dropped."""
    return ascii_v1(" ".join(paragraph.split()))


# Words that end with a full stop but do not end a sentence. `cut_prose` also skips a single capital letter.
ABBREVIATIONS = ("Mr", "Mrs", "Ms", "Dr", "St", "Prof", "Capt", "Col", "Gen", "Lieut", "Rev", "vs", "etc", "Jr", "Sr", "Mt")

# The space where `cut_prose` ends a sentence. Python can only look back over text of one fixed
# length, so each word has its own test. The test for `.`, `!` or `?` is first, so the other
# tests run only after a likely sentence end.
SENTENCE_END = re.compile(
    r"(?<=[.!?])" + "".join(rf"(?<!\b{word}\.)" for word in (*ABBREVIATIONS, "[A-Z]")) + r" (?=[A-Z\"'])"
)


def cut_prose(text: str, limit: int, min_length: int) -> list[str]:
    """A normalised paragraph cut into pieces of at most `limit` characters, each with as many
    whole sentences as fit. A sentence ends at `.`, `!` or `?` followed by a space and a capital
    letter or a quote. A full stop after one of the `ABBREVIATIONS` or after a single capital
    letter, such as "Mr." or "J.", does not end a sentence. A sentence over `limit` starts a new
    piece, and is cut at the last semicolon, colon or comma that keeps the piece within `limit`,
    else at the last space that does. A last piece shorter than `min_length` is joined to the
    piece before it. The text is the pieces with a space between them."""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in SENTENCE_END.split(text):
        if current and len(current) + 1 + len(sentence) <= limit:
            current += " " + sentence
            continue
        if current:
            pieces.append(current)
        while len(sentence) > limit:
            window = sentence[: limit + 1]
            ends = [m.end() for m in re.finditer(r"[;:,](?= )", window)]
            end = ends[-1] if ends else window.rfind(" ")
            if end <= 0:  # a word over the limit
                break
            pieces.append(sentence[:end])
            sentence = sentence[end:].lstrip()
        current = sentence
    pieces.append(current)
    if len(pieces) > 1 and len(pieces[-1]) < min_length:
        pieces[-2:] = [" ".join(pieces[-2:])]
    return pieces


def code_passages(text: str, max_dropped: float, min_length: int, code_chars: int) -> tuple[list[str], int]:
    """The Passages made from one code file with `ascii-v1`: one for each function, and how many were skipped.

    The file is tidied with `tidy_code` and split into `top_level_parts`. A function is skipped by
    the same rule as a prose paragraph, and a long one is cut by `cut_code`.
    """
    parts = [ascii_v1(f) for f in top_level_parts(tidy_code(text))]
    return keep_passages(parts, max_dropped, min_length, code_chars, cut_code)


def top_level_parts(code: str) -> list[str]:
    """Tidied code split at blank lines before unindented lines: the functions, classes and
    other top-level parts, in written order. Runs of blank lines become one blank line."""
    return [part for part in re.split(r"\n\n(?=\S)", squeeze(code)) if part]


def squeeze(code: str) -> str:
    """Code without blank lines at its ends, and with each run of blank lines made one blank line."""
    return re.sub(r"\n\n+", "\n\n", code.strip("\n"))


def cut_code(code: str, limit: int, min_length: int) -> list[str]:
    """Tidied code cut into pieces. Each piece starts at the line after the one before it, and
    ends at the first of these that exists:

    1. The last blank line that ends the piece at no more than `limit` plus a quarter of it, and
       at no less than half of `limit`. The blank line is not in any piece.
    2. The last line break that ends the piece at no more than `limit`, after a line that is
       not blank.
    3. The end of the first line, so a single line over `limit` stays whole.

    The rest of the code is the last piece when it is within a quarter more than `limit`, so that
    no piece is cut again. A last piece shorter than `min_length` is joined to the piece before it.
    """
    lines = code.split("\n")
    # The length of lines[start:end] joined is totals[end] - totals[start] - 1.
    totals = [0]
    for line in lines:
        totals.append(totals[-1] + len(line) + 1)

    def size(start: int, end: int) -> int:
        return totals[end] - totals[start] - 1

    longest = limit * 5 / 4  # the most for a piece that ends at a blank line, and for the last piece
    ranges = []
    start = 0
    while start < len(lines):
        if size(start, len(lines)) <= longest:
            end = len(lines)
        elif blanks := [e for e in range(start + 1, len(lines)) if not lines[e] and limit / 2 <= size(start, e) <= longest]:
            end = blanks[-1]
        else:
            fits = (e for e in range(start + 1, len(lines)) if lines[e - 1] and size(start, e) <= limit)
            end = max(fits, default=start + 1)
        ranges.append((start, end))
        start = end + 1 if end < len(lines) and not lines[end] else end
    if len(ranges) > 1 and size(*ranges[-1]) < min_length:
        ranges[-2:] = [(ranges[-2][0], ranges[-1][1])]
    return ["\n".join(lines[start:end]) for start, end in ranges]


def cut_stored_passages(db: sqlite3.Connection, prose_chars: int, code_chars: int, min_length: int):
    """Cuts the stored Passages that are over their limit, in every Source. A Source's text is
    not cut again, only its Passages. A Passage that is cut is marked `replaced` and stays,
    because Attempts point to it. Its pieces are new Passages with its heading and `code` value.
    The Passages that are not replaced get new consecutive `ord` numbers, the Source's `total`
    counts them, and its bookmark moves to the Passage that holds the start of the Passage it
    was at. A Source with no Passage to cut is not changed, so a second run does nothing."""
    with db:
        for source, bookmark in db.execute("SELECT id, bookmark FROM source").fetchall():
            old = db.execute(
                "SELECT id, ord, text, normaliser, heading, code FROM passage WHERE source = ? AND NOT replaced ORDER BY ord",
                (source,),
            ).fetchall()
            pieces = [
                cut_code(text, code_chars, min_length) if code else cut_prose(text, prose_chars, min_length)
                for _, _, text, _, _, code in old
            ]
            if all(len(parts) == 1 for parts in pieces):
                continue
            new_ords: dict[int, int] = {}  # each old ord, with the new ord of its Passage or first piece
            total = 0
            for (id, old_ord, _, normaliser, heading, code), parts in zip(old, pieces):
                new_ords[old_ord] = total
                if len(parts) == 1:
                    db.execute("UPDATE passage SET ord = ? WHERE id = ?", (total, id))
                else:
                    db.execute("UPDATE passage SET replaced = 1 WHERE id = ?", (id,))
                    db.executemany(
                        "INSERT INTO passage (source, ord, text, normaliser, heading, code) VALUES (?, ?, ?, ?, ?, ?)",
                        [(source, total + i, part, normaliser, heading, code) for i, part in enumerate(parts)],
                    )
                total += len(parts)
            db.execute(
                "UPDATE source SET total = ?, bookmark = ? WHERE id = ?", (total, new_ords.get(bookmark, total), source)
            )


def tidy_code(text: str) -> str:
    """Code with tabs made 4 columns, and each line with its indentation, each run of whitespace
    after it made one space, and no trailing whitespace."""
    return "\n".join(re.sub(r"(?<=\S)\s+", " ", line).rstrip() for line in text.expandtabs(4).splitlines())


# The start of a line that opens or closes a fenced code block. The text after it is ignored.
FENCE_MARK = r"[ \t]*(?:```|~~~)"
FENCE = re.compile(FENCE_MARK)
# A whole fenced code block, by the same rule as `lesson_passages`; group 1 is its code, with a
# newline after each line. A block with no closing fence is not one: `lesson_passages` drops it.
CODE_BLOCK = re.compile(rf"^{FENCE_MARK}.*\n((?:.*\n)*?){FENCE_MARK}.*$", re.M)


def lesson_passages(
    markdown: str, max_dropped: float, min_length: int, prose_chars: int, code_chars: int
) -> tuple[list[tuple[str | None, str, bool]], int]:
    """The Passages of a Lesson written in Markdown, each with the heading above it and whether
    it is code, and how many paragraphs and code blocks were skipped (spec §9).

    Headings are not typed. Each paragraph and each list item is a prose Passage, with inline
    markup removed: code spans keep their text without the backticks, and bold, italics and
    links keep their words. A table is dropped, and counts as skipped. Each fenced code block is
    a code Passage, tidied like a code file with runs of blank lines made one. Each paragraph
    and block is normalised with `ascii-v1` and skipped by the rule of `keep_passages`. One that
    is kept is cut by `cut_prose` or `cut_code`, and each piece keeps the heading.
    """
    heading = None
    normalised: list[tuple[str | None, str, int, bool]] = []  # (heading, text, characters dropped, code)
    paragraph: list[str] = []
    code: list[str] | None = None  # the lines of the open code block

    def end_paragraph():
        if paragraph and paragraph[0].lstrip().startswith("|"):
            normalised.append((heading, "", 0, False))  # a table: never long enough to keep
        elif paragraph:
            normalised.append((heading, *prose(plain(" ".join(paragraph))), False))
        paragraph.clear()

    for line in markdown.splitlines():
        if code is not None:
            if FENCE.match(line):
                normalised.append((heading, *code_block("\n".join(code)), True))
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
    parts = []
    skipped = 0
    for under, text, dropped, is_code in normalised:  # `under` is the heading above it
        limit, cut = (code_chars, cut_code) if is_code else (prose_chars, cut_prose)
        pieces, n = keep_passages([(text, dropped)], max_dropped, min_length, limit, cut)
        parts += [(under, piece, is_code) for piece in pieces]
        skipped += n
    return parts, skipped


def plain(text: str) -> str:
    """Markdown text without inline markup. Code spans keep their text exactly."""
    pieces = re.split(r"`([^`]*)`", text)  # odd pieces are the text of code spans
    for i in range(0, len(pieces), 2):
        words = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", pieces[i])  # links and images
        words = re.sub(r"(\*\*|__)(.+?)\1", r"\2", words)  # bold
        pieces[i] = re.sub(r"(?<!\w)([*_])(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", words)  # italics
    return "".join(pieces)


def code_block(code: str) -> tuple[str, int]:
    """A code block tidied like a code file, with runs of blank lines made one, and normalised
    with `ascii-v1`; and how many characters were dropped."""
    return ascii_v1(squeeze(tidy_code(code)))


def git(*args: str) -> str:
    """Runs git and gives its output. git uses the Mac's own credentials. GIT_TERMINAL_PROMPT=0
    stops it from asking for a password that nobody would see."""
    env = os.environ | {"GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, env=env).stdout


def repo_text(files: Sequence[tuple[str | Path, str]]) -> str:
    """The text of a Source made from the files of a repo: each file's text after a `--- path` line."""
    return "".join(f"--- {path}\n{text}" for path, text in files)


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
