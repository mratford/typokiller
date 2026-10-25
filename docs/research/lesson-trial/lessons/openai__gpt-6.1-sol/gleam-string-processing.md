# String Processing in Gleam

String processing turns raw text into useful values. A program might clean up a label, split a line into fields, read numbers from a report, or compare text after applying a consistent format.

In Gleam, strings are immutable UTF-8 values. A transformation produces a new string rather than changing the original. This makes pipelines particularly useful: each step receives a value and returns the next version.

This lesson uses Gleam 1.18 on the Erlang target. Each example is a complete module using only the standard library. Run the examples separately, replacing your project's main module with the example you want to try.

## 1. Clean and normalize text

Text often needs a little preparation before comparison or display. Leading spaces, trailing line breaks, and inconsistent capitalization can make otherwise similar values behave differently.

The `gleam/string` module provides small functions that compose well. Start by importing it alongside `gleam/io`, which lets us display the results.

```gleam
import gleam/io
import gleam/string

pub fn main() -> Nil {
  let raw = "  Gleam String Workshop  \n"

  let title =
    raw
    |> string.trim
    |> string.replace("Workshop", "Lesson")

  let key =
    title
    |> string.lowercase
    |> string.replace(" ", "-")

  io.println(title)
  io.println(key)

  case string.starts_with(key, "gleam-") {
    True -> io.println("The key has the expected prefix.")
    False -> io.println("The key has a different prefix.")
  }
}
```

The first pipeline removes whitespace from the beginning and end, then replaces `"Workshop"` with `"Lesson"`. Its result is `"Gleam String Lesson"`.

The second pipeline makes a simple key: `"gleam-string-lesson"`. Notice that the original `raw` value remains available. Neither pipeline modifies it.

The pipe operator, `|>`, passes the expression on its left as the first argument to the function on its right. For example, piping into `string.replace(" ", "-")` supplies the source string, leaving the search text and replacement text visible.

`string.starts_with` returns a `Bool`, so we handle its two possibilities with a `case` expression.

This key-making procedure is intentionally limited. Replacing ordinary spaces does not remove tabs, collapse repeated separators, or validate punctuation. A production identifier needs an explicit policy. Normalization is not a substitute for validation.

## 2. Split text, transform fields, and join them

Delimited text appears in configuration, pasted lists, and small reports. A useful processing pattern is:

1. Split the input into fields.
2. Clean each field.
3. Remove fields you do not want.
4. Join the remaining values.

The `gleam/list` module supplies the collection operations. `list.map` transforms every element, while `list.filter` keeps only elements that satisfy a predicate.

```gleam
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let raw = " pear, apple, , banana, pear "

  let fruits =
    raw
    |> string.split(",")
    |> list.map(fn(field) {
      field
      |> string.trim
      |> string.lowercase
    })
    |> list.filter(fn(field) { field != "" })

  let display = string.join(fruits, " | ")

  io.println(display)

  case list.contains(fruits, "apple") {
    True -> io.println("Apples are included.")
    False -> io.println("No apples were found.")
  }
}
```

The displayed list is `"pear | apple | banana | pear"`.

The anonymous function passed to `list.map` receives one field at a time. Its inner pipeline trims that field and converts it to lowercase. This makes the outer pipeline read like a sequence of larger processing stages.

Filtering happens after trimming. That order matters: a field containing one space is not initially equal to the empty string. Once trimmed, it becomes empty and the filter removes it.

The repeated `"pear"` remains repeated. Neither splitting nor mapping removes duplicates, and filtering only checks for empty fields. Keep transformations explicit so that the reader can predict which information survives.

Also distinguish exact list membership from substring matching. `list.contains(fruits, "apple")` checks whether an entire field equals `"apple"`. By contrast, `string.contains` searches within a string.

Finally, splitting on commas is not a general CSV parser. Quoted fields can contain commas, and escaping rules require more structure. This example is appropriate when the input format defines every comma as a separator.

## 3. Parse numbers without hiding errors

Text is often only an intermediate representation. Once a field represents a number, converting it to an `Int` lets the type system help with later calculations.

