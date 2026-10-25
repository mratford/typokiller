# String processing

Strings are used for names, messages, file paths, and many other kinds of text. In Gleam, the `String` type is immutable: an operation such as trimming or replacing text returns a new string rather than changing the original. This makes each transformation explicit and easy to combine.

The examples in this lesson use Gleam 1.18 on the Erlang target. Each is a standalone module with its own imports and `main` function. They need only the standard library.

## Trimming and changing case

Whitespace at the start or end of text can get in the way of comparisons. Use `string.trim` to remove it. Case conversion can make text more consistent when capitalization does not matter.

```gleam
import gleam/io
import gleam/string

pub fn main() -> Nil {
  let raw = "  Gleam Strings  "
  let cleaned = string.trim(raw)
  let normalized = string.lowercase(cleaned)

  io.println(normalized)
}
```

This prints `gleam strings`. The original value in `raw` remains unchanged; `cleaned` and `normalized` are new values. Gleam's `let` bindings are immutable, so the same name cannot later be assigned a different value.

Trimming is not the same as removing every space. In this example, the spaces between `Gleam` and `Strings` remain. If a particular character needs to be changed throughout a string, use `string.replace` instead.

```gleam
import gleam/io
import gleam/string

pub fn main() -> Nil {
  let source = "red green blue"
  let dashed = string.replace(source, each: " ", with: "-")
  let message = string.append("labels: ", dashed)

  io.println(message)
}
```

The `each` argument names the text to find, and `with` names its replacement. Here, each space is replaced by a hyphen. `string.append` joins two strings and returns the combined string.

Keep in mind that replacement is literal: it finds the exact text given by `each`. It is not a pattern-matching or regular-expression operation. For more elaborate text rules, first decide which smaller transformations you need, then compose them.

## Splitting text into pieces

`string.split` separates a string wherever it finds a chosen delimiter. For example, splitting on a comma is useful for a simple comma-separated line. The result is a list of strings, which you can handle with the usual list operations.

```gleam
import gleam/io
import gleam/string

fn print_parts(parts: List(String)) -> Nil {
  case parts {
    [] -> Nil
    [first, ..rest] -> {
      io.println(string.trim(first))
      print_parts(rest)
    }
  }
}

pub fn main() -> Nil {
  let line = "pear, plum, peach"
  let parts = string.split(line, on: ",")

  print_parts(parts)
}
```

The helper function processes one list item at a time. An empty list is the stopping case. Otherwise, the pattern `[first, ..rest]` separates the first item from the remaining items. The function prints the trimmed item, then calls itself with the rest.

Trimming each item is useful here because the spaces after the commas are not part of the delimiter. Splitting on `","` does not also remove those spaces. This example deliberately splits on a comma rather than on a space: delimiters should match the structure of the input you expect.

Splitting does not validate the data. If a line must contain a particular number of fields, check the resulting list before treating it as a complete record. Likewise, if a field may itself contain a comma, splitting on commas alone is not enough to parse a quoted data format.

## Checking and normalizing text

Text comparisons are sensitive to details such as capitalization. A common approach is to normalize text first, then compare the normalized values. The following example uses a `case` expression to choose a message based on the normalized input.

```gleam
import gleam/io
import gleam/string

pub fn main() -> Nil {
  let supplied = "  Gleam "
  let name = string.lowercase(string.trim(supplied))

  case name {
    "gleam" -> io.println("Welcome to Gleam.")
    _ -> io.println("That name is not recognized.")
  }
}
```

The expression `string.lowercase(string.trim(supplied))` applies two transformations in order. First, trimming removes whitespace at the ends. Then lowercasing changes the case. The resulting value can be matched against `"gleam"`.

A case expression must account for every possible value. The `_` pattern is a catch-all: it handles any value not matched by the earlier pattern. This is useful for a default response, but do not use it to conceal invalid input when the program needs to report a specific problem.

The same normalization idea works for simple search and prefix checks. These functions return `Bool`, so you can use their results in conditions or `case` expressions. For example, `string.contains(text, pattern: "gleam")` checks whether a particular piece of text occurs in `text`. A check for `"Gleam"` is different from a check for `"gleam"` unless you normalize the text and pattern first.

## Counting pieces

A split operation often provides a useful next step: the number of pieces. The standard library's `list.length` counts the items in a list. In this example, splitting a sentence on a single space gives a list, and the list length is printed as text.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let sentence = "type small steps carefully"
  let words = string.split(sentence, on: " ")
  let count = list.length(words)

  io.println(int.to_string(count))
}
```

This prints `4`. `list.length` returns an integer, while `io.println` prints a string, so `int.to_string` converts the count before printing.

This is a small example, not a complete word-counting routine for arbitrary prose. It assumes that words are separated by exactly one space and that there are no leading or trailing spaces. With repeated spaces, splitting on `" "` can produce empty pieces. Trimming first handles whitespace at the ends, but repeated internal spaces still need to be considered. A robust parser should define how it treats tabs, line breaks, punctuation, and empty fields rather than assuming every input follows the same format.

## A practical sequence

String-processing code is often clearest when it follows the order of the task:

1. Start with the original text.
2. Trim unwanted whitespace at the edges.
3. Normalize case if the task is case-insensitive.
4. Split or replace text according to a clearly chosen delimiter or literal.
5. Check the resulting values before using them.

Each step has a specific purpose, and naming the intermediate values makes that purpose visible. Compare a chain of nested calls with bindings such as `trimmed`, `normalized`, and `parts`: the bindings make it easier to inspect the result of each operation while debugging.

Also keep the input format in mind. A comma-separated list, a sentence, and a user-entered name have different rules. Splitting a sentence on spaces is not the same as parsing a structured data format, and lowercasing is not always appropriate for identifiers or text where capitalization carries meaning. Choose transformations to suit the data, not just because a function is available.

## Practice

Try changing the examples in small ways:

- Change the replacement text from `"-"` to `"_"`.
- Split the line on a different delimiter and update the input to match.
- Change the name supplied to the case example, including its surrounding spaces and capitalization.
- Add or remove a word in the counting example and check the printed result.

The main habit is to treat each operation as a clear transformation from one value to another. That keeps string code predictable, readable, and straightforward to test.