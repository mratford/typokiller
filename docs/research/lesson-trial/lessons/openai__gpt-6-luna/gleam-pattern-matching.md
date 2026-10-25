# Pattern matching

Pattern matching lets a program inspect a value and choose what to do based on its shape. In Gleam, `case` is the main tool for this. It can distinguish values such as integers, tuples, lists, and custom types, and it can bind parts of a value to names for use in a branch.

A `case` expression has a subject followed by branches. Each branch has a pattern and an expression after `->`. The first pattern that matches is selected. Branches do not fall through to the next branch, so each branch should describe the result for its own match.

## Match a tuple

A tuple pattern has the same shape as the tuple it matches. In the example, `#(name, age)` matches a two-item tuple and binds its items to `name` and `age`.

The matched parts can be used immediately in the branch expression. This is often clearer than assigning a tuple to a variable and then retrieving its items by position.

```gleam
import gleam/io

pub fn main() -> Nil {
  let person = #("Mina", 8)

  let description = case person {
    #(name, age) -> name <> " is " <> int.to_string(age)
  }

  io.println(description)
}
```

This example uses `int.to_string`, so it needs the `gleam/int` module. A complete version with that import is:

```gleam
import gleam/int
import gleam/io

pub fn main() -> Nil {
  let person = #("Mina", 8)

  let description = case person {
    #(name, age) -> name <> " is " <> int.to_string(age)
  }

  io.println(description)
}
```

The tuple has exactly two items, and the pattern has exactly two positions. Gleam checks types as it compiles the program, so a pattern must fit the type of the value being matched. A tuple with a different number of items is a different type of tuple.

## Match custom types

A custom type describes a set of possible alternatives. Each alternative is a constructor, and matching on the type means handling its possible constructors.

Here, `Delivery` has two constructors: `Pickup` and `Courier`. The `Courier` constructor carries an address, which its pattern can bind to a name. The `Pickup` constructor carries no data.

```gleam
import gleam/io

pub type Delivery {
  Pickup
  Courier(address: String)
}

pub fn main() -> Nil {
  let order = Courier("14 Cedar Lane")

  let message = case order {
    Pickup -> "Collect your order at the counter."
    Courier(address) -> "Deliver to " <> address
  }

  io.println(message)
}
```

The `case` includes one branch for each constructor. Gleam checks that a match covers every possible alternative. If a new constructor is added to `Delivery`, the compiler can point out matches that need updating.

Constructor patterns can also be nested. For example, a constructor may contain a tuple, another custom type, or a list. The pattern should reflect the value's actual structure. If the structure is not yet known, use a `case` to inspect it rather than assuming it has a particular shape.

## Match values and use guards

Patterns can match particular literal values. A branch can also include a guard: a condition that must be true after the pattern matches. Guards help express ranges without creating a separate constructor for each number.

Branch order matters. A general pattern placed before a more specific one can take the value first, leaving the specific branch unreachable. Put special cases first, then broader cases, and finish with a catch-all pattern when appropriate.

```gleam
import gleam/io

pub fn main() -> Nil {
  let score = 84

  let result = case score {
    100 -> "Perfect score"
    points if points >= 60 -> "Passed"
    _ -> "Try again"
  }

  io.println(result)
}
```

The first branch handles exactly `100`. The second binds the score to `points`, then checks whether the guard is true. The underscore, `_`, matches any remaining value without binding it to a name. In this example it covers scores below `60`.

A guard does not replace the pattern. First the pattern must match; then its guard must pass. If the pattern matches but the guard is false, Gleam tries the next branch. Guards are useful for conditions such as numeric bounds, but ordinary branching logic can often be expressed more simply with patterns alone.

## Match lists from the front

List patterns describe both the elements at the front of a list and what remains. `[]` matches an empty list. `[only]` matches a list containing exactly one element. A pattern such as `[first, second, ..rest]` matches a list with at least two elements: it binds the first two and collects the remaining elements into `rest`.

The order of these branches makes the intended cases clear. The longer-list pattern comes after the empty and one-item patterns. Gleam can check that the match handles all list shapes.

```gleam
import gleam/io
import gleam/list

pub fn main() -> Nil {
  let items = ["tea", "bread", "apples"]

  let message = case items {
    [] -> "The basket is empty."
    [only] -> "One item: " <> only
    [first, second, ..rest] -> {
      let remaining = list.length(rest)
      first <> " and " <> second <> " are first; "
      <> int.to_string(remaining) <> " more item(s) follow."
    }
  }

  io.println(message)
}
```

This module also needs the `gleam/int` import for `int.to_string`, so the complete module is:

```gleam
import gleam/int
import gleam/io
import gleam/list

pub fn main() -> Nil {
  let items = ["tea", "bread", "apples"]

  let message = case items {
    [] -> "The basket is empty."
    [only] -> "One item: " <> only
    [first, second, ..rest] -> {
      let remaining = list.length(rest)
      first <> " and " <> second <> " are first; "
      <> int.to_string(remaining) <> " more item(s) follow."
    }
  }

  io.println(message)
}
```

The `..rest` part is not a wildcard for the entire list. It means that zero or more items may remain after the two named elements. This makes it possible to handle a list's first items while still using or passing on its tail.

## Choose patterns that explain the data

Pattern matching is especially valuable when the shape of a value carries meaning. A match on a custom type can document every state a value may represent. A match on a list can distinguish empty, short, and longer lists. A match on a tuple can name its components where they are used.

Use `_` when a value is irrelevant, and use a named pattern when the matched data contributes to the result. Keep branches specific and readable, and let Gleam's exhaustiveness checks help you notice missing cases as your types change.