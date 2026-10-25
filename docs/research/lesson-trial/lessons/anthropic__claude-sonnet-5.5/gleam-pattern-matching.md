# Pattern Matching in Gleam

Pattern matching is the main way Gleam code makes decisions. A pattern describes the shape of a value. When the value fits, the pattern can also pull parts of it out into variables. The compiler checks that every possible shape is handled, so a missing case is a compile error, not a runtime surprise.

## The case expression

A `case` expression compares a value against a series of patterns from top to bottom. The first pattern that matches wins, and its branch becomes the result of the whole expression.

You can match literals, bind a value to a name, or use `_` to ignore it. Two more tools are useful:

- `|` lets several patterns share one branch.
- `if` adds a guard, an extra boolean condition that must also be true.

```gleam
import gleam/int
import gleam/io

pub fn describe(n: Int) -> String {
  case n {
    0 -> "zero"
    1 | 2 | 3 -> "small"
    n if n < 0 -> "negative"
    n if n < 100 -> "medium"
    _ -> "large"
  }
}

pub fn main() -> Nil {
  let numbers = [0, 2, -7, 42, 1000]
  case numbers {
    [] -> io.println("nothing to describe")
    _ -> Nil
  }
  io.println("0 is " <> describe(0))
  io.println("2 is " <> describe(2))
  io.println("-7 is " <> describe(-7))
  io.println("42 is " <> describe(42))
  io.println(int.to_string(1000) <> " is " <> describe(1000))
}
```

Order matters. Gleam tries the branches in sequence, so put specific patterns before general ones. The final `_` branch catches everything left over, which makes the match exhaustive.

## Matching custom types and tuples

Custom types are where pattern matching shines. Each variant is a pattern, and you can destructure its fields right in the branch. For labelled fields you can write `width:` to bind a variable with the same name as the label. You can also write `..` to ignore the remaining fields.

Tuples work the same way. You can match several things at once by building a tuple, or by listing several subjects after `case`, separated by commas.

```gleam
import gleam/int
import gleam/io

pub type Shape {
  Circle(radius: Int)
  Rectangle(width: Int, height: Int)
  Square(Int)
}

pub fn area(shape: Shape) -> Int {
  case shape {
    Rectangle(width: 0, ..) -> 0
    Rectangle(width:, height:) -> width * height
    Circle(radius) -> 3 * radius * radius
    Square(side) -> side * side
  }
}

pub fn fizzbuzz(n: Int) -> String {
  case n % 3, n % 5 {
    0, 0 -> "FizzBuzz"
    0, _ -> "Fizz"
    _, 0 -> "Buzz"
    _, _ -> int.to_string(n)
  }
}

pub fn compare_points(a: #(Int, Int), b: #(Int, Int)) -> String {
  case a, b {
    #(x1, y1), #(x2, y2) if x1 == x2 && y1 == y2 -> "same point"
    #(x1, _), #(x2, _) if x1 == x2 -> "same column"
    #(_, y1), #(_, y2) if y1 == y2 -> "same row"
    _, _ -> "different"
  }
}

pub fn main() -> Nil {
  io.println(int.to_string(area(Circle(2))))
  io.println(int.to_string(area(Rectangle(width: 3, height: 4))))
  io.println(int.to_string(area(Rectangle(width: 0, height: 9))))
  io.println(int.to_string(area(Square(5))))

  io.println(fizzbuzz(15))
  io.println(fizzbuzz(9))
  io.println(fizzbuzz(10))
  io.println(fizzbuzz(7))

  io.println(compare_points(#(1, 2), #(1, 2)))
  io.println(compare_points(#(1, 2), #(1, 5)))
  io.println(compare_points(#(1, 2), #(4, 2)))
  io.println(compare_points(#(1, 2), #(3, 4)))
}
```

If you add a new variant to `Shape` later, the compiler points at every `case` that no longer covers it. That is a big reason to prefer custom types over loose strings or numbers.

## Matching lists and strings

Lists are built from two shapes: the empty list `[]` and a head followed by a tail. Patterns mirror this. `[first, ..rest]` matches a non-empty list, binding the first element and the remainder. You can also match exact lengths, such as `[a, b]`.

Strings support prefix matching with `<>`. The left side must be a literal string, and the right side is bound to the rest of the text.

