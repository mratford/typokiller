# String Processing in Python

Text is everywhere: log files, user input, configuration, CSV rows. Python's `str` type comes with a rich set of tools for slicing, searching, cleaning, and reshaping it. This lesson walks through the essentials, with four complete scripts you can type and run.

## Strings Are Immutable Sequences

A string is an ordered sequence of characters. You can index it, slice it, and loop over it, but you cannot change it in place. Every "modification" produces a new string.

```python
text = "  Hello, Typing World!  "

print(repr(text))
print(len(text))

# Indexing and slicing
clean = text.strip()
print(clean[0])        # first character
print(clean[-1])       # last character
print(clean[7:13])     # slice from index 7 up to (not including) 13
print(clean[::-1])     # reversed copy

# Common transformations return new strings
print(clean.upper())
print(clean.lower())
print(clean.replace("World", "Python"))
print(text)            # the original is unchanged
```

Slices use `start:stop:step`. Omitted parts default to the beginning, the end, and a step of 1. A step of `-1` walks backward, which is the idiomatic way to reverse a string.

Notice that `strip()` removes whitespace from both ends, while `lstrip()` and `rstrip()` handle one side each. Passing an argument, such as `strip("!")`, removes those specific characters instead.

## Splitting, Joining, and Searching

Two methods do most of the heavy lifting in text processing: `split()` breaks a string into a list, and `join()` glues a list back into a string.

`join()` is called on the separator, not on the list. That feels backward at first, but it means the method works on any iterable of strings.

For searching, use `in` for a simple membership test, `find()` when you need a position (it returns `-1` if nothing matches), and `startswith()` or `endswith()` for prefix and suffix checks.

```python
line = "error: disk full; code=28; host=alpha"

# Split on a separator
parts = line.split("; ")
print(parts)

# Split once, from the left
level, message = parts[0].split(": ", 1)
print(level, "->", message)

# Build a dictionary from key=value pairs
fields = {}
for part in parts[1:]:
    key, value = part.split("=")
    fields[key] = value
print(fields)

# Join with a different separator
print(" | ".join(parts))

# Searching
print("disk" in line)
print(line.find("code"))
print(line.find("missing"))
print(line.startswith("error"))
print(line.endswith("alpha"))
print(line.count(";"))
```

Calling `split()` with no arguments is special: it splits on any run of whitespace and discards empty pieces, which makes it ideal for tokenizing sentences. The optional second argument, as in `split(": ", 1)`, limits the number of splits.

## Formatting with f-strings

F-strings are the modern way to build strings from values. Put an expression inside braces, and optionally add a format specifier after a colon.

Useful specifiers include `:>10` to right-align in a field of width 10, `:<10` to left-align, `:^10` to center, `:.2f` for two decimal places, `:,` for thousands separators, and `:08.3f` for zero-padded numbers. Adding `=` after an expression, as in `{x=}`, prints both the expression and its value, which is handy for debugging.

```python
items = [
    ("Keyboard", 3, 49.99),
    ("Mouse", 10, 19.5),
    ("Monitor", 2, 1299.0),
    ("Cable", 125, 2.25),
]

header = f"{'Item':<12}{'Qty':>6}{'Price':>12}{'Total':>14}"
print(header)
print("-" * len(header))

grand_total = 0.0
for name, qty, price in items:
    total = qty * price
    grand_total += total
    print(f"{name:<12}{qty:>6}{price:>12,.2f}{total:>14,.2f}")

print("-" * len(header))
print(f"{'Grand total':<30}{grand_total:>14,.2f}")

ratio = 0.4375
print(f"Ratio as percent: {ratio:.1%}")
print(f"{grand_total=:.1f}")
```

Because the width and alignment are part of the format specifier, you can produce neat columns without any manual padding. Quotes inside an f-string expression must differ from the outer quotes in older Pythons, but Python 3.12 and later relax that rule. Mixing styles, as in `{'Item':<12}`, still reads clearly.

## Cleaning and Analyzing Text

Real-world text is messy. A typical pipeline lowercases everything, strips punctuation, splits into words, and counts them. The standard library helps here: `string.punctuation` lists punctuation characters, `str.translate()` with `str.maketrans()` deletes or swaps characters quickly, and `collections.Counter` tallies items.

```python
import string
from collections import Counter

text = """
Practice makes progress. Practice, patience, and rhythm:
that is how typing becomes automatic. Type slowly, type
accurately, and speed will follow!
"""

# Remove punctuation using a translation table
table = str.maketrans("", "", string.punctuation)
cleaned = text.translate(table).lower()

words = cleaned.split()
print(f"Total words: {len(words)}")
print(f"Unique words: {len(set(words))}")

counts = Counter(words)
for word, number in counts.most_common(3):
    print(f"{word:<10} {number}")

# Longest word, using a key function
longest = max(words, key=len)
print("Longest word:", longest)

# Capitalize each word for a title
title = " ".join(word.capitalize() for word in words[:4])
print(title)

# Character-level check: is it a palindrome?
def is_palindrome(s):
    letters = [c.lower() for c in s if c.isalnum()]
    return letters == letters[::-1]

print(is_palindrome("A man, a plan, a canal: Panama"))
print(is_palindrome("Typing trainer"))
```

`str.maketrans("", "", chars)` builds a table where the third argument lists characters to delete. Applying it with `translate()` is much faster than calling `replace()` repeatedly.

## Regular Expressions for Patterns

When simple methods are not enough, the `re` module matches patterns. Use raw strings (prefix `r`) so backslashes reach the regex engine untouched.

Key functions: `re.search()` finds the first match anywhere, `re.findall()` returns all matches, `re.sub()` replaces matches, and `re.compile()` prepares a pattern for reuse. Parentheses create groups, and `(?P<name>...)` gives a group a name.

```python
import re

log = """
2025-03-14 09:26:53 INFO  user=alice action=login
2025-03-14 09:27:10 ERROR user=bob action=upload size=2048
2025-03-14 09:30:02 INFO  user=carol action=logout
"""

pattern = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+)\s+"
    r"user=(?P<user>\w+)"
)

for match in pattern.finditer(log):
    info = match.groupdict()
    print(f"{info['level']:<6}{info['user']:<8}{info['time']}")

# Find every key=value pair
pairs = re.findall(r"(\w+)=(\w+)", log)
print(pairs[:3])

# Replace digits with a mask
masked = re.sub(r"\d", "#", "Card 1234-5678")
print(masked)

# Validate a simple identifier
for name in ["total_1", "1total", "ok"]:
    ok = re.fullmatch(r"[A-Za-z_]\w*", name) is not None
    print(name, ok)
```

`finditer()` yields match objects lazily, so it scales well to large inputs. `fullmatch()` requires the entire string to fit the pattern, which is safer for validation than `search()`.

## Quick Reference

- Slice with `s[start:stop:step]`; reverse with `s[::-1]`.
- Clean with `strip()`, `lower()`, `replace()`, and `translate()`.
- Break apart with `split()`; rebuild with `separator.join(items)`.
- Search with `in`, `find()`, `startswith()`, and `endswith()`.
- Format with f-strings and specifiers like `:>10`, `:.2f`, and `:,`.
- Reach for `re` only when plain string methods cannot express the pattern.

## Practice Ideas

Try modifying the scripts above. Count letter frequencies instead of words, parse a different log format, or build a function that wraps long text at a fixed width. Each exercise reinforces the same small toolkit, and the more you type these patterns, the more automatic they become.