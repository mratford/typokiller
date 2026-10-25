# Pattern Matching in Gleam

Pattern matching lets you inspect a value, select a branch, and give names to the pieces you need. It is one of the main ways Gleam programs make decisions.

A pattern describes the shape of a value. It might describe a particular integer, a tuple with two fields, an empty list, or a custom type constructor. Unlike a Boolean comparison, a pattern can also extract data.

This lesson uses Gleam 1.18 on the Erlang target. Each example is a separate, complete module. Run them independently rather than combining their definitions into one file.

## 1. Match values and tuple shapes

A `case` expression compares a value against patterns. Gleam tries the branches from top to bottom and evaluates the first branch that matches.

Each branch has a pattern, an arrow, and a result expression. All branches must produce the same type. In this example, every branch produces a `String`.

```gleam
import gleam/int
import gleam/io

fn describe_reading(reading: #(String, Int)) -> String {
  case reading {
    #("north", 0) -> "The north sensor is idle."
    #(location, value) if value < 0 ->
      location <> " reported a negative reading."
    #(location, value) ->
      location <> " reported " <> int.to_string(value) <> "."
  }
}

pub fn main() -> Nil {
  io.println(describe_reading(#("north", 0)))
  io.println(describe_reading(#("south", -3)))
  io.println(describe_reading(#("east", 8)))
}
```

The notation `#(String, Int)` is a tuple type. The expression `#("north", 0)` constructs a tuple, while the same shape inside a branch is a pattern.

The first branch matches only the exact pair `"north"` and `0`. Both fields must match for that branch to run.

The second branch binds the fields to `location` and `value`. A lowercase name in a pattern introduces a binding; it does not compare against a previously stored value.

The condition after `if` is a guard. Here, the branch accepts a tuple only when its integer field is negative. Guards provide extra tests after a structural match. They support a restricted set of operations, rather than arbitrary function calls.

The final branch binds both fields without adding a condition. It handles every remaining tuple.

Ordering matters. If the unrestricted tuple pattern came first, it would accept every reading before the more specific patterns could run. Start with special cases and finish with broader cases.

Also notice that `case` returns a value. The function does not need a separate return statement: its final expression is the result.

## 2. Match empty and nonempty lists

Lists have a recursive shape: a list is either empty, or it has a first element followed by another list. Pattern matching makes this structure easy to express.

The pattern `[]` matches an empty list. The pattern `[first, ..rest]` matches a nonempty list, binding its first element and its remaining elements separately.

```gleam
import gleam/int
import gleam/io

fn sum(numbers: List(Int)) -> Int {
  case numbers {
    [] -> 0
    [first, ..rest] -> first + sum(rest)
  }
}

fn describe_start(numbers: List(Int)) -> String {
  case numbers {
    [] -> "The list is empty."
    [only] -> "One number: " <> int.to_string(only)
    [first, second, .._] ->
      "The first two numbers are "
      <> int.to_string(first)
      <> " and "
      <> int.to_string(second)
      <> "."
  }
}

pub fn main() -> Nil {
  let numbers = [4, 7, 9]

  io.println("Sum: " <> int.to_string(sum(numbers)))
  io.println(describe_start(numbers))
  io.println(describe_start([5]))
  io.println(describe_start([]))
}
```

The `sum` function follows the list's structure. An empty list contributes zero. A nonempty list contributes its first number plus the sum of the remaining numbers.

Each recursive call receives a shorter list, so these calls eventually reach the empty-list branch. This example uses tiny lists and finishes immediately. For production code, the standard library's list operations are often preferable to writing a recursive traversal yourself.

The second function distinguishes three shapes: zero elements, exactly one element, and at least two elements.

The pattern `[only]` means exactly one element. It does not match the beginning of a longer list.

By contrast, `[first, second, .._]` allows any number of additional elements. The `..` introduces the remaining list, and `_` discards it.

An underscore is useful when a value is structurally necessary but irrelevant to the result. It communicates that ignoring the value is intentional.

These three branches cover every possible list length. If you removed the empty-list branch, Gleam would report that the match is incomplete.

## 3. Match custom types and nested data

