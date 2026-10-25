# Error Handling in Gleam

Error handling is part of a function's interface. If a function can fail in an expected way, its return type should describe both success and failure. That lets callers decide whether to stop, recover, retry, or report a problem.

In Gleam, the usual tool is `Result(value, error)`. A successful computation returns `Ok(value)`. An unsuccessful computation returns `Error(error)`. Both constructors belong to the same type, so the compiler can check how you handle each possibility.

This lesson uses Gleam 1.18 on the Erlang target. Each example is a separate, complete module. Run them individually rather than combining their definitions into one file.

## 1. Start with explicit results

Suppose a program receives an age as text. Converting the text to an integer can fail, and a valid integer might still be an invalid age.

These are two different checks:

- Parsing checks whether the text represents an integer.
- Validation checks whether that integer is acceptable.

The following function handles both checks and returns a readable error message.

```gleam
import gleam/int
import gleam/io

fn parse_age(text: String) -> Result(Int, String) {
  case int.parse(text) {
    Error(_) -> Error("Age must be a whole number.")
    Ok(age) ->
      case age >= 0 {
        True -> Ok(age)
        False -> Error("Age cannot be negative.")
      }
  }
}

fn report_age(text: String) -> Nil {
  case parse_age(text) {
    Ok(age) -> io.println("Accepted age: " <> int.to_string(age))
    Error(message) -> io.println("Rejected age: " <> message)
  }
}

pub fn main() -> Nil {
  report_age("27")
  report_age("-4")
  report_age("many")
}
```

The `case` expressions inspect the constructors, not just the values inside them. An `Ok` branch receives the successful value. An `Error` branch receives the error.

The underscore in `Error(_)` deliberately ignores the parsing error's payload. Here, `int.parse` returns `Result(Int, Nil)`, so there is no detailed message to preserve. Our function supplies a message appropriate to its own purpose.

Notice that a negative age is not a parsing error. The text `"-4"` is a valid integer representation. Separating parsing from validation makes the program's meaning clearer.

Returning an error is also different from printing one. `parse_age` does not perform output. Its caller decides how to present the outcome. This separation makes the parsing function useful in a command-line program, a web service, or a test.

## 2. Give errors their own type

Strings are convenient for small examples, but they are a weak interface between functions. A caller should not have to compare message text to discover what went wrong.

A custom error type gives each failure a distinct constructor. Constructors can also carry useful context.

The next example reads a stock entry such as `"bolts:12"`. It checks the overall shape, converts the quantity, and rejects negative quantities.

```gleam
import gleam/int
import gleam/io
import gleam/result
import gleam/string

type StockError {
  InvalidShape
  InvalidNumber(String)
  NegativeQuantity
}

fn parse_quantity(text: String) -> Result(Int, StockError) {
  use quantity <- result.try(
    result.map_error(int.parse(text), fn(_) { InvalidNumber(text) }),
  )

  case quantity >= 0 {
    True -> Ok(quantity)
    False -> Error(NegativeQuantity)
  }
}

fn parse_stock(text: String) -> Result(#(String, Int), StockError) {
  case string.split(text, on: ":") {
    [name, quantity_text] -> {
      use quantity <- result.try(parse_quantity(quantity_text))
      Ok(#(name, quantity))
    }
    _ -> Error(InvalidShape)
  }
}

fn error_message(error: StockError) -> String {
  case error {
    InvalidShape -> "Expected a name and quantity separated by one colon."
    InvalidNumber(text) -> "Invalid quantity: " <> text
    NegativeQuantity -> "Quantity cannot be negative."
  }
}

fn report_stock(text: String) -> Nil {
  case parse_stock(text) {
    Ok(#(name, quantity)) ->
      io.println(name <> ": " <> int.to_string(quantity))
    Error(error) -> io.println(error_message(error))
  }
}

pub fn main() -> Nil {
  report_stock("bolts:12")
  report_stock("nuts:many")
  report_stock("washers:-3")
  report_stock("missing separator")
}
```

The return type now documents the possible failures. A caller handling `StockError` must account for all its constructors. Adding another constructor can therefore reveal places that need an updated decision.

`result.map_error` changes only the error side. Successful integers pass through unchanged. A parsing failure becomes `InvalidNumber(text)`, preserving the original text for later reporting.

The `use` expression introduces a callback for `result.try`. When the supplied result is `Ok`, the callback receives its value and execution continues with the remaining expressions. When it is `Error`, the callback is skipped and that error becomes the result of the expression.