`int.parse` returns a `Result`. A successful parse contains an integer in `Ok`; an unsuccessful parse contains an error in `Error`. Pattern matching makes both paths visible.

The next example counts successful and failed fields while adding the valid numbers.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

type Totals {
  Totals(sum: Int, accepted: Int, rejected: Int)
}

fn collect(totals: Totals, field: String) -> Totals {
  let Totals(sum, accepted, rejected) = totals

  case int.parse(field) {
    Ok(number) ->
      Totals(sum + number, accepted + 1, rejected)

    Error(_) ->
      Totals(sum, accepted, rejected + 1)
  }
}

pub fn main() -> Nil {
  let fields =
    "12, 7, oops, -3, 4"
    |> string.split(",")
    |> list.map(string.trim)

  let Totals(sum, accepted, rejected) =
    list.fold(fields, Totals(0, 0, 0), collect)

  io.println("Sum: " <> int.to_string(sum))
  io.println("Accepted: " <> int.to_string(accepted))
  io.println("Rejected: " <> int.to_string(rejected))
}
```

This program prints a sum of `20`, with four accepted fields and one rejected field.

The custom `Totals` type gives names to the three pieces of state. The `collect` function receives the current state and one field, then returns updated state.

`list.fold` starts with `Totals(0, 0, 0)` and repeatedly calls `collect`. Nothing is mutated. Each call constructs a new value for the next step.

In the error branch, `_` deliberately ignores the error's details. The program still records that a failure occurred. This is different from silently replacing invalid text with zero, which would make malformed input indistinguishable from a valid zero.

The string concatenation operator, `<>`, joins two strings. Because `sum`, `accepted`, and `rejected` are integers, we convert them with `int.to_string` before joining them to labels.

For a stricter application, one invalid field might reject the whole input. For an interactive report, collecting all invalid fields might be more helpful. The important lesson is to choose that behavior deliberately rather than assuming parsing always succeeds.

## 4. Work with graphemes, not byte positions

UTF-8 uses a variable number of bytes to encode text. A byte offset is therefore not necessarily a character boundary. Even a Unicode code point is not always a complete user-perceived character: a visible character can involve multiple code points.

Gleam's string API provides grapheme-oriented operations. A grapheme is a useful unit when working with text as readers perceive it. `string.to_graphemes` converts a string into a list of small strings, and `string.length` counts graphemes.

Here is a small palindrome checker. It also demonstrates rebuilding text from a list.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let phrase = "Never odd or even"

  let normalized =
    phrase
    |> string.lowercase
    |> string.replace(" ", "")

  let graphemes = string.to_graphemes(normalized)

  let reversed =
    graphemes
    |> list.reverse
    |> string.join("")

  io.println("Normalized: " <> normalized)
  io.println("Reversed: " <> reversed)

  io.println(
    "Grapheme count: "
    <> int.to_string(string.length(normalized)),
  )

  case normalized == reversed {
    True -> io.println("This phrase is a palindrome.")
    False -> io.println("This phrase is not a palindrome.")
  }
}
```

The normalized text is `"neveroddoreven"`, which reads the same in reverse. Its grapheme count is `14`.

Joining with `""` adds no separator between the reversed graphemes. Using `" "` instead would insert spaces and change the comparison.

This checker has a narrow normalization rule: lowercase the text and remove ordinary spaces. It does not remove punctuation or every kind of whitespace. That limitation is useful to notice because many string-processing bugs come from assuming a cleanup function handles more cases than it actually does.

Unicode-aware iteration also does not automatically solve every text comparison problem. Case rules and equivalent Unicode representations can require additional decisions. Define what equality means for your application before applying transformations.

## Build pipelines with clear contracts

Reliable string processing combines small steps with explicit assumptions. Decide which separators are meaningful, whether empty fields should survive, which whitespace is removable, and how invalid values should be reported.

Use `string` functions for text operations, `list` functions for collections of fields, and `Result` matching when conversion can fail. Prefer grapheme-aware operations when manipulating visible text.

Most importantly, preserve the distinction between cleaning, parsing, and validating. A string can be neatly formatted and still be invalid. Clear pipelines make those boundaries easier to read, test, and maintain.