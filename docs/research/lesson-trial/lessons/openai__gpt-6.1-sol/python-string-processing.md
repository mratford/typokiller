# String Processing in Python

String processing means turning text into something useful: cleaning a label, extracting a field, counting words, or reading a small table. Python provides string methods for everyday transformations, plus standard library modules for structured formats and pattern matching.

This lesson uses Python 3.14. Each example is a complete script that runs without input. As you type, notice the boundaries between steps: preserve the original text, normalize only what needs normalization, and validate assumptions before using the result.

## 1. Clean Text with String Methods

A Python string is an immutable sequence of Unicode characters. Immutable means that you cannot replace a character inside an existing string. Methods such as `strip()` and `replace()` return strings rather than changing the original.

Start with the smallest operation that expresses your intention:

- `strip()` removes whitespace from both ends.
- `split()` without an argument separates text on runs of whitespace.
- `join()` combines strings with a chosen separator.
- `casefold()` prepares text for caseless comparison.
- `replace()` substitutes literal substrings.

The first script cleans a short list of names. It collapses repeated whitespace while preserving each name's capitalization. It also detects duplicates without treating uppercase and lowercase letters as different.

```python
def clean_name(raw: str) -> str:
    return " ".join(raw.split())


def main() -> None:
    raw_names = [
        "  Ada   Lovelace ",
        "\tGrace Hopper\n",
        "ada lovelace",
        "  Katherine    Johnson  ",
        "   ",
    ]

    names: list[str] = []
    seen: set[str] = set()

    for raw in raw_names:
        name = clean_name(raw)
        if not name:
            continue

        key = name.casefold()
        if key in seen:
            continue

        seen.add(key)
        names.append(name)

    print("Clean names:")
    for number, name in enumerate(names, start=1):
        print(f"{number}. {name}")

    print(f"Original entries: {len(raw_names)}")
    print(f"Unique names: {len(names)}")


if __name__ == "__main__":
    main()
```

The expression `" ".join(raw.split())` is a useful normalization pattern. Calling `split()` without a separator ignores leading and trailing whitespace and treats consecutive whitespace characters as one boundary. Joining the resulting words inserts exactly one ordinary space between them.

This transformation is appropriate for these names, but it is not a universal cleanup rule. Repeated spaces can matter in source code, poetry, or fixed-width records. Normalize according to the meaning of your data, not merely its appearance.

The script keeps two representations: a display name and a comparison key. That separation avoids forcing lowercase text into the final output. The list preserves the first spelling encountered, while the set makes duplicate checks straightforward.

For caseless comparison, prefer `casefold()` over `lower()` when working with general Unicode text. Neither operation, however, decides every question about identity. Two similarly written names are not necessarily the same person.

## 2. Separate Fields and Validate Them

Many small text formats use a delimiter, such as an equals sign between a setting name and its value. Before choosing a parsing method, decide what should happen when the delimiter is missing or appears more than once.

Use `partition()` when you need the first occurrence of a separator. It always returns three strings: the part before the separator, the separator itself, and the remainder. If the separator is absent, the middle string is empty.

That fixed shape makes validation readable. Unlike an unrestricted `split("=")`, it also preserves additional equals signs inside a value.

```python
def parse_setting(line: str) -> tuple[str, str] | None:
    text = line.strip()

    if not text or text.startswith("#"):
        return None

    key, separator, value = text.partition("=")
    if not separator:
        raise ValueError("missing equals sign")

    key = key.strip()
    value = value.strip()

    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_"
    if not key or any(char not in allowed for char in key):
        raise ValueError("invalid setting name")

    return key, value


def main() -> None:
    lines = [
        "# Example settings",
        "user = ada",
        "token = part=another_part",
        "retries = 3",
        "broken setting",
        "Bad-Key = ignored",
    ]

    settings: dict[str, str] = {}

    for line_number, line in enumerate(lines, start=1):
        try:
            result = parse_setting(line)
        except ValueError as error:
            print(f"Line {line_number}: {error}")
            continue

        if result is not None:
            key, value = result
            settings[key] = value

    for key, value in settings.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
```

This parser defines a deliberately small format. Blank lines and full-line comments are ignored. Keys contain only lowercase ASCII letters, digits, and underscores. Values remain strings, including the value `"3"`.