The `as` keyword gives a name to a whole matched value while you also destructure it.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn sum(numbers: List(Int)) -> Int {
  case numbers {
    [] -> 0
    [first, ..rest] -> first + sum(rest)
  }
}

pub fn summarise(items: List(String)) -> String {
  case items {
    [] -> "empty"
    [one] -> "just " <> one
    [first, second] -> first <> " and " <> second
    [first, ..] as all ->
      first <> " plus " <> int.to_string(list.length(all) - 1) <> " more"
  }
}

pub fn greeting(message: String) -> String {
  case message {
    "Hello, " <> name -> "Nice to meet you, " <> name
    "Bye, " <> name -> "See you, " <> name
    "" -> "Silence"
    other -> "Unknown message: " <> string.uppercase(other)
  }
}

pub fn main() -> Nil {
  io.println(int.to_string(sum([1, 2, 3, 4])))

  io.println(summarise([]))
  io.println(summarise(["apple"]))
  io.println(summarise(["apple", "pear"]))
  io.println(summarise(["apple", "pear", "plum", "fig"]))

  io.println(greeting("Hello, Ada"))
  io.println(greeting("Bye, Grace"))
  io.println(greeting(""))
  io.println(greeting("what"))
}
```

The `sum` function shows the classic recursive shape: handle the empty list, then handle one element and recurse on the rest. Most list functions in `gleam/list` are built on this idea.

## Results, options, and destructuring with let

Gleam has no exceptions and no null. Operations that can fail return a `Result`, which is either `Ok(value)` or `Error(reason)`. Values that may be absent use `Option`, which is either `Some(value)` or `None`. You handle both by matching on them.

Patterns can be nested, so one branch can look inside a `Result` and test the value within it. Guards can refine this further.

A `let` binding is also a pattern. When the pattern can never fail, such as a tuple, plain `let` works. When it might fail, use `let assert`, which crashes at runtime if the value does not fit. Use it sparingly, for cases where a mismatch would be a bug.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/option.{type Option, None, Some}
import gleam/result

pub fn classify(text: String) -> String {
  case int.parse(text) {
    Ok(n) if n > 100 -> "big number " <> int.to_string(n)
    Ok(0) -> "exactly zero"
    Ok(n) -> "number " <> int.to_string(n)
    Error(Nil) -> "not a number"
  }
}

pub fn greet(name: Option(String)) -> String {
  case name {
    Some("") | None -> "Hello, stranger"
    Some(name) -> "Hello, " <> name
  }
}

pub fn first_even(numbers: List(Int)) -> Result(Int, String) {
  numbers
  |> list.find(fn(n) { n % 2 == 0 })
  |> result.replace_error("no even number found")
}

pub fn main() -> Nil {
  io.println(classify("500"))
  io.println(classify("0"))
  io.println(classify("17"))
  io.println(classify("abc"))

  io.println(greet(Some("Ada")))
  io.println(greet(Some("")))
  io.println(greet(None))

  case first_even([1, 3, 6, 8]) {
    Ok(n) -> io.println("found " <> int.to_string(n))
    Error(message) -> io.println(message)
  }
  case first_even([1, 3, 5]) {
    Ok(n) -> io.println("found " <> int.to_string(n))
    Error(message) -> io.println(message)
  }

  let #(name, age) = #("Grace", 36)
  io.println(name <> " is " <> int.to_string(age))

  let assert [head, ..] = [10, 20, 30]
  io.println("head is " <> int.to_string(head))
}
```

Notice `Some("") | None` in `greet`. Alternative patterns are allowed as long as they bind the same variables, and here neither binds any.

## Tips to remember

- Patterns are checked top to bottom, so put specific ones first.
- The compiler enforces exhaustiveness. Use `_` as a catch-all only when you truly mean "everything else", because a wildcard hides the errors you would get when a new variant is added.
- Use `..` to ignore the rest of a record's fields or the tail of a list.
- Guards (`if`) can use comparisons and boolean operators, but not arbitrary function calls.
- A variable can appear only once within a single pattern. To compare two values for equality, use a guard.
- Prefer `case` over `let assert` for anything that can legitimately fail.

Practice by rewriting small `if`-style decisions as `case` expressions over custom types. Once the shapes of your data are explicit, the compiler does much of the checking for you.