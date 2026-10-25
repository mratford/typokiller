# Defining and Using Your Own Data Types in Gleam

A custom data type gives a name and structure to values that belong in your program. Instead of representing every choice with a string or every measurement with an integer, you can describe what those values mean.

In Gleam, custom types can represent simple choices, records with named fields, or alternatives carrying different kinds of data. Pattern matching lets you work with each possibility explicitly.

This lesson builds five independent examples. Each code block is a complete module with its own `main` function. Run them separately on the Erlang target.

## 1. Represent a fixed set of choices

Suppose a delivery can be waiting, moving, or complete. Strings could represent those states, but a typo such as `"movng"` would still be a valid string.

A custom type limits the possibilities to the constructors you define.

```gleam
import gleam/io

pub type DeliveryStatus {
  Waiting
  Moving
  Complete
}

fn describe(status: DeliveryStatus) -> String {
  case status {
    Waiting -> "The parcel is waiting."
    Moving -> "The parcel is on its way."
    Complete -> "The parcel has arrived."
  }
}

fn next_status(status: DeliveryStatus) -> DeliveryStatus {
  case status {
    Waiting -> Moving
    Moving -> Complete
    Complete -> Complete
  }
}

pub fn main() -> Nil {
  let initial = Waiting
  let current = next_status(initial)

  io.println(describe(initial))
  io.println(describe(current))
  io.println(describe(next_status(current)))
}
```

`DeliveryStatus` is the type name. `Waiting`, `Moving`, and `Complete` are its constructors. Each constructor creates a value of that type.

Type names and constructors begin with uppercase letters. Function names and variables use lowercase letters, with underscores between words.

The `case` expression selects a branch by matching the value against a pattern. Gleam checks that the patterns cover every possible constructor. If you add another delivery status, the compiler identifies matches that need attention.

Notice that `case` produces a value. In `describe`, every branch produces a string. In `next_status`, every branch produces a `DeliveryStatus`.

A type like this is useful whenever the possible choices form a small, known set: directions, application screens, processing states, or supported commands.

## 2. Group related values into a record

A constructor can also carry data. When a type has one constructor with labeled fields, it is commonly used as a record.

Here, a player has a name and a score. Keeping them together is clearer than passing unrelated arguments throughout the program.

```gleam
import gleam/int
import gleam/io

pub type Points =
  Int

pub type Player {
  Player(name: String, score: Points)
}

fn award_points(player: Player, amount: Points) -> Player {
  Player(..player, score: player.score + amount)
}

fn describe(player: Player) -> String {
  player.name <> " has " <> int.to_string(player.score) <> " points."
}

pub fn main() -> Nil {
  let original = Player(name: "Ada", score: 10)
  let updated = award_points(original, 5)

  io.println(describe(original))
  io.println(describe(updated))
}
```

The constructor is also named `Player`. Giving a single-constructor type and its constructor the same name is a common convention.

The field labels allow readable construction and access. The expression `player.name` retrieves the name, while `player.score` retrieves the score.

Gleam values are immutable. The record update expression `Player(..player, score: ...)` creates a new player, copying the existing fields except for the supplied replacement. It does not modify `player`.

That distinction explains the output: the original player still has 10 points, and the updated player has 15.

`Points` demonstrates a type alias. It is another name for `Int`, not a separate kind of value. Any integer can be used where `Points` is expected.

Use aliases to communicate intent or shorten long type expressions. Use custom types when you need a genuinely distinct representation. For example, a custom wrapper can keep a distance separate from a duration, even when both contain integers.

## 3. Give different alternatives different data

Not every alternative needs the same fields. A payment method might contain a cash amount, a card name, or an account identifier.

Each constructor can carry exactly the information its alternative requires.

```gleam
import gleam/int
import gleam/io

pub type Payment {
  Cash(amount: Int)
  Card(holder: String, last_four: String)
  StoreCredit(account: String, amount: Int)
}

fn receipt(payment: Payment) -> String {
  case payment {
    Cash(amount) ->
      "Cash payment: " <> int.to_string(amount)
    Card(holder, last_four) ->
      "Card payment by " <> holder <> ", ending " <> last_four
    StoreCredit(account, amount) ->
      "Credit from " <> account <> ": " <> int.to_string(amount)
  }
}

fn cash_payment(amount: Int) -> Result(Payment, String) {
  case amount > 0 {
    True -> Ok(Cash(amount: amount))
    False -> Error("The cash amount must be positive.")
  }
}

pub fn main() -> Nil {
  let card = Card(holder: "Mira", last_four: "1234")
  io.println(receipt(card))

  let message = case cash_payment(25) {
    Ok(payment) -> receipt(payment)
    Error(reason) -> reason
  }

  io.println(message)

  let invalid_message = case cash_payment(0) {
    Ok(payment) -> receipt(payment)
    Error(reason) -> reason
  }

  io.println(invalid_message)
}
```

