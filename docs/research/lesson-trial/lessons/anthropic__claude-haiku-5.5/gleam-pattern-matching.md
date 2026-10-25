# Pattern Matching in Gleam

Pattern matching is one of the main ways to work with data in Gleam. Instead of asking "what kind of value is this?" with a chain of checks and then pulling out the pieces yourself, you describe the shape you expect and the compiler does both jobs. The main tool is the `case` expression.

## The shape of a `case`

A `case` takes one or more subjects and compares them against a list of patterns from top to bottom. The first pattern that matches wins, and its branch becomes the value of the whole expression.

```gleam
import gleam/int
import gleam/io
import gleam/list

pub fn fizz(n: Int) -> String {
  case n % 3, n % 5 {
    0, 0 -> "FizzBuzz"
    0, _ -> "Fizz"
    _, 0 -> "Buzz"
    _, _ -> int.to_string(n)
  }
}

pub fn main() -> Nil {
  list.range(1, 15)
  |> list.each(fn(n) { io.println(fizz(n)) })
}
```

Here the `case` has two subjects, separated by a comma. Each branch lists one pattern per subject. The pattern `0` matches only the number zero. The underscore `_` matches anything and throws the value away.

Order matters. The first branch `0, 0` must come before `0, _`, otherwise the more specific case would never be reached. Because the last branch `_, _` matches everything, a `case` always produces a result.

## Literals, variables and the catch-all

A plain name in a pattern is not a comparison. It is a new binding that takes whatever value is there:

```gleam
pub fn describe(n: Int) -> String {
  case n {
    0 -> "zero"
    1 -> "one"
    other -> "the number " <> int.to_string(other)
  }
}
```

The name `other` matches any integer and binds it so the branch can use it. If you want to ignore the value, use `_` instead. If you want to check a condition on a bound value, use a guard, which we cover below.

Gleam compiles `case` to check that every possible value is handled. If you remove the final `other` branch in the example above, the compiler will report that the patterns are not exhaustive. This is one of the main reasons pattern matching is safe to rely on: adding a new variant to a type later will show you every `case` that needs updating.

## Matching lists

Lists are matched by their structure. The empty list is written `[]`. A list with a first element and the rest is written `[first, ..rest]`. You can match exact lengths too.

```gleam
import gleam/int
import gleam/io
import gleam/list

pub fn sum(xs: List(Int)) -> Int {
  case xs {
    [] -> 0
    [first, ..rest] -> first + sum(rest)
  }
}

pub fn describe(xs: List(Int)) -> String {
  case xs {
    [] -> "empty"
    [only] -> "just " <> int.to_string(only)
    [a, b] -> "pair " <> int.to_string(a) <> " and " <> int.to_string(b)
    [first, ..] as whole ->
      "starts with "
      <> int.to_string(first)
      <> ", length "
      <> int.to_string(list.length(whole))
  }
}

pub fn main() -> Nil {
  io.println(int.to_string(sum([1, 2, 3, 4])))
  io.println(describe([]))
  io.println(describe([7]))
  io.println(describe([7, 8]))
  io.println(describe([7, 8, 9]))
}
```

The pattern `[first, ..] as whole` uses `as` to name the entire matched value while also taking the first element out of it. Without `as`, you would have to rebuild the list yourself if you needed it.

The `sum` function is recursive and follows the structure of the list. This is the normal style in Gleam: a function for the empty case, and a function for the case where a list has a head and a tail.

## Custom types, Result, Option and tuples

Patterns become most useful with custom types. Each variant of a type can be matched separately, and the fields can be pulled out by name.

```gleam
import gleam/int
import gleam/io
import gleam/option.{type Option, None, Some}

pub type Shape {
  Circle(radius: Int)
  Rect(width: Int, height: Int)
  Square(side: Int)
}

pub fn area(shape: Shape) -> Int {
  case shape {
    Circle(radius: r) -> 3 * r * r
    Rect(width: w, height: h) -> w * h
    Square(side: s) -> s * s
  }
}

pub fn parse_port(text: String) -> Result(Int, String) {
  case int.parse(text) {
    Ok(n) if n > 0 && n < 65_536 -> Ok(n)
    Ok(_) -> Error("out of range")
    Error(_) -> Error("not a number")
  }
}

pub fn describe_pair(pair: #(Option(Int), Bool)) -> String {
  case pair {
    #(Some(n), True) -> "value " <> int.to_string(n) <> " enabled"
    #(Some(n), False) -> "value " <> int.to_string(n) <> " disabled"
    #(None, _) -> "no value"
  }
}

fn show_port(text: String) -> String {
  case parse_port(text) {
    Ok(port) -> "port " <> int.to_string(port)
    Error(reason) -> "error: " <> reason
  }
}

pub fn main() -> Nil {
  io.println(int.to_string(area(Circle(radius: 2))))
  io.println(int.to_string(area(Rect(width: 3, height: 4))))
  io.println(int.to_string(area(Square(side: 5))))
  io.println(show_port("8080"))
  io.println(show_port("70000"))
  io.println(show_port("http"))
  io.println(describe_pair(#(Some(7), True)))
  io.println(describe_pair(#(None, False)))
}
```

Some points to notice:

- `Circle(radius: r)` matches a `Circle` and binds its `radius` field to `r`. The label is part of the pattern, which makes the code easy to read.
- `Result` and `Option` are ordinary custom types. `Ok`, `Error`, `Some` and `None` are matched the same way as any other variant.
- Tuples are written `#(...)` and matched element by element. Here the pattern `#(Some(n), True)` combines a tuple with two nested variant patterns.
- The `describe_pair` function has no catch-all branch. It covers every combination: `Some` with `True`, `Some` with `False`, and `None` with any boolean. The compiler checks this for you.

## Guards and string patterns

A guard is an `if` clause placed after a pattern. The branch runs only when the pattern matches and the guard is true. Guards let you test conditions that a pattern alone cannot express, such as ranges.

Strings can be matched with `<>` to split off a known prefix:

```gleam
import gleam/io

pub fn greet(input: String) -> String {
  case input {
    "hello " <> name -> "Hi, " <> name
    "" -> "silence"
    other -> "unknown: " <> other
  }
}

pub fn bucket(n: Int) -> String {
  case n {
    x if x < 0 -> "negative"
    0 -> "zero"
    x if x < 10 -> "small"
    _ -> "large"
  }
}

pub fn main() -> Nil {
  io.println(greet("hello Sam"))
  io.println(greet(""))
  io.println(greet("bye"))
  io.println(bucket(-4))
  io.println(bucket(0))
  io.println(bucket(7))
  io.println(bucket(99))

  let assert [first, second, ..] = [10, 20, 30]
  io.println("first and second: " <> bucket(first) <> ", " <> bucket(second))
}
```

Only the prefix `"hello "` is a pattern here. The rest of the string is bound to `name`. A string pattern can only take apart the start of a string, not the middle or the end.

The `let assert` line at the end uses a pattern outside a `case`. It binds `first` and `second` from the list and crashes the program if the value does not match. Use `let assert` when you are certain of the shape, such as in tests or in values you have just constructed. For data that might be wrong, use `case` so you can handle the failure.

## Summary

- A `case` compares subjects against patterns from top to bottom and runs the first branch that matches.
- A bare name binds a value. Use `_` to ignore it and a guard with `if` to add a condition.
- Lists are matched as `[]` and `[first, ..rest]`, and `as` names the whole value.
- Custom types, `Result`, `Option` and tuples are matched by variant and by position or label.
- The compiler checks that every case is covered, so missing branches show up before the program runs.

In the next lesson we will use these patterns to write functions that transform whole lists.