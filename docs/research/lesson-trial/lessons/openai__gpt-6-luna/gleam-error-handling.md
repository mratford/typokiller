# Error handling

Errors are ordinary values in Gleam. Instead of throwing an exception or returning a special null value, a function can return a `Result`. The caller then has to account for success and failure explicitly.

A `Result(value, error)` is either `Ok(value)` or `Error(error)`. The two type parameters describe the types carried by those cases. For example, `Result(Int, String)` means that a function can produce an integer or an error message.

## Return a `Result`

Use `Result` when a function can fail for a reason its caller may need to handle. Here, division succeeds with an integer unless the divisor is zero. The function's return type makes that possibility visible to every caller.

```gleam
import gleam/io

pub fn divide(numerator: Int, denominator: Int) -> Result(Int, String) {
  case denominator == 0 {
    True -> Error("cannot divide by zero")
    False -> Ok(numerator / denominator)
  }
}

pub fn main() -> Nil {
  case divide(42, 6) {
    Ok(answer) -> io.println("The answer is " <> int_to_string(answer))
    Error(message) -> io.println("Error: " <> message)
  }
}

fn int_to_string(value: Int) -> String {
  case value {
    _ -> value |> gleam/int.to_string
  }
}
```

In Gleam, import a module before calling its functions. The small conversion helper above needs an import, so a complete module should include it:

```gleam
import gleam/int
import gleam/io

pub fn divide(numerator: Int, denominator: Int) -> Result(Int, String) {
  case denominator == 0 {
    True -> Error("cannot divide by zero")
    False -> Ok(numerator / denominator)
  }
}

pub fn main() -> Nil {
  case divide(42, 6) {
    Ok(answer) -> io.println("The answer is " <> int.to_string(answer))
    Error(message) -> io.println("Error: " <> message)
  }
}
```

The second block is the complete version to type. Pattern matching on both constructors makes the handling explicit: the success branch receives an `Int`, and the error branch receives a `String`. The first block is deliberately not needed; use the complete module above.

## Chain fallible steps with `use`

When a function performs several operations that can fail, nested `case` expressions can become hard to read. The `use` expression provides a compact way to continue with a successful value and return an error immediately if a step fails.

`int.parse` attempts to read an integer from a string. It returns a `Result`, so it can be used with `result.try`. This example accepts only positive integers. Both parsing failure and a non-positive value are represented by `Error(Nil)`: no extra error detail is needed for this small example.

```gleam
import gleam/io
import gleam/int
import gleam/result

pub fn positive_integer(text: String) -> Result(Int, Nil) {
  use value <- result.try(int.parse(text))

  case value > 0 {
    True -> Ok(value)
    False -> Error(Nil)
  }
}

pub fn main() -> Nil {
  case positive_integer("27") {
    Ok(value) -> io.println("Accepted: " <> int.to_string(value))
    Error(Nil) -> io.println("Please enter a positive integer.")
  }
}
```

The line beginning with `use` means: if `int.parse(text)` is `Ok(value)`, continue the function using `value`. If it is `Error(error)`, return that error from `positive_integer` without running the remaining code. This pattern is useful when each step depends on the previous step succeeding.

The error type here is `Nil`, Gleam's type for the single value `Nil`. That is appropriate when callers need to know that something failed but do not need to distinguish why. If callers need more information, define a more descriptive error type.

## Give errors meaningful names

A string can describe an error, but callers cannot reliably use its wording to decide what to do. A custom error type gives each failure case a stable name. The caller can then match on those cases without inspecting text.

This example validates a simple registration record. It returns the first problem it finds.

```gleam
import gleam/io

pub type RegistrationError {
  EmptyName
  InvalidAge
}

pub fn validate_registration(
  name: String,
  age: Int,
) -> Result(String, RegistrationError) {
  case name == "" {
    True -> Error(EmptyName)
    False ->
      case age >= 18 {
        True -> Ok(name)
        False -> Error(InvalidAge)
      }
  }
}

pub fn main() -> Nil {
  case validate_registration("Mina", 16) {
    Ok(name) -> io.println("Registered: " <> name)
    Error(EmptyName) -> io.println("A name is required.")
    Error(InvalidAge) -> io.println("The minimum age is 18.")
  }
}
```

`RegistrationError` is a custom type with two constructors. Because each constructor names a distinct problem, callers can respond differently to `EmptyName` and `InvalidAge`. The function returns the validated name in `Ok`, so the caller can use the result rather than having to validate it again.

As a program grows, custom error types can also carry useful details. For instance, a constructor could include the value that failed validation. Keep the cases focused on problems callers genuinely need to distinguish.

## Handle failure where it makes sense

Not every error must be shown to a user or passed further up the call chain. Sometimes a caller has a sensible fallback. Handle that choice explicitly with a `case`, and keep the original fallible function honest about the possibility of failure.

In this example, a configured port is used if it is valid. If it is unavailable, the application uses a default port instead.

```gleam
import gleam/io
import gleam/int

pub fn choose_port(configured: Result(Int, String)) -> Int {
  case configured {
    Ok(port) -> port
    Error(_reason) -> 8080
  }
}

pub fn main() -> Nil {
  let configured = Error("port setting was not provided")
  let port = choose_port(configured)
  io.println("Listening on port " <> int.to_string(port))
}
```

The underscore-prefixed name indicates that the function deliberately does not use the error details. This is different from pretending that no error occurred: the `Error` case is still handled, and the fallback is visible in the code.

A fallback is appropriate only when it is safe. Replacing a missing optional setting with a default may be reasonable; silently replacing a failed payment or a corrupted file operation usually is not. Decide at the point where the program has enough context to choose.

## Keep errors in the return type

A `Result` makes failure part of a function's contract. Callers can inspect it, transform it, pass it along, or choose a recovery strategy. Returning an error is not the same as crashing: the caller remains in control.

Use `Result` for expected failures such as invalid input, missing files, or unavailable resources. Use meaningful error types when callers need to tell those failures apart. Use `Nil` when the distinction does not matter. For a single fallible operation, a `case` is direct and easy to read. For a sequence of fallible operations, `use` can keep the successful path concise while still propagating errors.

The key habit is to make each failure path visible. When a function returns a `Result`, handle both `Ok` and `Error` deliberately, and choose whether to report, recover, or pass the error onward.