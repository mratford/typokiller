# String Processing in Gleam

Strings in Gleam are immutable UTF-8 binaries. Every function that "changes" a string returns a new one. The `gleam/string` module in the standard library covers most everyday work, and the `<>` operator joins two strings. This lesson covers inspecting and transforming strings, splitting and parsing them, matching on their structure, and building larger ones efficiently.

## 1. The Basics

Most string functions take the string as their first argument, which makes them pipe-friendly. Here are the common ones:

```gleam
import gleam/int
import gleam/io
import gleam/string

pub fn main() -> Nil {
  let text = "  Gleam is Fun  "
  let clean = string.trim(text)

  io.println("[" <> clean <> "]")
  io.println("length: " <> int.to_string(string.length(clean)))
  io.println(string.uppercase(clean))
  io.println(string.lowercase(clean))
  io.println(string.reverse(clean))

  io.println("contains is: " <> string.inspect(string.contains(clean, "is")))
  io.println("starts: " <> string.inspect(string.starts_with(clean, "Gleam")))
  io.println("ends: " <> string.inspect(string.ends_with(clean, "Fun")))

  io.println(string.replace(clean, "Fun", "Great"))
  io.println(string.slice(clean, 0, 5))
  io.println(string.repeat("ab", 3))
  io.println(string.capitalise("hello"))

  let greeting = "Hello, " <> "World" <> "!"
  io.println(greeting)
}
```

Some notes on this code:

- `string.trim` removes whitespace from both ends of a string.
- `string.length` counts graphemes, meaning user-perceived characters, not bytes.
- `string.slice(string, at_index, length)` takes a substring. Out-of-range indexes do not crash, they just give a shorter or empty result.
- `string.inspect` turns any value into a readable string. It is handy for printing booleans, lists and results.
- `string.replace` replaces every occurrence of the pattern.

## 2. Splitting, Joining and Parsing

Real input is rarely clean. A typical workflow is to split text into pieces, clean up each piece, and convert it into something typed. `string.split` breaks a string on a separator and returns a list. `string.join` does the reverse. `string.split_once` splits on only the first separator and returns a `Result`, which is ideal for `key=value` lines.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/result
import gleam/string

