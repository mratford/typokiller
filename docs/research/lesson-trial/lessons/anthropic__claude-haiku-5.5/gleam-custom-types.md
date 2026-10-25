# Lesson: Defining Your Own Data Types

Gleam lets you describe your own shapes of data. You write a **custom type** with `pub type`, give it one or more **variants**, and then use `case` to decide what to do with each variant. This lesson covers variants with fields, records with labelled fields, recursive types, and generic types.

## Custom types with variants

A custom type lists its variants inside curly braces. Each variant can carry values:

```gleam
pub type Shape {
  Circle(radius: Float)
  Rectangle(width: Float, height: Float)
}
```

A value of type `Shape` is either a `Circle` or a `Rectangle`, and never both. You build one by calling the variant like a function: `Circle(1.0)`. Variant names start with a capital letter. Field names, such as `radius`, are optional labels. You can omit them and write `Circle(Float)`, but labels make code easier to read.

To use a value, you pattern match it with `case`:

```gleam
import gleam/float
import gleam/io
import gleam/list

pub type Shape {
  Circle(radius: Float)
  Rectangle(width: Float, height: Float)
  Square(side: Float)
}

pub fn area(shape: Shape) -> Float {
  case shape {
    Circle(radius: r) -> 3.14159 *. r *. r
    Rectangle(width: w, height: h) -> w *. h
    Square(side: s) -> s *. s
  }
}

pub fn main() -> Nil {
  let shapes = [Circle(1.0), Rectangle(2.0, 3.5), Square(4.0)]
  list.each(shapes, fn(s) { io.println(float.to_string(area(s))) })
}
```

Notice the float operators `*.` and `+.`. Gleam uses separate operators for floats and integers, so `3.14159 *. r` is a float multiplication, and `2 * 3` would be an integer multiplication.

Gleam checks `case` expressions for exhaustiveness. If you add a new variant to `Shape` and forget to handle it in `area`, the compiler reports an error. This is one of the main benefits of custom types: the compiler keeps your code in sync with your data.

## Records and updates

When a type has one variant, it works like a record. You can read its fields with dot syntax, and you can create a modified copy with the `..` update syntax. The original value is never changed, because Gleam values are immutable.

```gleam
import gleam/int
import gleam/io

pub type User {
  User(name: String, age: Int, active: Bool)
}

pub fn birthday(user: User) -> User {
  User(..user, age: user.age + 1)
}

pub fn main() -> Nil {
  let alice = User(name: "Alice", age: 30, active: True)
  let older = birthday(alice)

  io.println(older.name)
  io.println(int.to_string(older.age))
  io.println(int.to_string(alice.age))

  let deactivated = User(..older, active: False)
  io.println(case deactivated.active {
    True -> "still active"
    False -> "deactivated"
  })
}
```

The output is `Alice`, `31`, `30`, and `deactivated`. The `alice` value still has age 30 after `birthday` runs, because `birthday` built a new `User`.

A labelled field can be given in any order when you construct a value, but the labels must match the definition. Dot access such as `user.age` works only on types with a single variant. For a type with several variants, use `case`.

## Recursive types

A variant can contain its own type. This is how you describe trees and nested expressions. The type below represents arithmetic expressions:

```gleam
import gleam/int
import gleam/io

pub type Expr {
  Num(Int)
  Add(Expr, Expr)
  Mul(Expr, Expr)
  Neg(Expr)
}

pub fn eval(e: Expr) -> Int {
  case e {
    Num(n) -> n
    Add(a, b) -> eval(a) + eval(b)
    Mul(a, b) -> eval(a) * eval(b)
    Neg(a) -> 0 - eval(a)
  }
}

pub fn main() -> Nil {
  // 2 + 3 * (-4)
  let e = Add(Num(2), Mul(Num(3), Neg(Num(4))))
  io.println(int.to_string(eval(e)))
}
```

`eval` calls itself on the smaller parts of the expression. Each recursive call works on a smaller tree, so the recursion always ends at a `Num`. The program prints `-10`.

## Variants without fields and generic types

A variant does not need fields. Variants like these work like enumerations:

```gleam
pub type Color {
  Red
  Green
  Blue
}
```

Type parameters let a type work with any other type. The type `Pair(a, b)` holds a first value of type `a` and a second value of type `b`:

```gleam
import gleam/int
import gleam/io

pub type Color {
  Red
  Green
  Blue
}

pub type Pair(a, b) {
  Pair(first: a, second: b)
}

pub fn color_name(c: Color) -> String {
  case c {
    Red -> "red"
    Green -> "green"
    Blue -> "blue"
  }
}

pub fn swap(p: Pair(a, b)) -> Pair(b, a) {
  Pair(first: p.second, second: p.first)
}

pub fn main() -> Nil {
  let p = Pair(first: Red, second: 42)
  let s = swap(p)
  io.println(int.to_string(s.first))
  io.println(color_name(s.second))
}
```

The type of `p` is `Pair(Color, Int)`, and `swap` returns `Pair(Int, Color)`. Gleam works out these types for you. The function `swap` is written once and works for any pair.

## Summary

- `pub type Name { ... }` defines a custom type with one or more variants.
- Variants can carry labelled fields, such as `Circle(radius: Float)`, or no fields at all.
- Use `case` to handle each variant. The compiler checks that you covered all of them.
- With a single variant, you can read fields with `value.field` and copy with `Type(..value, field: new)`.
- Types can refer to themselves, which is how you build trees, and they can take type parameters, as in `Pair(a, b)`.

In the next lesson you will combine these types with `Result` to handle errors without exceptions.