# Defining and Using Your Own Data Types in Gleam

Gleam's built-in types (`Int`, `String`, `List`, `Result`) go a long way. Real programs need to model their own domain: a traffic light, a user, a shape, a tree. Gleam does this with **custom types**. A custom type lists every form a value can take, and the compiler then checks that you handle each form.

## Variants: a type with a fixed set of values

The simplest custom type is a list of named **variants**. Type names and variant names both start with a capital letter and use `UpperCamelCase`.

You take these values apart with `case`. Gleam requires `case` to be **exhaustive**: if you forget a variant, the program will not compile. This is one of the best safety features of the language, because adding a variant later makes the compiler point at every place that needs updating.

```gleam
import gleam/io

pub type Color {
  Red
  Green
  Blue
}

pub fn describe(color: Color) -> String {
  case color {
    Red -> "the color of fire"
    Green -> "the color of grass"
    Blue -> "the color of the sky"
  }
}

pub fn next(color: Color) -> Color {
  case color {
    Red -> Green
    Green -> Blue
    Blue -> Red
  }
}

pub fn main() -> Nil {
  io.println(describe(Red))
  io.println(describe(next(Red)))
  io.println(describe(next(next(Red))))
}
```

Notice there are no quotes or special syntax around `Red`. It is a value of type `Color`, just as `True` is a value of type `Bool`.

## Records: variants that carry data

A variant can hold fields. A type with a single variant and named fields works like a record or struct in other languages.

```gleam
import gleam/int
import gleam/io

pub type User {
  User(name: String, age: Int, active: Bool)
}

pub fn birthday(user: User) -> User {
  User(..user, age: user.age + 1)
}

pub fn summary(user: User) -> String {
  user.name <> " is " <> int.to_string(user.age)
}

pub fn main() -> Nil {
  let ada = User(name: "Ada", age: 36, active: True)
  let older = birthday(ada)

  io.println(summary(ada))
  io.println(summary(older))
}
```

Points to remember:

- **Construct** a record by writing the variant name with its fields: `User(name: "Ada", age: 36, active: True)`.
- **Access** a field with a dot: `user.age`.
- **Update** a record with the spread syntax `User(..user, age: 37)`. It builds a *new* record that copies every field from `user` and replaces the ones you list.
- Values in Gleam are immutable. `birthday` does not change `ada`; it returns a fresh `User`. That is why `ada` still prints its original age.

Field labels are optional when you construct a value, so `User("Ada", 36, True)` also works. Labels make code easier to read, especially when several fields share a type.

## Types with several variants, each with its own fields

The two ideas combine. A type can have many variants, and each variant can carry different data. This is often called a *sum type* or *tagged union*, and it is how you model "one of these things" precisely.

```gleam
import gleam/int
import gleam/io

pub type Shape {
  Circle(radius: Float)
  Rectangle(width: Float, height: Float)
  Square(side: Float)
  Point
}

pub fn area(shape: Shape) -> Float {
  case shape {
    Circle(radius: r) -> 3.14159 *. r *. r
    Rectangle(width: w, height: h) -> w *. h
    Square(side: s) -> s *. s
    Point -> 0.0
  }
}

pub fn name(shape: Shape) -> String {
  case shape {
    Circle(..) -> "circle"
    Rectangle(..) -> "rectangle"
    Square(..) -> "square"
    Point -> "point"
  }
}

pub fn main() -> Nil {
  let shapes = [
    Circle(radius: 2.0),
    Rectangle(width: 3.0, height: 4.5),
    Square(side: 5.0),
    Point,
  ]

  case shapes {
    [first, ..] -> {
      io.println(name(first) <> " area: " <> int.to_string(float_round(area(first))))
    }
    [] -> io.println("no shapes")
  }
}

fn float_round(value: Float) -> Int {
  truncate(value +. 0.5)
}

@external(erlang, "erlang", "trunc")
fn truncate(value: Float) -> Int
```

A few things are worth studying here:

- In a pattern, you can bind fields to names: `Circle(radius: r)`. Floats use their own operators, `*.` and `+.`.
- `Circle(..)` means "a circle, and I do not care about its fields". It is handy when you only need to know which variant you have.
- `Point` has no fields, so it is written with no parentheses.
- The `@external` attribute links to an Erlang function. You will not need it often, but it shows how Gleam calls into the host platform. Normally you would use `float.round` from `gleam/float`.