Notice that `token` retains its internal equals sign. Also notice that the parser does not remove comments from the end of a value. A hash character might be legitimate data, so adding inline comments would require another explicit rule.

The dictionary gives repeated keys a last-value-wins policy. That may be useful for configuration overrides. If duplicates should be errors instead, check whether a key already exists before assigning its value.

Avoid using `strip()` to remove a specific prefix or suffix. Its argument describes a set of characters, not an exact substring. For exact removal, use `removeprefix()` or `removesuffix()`.

## 3. Extract Patterns with Regular Expressions

String methods work well for literal separators and simple transformations. Regular expressions become useful when the target has a recognizable shape rather than one fixed spelling.

Python's `re` module supports searching, matching, extracting, and replacing patterns. Use it when a pattern makes the rule clearer, not merely because it can compress several operations into one line.

The next script counts words. Its definition of a word is intentionally narrow: ASCII letters, optionally followed by groups consisting of an apostrophe and more letters. This keeps contractions together without treating punctuation as part of every token.

```python
import re
from collections import Counter


WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")


def main() -> None:
    text = (
        "Python makes text processing pleasant. "
        "Text needs rules, and rules need tests. "
        "Don't guess: test what Python extracts."
    )

    words = WORD_PATTERN.findall(text)
    counts = Counter(word.casefold() for word in words)

    print(f"Total words: {sum(counts.values())}")
    print(f"Distinct words: {len(counts)}")
    print("Most frequent:")

    ranked = sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0]),
    )

    for word, count in ranked[:6]:
        print(f"{word:<12} {count:>3}")

    assert WORD_PATTERN.findall("Don't stop.") == ["Don't", "stop"]
    assert WORD_PATTERN.findall("red-blue") == ["red", "blue"]


if __name__ == "__main__":
    main()
```

The raw string prefix, `r`, helps keep backslashes readable in regular expressions. This particular pattern does not need a backslash, but using raw strings consistently is a helpful habit.

The character class `[A-Za-z]` matches one ASCII letter. The plus sign requires one or more letters. The group `(?:...)` groups pattern elements without capturing a separate result, and the final star allows zero or more repetitions.

The assertions document two important choices: contractions stay together, while hyphens separate words. Digits and non-ASCII letters are excluded. For multilingual text, this is not a complete tokenizer.

Sorting by negative count puts larger counts first. The word itself provides an alphabetical tie-breaker, making the output predictable. The format specifiers align words and numbers without changing the stored values.

## 4. Use a Parser for Structured Text

A delimiter alone does not define a complete format. In CSV, commas inside quoted fields are data rather than separators. Splitting every line on commas would therefore corrupt valid records.

Use the standard library's `csv` module for CSV input and output. `io.StringIO` supplies an in-memory text stream, so this example needs no external file.

```python
import csv
import io
from decimal import Decimal


def main() -> None:
    source = (
        "item,quantity,price\n"
        '"Notebook, blue",2,3.50\n'
        "Pencil,5,0.40\n"
        "Folder,1,2.25\n"
    )

    reader = csv.DictReader(io.StringIO(source, newline=""))
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["item", "quantity", "total"])

    grand_total = Decimal("0")

    for row in reader:
        item = row["item"].strip()
        quantity = int(row["quantity"])
        price = Decimal(row["price"])

        if quantity < 0 or price < 0:
            raise ValueError("quantity and price must be nonnegative")

        total = quantity * price
        grand_total += total
        writer.writerow([item, quantity, f"{total:.2f}"])

    print(output.getvalue(), end="")
    print(f"Grand total: {grand_total:.2f}")


if __name__ == "__main__":
    main()
```

`DictReader` uses the header row as dictionary keys. The quoted notebook description remains one field, and the writer adds the necessary quoting when producing the result.

Conversion happens after parsing: quantities become integers, and prices become `Decimal` values. Constructing decimals directly from strings avoids introducing binary floating-point approximations into these prices.

This script assumes the required columns are present and numeric fields are valid. A production importer should also decide how to report missing columns, malformed rows, and failed conversions.

## Build a Small Processing Pipeline

Reliable string processing usually follows a simple order: identify the format, parse its structure, normalize selected fields, validate their values, and format the result.

Keep these stages distinct. Preserve meaningful text, make comparison rules explicit, and use a format-aware parser whenever quoting or escaping is involved. Clear rules make text transformations easier to type, test, and maintain.