fn parse_pair(line: String) -> Result(#(String, Int), Nil) {
  use #(key, value) <- result.try(string.split_once(line, "="))
  use number <- result.try(int.parse(string.trim(value)))
  Ok(#(string.trim(key), number))
}

fn count_words(sentence: String) -> Int {
  sentence
  |> string.split(" ")
  |> list.filter(fn(word) { word != "" })
  |> list.length
}

pub fn main() -> Nil {
  let csv = "red,green,blue"
  let colours = string.split(csv, ",")
  io.println(string.inspect(colours))
  io.println(string.join(colours, " | "))

  let sentence = "the  quick brown   fox"
  io.println("words: " <> int.to_string(count_words(sentence)))

  let lines = string.split("a=1\nb = 22\nbad\nc=x", "\n")
  lines
  |> list.map(parse_pair)
  |> list.each(fn(result) { io.println(string.inspect(result)) })

  let good =
    lines
    |> list.filter_map(parse_pair)
  io.println("valid entries: " <> int.to_string(list.length(good)))
}
```

Two points to notice:

1. Splitting `"the  quick"` on a single space produces an empty string between the two spaces. Filtering out empty strings is the usual fix.
2. `parse_pair` uses `use` together with `result.try`. If either step returns `Error(Nil)`, the whole function returns that error immediately. The lines `"bad"` (no `=`) and `"c=x"` (not a number) both fail, and `list.filter_map` quietly keeps only the successes.

## 3. Pattern Matching on Strings

Gleam can match on the beginning of a string with a literal prefix followed by `<>` and a variable. This is clearer than calling `starts_with` followed by `slice`. You can only match a prefix this way, not a suffix or a middle section.

The same section covers graphemes versus codepoints. A grapheme is what a reader sees as one character. A codepoint is a single Unicode value, and a grapheme may be built from several codepoints. For example, "e" followed by a combining accent is two codepoints but one grapheme.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

fn describe(s: String) -> String {
  case s {
    "" -> "empty"
    "https://" <> rest -> "secure link to " <> rest
    "http://" <> rest -> "insecure link to " <> rest
    "#" <> title -> "heading: " <> string.trim(title)
    _ -> "plain text"
  }
}

fn is_palindrome(input: String) -> Bool {
  let letters =
    input
    |> string.lowercase
    |> string.to_graphemes
    |> list.filter(fn(g) { g != " " })
  letters == list.reverse(letters)
}

pub fn main() -> Nil {
  io.println(describe(""))
  io.println(describe("https://gleam.run"))
  io.println(describe("http://example.com"))
  io.println(describe("# Intro"))
  io.println(describe("just words"))

  io.println(string.inspect(is_palindrome("Never odd or even")))
  io.println(string.inspect(is_palindrome("Gleam")))

  let accented = "e\u{0301}"
  let graphemes = string.to_graphemes(accented)
  let codepoints = string.to_utf_codepoints(accented)
  io.println("graphemes: " <> int.to_string(list.length(graphemes)))
  io.println("codepoints: " <> int.to_string(list.length(codepoints)))
  io.println("length: " <> int.to_string(string.length(accented)))
}
```

Order matters in a `case`. `"https://"` is listed before `"http://"` for clarity, though here they could not overlap anyway. The first matching branch wins, so put more specific patterns first and the catch-all `_` last.

The palindrome check turns the string into a list of graphemes, drops spaces, and compares the list with its reverse. Lists support `==` structurally, so no loop is needed.

## 4. Codepoints and a Caesar Cipher

Sometimes you need to work with the numeric value of each character. `string.to_utf_codepoints` gives a list of `UtfCodepoint` values. `string.utf_codepoint_to_int` reads the number, and `string.utf_codepoint` builds a codepoint from an integer, returning a `Result` because not every integer is valid. `string.from_utf_codepoints` assembles the list back into a string.

```gleam
import gleam/io
import gleam/list
import gleam/string

fn shift(cp: UtfCodepoint, by: Int) -> UtfCodepoint {
  let n = string.utf_codepoint_to_int(cp)
  let shifted = case n >= 97 && n <= 122 {
    True -> 97 + { n - 97 + by } % 26
    False -> n
  }
  case string.utf_codepoint(shifted) {
    Ok(new_cp) -> new_cp
    Error(_) -> cp
  }
}

fn caesar(text: String, by: Int) -> String {
  text
  |> string.lowercase
  |> string.to_utf_codepoints
  |> list.map(fn(cp) { shift(cp, by) })
  |> string.from_utf_codepoints
}

pub fn main() -> Nil {
  let secret = caesar("hello, world", 3)
  io.println(secret)
  io.println(caesar(secret, 23))
}
```

Only lowercase letters (codepoints 97 to 122) are shifted. Everything else, such as spaces and punctuation, passes through untouched. Shifting by 3 and then by 23 adds up to 26, which returns the original text. The `Error(_)` branch cannot occur for these values, but handling it keeps the function total, and Gleam requires every case to be covered.

## 5. Building Large Strings Efficiently

Repeated use of `<>` is fine for small strings. When you assemble output from many pieces, such as a report or a page of text, use `gleam/string_tree`. A `StringTree` collects pieces without copying the whole string each time, and you convert it to a regular `String` once at the end.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string
import gleam/string_tree

fn render_row(index: Int, name: String) -> String {
  int.to_string(index) <> ". " <> string.capitalise(name) <> "\n"
}

pub fn main() -> Nil {
  let names = ["ada", "grace", "linus", "margaret"]

  let tree =
    names
    |> list.index_map(fn(name, i) { render_row(i + 1, name) })
    |> list.fold(string_tree.new(), fn(acc, row) {
      string_tree.append(acc, row)
    })
    |> string_tree.append("-- end of list --")

  let report = string_tree.to_string(tree)
  io.println(report)
  io.println("bytes: " <> int.to_string(string.byte_size(report)))
}
```

`list.index_map` passes each element and its zero-based index to the callback, so adding one gives a human-friendly row number. `string.byte_size` reports the size in bytes, which can differ from `string.length` once non-ASCII text is involved.

## Quick Reference

| Task | Function |
| --- | --- |
| Join two strings | `a <> b` |
| Number of graphemes | `string.length` |
| Remove outer whitespace | `string.trim` |
| Change case | `string.uppercase`, `string.lowercase`, `string.capitalise` |
| Test content | `string.contains`, `string.starts_with`, `string.ends_with` |
| Replace text | `string.replace` |
| Take part of a string | `string.slice` |
| Break apart | `string.split`, `string.split_once`, `string.to_graphemes` |
| Combine | `string.join`, `string.concat` |
| Low-level text | `string.to_utf_codepoints`, `string.from_utf_codepoints` |
| Efficient building | `string_tree.new`, `string_tree.append`, `string_tree.to_string` |

## Practice Ideas

- Write a function that turns `"hello world"` into `"Hello World"` by splitting, capitalising each word and joining.
- Extend `parse_pair` so that blank keys are rejected.
- Add support for uppercase letters to the Caesar cipher by handling codepoints 65 to 90.
- Count how often each letter appears using `string.to_graphemes` and `list.fold` with a `Dict`.

These patterns of splitting, matching, transforming and joining cover most of the string work you will do in everyday Gleam programs.