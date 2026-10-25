# Lesson: String Processing in Gleam

Strings are everywhere in real programs: user input, log lines, CSV files, and text for display. This lesson covers the core tools in the `gleam/string` module and shows how to combine them with `gleam/list` and `gleam/int`.

## Strings are immutable

Gleam strings never change in place. Every function in `gleam/string` takes a string and returns a new one. This is why you will often see chains of transformations joined by the pipe operator `|>`:

```gleam
"  hello  "
|> string.trim
|> string.uppercase
```

The pipe passes the result of each step as the first argument of the next. Read it top to bottom as a sequence of steps.

## Basic operations

Here are the functions you will use most often:

- `string.length(s)` counts graphemes (user-visible characters), not bytes.
- `string.trim(s)` removes whitespace from both ends.
- `string.uppercase(s)` and `string.lowercase(s)` change case.
- `string.contains(s, sub)` tells you whether `sub` appears in `s`.
- `string.replace(s, each, with)` replaces every occurrence.
- `string.split(s, on)` breaks a string into a `List(String)`.
- `string.join(parts, with)` does the reverse, gluing a list back together.

Here is a complete program that uses several of them:

```gleam
import gleam/int
import gleam/io
import gleam/string

pub fn main() -> Nil {
  let raw = "   Hello, Gleam World!   "
  let trimmed = string.trim(raw)

  io.println("trimmed: " <> trimmed)
  io.println("length: " <> int.to_string(string.length(trimmed)))
  io.println("upper: " <> string.uppercase(trimmed))
  io.println("has Gleam: " <> bool_to_text(string.contains(trimmed, "Gleam")))

  let swapped = string.replace(trimmed, "World", "Learner")
  io.println("replaced: " <> swapped)

  let words = string.split(trimmed, " ")
  io.println("word count: " <> int.to_string(list_length(words)))
  io.println("rejoined: " <> string.join(words, "_"))
}

fn bool_to_text(value: Bool) -> String {
  case value {
    True -> "yes"
    False -> "no"
  }
}

fn list_length(items: List(String)) -> Int {
  case items {
    [] -> 0
    [_, ..rest] -> 1 + list_length(rest)
  }
}
```

Notice that `string.length` counts graphemes. A grapheme is what a reader perceives as one character, even if it is built from several code points. That makes `length` safe for text containing accented letters or emoji, where byte counts would mislead you.

`string.split` on a single space is simple, but it produces empty strings when there are repeated spaces. You will handle that in the parsing example below.

## Slicing and graphemes

Gleam has no indexing syntax like `s[0]`. Instead, you slice with functions:

- `string.slice(s, at_index, length)` extracts a substring.
- `string.drop_start(s, up_to)` removes characters from the front.
- `string.drop_end(s, up_to)` removes characters from the back.
- `string.to_graphemes(s)` turns the string into a `List(String)` with one entry per character.

Because indexing is not built in, working with characters usually means converting to a list of graphemes and then using the `list` module:

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let word = "stressed"

  io.println("reversed: " <> string.reverse(word))
  io.println("first six: " <> string.slice(word, 0, 6))
  io.println("without first three: " <> string.drop_start(word, 3))

  let letters = string.to_graphemes(word)
  let vowels =
    list.filter(letters, fn(ch) { string.contains("aeiou", ch) })
  io.println("vowel count: " <> int.to_string(list.length(vowels)))
}
```

Converting to graphemes is the standard way to process text one character at a time. Once you have a `List(String)`, every function in `gleam/list` is available: `map`, `filter`, `fold`, and so on.

## Parsing text into values

Input data is usually text that needs to become numbers. `int.parse(s)` returns `Result(Int, Nil)`, so a bad value becomes `Error(Nil)` rather than a crash. The `list.filter_map` function is useful here: it applies a function that returns a `Result`, keeps the `Ok` values, and drops the `Error` values.

This program parses a messy comma-separated line:

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let line = "12, 7,x, 30 ,,5"

  let fields =
    string.split(line, ",")
    |> list.map(string.trim)
    |> list.filter(fn(field) { field != "" })

  let numbers = list.filter_map(fields, int.parse)
  let total = list.fold(numbers, 0, fn(acc, n) { acc + n })
  let rejected = list.length(fields) - list.length(numbers)

  io.println("fields: " <> int.to_string(list.length(fields)))
  io.println("parsed: " <> int.to_string(list.length(numbers)))
  io.println("rejected: " <> int.to_string(rejected))
  io.println("total: " <> int.to_string(total))
}
```

The steps are:

1. Split on commas, which gives `["12", " 7", "x", " 30 ", "", "5"]`.
2. Trim each field.
3. Drop empty fields.
4. Parse each remaining field, keeping only the successes.
5. Fold the numbers into a sum.

This pattern (split, clean, filter, parse, reduce) covers most real-world parsing. Handling bad input as data, rather than as an exception, keeps the program predictable.

## Normalizing and checking text

Comparing text often requires normalizing it first. A palindrome check, for example, should ignore case, spaces, and punctuation. Build a small normalizer from the tools above:

```gleam
import gleam/io
import gleam/list
import gleam/string

fn normalize(text: String) -> String {
  text
  |> string.lowercase
  |> string.to_graphemes
  |> list.filter(is_letter)
  |> string.concat
}

fn is_letter(ch: String) -> Bool {
  string.contains("abcdefghijklmnopqrstuvwxyz", ch)
}

fn is_palindrome(text: String) -> Bool {
  let cleaned = normalize(text)
  cleaned == string.reverse(cleaned)
}

pub fn main() -> Nil {
  let samples = [
    "A man, a plan, a canal: Panama",
    "Gleam",
    "Was it a car or a cat I saw?",
  ]

  list.each(samples, fn(sample) {
    let verdict = case is_palindrome(sample) {
      True -> "palindrome"
      False -> "not a palindrome"
    }
    io.println(sample <> " -> " <> verdict)
  })
}
```

`string.concat` joins a `List(String)` with no separator, which is exactly what the normalizer needs. Because `normalize` is a plain function, you can test it, reuse it, or swap in a different rule for what counts as a letter.

## Building formatted output

Real programs often print tables and reports. Two tools help: `string.pad_end` pads a string to a fixed width, and `string.repeat` builds a string by repeating another.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let scores = [#("ada", 9), #("grace", 14), #("linus", 6)]

  io.println(string.pad_end("name", 8, " ") <> "score")
  io.println(string.repeat("-", 14))

  list.each(scores, fn(entry) {
    let #(name, score) = entry
    let bar = string.repeat("#", score)
    io.println(
      string.pad_end(name, 8, " ") <> string.pad_end(int.to_string(score), 6, " ") <> bar,
    )
  })
}
```

Padding columns to a fixed width is what makes the output line up, and `string.repeat` makes simple bar charts with no loops.

## Key points

- Strings are immutable. Every operation returns a new string, so chain them with `|>`.
- `string.length` and `string.reverse` work on graphemes, which keeps them correct for non-ASCII text.
- Gleam has no `s[i]` indexing. Use `string.slice`, `string.drop_start`, or `string.to_graphemes` plus `list` functions.
- `int.parse` returns a `Result`. Combine `list.filter_map` with it to parse messy input without crashing.
- Normalize text before comparing it, and keep normalization in its own function.
- Use `string.pad_end` and `string.repeat` to format aligned output.

## Exercise

Write a program that takes the sentence `"the quick brown fox jumps over the lazy dog"`, splits it into words, and prints each word's length alongside the word, padded to a fixed width. Then print the longest word. Use only the functions covered in this lesson.