Matching a constructor also extracts its contents. In the `Cash(amount)` branch, `amount` is an integer. In the `Card(holder, last_four)` branch, both bound values are strings.

This design avoids fields that make sense only sometimes. A cash payment does not need an empty card number, and a card payment does not need an unused cash amount.

The validation function returns `Result(Payment, String)`. `Result` is a built-in generic type with two constructors: `Ok` for success and `Error` for failure.

Here, success carries a payment and failure carries an explanation. The caller must handle both possibilities before using the payment.

The custom type describes the shape of the data. The validation function adds a rule about acceptable values. Those are related responsibilities, but they are not the same thing: `Cash(amount: -5)` is still directly constructible in this module.

## 4. Define a generic, recursive type

A generic type can hold different kinds of values without duplicating its definition. A recursive type can contain another value of the same type.

Combining these features gives us a small chain structure.

```gleam
import gleam/int
import gleam/io

pub type Chain(a) {
  End
  Link(value: a, rest: Chain(a))
}

fn length(chain: Chain(a)) -> Int {
  case chain {
    End -> 0
    Link(_, rest) -> 1 + length(rest)
  }
}

fn total(chain: Chain(Int)) -> Int {
  case chain {
    End -> 0
    Link(value, rest) -> value + total(rest)
  }
}

pub fn main() -> Nil {
  let numbers = Link(4, Link(7, Link(2, End)))
  let words = Link("red", Link("blue", End))

  io.println("Number count: " <> int.to_string(length(numbers)))
  io.println("Number total: " <> int.to_string(total(numbers)))
  io.println("Word count: " <> int.to_string(length(words)))
}
```

The lowercase `a` is a type parameter. `Chain(Int)` holds integers, while `Chain(String)` holds strings.

Every link in a particular chain uses the same element type. A chain cannot mix integers and strings merely because its definition is generic.

`End` marks the stopping point. `Link` stores one value and the remainder of the chain.

The `length` function works with any element type because it never examines the stored values. Its underscore pattern deliberately ignores each value.

The `total` function is more specific: it accepts only `Chain(Int)` because addition requires integers here.

Both functions follow the structure of the data. Handle the terminating constructor first, then recursively process the smaller remainder. Real applications would normally use Gleam's standard lists for a sequence like this, but the example exposes how recursive types work.

## 5. Protect rules with an opaque type

Sometimes every value of a type should satisfy a rule. A percentage, for example, might need to stay between 0 and 100.

An opaque type hides its constructors from other modules. Those modules must use the functions you provide.

```gleam
import gleam/int
import gleam/io

pub opaque type Percent {
  Percent(Int)
}

pub fn new_percent(value: Int) -> Result(Percent, String) {
  case value >= 0 && value <= 100 {
    True -> Ok(Percent(value))
    False -> Error("A percentage must be between 0 and 100.")
  }
}

pub fn to_int(percent: Percent) -> Int {
  let Percent(value) = percent
  value
}

pub fn main() -> Nil {
  let valid_message = case new_percent(75) {
    Ok(percent) -> int.to_string(to_int(percent)) <> "%"
    Error(reason) -> reason
  }

  let invalid_message = case new_percent(120) {
    Ok(percent) -> int.to_string(to_int(percent)) <> "%"
    Error(reason) -> reason
  }

  io.println(valid_message)
  io.println(invalid_message)
}
```

Inside this module, the constructor remains available. The `to_int` function can unpack it with a `let` pattern because the type has only one constructor.

Outside the module, callers can name `Percent` but cannot directly construct or unpack it. They use `new_percent` to create values and `to_int` to inspect them.

Opacity therefore establishes a module boundary, not a restriction on the implementing module itself. That module must preserve its own rules.

Together, custom types, exhaustive matching, generics, and opacity let you describe both the possibilities in your data and the operations that make sense for them. Start with the shape of the values, then let the compiler help you handle every case.