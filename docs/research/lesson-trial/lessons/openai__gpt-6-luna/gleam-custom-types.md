# Defining and Using Your Own Data Types

A program becomes easier to understand when its values have names that describe what they mean. An `Int` might represent an age, a page count, or a temperature. Those values have the same basic representation, but they are not necessarily interchangeable in the way your program should treat them. Gleam lets you define your own data types so that your code can express these distinctions directly.

A custom type declaration describes the values that belong to a type. Gleam checks that values are used consistently and that pattern matches handle the possible cases. This lesson introduces custom types with named alternatives, data-carrying variants, and type parameters.

## Types with named alternatives

A custom type can list several alternatives, also called variants or constructors. Each variant starts with a capital letter. In this example, `TrafficLight` can have exactly three values:

```gleam
import gleam/io

pub type TrafficLight {
  Red
  Yellow
  Green
}

pub fn next_light(light: TrafficLight) -> TrafficLight {
  case light {
    Red -> Green
    Yellow -> Red
    Green -> Yellow
  }
}

pub fn main() -> Nil {
  let light = Yellow
  let next = next_light(light)

  case next {
    Red -> io.println("Stop")
    Yellow -> io.println("Prepare")
    Green -> io.println("Go")
  }
}
```

`TrafficLight` is the type's name. `Red`, `Yellow`, and `Green` are its constructors. A constructor with no fields is also a value, so `Yellow` can be bound with `let` just like an integer or string.

The function `next_light` accepts a `TrafficLight` and returns one. Its `case` expression lists every possible variant. Gleam checks this match: if you add another variant to the type, the compiler can point out matches that need to be updated. This helps keep related parts of a program in sync.

The `pub` keyword makes the type, its constructors, and the function available to other modules. Without `pub`, a declaration is private to its module. In a multi-module project, expose only what other code needs; private types and functions can be changed without affecting callers.

## Variants with data

A variant can carry values, called fields. Fields let you package related data together and give the package a meaningful type name. For example, a `Book` can hold a title and a page count.

```gleam
import gleam/io

pub type Book {
  Book(title: String, pages: Int)
}

pub fn is_long(book: Book) -> Bool {
  book.pages > 300
}

pub fn main() -> Nil {
  let book = Book(title: "Small Steps", pages: 240)
  let revised = Book(..book, pages: 320)

  case is_long(revised) {
    True -> io.println("This is a long book")
    False -> io.println("This is a short book")
  }
}
```

The declaration gives `Book` one constructor, also named `Book`, with two named fields. Construct a value by calling that constructor and supplying its fields. Field labels make construction easier to read, especially when a constructor has several fields.

You can read a field with dot access, as `book.pages` does. To make a modified copy, Gleam provides record update syntax: `Book(..book, pages: 320)` reuses the other fields from `book` and replaces `pages`. The original value is unchanged. Gleam values are immutable, so an update produces a new value rather than changing the old one.

A function that accepts `Book` cannot accidentally be given an unrelated value such as a `TrafficLight`. That guarantee comes from the type checker, before the program runs.

## Choosing between different kinds of data

A type can have multiple variants, and each variant can carry different fields. This is useful when a value represents one of several alternatives. A shape, for example, is either a circle with a radius or a rectangle with a width and height.

```gleam
import gleam/io

pub type Shape {
  Circle(radius: Float)
  Rectangle(width: Float, height: Float)
}

pub fn area(shape: Shape) -> Float {
  case shape {
    Circle(radius) -> 3.14 *. radius *. radius
    Rectangle(width, height) -> width *. height
  }
}

pub fn main() -> Nil {
  let circle = Circle(radius: 2.0)
  let rectangle = Rectangle(width: 3.0, height: 4.0)
  let circle_area = area(circle)
  let rectangle_area = area(rectangle)

  case circle_area > rectangle_area {
    True -> io.println("The circle has more area")
    False -> io.println("The rectangle has at least as much area")
  }
}
```

Both constructors belong to `Shape`, but their fields differ. `Circle` needs one `Float`; `Rectangle` needs two. The `case` expression first determines which variant it has, then makes that variant's fields available. The `area` function does not need a separate check for whether a circle has a height: that field exists only on a rectangle.

The `*.` operator performs floating-point multiplication. Gleam keeps floating-point arithmetic visually distinct from integer arithmetic. Here, the result is a `Float`, which is also the return type of `area`.

Pattern matching is more than a way to read values. It is a precise description of what the program does for each variant. If a new shape is added, such as `Triangle`, this function needs a new branch before the match is complete. That compiler feedback is especially valuable as a type grows.

## Types with a parameter

A custom type can use a type parameter when it holds data of different types. The following `Outcome(a)` represents either a successful value of type `a` or a failure message. The letter `a` is a placeholder: a particular outcome might contain an `Int`, a `String`, or another type.

```gleam
import gleam/io

pub type Outcome(a) {
  Success(value: a)
  Failure(message: String)
}

pub fn map(
  outcome: Outcome(a),
  transform: fn(a) -> b,
) -> Outcome(b) {
  case outcome {
    Success(value) -> Success(transform(value))
    Failure(message) -> Failure(message)
  }
}

pub fn main() -> Nil {
  let original = Success(value: 7)
  let doubled = map(original, fn(value) { value * 2 })

  case doubled {
    Success(value) -> {
      case value {
        14 -> io.println("The result is fourteen")
        _ -> io.println("The result is something else")
      }
    }
    Failure(_) -> io.println("The operation failed")
  }
}
```

The type parameter in `Outcome(a)` says that the successful value's type is chosen by the code using the type. The failure message remains a `String` regardless. Gleam infers that `original` is an `Outcome(Int)` and that `doubled` is also an `Outcome(Int)` because the transformation doubles an integer.

The `map` function takes a function from `a` to `b`. If it receives `Success`, it applies that function to the value and returns a `Success` containing the new type. If it receives `Failure`, there is no successful value to transform, so it passes the message through unchanged. This pattern is useful when you want to work with a result while preserving the possibility of failure.

The underscore in the final match is a wildcard: it matches any integer other than `14`. In `Failure(_)`, it matches a failure without binding a name for the message. Use a wildcard when a value matters for selecting a branch but its contents are not needed.

## Choosing a good custom type

A custom type is most useful when its name and constructors make invalid or confusing states harder to express. If a value must be one of a known set of alternatives, represent those alternatives as variants rather than as arbitrary strings. If several values belong together, put them in a constructor with named fields. If the same shape of data can hold different types, consider a type parameter.

Keep type and constructor names descriptive. `Shape`, `Circle`, and `Rectangle` explain more than a collection of loosely related numbers. Prefer a type that captures what the value means, not merely what it is made from.

When you define a type, consider every way it can be constructed and every place it is matched. Gleam's checks help reveal incomplete matches and mismatched values during compilation. Together, expressive types and exhaustive pattern matching make programs easier to read, safer to change, and more direct about their intentions.