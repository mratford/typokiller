"""The symbol docs (#49): four code Sources taken from the Python and Gleam documentation.

The repos are cloned at run time and only the database keeps their text, so nothing from
the docs goes into git.
"""

import ast
import random
import re
import tempfile
import textwrap
import warnings
from collections.abc import Callable
from itertools import dropwhile
from pathlib import Path

from typokiller.sources import code_parts, git, kept, repo_text

CPYTHON = "https://github.com/python/cpython.git"
TOUR = "https://github.com/gleam-lang/language-tour.git"
STDLIB = "https://github.com/gleam-lang/stdlib.git"


def clone_docs(folder: Path, python_branch: str):
    """Clones the doc repos into `folder` as `cpython`, `tour` and `stdlib`. CPython is large,
    so its clone is shallow and sparse: only the files of `Doc/tutorial` and `Doc/library`
    are downloaded."""
    cpython = str(folder / "cpython")
    git("clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", "--branch", python_branch, CPYTHON, cpython)
    git("-C", cpython, "sparse-checkout", "set", "Doc/tutorial", "Doc/library")
    git("clone", "-q", "--depth", "1", TOUR, str(folder / "tour"))
    git("clone", "-q", "--depth", "1", STDLIB, str(folder / "stdlib"))


# A Source as (title, text, Passages), where each Passage is (heading, text).
DocSource = tuple[str, str, list[tuple[str, str]]]


def symbol_docs(python_branch: str, split_lines: int, max_dropped: float, min_length: int) -> list[DocSource]:
    """The four symbol doc Sources, from the repos that `clone_docs` puts in a temporary folder.
    The tutorial and the tour are in doc order; the library and the stdlib are shuffled once by file."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        clone_docs(folder, python_branch)
        doc = folder / "cpython/Doc"
        tutorial = re.findall(r"^\s+(\S+\.rst)$", (doc / "tutorial/index.rst").read_text(), re.M)  # its toctree
        library = sorted((doc / "library").glob("*.rst"))
        stdlib = sorted((folder / "stdlib/src/gleam").glob("**/*.gleam"))
        random.shuffle(library)
        random.shuffle(stdlib)
        found = [
            (f"Python {python_branch} tutorial", [doc / "tutorial" / name for name in tutorial], python_blocks),
            (f"Python {python_branch} library", library, python_blocks),
            ("Gleam tour", sorted((folder / "tour/src/content").glob("chapter*/lesson*/code.gleam")), tour_block),
            ("Gleam stdlib", stdlib, stdlib_blocks),
        ]
        return [
            doc_source(title, folder, files, blocks, split_lines, max_dropped, min_length) for title, files, blocks in found
        ]


def doc_source(
    title: str,
    folder: Path,
    files: list[Path],
    blocks: Callable[[Path, str], list[tuple[str, str]]],
    split_lines: int,
    max_dropped: float,
    min_length: int,
) -> DocSource:
    """A Source made of the code blocks that `blocks` finds in each of `files`, with their
    headings. Its text is like a code repo's. Each block is a code Passage, split and skipped
    like a Lesson's code block."""
    texts = [(path.relative_to(folder), path.read_text()) for path in files]
    passages = []
    for path, text in texts:
        for heading, code in blocks(path, text):
            parts = code_parts(code, split_lines)
            passages += [(heading, part) for part, dropped in parts if kept(part, dropped, max_dropped, min_length)]
    return title, repo_text(texts), passages


# The line under an rst section title.
UNDERLINE = re.compile(r"([=\-~^\"'*+#`:.<>_])\1+\s*")
# The first line of what a Gleam doc comment documents; group 1 is its name.
DOCUMENTED = re.compile(r"^\s*(?:pub\s+)?(?:opaque\s+)?(?:fn|type|const)\s+(\w+)", re.M)
# The directives whose content is a code block.
CODE_DIRECTIVE = re.compile(r"\s*\.\. (?:code-block|doctest|testcode)::")


def python_blocks(path: Path, rst: str) -> list[tuple[str, str]]:
    """The Python code blocks of an rst file, each with the section title it is under.

    A block is the content of a `::` literal block or of a `code-block`, `doctest` or `testcode`
    directive, or a paragraph that starts with `>>>`. The `>>> ` and `... ` prompts are removed;
    in a block with prompts, a line without one is output and is dropped. A block is kept only
    when `ast.parse` accepts it, which drops shell commands, grammar and sample output.
    """
    lines = rst.splitlines()
    blocks = []
    heading = path.stem
    i = 0
    while i < len(lines):
        line = lines[i]
        indent = len(line) - len(line.lstrip())
        if (
            line.strip()
            and not indent
            and i + 1 < len(lines)
            and UNDERLINE.fullmatch(lines[i + 1])
            and len(lines[i + 1].rstrip()) >= len(line.rstrip())
        ):
            heading = rst_plain(line.strip())
            i += 2
            continue
        if line.lstrip().startswith(">>>"):
            end = next((j for j in range(i, len(lines)) if not lines[j].strip()), len(lines))
            body = lines[i:end]
        elif CODE_DIRECTIVE.match(line) or (line.rstrip().endswith("::") and not line.lstrip().startswith("..")):
            end = i + 1
            while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) > indent):
                end += 1
            body = list(dropwhile(lambda option: option.lstrip().startswith(":"), lines[i + 1 : end]))
        else:
            i += 1
            continue
        code = without_prompts(textwrap.dedent("\n".join(body)))
        if code.strip() and parses(code):
            blocks.append((heading, code))
        i = end
    return blocks


def rst_plain(title: str) -> str:
    """An rst title without roles and inline literals: ":mod:`!array` --- Arrays" is "array --- Arrays"."""
    title = re.sub(r":[\w:-]+:`[!~]?([^`<]*?)\s*(?:<[^`]*>)?`", r"\1", title)
    return re.sub(r"``(.*?)``", r"\1", title)


def without_prompts(code: str) -> str:
    """Code with its `>>> ` and `... ` prompts removed. When it has prompts, a line with none is output and is dropped."""
    lines = code.splitlines()
    if not any(line.startswith(">>>") for line in lines):
        return code
    return "\n".join(line[4:] for line in lines if line.startswith((">>> ", "... ")) or line in (">>>", "..."))


def parses(code: str) -> bool:
    """Whether `ast.parse` accepts the code. Its warnings, such as for an invalid escape, are not shown."""
    with warnings.catch_warnings(action="ignore"):
        try:
            ast.parse(code)
        except (SyntaxError, ValueError):
            return False
    return True


def tour_block(path: Path, code: str) -> list[tuple[str, str]]:
    """A Gleam tour lesson's `code.gleam`, whole, under the lesson's title: `lesson02_string_concat`
    is "String concat", as the tour names it."""
    return [(path.parent.name.split("_", 1)[1].replace("_", " ").capitalize(), code)]


def stdlib_blocks(path: Path, code: str) -> list[tuple[str, str]]:
    """The ```` ```gleam ```` fences in the `///` doc comments of a Gleam stdlib module, without the
    `/// ` prefix, each under the module and the name that the comment documents, such as `list.map`.
    Module comments (`////`) and other fences are not taken."""
    blocks = []
    for comment in re.finditer(r"(?:^[ \t]*///(?!/).*\n)+", code, re.M):
        name = DOCUMENTED.search(code, comment.end())
        text = re.sub(r"^[ \t]*/// ?", "", comment[0], flags=re.M)
        for block in re.findall(r"^```gleam\n((?:.*\n)*?)```", text, re.M):
            blocks.append((f"{path.stem}.{name[1]}" if name else path.stem, block))
    return blocks
