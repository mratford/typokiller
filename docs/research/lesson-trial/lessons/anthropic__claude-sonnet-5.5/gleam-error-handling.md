# Error Handling in Gleam

Gleam has no exceptions. A function that can fail says so in its return type, and the compiler makes you deal with every outcome. This Lesson covers the `Result` type, custom error types, chaining with `use`, and the few places where crashing is acceptable.

## The Result type

The standard library defines `Result` like this:

```gleam
pub type Result(value, error) {
  Ok(value)
  Error(error)
}
```

A function that might fail returns `Ok` with a value on success, or `Error` with a description of what went wrong. The caller usually unpacks it with `case`. The compiler rejects a `case` that forgets one of the two variants, so a failure cannot be silently ignored.

Many standard library functions work this way. `int.parse` returns `Result(Int, Nil)`: when parsing fails there is nothing more to say, so the error is just `Nil`.

```gleam
import gleam/int
import gleam/io

pub fn describe(input: String) -> String {
  case int.parse(input) {
    Ok(n) -> "Parsed " <> int.to_string(n)
    Error(Nil) -> "Not a number: " <> input
  }
}

pub fn main() -> Nil {
  io.println(describe("42"))
  io.println(describe("forty-two"))
}
```

Both branches produce a `String`, so `describe` is a total function. Whatever the input, the caller gets a sensible answer.

## Custom error types

`Nil` as an error is fine for simple cases, but real programs need to distinguish failures. Define a custom type with one variant per kind of failure, and attach data to the variants that need it.

Two helpers from `gleam/result` do most of the work:

- `result.replace_error` swaps the error of a failed result for another value.
- `result.try` takes a result and a function. If the result is `Ok`, it passes the inner value to the function. If it is `Error`, it returns that error unchanged and skips the function.

The `use` expression makes `result.try` pleasant to read. It takes the rest of the block and passes it as a callback, so the code reads top to bottom without nesting.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/result

pub type AgeError {
  NotANumber(String)
  OutOfRange(Int)
}

fn parse_age(input: String) -> Result(Int, AgeError) {
  use n <- result.try(
    int.parse(input)
    |> result.replace_error(NotANumber(input)),
  )
  case n >= 0 && n <= 150 {
    True -> Ok(n)
    False -> Error(OutOfRange(n))
  }
}

fn describe_error(error: AgeError) -> String {
  case error {
    NotANumber(text) -> "not a number: " <> text
    OutOfRange(n) -> "out of range: " <> int.to_string(n)
  }
}

fn show(input: String) -> Nil {
  case parse_age(input) {
    Ok(age) -> io.println("age " <> int.to_string(age))
    Error(error) -> io.println("error, " <> describe_error(error))
  }
}

pub fn main() -> Nil {
  ["30", "abc", "200"]
  |> list.each(show)
}
```

Read `parse_age` carefully. The line starting with `use n <-` means: "if the parse succeeded, bind the number to `n` and continue with the rest of the function; otherwise return the error right now." The remaining lines are the callback body, so they only run on success.

The error type is part of the function's contract. Anyone calling `parse_age` can see from its signature exactly which failures to expect.

## Chaining steps and combining errors

Larger operations are built from several fallible steps. The trouble is that each step may have its own error type, such as `Nil` from `int.parse` or `Nil` from `dict.get`. Your function needs one error type that covers everything. The usual approach is to convert each step's error into your own type as you go, with `result.replace_error` or `result.map_error`.

The next example parses a tiny configuration format made of `key=value` lines and extracts a port number. It also uses `result.all`, which turns a `List(Result(a, e))` into a `Result(List(a), e)`. It returns the first error if there is one.

```gleam
import gleam/dict.{type Dict}
import gleam/int
import gleam/io
import gleam/list
import gleam/result
import gleam/string

pub type ConfigError {
  MissingSeparator(String)
  MissingKey(String)
  BadNumber(String)
}

fn parse_line(line: String) -> Result(#(String, String), ConfigError) {
  string.split_once(line, "=")
  |> result.replace_error(MissingSeparator(line))
}

fn parse_lines(
  lines: List(String),
) -> Result(Dict(String, String), ConfigError) {
  lines
  |> list.map(parse_line)
  |> result.all
  |> result.map(dict.from_list)
}

