# Working with lists and recursion

A list is an ordered sequence of values of the same type. Gleam writes lists with square brackets: `[4, 7, 9]`. An empty list is `[]`. A list has one element type throughout, so `[1, 2, 3]` is a `List(Int)`, while `["red", "blue"]` is a `List(String)`.

Lists are immutable: a function does not change a list in place. Instead, it returns a list that can share existing values with the original. This makes recursive functions a natural way to describe list operations. A recursive function handles a small part of the list, then calls itself on what remains.

A list can be viewed in two cases:

- It is empty.
- It has a first element followed by the rest of the list.

Gleam expresses those cases with pattern matching. In a pattern such as `[first, ..rest]`, `first` is the first value and `rest` is a list containing all the remaining values. Every recursive list function needs a stopping case, usually the empty list. Without one, recursion has no reason to stop.

## Start with a recursive sum

The sum of an empty list is zero. The sum of a non-empty list is its first value plus the sum of the rest. This definition translates directly into a `case` expression:

```gleam
import gleam/int
import gleam/io

fn sum(numbers: List(Int)) -> Int {
  case numbers {
    [] -> 0
    [first, ..rest] -> first + sum(rest)
  }
}

pub fn main() -> Nil {
  let total = sum([3, 5, 8])
  io.println(int.to_string(total))
}
```

The recursive call receives a shorter list each time. For `[3, 5, 8]`, the function adds `3` to the sum of `[5, 8]`, then adds `5` to the sum of `[8]`, and finally adds `8` to the sum of `[]`. That last call returns zero, so the result is `16`.

The type annotation says that `sum` accepts a `List(Int)` and returns an `Int`. Gleam checks that both branches of the `case` return an integer. A missing or incompatible branch is caught before the program runs.

## Build a new list

A recursive function can also transform each element and return a new list. Here, `double_all` doubles the first value, then puts that result at the front of the transformed rest. When it reaches the empty list, it returns an empty list.

```gleam
import gleam/int
import gleam/io

fn double_all(numbers: List(Int)) -> List(Int) {
  case numbers {
    [] -> []
    [first, ..rest] -> [first * 2, ..double_all(rest)]
  }
}

pub fn main() -> Nil {
  let doubled = double_all([2, 4, 7])
  let total = doubled |> list_total
  io.println(int.to_string(total))
}

fn list_total(numbers: List(Int)) -> Int {
  case numbers {
    [] -> 0
    [first, ..rest] -> first + list_total(rest)
  }
}
```

This example uses the list spread syntax `[..]` to put a value before another list. The result of `double_all([2, 4, 7])` is `[4, 8, 14]`, in the same order as the input. The helper `list_total` sums those values, so the program prints `26`.

The function calls are not tail-recursive: after the call to `double_all(rest)` returns, Gleam still has to build the list with the current doubled value at the front. This direct style is easy to read and works well for many everyday lists. For very long lists, an accumulator can avoid keeping this work pending.

## Use an accumulator

An accumulator is a value carried through the recursive calls. To reverse a list, begin with an empty accumulator. At each step, move the first remaining value to the front of the accumulator. When no input remains, the accumulator is the reversed list.

```gleam
import gleam/int
import gleam/io

fn reverse_into(remaining: List(Int), reversed: List(Int)) -> List(Int) {
  case remaining {
    [] -> reversed
    [first, ..rest] -> reverse_into(rest, [first, ..reversed])
  }
}

fn reverse(numbers: List(Int)) -> List(Int) {
  reverse_into(numbers, [])
}

pub fn main() -> Nil {
  let backwards = reverse([1, 2, 3, 4])
  io.println(int.to_string(first_value(backwards)))
}

fn first_value(numbers: List(Int)) -> Int {
  case numbers {
    [] -> 0
    [first, .._] -> first
  }
}
```

Each call to `reverse_into` immediately returns the next recursive call. This is called tail recursion: the recursive call is the final operation. The accumulator keeps the partial result, so no work needs to wait for a call to return. The helper `first_value` reads the first item of the reversed list; the fallback value makes the function total even if it is given an empty list.

For `[1, 2, 3, 4]`, the accumulator grows through `[1]`, `[2, 1]`, `[3, 2, 1]`, and `[4, 3, 2, 1]`. The program prints `4`. Accumulators are useful for operations such as counting, summing, and building results. They can also make a recursive definition less immediately obvious, so use them when they help with efficiency or clarity.

## Use the standard list functions

Many common operations are already available in `gleam_stdlib`. The `gleam/list` module provides functions such as `map`, `filter`, and `fold`. These are still functional ways to process a list; they save you from writing the same recursion for common patterns.

- `list.map` transforms each element and preserves the list length.
- `list.filter` keeps only elements that pass a predicate.
- `list.fold` walks through the list while updating an accumulator.

The next example filters for even numbers, squares them, then folds them into a total. It uses each operation on the result of the previous one.

```gleam
import gleam/int
import gleam/io
import gleam/list

pub fn main() -> Nil {
  let numbers = [1, 2, 3, 4, 5, 6]

  let even_squares =
    numbers
    |> list.filter(fn(number) { number % 2 == 0 })
    |> list.map(fn(number) { number * number })

  let total =
    list.fold(even_squares, 0, fn(accumulator, square) {
      accumulator + square
    })

  io.println(int.to_string(total))
}
```

The even values are `2`, `4`, and `6`; their squares are `4`, `16`, and `36`, which add to `56`. The pipe operator `|>` passes the value on its left as the first argument to the function on its right. It lets the steps read in the order the data flows: filter, then map. The fold receives an initial accumulator of zero and adds each square to it.

## Choose a clear approach

For a short, list-specific operation, pattern matching makes the empty and non-empty cases explicit. It also gives you control over exactly how the output is built. For familiar operations such as mapping, filtering, and folding, the standard library functions are concise and well tested.

When writing recursion, check three things:

1. **Is there a base case?** An empty list is often the right one.
2. **Does each recursive call get closer to that case?** Pass `rest`, not the original list.
3. **Does the function return the intended type in every branch?** Gleam's type checker can help catch mismatches.

Lists and recursion are useful together because each pattern match exposes one element and a smaller list. Once you can read `[first, ..rest]` comfortably, you can describe a broad range of list algorithms in a direct, type-checked way.