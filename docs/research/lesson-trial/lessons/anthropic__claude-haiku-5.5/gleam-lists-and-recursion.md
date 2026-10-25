# Working with Lists and Recursion

Gleam has no `for` or `while` loops. To repeat work over a list, you use recursion: a function calls itself on a smaller piece of the list until it reaches the end. This lesson shows how lists are built, how to take them apart with pattern matching, and how to write recursive functions that run in constant stack space.

## Lists are linked

A Gleam list is a linked chain of cells. Each cell holds one element and a pointer to the rest of the list. The empty list is written `[]`. You build a list by prepending an element onto an existing list:

```gleam
let numbers = [1, 2, 3]
let more = [0, ..numbers]   // [0, 1, 2, 3]
```

Prepending is cheap because it only creates one new cell and reuses the old list. Appending to the end is not cheap, because the whole list has to be copied. This is why recursive list code usually builds results by prepending and then reversing at the end.

## Taking a list apart with pattern matching

A `case` expression can match the two shapes a list can have: empty, or a first element followed by the rest.

```gleam
case numbers {
  [] -> "empty"
  [first, ..rest] -> "starts with " <> int.to_string(first)
}
```

The `..rest` pattern binds everything after the first element to `rest`. Pattern matching is the basic tool for every recursive list function. The first branch is the base case, which stops the recursion. The second branch handles one element and recurses on the rest.

Here is a sum function written the direct way:

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
  let total = sum([1, 2, 3, 4])
  io.println("Sum: " <> int.to_string(total))
}
```

Read the function as a definition: the sum of an empty list is 0, and the sum of a list is its first element plus the sum of the rest. This works, but each call to `sum` has to wait for the recursive call to return before it can add. With a very long list, that waiting builds up a deep call stack.

## Tail recursion with an accumulator

A call is in tail position when nothing happens after it returns. The Erlang VM, which Gleam runs on, optimizes tail calls by reusing the current stack frame, so a tail-recursive function can loop over millions of elements without growing the stack. You get tail recursion by carrying the partial result in an extra argument, called an accumulator.

```gleam
import gleam/int
import gleam/io
import gleam/list

fn sum_loop(numbers: List(Int), acc: Int) -> Int {
  case numbers {
    [] -> acc
    [first, ..rest] -> sum_loop(rest, acc + first)
  }
}

pub fn sum(numbers: List(Int)) -> Int {
  sum_loop(numbers, 0)
}

pub fn main() -> Nil {
  let total = sum(list.range(1, 100))
  io.println("Sum of 1 to 100: " <> int.to_string(total))
}
```

The public `sum` function hides the accumulator from callers by starting it at `0`. The helper `sum_loop` does the work. In the recursive branch, the addition happens before the call, so the call to `sum_loop` is the last thing the function does. This is the standard pattern: a small public wrapper, and a private helper that carries an accumulator.

## Building a new list

When a recursive function produces a list, the accumulator is usually a list too. Each element is prepended onto the accumulator, which leaves the results in reverse order. Call `list.reverse` once at the end to fix the order.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

fn double_loop(numbers: List(Int), acc: List(Int)) -> List(Int) {
  case numbers {
    [] -> list.reverse(acc)
    [first, ..rest] -> double_loop(rest, [first * 2, ..acc])
  }
}

pub fn double_all(numbers: List(Int)) -> List(Int) {
  double_loop(numbers, [])
}

pub fn main() -> Nil {
  let doubled = double_all([1, 2, 3])
  io.println(string.join(list.map(doubled, int.to_string), ", "))
}
```

This prints `2, 4, 6`. Notice the single reverse at the end. Reversing once costs one pass over the list, which is the same cost as the traversal you already did, so the total work stays linear.

## Using the standard library

You rarely need to write `double_loop` by hand. The `gleam/list` module provides tested functions for the common patterns: `map` transforms each element, `filter` keeps elements that pass a test, and `fold` reduces a list to a single value using an accumulator. These functions are implemented with the same tail-recursive technique you just saw. Pipes (`|>`) let you chain them so each step reads from top to bottom:

```gleam
import gleam/int
import gleam/io
import gleam/list

pub fn main() -> Nil {
  let result =
    list.range(1, 10)
    |> list.filter(fn(n) { n % 2 == 0 })
    |> list.map(fn(n) { n * n })
    |> list.fold(0, fn(acc, n) { acc + n })

  io.println("Sum of squared evens: " <> int.to_string(result))
}
```

`list.range(1, 10)` produces `[1, 2, ..., 10]`. The filter keeps the evens, the map squares them, and the fold adds them up. The output is `220`, which is 4 + 16 + 36 + 64 + 100.

Note that `list.fold` takes the initial accumulator first, then the function, and the function receives the accumulator before the element. Check the argument order in the documentation when you use it, since it is easy to swap.

## When to write your own recursion

Use the stdlib functions when they fit, because they are short and well tested. Write your own recursion when the logic does not match a single map, filter, or fold, such as when you need to look at two neighboring elements or stop early on a condition. In both cases, follow the same rules:

- Always include a base case that matches `[]`.
- Handle one element in each recursive branch and recurse on `rest`.
- Carry results in an accumulator so the recursive call is in tail position.
- Reverse the accumulator once at the end if you built a list.

With these habits, recursive list code in Gleam stays clear, runs in constant stack space, and avoids the loops that other languages use.