## Generic types and recursion

Types can take **type parameters**, written in parentheses after the name. `List(a)` and `Result(value, error)` work this way. Your own types can too. They can also refer to themselves, which is how you build trees and linked structures.

Here is a binary search tree. `Tree(a)` is either a `Leaf` (empty) or a `Node` holding a left subtree, a value, and a right subtree.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/order
import gleam/string

pub type Tree(a) {
  Leaf
  Node(left: Tree(a), value: a, right: Tree(a))
}

pub fn insert(tree: Tree(Int), value: Int) -> Tree(Int) {
  case tree {
    Leaf -> Node(Leaf, value, Leaf)
    Node(left, current, right) ->
      case int.compare(value, current) {
        order.Lt -> Node(insert(left, value), current, right)
        order.Gt -> Node(left, current, insert(right, value))
        order.Eq -> tree
      }
  }
}

pub fn to_list(tree: Tree(a)) -> List(a) {
  case tree {
    Leaf -> []
    Node(left, value, right) ->
      list.append(to_list(left), [value, ..to_list(right)])
  }
}

pub fn depth(tree: Tree(a)) -> Int {
  case tree {
    Leaf -> 0
    Node(left, _, right) -> 1 + int.max(depth(left), depth(right))
  }
}

pub fn main() -> Nil {
  let tree = list.fold([5, 3, 8, 1, 4, 7, 9, 3], Leaf, insert)

  to_list(tree)
  |> list.map(int.to_string)
  |> string.join(", ")
  |> io.println

  io.println("depth: " <> int.to_string(depth(tree)))
}
```

`to_list` and `depth` work for a tree of *any* element type, because they never inspect the values. `insert` is restricted to `Tree(Int)` because it compares values with `int.compare`. The duplicate `3` in the input is ignored by the `order.Eq` branch.

The recursion in each function mirrors the shape of the type: one `case` branch for each variant. This pattern shows up constantly in Gleam.

## Opaque types and type aliases

By default, a `pub type` exposes its variants, so any module can construct or match on them. Sometimes you want to guarantee that values are only created through your own functions, for example to enforce validation. Mark the type `pub opaque`. Other modules can then use the type but cannot see its constructors.

A **type alias** is different: it only gives a new name to an existing type and creates nothing new.

```gleam
import gleam/io
import gleam/string

pub type Name =
  String

pub opaque type Email {
  Email(address: String)
}

pub fn parse_email(input: String) -> Result(Email, String) {
  case string.contains(input, "@") {
    True -> Ok(Email(address: string.lowercase(input)))
    False -> Error("not an email address: " <> input)
  }
}

pub fn to_string(email: Email) -> String {
  email.address
}

pub fn greet(name: Name, email: Email) -> String {
  "Hello, " <> name <> " <" <> to_string(email) <> ">"
}

pub fn main() -> Nil {
  case parse_email("Ada@Example.com") {
    Ok(email) -> io.println(greet("Ada", email))
    Error(message) -> io.println(message)
  }

  case parse_email("nonsense") {
    Ok(email) -> io.println(to_string(email))
    Error(message) -> io.println(message)
  }
}
```

If `Email` lived in its own module, code elsewhere could never write `Email("anything")`. It would have to call `parse_email`, so every `Email` in the program is known to contain an `@`. Returning a `Result` is the idiomatic way to report that validation can fail.

## Summary

- Define a type with `type Name { Variant1 Variant2(field: Type) }`.
- Variants with no fields are plain values; variants with fields are constructors, called like functions.
- `case` takes values apart and must cover every variant.
- Use `Record(..existing, field: new_value)` to make a modified copy.
- Add type parameters, as in `Tree(a)`, for reusable structures, and use recursion for self-referential types.
- Use `opaque` to hide constructors and protect invariants, and `type Alias = Existing` to give a type a clearer name.

Practice by modeling something from your own life: a deck of cards, a traffic light, a chat message with several kinds of content. Write the type first, and let the compiler guide you through the functions.