# String Processing

Strings hold text. Python's string type is `str`, and it provides tools for cleaning, searching, splitting, combining, and displaying that text. These operations appear in everyday programs: preparing names, reading simple records, checking dates, and building reports.

A string is immutable: its contents cannot be changed in place. Methods such as `strip` and `replace` return new strings. If you want to keep a result, assign it to a variable. String literals can use single or double quotes. Use triple quotes for text that spans multiple lines.

## Clean and inspect text

Whitespace includes spaces, tabs, and line breaks. The `strip` method removes whitespace from both ends of a string. Its related methods, `lstrip` and `rstrip`, remove it from just one end. They do not remove whitespace from the middle.

Text methods can be chained. In the example, `strip` runs first, then `lower`, then `replace`. Each method returns a string for the next method to use. The original value in `message` remains unchanged.

Use `in` to test whether one string occurs inside another. Use `len` to count the number of characters in a string. Indexing and slicing are covered in the same example: an index selects one character, while a slice selects a range. Indexes start at zero, and a slice's end index is excluded.

```python
message = "  Python makes text work!  "

clean = message.strip().lower().replace("text", "strings")

print(clean)
print("work" in clean)
print(len(clean))
print(clean[0])
print(clean[0:6])
print(clean[-4:])
```

The slice `clean[0:6]` starts at index zero and stops before index six. Leaving out the start or end uses the beginning or end of the string. A negative index counts from the end, so `clean[-4:]` selects the final four characters.

Remember that `len` counts string elements, not bytes. Python strings can contain characters from many writing systems. Some displayed symbols are made from multiple Unicode code points, so a visible symbol does not always correspond to exactly one element counted by `len`.

## Split and join

`split` breaks a string into a list of smaller strings. With no argument, it splits on runs of whitespace and ignores whitespace at the ends. With an explicit separator, it splits wherever that exact separator occurs. The two forms behave differently, so choose the one that matches the data.

`splitlines` is useful when a string contains several lines. To divide a simple key and value, `partition` returns a three-item tuple: the part before the first separator, the separator itself, and the part after it. Unlike splitting on every occurrence, `partition` leaves later separators in the value.

Here is a small configuration reader. It ignores blank lines and comments, then collects valid key-value pairs in a dictionary. The check for an empty separator makes malformed lines easy to detect.

```python
text = """
# Display settings
theme = dusk
font = mono
note = keep spaces = inside the value
"""

settings = {}

for line in text.splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue

    key, separator, value = line.partition("=")
    if not separator:
        print(f"Skipping malformed line: {line}")
        continue

    key = key.strip()
    value = value.strip()
    if key:
        settings[key] = value

for key, value in settings.items():
    print(f"{key}: {value}")
```

The line is stripped before it is examined, and the key and value are stripped separately after partitioning. That preserves the extra equals sign inside the `note` value. The dictionary keeps the most recently assigned value for a repeated key. This is a useful pattern for small, controlled text formats, but real configuration files may need a dedicated parser.

To combine pieces, use `join`. It is called on the separator, and it joins an iterable of strings. For example, `", ".join(words)` places a comma and a space between each item. It does not add a separator before the first item or after the last one.

## Search with regular expressions

For simple checks, prefer direct string methods such as `startswith`, `endswith`, `find`, and `in`. When the pattern is more involved, the standard library's `re` module provides regular expressions. A pattern can describe a shape, such as four digits, a hyphen, two digits, another hyphen, and two digits.

A regular expression can recognize the shape of a date, but that does not prove the date exists. For instance, a pattern can match a month value of `19`. This example uses `fullmatch` to require that the entire string match the pattern, then uses `date.fromisoformat` to check calendar validity. The `re.ASCII` flag makes `\d` match ASCII digits only, which is helpful when the format specifically requires digits from `0` through `9`.

```python
import re
from datetime import date

date_pattern = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})",
    re.ASCII,
)

candidates = ["2024-02-29", "2023-02-29", "2024-13-01", "today"]

for candidate in candidates:
    match = date_pattern.fullmatch(candidate)
    if match is None:
        print(f"{candidate}: wrong format")
        continue

    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        print(f"{candidate}: invalid calendar date")
    else:
        print(f"{candidate}: valid ({parsed:%A})")
```

The named groups make individual portions of the match available as `match.group("year")`, for example. They are not needed in this script because the date parser handles the matched string directly, but named groups can be useful when a program needs to process parts separately. A raw string literal, written with an `r` prefix, is commonly used for regular expression patterns so backslashes are passed through as written.

For repeated matching inside a longer string, `finditer` yields match objects in order. For a single search, `search` finds the first match, while `fullmatch` checks the entire string. Use the narrowest operation that expresses the requirement; it makes the code easier to understand.

## Format and combine output

When you need to create a string from values, an f-string is often the clearest choice. Put an expression inside braces, and add a format specification after a colon. For example, `:>12` right-aligns a value in a field twelve characters wide. Formatting affects the resulting text; it does not change the original value.

Here, a list of records becomes a compact report. `join` combines the completed lines, while the f-string formats each name and count. The code uses `casefold` to compare names without relying on a particular capitalization. It is intended for caseless comparison, especially for Unicode text, and is more thorough than `lower` for this purpose.

```python
records = [
    ("Maple", 4),
    ("birch", 12),
    ("PINE", 7),
]

records.sort(key=lambda item: item[0].casefold())

lines = ["TREE      COUNT", "---------- -----"]
for name, count in records:
    lines.append(f"{name:<10} {count:>5}")

report = "\n".join(lines)
print(report)
```

The sort key tells Python to compare case-folded names while keeping the original spelling for display. The `:<10` specification left-aligns the name in a ten-character field, and `:>5` right-aligns the count in a five-character field. These widths are minimum widths: a longer value is not cut off.

Formatting is for presentation, not necessarily for saving data that another program must read. If fields contain separators or line breaks, simply joining them may create an ambiguous format. For structured interchange, consider a standard format such as JSON or CSV from the standard library rather than inventing escaping rules.

## A reliable workflow

When processing text, first decide what the input is allowed to contain. Then clean it, split or search it, validate the pieces, and finally format the result. Keep these steps visible instead of hiding many transformations in one expression. Clear intermediate names make it easier to find mistakes.

A few habits help prevent common errors:

- Check whether a method returns a new string; assign its result when needed.
- Distinguish whitespace splitting from splitting on an exact separator.
- Validate the complete value when extra characters would be invalid.
- Treat a matching pattern as a format check, not proof that the value is meaningful.
- Use `join` for combining many strings, and f-strings for readable display.

These tools work together. A program might strip a line, use `partition` to find a delimiter, validate the value with a regular expression or a dedicated parser, then use an f-string to report what happened. Practice each operation separately, and string-processing code becomes easier to read and type.