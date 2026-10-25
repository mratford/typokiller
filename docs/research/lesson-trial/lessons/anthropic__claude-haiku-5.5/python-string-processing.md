# Lesson: String Processing in Python

A string is an immutable sequence of characters. You cannot change a string in place. Every method returns a new string, so you assign the result to a name when you want to keep it. Once you understand that, most string work comes down to three moves: slice, search, and rebuild.

## Indexing and Slicing

Each character has an index, starting at 0. Negative indexes count from the end, so `-1` is the last character. A slice `s[start:stop]` returns the characters from `start` up to, but not including, `stop`. A third value sets the step, and `s[::-1]` reverses a string.

The next example covers the most common methods: cleaning, case changes, searching, and replacing.

```python
text = "  Hello, String World!  "

clean = text.strip()          # remove leading and trailing whitespace
print(repr(clean))
print(len(clean))
print(clean[0], clean[-1])    # first and last characters
print(clean[7:13])            # slice: "String"
print(clean[::-1])            # reversed copy
print(clean.upper())
print(clean.lower())
print(clean.replace("World", "Python"))
print(clean.startswith("Hello"), clean.endswith("?"))
print(clean.find("World"))    # index of first match
print(clean.find("xyz"))      # -1 means not found
print("ab" * 3)
print("-".join(["a", "b", "c"]))
```

Notice that `clean` is still the original stripped text after `clean.upper()` runs. The method returned a new string, and nothing was stored. `find` returns `-1` when the text is absent, so check for that value rather than assuming a match.

## Splitting, Joining, and Counting Words

`split()` with no arguments breaks text on any run of whitespace and drops empty pieces, which makes it a good default for words. `join()` does the reverse: it glues a sequence of strings together using the string it is called on.

A common pattern is to normalize text first, keep only letters and spaces, and then split. The `collections.Counter` class counts how often each item appears.

```python
from collections import Counter

paragraph = """
  The quick brown fox jumps over the lazy dog.
  The dog sleeps; the fox runs!
"""

# Keep letters and whitespace; turn everything else into nothing.
kept = []
for ch in paragraph.lower():
    if ch.isalpha() or ch.isspace():
        kept.append(ch)

words = "".join(kept).split()
print(len(words), "words")

counts = Counter(words)
for word, n in counts.most_common(3):
    print(f"{word:<6}{n}")
```

The loop builds a list of characters and joins them once at the end. This is faster than repeatedly adding strings with `+=` on large inputs, because each `+=` creates a new string. `most_common(3)` returns the three most frequent words. When two words tie, they appear in the order they were first seen.

## Formatting with f-Strings

An f-string puts expressions inside braces. A format spec after a colon controls the output. `<` aligns left, `>` aligns right, `^` centers, `.2f` gives two decimal places, `,` adds thousands separators, and `%` shows a fraction as a percentage. Column layout is where these matter most.

```python
items = [("Apple", 1.5, 3), ("Banana", 0.25, 12), ("Cherry", 10.0, 1)]

print(f"{'Item':<10}{'Price':>8}{'Qty':>5}{'Total':>10}")
print("-" * 33)

grand = 0.0
for name, price, qty in items:
    total = price * qty
    grand += total
    print(f"{name:<10}{price:>8.2f}{qty:>5}{total:>10.2f}")

print("-" * 33)
print(f"{'Grand total':<23}{grand:>10.2f}")

print(f"{1234567:,}".replace(",", "_"))   # swap separators: 1_234_567
print(f"{0.4567:.1%}")                    # 45.7%
print(f"[{'center':^12}]")
```

Each row lines up because every field has a fixed width. When you build tables, set widths once in the format spec rather than padding with manual spaces. This keeps the code short and the columns correct even when the data changes.

## Translating Characters: A Caesar Cipher and a Palindrome Check

`str.maketrans` builds a translation table that maps characters to other characters, and `str.translate` applies it in one pass. This is faster and clearer than looping over characters yourself. The example below uses it for a Caesar cipher, which shifts each letter by a fixed amount. It also checks palindromes by normalizing case and ignoring punctuation.

```python
import string

def caesar(text, shift):
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    rotated_lower = lower[shift:] + lower[:shift]
    rotated_upper = upper[shift:] + upper[:shift]
    table = str.maketrans(lower + upper, rotated_lower + rotated_upper)
    return text.translate(table)

def is_palindrome(text):
    # casefold() is a stronger form of lower() for case-insensitive comparison.
    letters = [c.casefold() for c in text if c.isalnum()]
    return letters == letters[::-1]

secret = caesar("Meet me at Noon!", 3)
print(secret)                  # Phhw ph dw Qrrq!
print(caesar(secret, -3))      # Meet me at Noon!

for phrase in ["A man, a plan, a canal: Panama", "Python"]:
    print(repr(phrase), is_palindrome(phrase))
```

The cipher works because `translate` leaves characters that are not in the table unchanged. That is why the space and the exclamation mark survive. The palindrome check builds a clean list of letters and compares it with its reverse, so the function ignores case, spaces, and punctuation.

## Key Points to Remember

- Strings are immutable. Methods return new strings, so assign results.
- Use `strip`, `split`, and `join` for most cleaning and tokenizing tasks.
- Build large strings from a list and join once.
- Check `find` results against `-1`.
- Put format specs inside f-strings to align and round output.
- Use `str.maketrans` with `translate` for character-by-character substitution.

## Practice

Type each example by hand, then change one thing at a time. Try a different Caesar shift, count letters instead of words, or add a column to the price table. Typing the code yourself is the fastest way to build the habits this lesson describes.