This is often called fail-fast composition: the first failure prevents later dependent work. It removes repetitive nested matching without hiding the possibility of failure.

The example intentionally checks only the separator structure and quantity. An empty name is still accepted. Validation rules should be explicit rather than inferred from a function's name.

## 3. Recover only when a fallback makes sense

Not every error should stop a larger operation. Optional configuration often has a sensible default.

Recovery is a policy decision, though. A default port might be reasonable for a small local tool. Silently substituting a default payment amount would be dangerous.

Keep the fallible function separate from the recovery policy. That preserves the choice for other callers.

```gleam
import gleam/int
import gleam/io
import gleam/result

fn parse_port(text: String) -> Result(Int, String) {
  use port <- result.try(
    result.map_error(int.parse(text), fn(_) {
      "Port must be a whole number."
    }),
  )

  case port >= 1 && port <= 65_535 {
    True -> Ok(port)
    False -> Error("Port must be between 1 and 65535.")
  }
}

fn configured_port(text: String) -> Int {
  parse_port(text)
  |> result.unwrap(8080)
}

fn endpoint(text: String) -> Result(String, String) {
  parse_port(text)
  |> result.map(fn(port) {
    "http://localhost:" <> int.to_string(port)
  })
}

pub fn main() -> Nil {
  io.println("Chosen port: " <> int.to_string(configured_port("bad")))
  io.println("Chosen port: " <> int.to_string(configured_port("9000")))

  case endpoint("3000") {
    Ok(address) -> io.println(address)
    Error(message) -> io.println(message)
  }

  case endpoint("70000") {
    Ok(address) -> io.println(address)
    Error(message) -> io.println(message)
  }
}
```

`result.unwrap` extracts the successful value or returns the supplied fallback. It does not panic. In this example, both malformed text and an out-of-range number select port `8080`.

That convenience discards the error information. If users need to know that their configuration was ignored, use an explicit `case` and report the error before choosing the fallback.

`result.map` serves a different purpose. It transforms a successful value while leaving an error unchanged. The `endpoint` function turns a valid port into an address, but it still returns a `Result`.

Use `map` when the transformation itself cannot fail. Use `try` when the next operation also returns a `Result` and should participate in the same failure path.

## 4. Collect independent failures

Fail-fast behavior is ideal when one step depends on another. It is not always ideal for a batch of independent records.

If ten lines are unrelated, one invalid line need not prevent processing the other nine. A batch importer might collect successful values and error messages separately, then present a summary.

The following example parses every item before separating the outcomes.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/result

fn parse_item(text: String) -> Result(Int, String) {
  int.parse(text)
  |> result.map_error(fn(_) { "Not an integer: " <> text })
}

fn separate(
  outcomes: List(Result(Int, String)),
) -> #(List(Int), List(String)) {
  case outcomes {
    [] -> #([], [])
    [outcome, ..rest] -> {
      let #(values, errors) = separate(rest)

      case outcome {
        Ok(value) -> #([value, ..values], errors)
        Error(message) -> #(values, [message, ..errors])
      }
    }
  }
}

pub fn main() -> Nil {
  let inputs = ["12", "bad", "7", "oops", "3"]
  let outcomes = list.map(inputs, parse_item)
  let #(values, errors) = separate(outcomes)
  let total = list.fold(values, 0, fn(sum, value) { sum + value })

  io.println("Accepted total: " <> int.to_string(total))
  io.println("Rejected items: " <> int.to_string(list.length(errors)))
  list.each(errors, fn(message) { io.println(message) })
}
```

The recursive function preserves the original order within each output list. It processes the remainder, then places the current value or message at the front of the appropriate list.

This example deliberately returns both lists rather than a single `Result`. Partial success is the desired outcome, so its return type represents partial success directly.

For a large importer, error values might also include a line number, field name, or original record. Preserve useful context where the failure occurs; reconstructing it later is often harder.

## Choosing a strategy

Use explicit matching when different errors require different decisions. Use `result.try` for dependent steps that should stop at the first failure. Use `result.map` for successful-value transformations, and `result.map_error` to translate error types.

Choose defaults deliberately, and collect errors when independent work should continue.

Expected bad input belongs in ordinary return values, not crashes. A clear result type makes failure visible, keeps recovery decisions near the caller, and gives the compiler more opportunities to help.