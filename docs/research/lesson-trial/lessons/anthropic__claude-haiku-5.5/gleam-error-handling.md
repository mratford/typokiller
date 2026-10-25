# Lesson: Error Handling with Result

Gleam has no exceptions. A function that can fail says so in its return type, and the compiler makes sure you deal with the failure. The main tool for this is `Result`.

## The Result type

`Result` is a custom type with two variants:

- `Ok(value)` means the operation succeeded and produced `value`.
- `Error(reason)` means it failed and gives a reason.

The standard library's `int.parse` returns a `Result(Int, Nil)`. It gives `Ok(42)` for `"42"` and `Error(Nil)` for `"forty"`. You handle it with an ordinary `case`:

```gleam
import gleam/int
import gleam/io

pub fn main() -> Nil {
  case int.parse("42") {
    Ok(n) -> io.println("Parsed: " <> int.to_string(n))
    Error(Nil) -> io.println("Not a number")
  }

  case int.parse("forty") {
    Ok(n) -> io.println("Parsed: " <> int.to_string(n))
    Error(Nil) -> io.println("Not a number")
  }
}
```

Running this prints `Parsed: 42` and then `Not a number`. Because the error case is part of the type, you cannot forget it. If you write `Ok(n)` alone, the compiler reports a missing pattern.

## Custom error types

`Nil` tells you that something failed but not why. When callers need to know the reason, define your own error type. Each variant can carry the details you need:

```gleam
pub type AgeError {
  NotANumber(input: String)
  OutOfRange(value: Int)
}
```

Now the error describes what went wrong, and you can print a helpful message or choose a different response for each case.

## Chaining with result.try and use

Real programs often perform several fallible steps in a row. Nesting `case` expressions for each step gets hard to read quickly. `result.try` takes a `Result` and a function. If the result is `Ok`, the function runs with the unwrapped value. If it is `Error`, the error passes through unchanged. The `use` keyword makes the chain read top to bottom:

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/result

pub type AgeError {
  NotANumber(input: String)
  OutOfRange(value: Int)
}

fn parse_age(input: String) -> Result(Int, AgeError) {
  use n <- result.try(
    int.parse(input) |> result.replace_error(NotANumber(input)),
  )
  check_range(n)
}

fn check_range(n: Int) -> Result(Int, AgeError) {
  case n >= 0 && n <= 150 {
    True -> Ok(n)
    False -> Error(OutOfRange(n))
  }
}

fn describe(err: AgeError) -> String {
  case err {
    NotANumber(input) -> "not a number: " <> input
    OutOfRange(value) -> "out of range: " <> int.to_string(value)
  }
}

pub fn main() -> Nil {
  list.each(["30", "abc", "200"], fn(s) {
    case parse_age(s) {
      Ok(age) -> io.println("ok: " <> int.to_string(age))
      Error(err) -> io.println("error: " <> describe(err))
    }
  })
}
```

`result.replace_error` swaps the `Nil` error from `int.parse` for our `NotANumber` value. The `use` line then means "take the success value and continue; if this fails, return the error now." The `check_range` call at the end is the final step, so its result becomes the function's result.

## Transforming and unwrapping

Some helpers let you work with results without a full `case`:

- `result.map` changes the success value and leaves errors alone.
- `result.map_error` changes the error type and leaves successes alone.
- `result.unwrap` gives the success value, or a default if the result is an error.
- `result.is_ok` and `result.is_error` return a `Bool`.

`list.try_map` applies a fallible function to every element. If every call succeeds, you get `Ok` with the new list. If any call fails, you get the first `Error` and the rest of the list is skipped.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/result
import gleam/string

pub fn main() -> Nil {
  let good = list.try_map(["1", "2", "3"], int.parse)
  io.println(string.inspect(good))

  let bad = list.try_map(["1", "x", "3"], int.parse)
  io.println(string.inspect(bad))

  // Use 0 if any element failed to parse
  let total = result.unwrap(result.map(bad, fn(nums) { list.fold(nums, 0, fn(acc, n) { acc + n }) }), 0)
  io.println("total: " <> int.to_string(total))

  // Replace the uninformative Nil error with a message
  let labelled =
    int.parse("x")
    |> result.map_error(fn(_) { "input was not an integer" })
  io.println(string.inspect(labelled))

  io.println(string.inspect(result.is_ok(good)))
}
```

Note that `result.map` takes the `Result` as its first argument, so we can pipe into it or call it directly. Here we call it directly to keep the example short. Using `result.unwrap` as the last step of a chain is a common pattern for turning a result into a plain value at the edge of your program.

## When to crash on purpose

Sometimes a failure should never happen, and if it does, the program is wrong. For these cases Gleam provides `let assert`. It destructures a value and crashes if the pattern does not match:

```gleam
import gleam/int
import gleam/io

pub fn main() -> Nil {
  let assert Ok(n) = int.parse("7")
  io.println("n is " <> int.to_string(n))

  case int.parse("oops") {
    Ok(_) -> io.println("unexpected success")
    Error(_) -> io.println("fallback used")
  }
}
```

This program succeeds because `"7"` parses. If you changed the first line to `int.parse("oops")`, the program would crash with a panic message that shows the source location. Use `let assert` when a failure means a bug, and use `Result` when a failure is an expected outcome, such as bad user input.

## Summary

- A function that can fail returns `Result(success, error)`.
- Handle results with `case`, or use `result.try` with `use` to chain steps.
- Define a custom error type when callers need to know the reason for failure.
- Use `result.map`, `result.map_error`, `result.unwrap`, and `list.try_map` to transform results.
- Use `let assert` only where a failure would mean a bug in your code.

Practice by writing a function that parses a `"name,age"` string into a record, returning a custom error for each way the input can be malformed.