Custom types describe a fixed set of alternatives. Each constructor represents one alternative and can carry its own data.

Pattern matching lets you distinguish those alternatives while extracting their fields. You can also match nested constructors directly, without first unpacking each layer into separate variables.

```gleam
import gleam/io

type Destination {
  Local
  Overseas(country: String)
}

type Parcel {
  Letter(destination: Destination)
  Box(destination: Destination, fragile: Bool)
}

fn handling_note(parcel: Parcel) -> String {
  case parcel {
    Letter(Local) -> "Sort the letter for local delivery."
    Letter(Overseas(country)) ->
      "Prepare the letter for " <> country <> "."
    Box(_, True) -> "Handle this fragile box carefully."
    Box(Local, False) -> "Load the box on the local van."
    Box(Overseas(country), False) ->
      "Prepare the box for " <> country <> "."
  }
}

pub fn main() -> Nil {
  io.println(handling_note(Letter(Local)))
  io.println(handling_note(Letter(Overseas("Canada"))))
  io.println(handling_note(Box(Overseas("Japan"), True)))
  io.println(handling_note(Box(Local, False)))
}
```

`Destination` has two constructors: `Local` carries no data, and `Overseas` carries a country name.

`Parcel` also has two constructors. A `Letter` carries a destination. A `Box` carries a destination and a Boolean indicating whether it is fragile.

The pattern `Letter(Overseas(country))` checks two layers at once. It accepts a letter whose destination is overseas, then binds the country name.

The pattern `Box(_, True)` deliberately ignores the destination. Every fragile box receives the same handling instruction, regardless of where it is going.

The remaining box branches explicitly match `False`. Together, the branches account for every possible parcel.

This is a major advantage of custom types over loosely structured strings. If you add another constructor later, the compiler can identify matches that need updating.

Keep constructor patterns specific enough to express your intent. A broad catch-all can be convenient, but it may hide distinctions that should become visible when your data model changes.

## 4. Match success and failure

Gleam represents many operations that can fail using `Result`. Its two constructors are `Ok(value)` and `Error(reason)`.

A result is ordinary data. Matching it makes both success and failure explicit, while allowing you to transform the information carried by either constructor.

```gleam
import gleam/int
import gleam/io

fn positive_number(text: String) -> Result(Int, String) {
  case int.parse(text) {
    Ok(value) if value > 0 -> Ok(value)
    Ok(_) -> Error("The number must be positive.")
    Error(_) -> Error("The text is not an integer.")
  }
}

fn report(text: String) -> String {
  case positive_number(text) {
    Ok(value) -> "Accepted: " <> int.to_string(value)
    Error(message) -> "Rejected: " <> message
  }
}

pub fn main() -> Nil {
  io.println(report("23"))
  io.println(report("0"))
  io.println(report("pear"))

  let assert Ok(number) = positive_number("12")
  io.println("Known valid number: " <> int.to_string(number))
}
```

The first match separates parsing failure from validation failure. A successfully parsed positive integer becomes `Ok(value)`. A parsed zero or negative integer becomes an error with a specific message.

The guard belongs only to the first branch. When parsing succeeds but the guard fails, matching continues to `Ok(_)`.

The `report` function then turns either result into a printable string. Its two branches cover both constructors, so callers always receive a message.

The final lines demonstrate `let assert`. This form extracts a value while asserting that a particular pattern matches. If it does not match, the program panics.

Here the assertion uses a fixed, known-valid string. For values that might legitimately fail, prefer a `case` expression and handle the error. An assertion is not a substitute for normal error handling.

## Choose patterns that explain the data

Good patterns make a program's assumptions visible. Literal patterns identify special values. Tuple and list patterns expose structure. Constructor patterns distinguish meaningful alternatives. Guards add small conditions when shape alone is insufficient.

Before finishing a match, ask three questions:

- Are the branches ordered from specific to general?
- Does every possible value have a branch?
- Are discarded fields truly irrelevant?

Gleam checks exhaustiveness, but clear patterns do more than satisfy the compiler. They help the next reader understand exactly which shapes your code expects and what each shape means.