fn get_port(config: Dict(String, String)) -> Result(Int, ConfigError) {
  use text <- result.try(
    dict.get(config, "port")
    |> result.replace_error(MissingKey("port")),
  )
  int.parse(text)
  |> result.replace_error(BadNumber(text))
}

pub fn load_port(lines: List(String)) -> Result(Int, ConfigError) {
  use config <- result.try(parse_lines(lines))
  get_port(config)
}

pub fn main() -> Nil {
  let inputs = [
    ["host=localhost", "port=8080"],
    ["host=localhost"],
    ["port=eighty"],
    ["just some text"],
  ]
  list.each(inputs, fn(lines) {
    io.println(string.inspect(load_port(lines)))
  })
}
```

Notice how `load_port` stays short. Each helper has one job and one clear error, and `use` joins them together. If `parse_lines` fails, `get_port` never runs.

`string.inspect` prints any value in Gleam syntax, which is handy for looking at results while you are learning or debugging.

## Recovering from errors

Sometimes a failure is not a problem, because you have a sensible default or an alternative. The `result` module has several tools for this:

- `result.unwrap(result, default)` returns the success value, or the default on error.
- `result.or(first, second)` returns `first` if it is `Ok`, otherwise `second`.
- `result.map(result, fun)` transforms a success value and leaves errors alone.
- `result.map_error(result, fun)` transforms an error and leaves successes alone.
- `result.is_ok` and `result.is_error` give you a plain `Bool`.

```gleam
import gleam/int
import gleam/io
import gleam/result

pub type AppError {
  InvalidInput(String)
}

pub fn main() -> Nil {
  // Fall back to a default value.
  let port =
    int.parse("oops")
    |> result.unwrap(8080)
  io.println("port: " <> int.to_string(port))

  // Try an alternative when the first attempt fails.
  let number =
    int.parse("x")
    |> result.or(int.parse("7"))
  io.println("number: " <> int.to_string(result.unwrap(number, 0)))

  // Transform a success value.
  let doubled =
    int.parse("21")
    |> result.map(fn(n) { n * 2 })
  io.println("doubled: " <> int.to_string(result.unwrap(doubled, 0)))

  // Convert the error into a richer type.
  let converted =
    int.parse("bad")
    |> result.map_error(fn(_) { InvalidInput("bad") })
  case converted {
    Ok(_) -> io.println("unexpected success")
    Error(InvalidInput(text)) -> io.println("invalid input: " <> text)
  }
}
```

Use `unwrap` with care. It is convenient, but it throws away the reason for the failure. Reach for it only when a default is truly the right behavior.

## When it is acceptable to crash

Some situations are bugs rather than expected failures: an invariant you are certain holds, or a state that should be impossible. Gleam gives you a few tools for those cases, and each one crashes the current process when triggered:

- `let assert Ok(value) = expression` crashes if the pattern does not match. You can add a message with `as "explanation"`.
- `panic as "message"` crashes immediately.
- `todo as "message"` marks code you have not written yet.

The rule of thumb is simple. If the failure could come from the outside world, such as user input, files, or the network, return a `Result`. If it could only come from a mistake in your own code, a crash with a clear message is acceptable. On the Erlang target a crash in one process does not take the whole system down, and supervisors from `gleam_otp` can restart it. That "let it crash" philosophy is only sensible for truly unexpected problems, never as a replacement for validating input.

A typical safe use of `let assert` is a value you have just constructed yourself:

```gleam
import gleam/int
import gleam/io

pub fn main() -> Nil {
  let assert Ok(n) = int.parse("123") as "literal is always a valid Int"
  io.println("n is " <> int.to_string(n))
}
```

The literal `"123"` is always a valid integer, so the assertion cannot fail. If someone later changes it to something invalid, the message explains what assumption was broken.

## Summary

- Fallible functions return `Result(value, error)`, and `case` forces you to handle both variants.
- Use custom error types to describe each failure precisely, and keep the type in the signature.
- Chain steps with `use x <- result.try(...)`, so the first error stops the sequence and the happy path reads straight down.
- Convert errors with `result.replace_error` and `result.map_error` so one function exposes one consistent error type.
- Recover with `result.unwrap` and `result.or` when a default or fallback makes sense.
- Reserve `let assert`, `panic`, and `todo` for bugs and unfinished code, not for expected failures.

Type each example slowly and watch how the error types flow from the small helpers up to the top-level function. That pattern repeats in nearly every Gleam program you will write.