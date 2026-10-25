# Lists and Recursion in Gleam

Lists are a natural fit for recursive programming. A list is either empty, or it contains a first element followed by another list. A recursive function can follow that structure: handle the empty case, then process one element and continue with the rest.

In this lesson, we will build lists, use standard library operations, write recursive functions, and introduce tail recursion. We will finish by merging two sorted lists.

Each example is a complete module for Gleam 1.18 on the Erlang target. Run the examples separately, using each module as your application's entry point.

## 1. Start with list operations

A Gleam list contains values of one type. For example, `[2, 4, 6]` has type `List(Int)`. You cannot mix integers and strings in the same list.

Lists are immutable. An operation does not change the original list; it returns a result that you can bind to another name.

The standard library provides most everyday list operations:

- `list.map` transforms each element.
- `list.filter` keeps elements that satisfy a condition.
- `list.fold` combines elements into one result.
- `list.length` counts the elements.

The pipe operator, `|>`, passes the expression on its left as the first argument to the function on its right.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let numbers = [1, 2, 3, 4, 5]

  let doubled =
    numbers
    |> list.map(fn(number) { number * 2 })

  let even =
    numbers
    |> list.filter(fn(number) { number % 2 == 0 })

  let total =
    numbers
    |> list.fold(0, fn(accumulator, number) {
      accumulator + number
    })

  io.println("Original: " <> show(numbers))
  io.println("Doubled: " <> show(doubled))
  io.println("Even: " <> show(even))
  io.println("Total: " <> int.to_string(total))
  io.println("Length: " <> int.to_string(list.length(numbers)))
}

fn show(numbers: List(Int)) -> String {
  numbers
  |> list.map(int.to_string)
  |> string.join(", ")
}
```

The original list remains `1, 2, 3, 4, 5`. The doubled list contains `2, 4, 6, 8, 10`, and the filtered list contains `2, 4`. The total is `15`.

Notice the argument order in the folding function: the accumulator comes first, then the current element. The initial accumulator is `0`. Each step adds one number to the running total.

The `show` helper demonstrates another transformation. It converts every integer to a string, then joins those strings with a separator.

Prefer these standard operations when they express your intention clearly. Understanding their recursive foundations will help when you need behavior that is less conventional.

## 2. Match the shape of a list

A list pattern can distinguish an empty list from a nonempty one.

The pattern `[]` matches an empty list. The pattern `[first, ..rest]` matches a nonempty list, binding its first element to `first` and its remaining list to `rest`.

The `..` syntax represents the list's remaining elements. It does not mean that the rest must contain anything: matching `[7]` produces `first` equal to `7` and `rest` equal to `[]`.

Here are recursive implementations of summing and counting.

```gleam
import gleam/int
import gleam/io

pub fn main() -> Nil {
  let numbers = [3, 6, 9, 12]

  io.println("Sum: " <> int.to_string(sum(numbers)))
  io.println("Count: " <> int.to_string(count(numbers)))
  io.println("Empty sum: " <> int.to_string(sum([])))
  io.println("Empty count: " <> int.to_string(count([])))
}

fn sum(numbers: List(Int)) -> Int {
  case numbers {
    [] -> 0
    [first, ..rest] -> first + sum(rest)
  }
}

fn count(numbers: List(Int)) -> Int {
  case numbers {
    [] -> 0
    [_, ..rest] -> 1 + count(rest)
  }
}
```

Both functions have a base case and a recursive case.

The base case stops the recursion. An empty list has a sum of zero and a count of zero. These choices also make the recursive cases work naturally for a single-element list.

The recursive case reduces the problem. Instead of processing the entire list again, each call receives only `rest`, which is one element shorter.

In `count`, the underscore ignores the first element because its value does not matter. We only need to know that an element exists.

For the supplied list, the sum is `30` and the count is `4`.

To trace `sum([3, 6])`, imagine expanding it into `3 + sum([6])`, then `3 + (6 + sum([]))`. The empty case returns zero, allowing the additions to produce the final result.

That trace also reveals pending work: each call must add its first element after the recursive call returns. For very long lists, a tail-recursive approach is preferable.

## 3. Carry progress in an accumulator

An accumulator stores the result built so far. Instead of waiting to combine results after recursion, a function updates the accumulator before making its next call.

A recursive call is in tail position when its result is returned directly, with no remaining calculation. On the Erlang target, tail calls let this style process long lists without growing the call stack for every element.

Reversing a list is a good example. Repeatedly take the next element from the input and prepend it to an accumulator.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let numbers = [10, 20, 30, 40]
  let reversed = reverse(numbers)

  let text =
    reversed
    |> list.map(int.to_string)
    |> string.join(", ")

  io.println("Reversed: " <> text)
  io.println(
    "Empty length: "
    <> int.to_string(list.length(reverse([]))),
  )
}

fn reverse(items: List(a)) -> List(a) {
  reverse_loop(items, [])
}

fn reverse_loop(
  remaining: List(a),
  accumulator: List(a),
) -> List(a) {
  case remaining {
    [] -> accumulator
    [first, ..rest] ->
      reverse_loop(rest, [first, ..accumulator])
  }
}
```

The lowercase type variable `a` makes this function generic. It can reverse integers, strings, or values of another type because it never examines an element's contents.

The accumulator begins empty. After reading `10`, it contains `[10]`. After reading `20`, it contains `[20, 10]`. Continuing this process produces `[40, 30, 20, 10]`.

Prepending with `[first, ..accumulator]` is efficient: it creates a new front element while reusing the existing tail.

By contrast, repeatedly appending to the end of a growing list requires traversing that growing list. That can turn a simple linear task into a quadratic one.

The wrapper function keeps the implementation detail private. Callers provide only the list, not an accumulator. In ordinary application code, use `list.reverse`; this implementation exposes the underlying technique.

## 4. Recurse over two lists

Recursion can make progress through more than one input. To merge two sorted lists, compare their first elements, keep the smaller one, and continue.

If either list is empty, the other list is already the remaining answer.

This function assumes both inputs are sorted in ascending order. It does not sort arbitrary inputs.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let left = [1, 4, 7]
  let right = [2, 4, 8, 10]
  let merged = merge(left, right)

  let text =
    merged
    |> list.map(int.to_string)
    |> string.join(", ")

  io.println("Merged: " <> text)
}

fn merge(left: List(Int), right: List(Int)) -> List(Int) {
  case left, right {
    [], remaining -> remaining
    remaining, [] -> remaining
    [left_first, ..left_rest], [right_first, ..right_rest] -> {
      case left_first <= right_first {
        True -> [
          left_first,
          ..merge(left_rest, right)
        ]
        False -> [
          right_first,
          ..merge(left, right_rest)
        ]
      }
    }
  }
}
```

The output is `1, 2, 4, 4, 7, 8, 10`. Equal values are preserved. Using `<=` selects the left value first when the leading values are equal.

Each recursive step removes one element from one input. This guarantees progress toward an empty-list case. The total work is linear in the combined input lengths.

Unlike the accumulator-based reverse, this implementation is not tail-recursive. It constructs a list around the recursive result. That direct form closely matches the algorithm, but an accumulator-based version would be a better exercise for handling very large inputs.

## A practical checklist

When writing a recursive list function, ask:

- What should happen for an empty list?
- Which elements does each recursive call remove?
- Is any work left after the recursive call?
- Would a standard library function express this more clearly?

Start with a small example, then test an empty list and a single-element list. Make sure every recursive path moves toward a base case.

Lists reward structural thinking: handle the empty shape, handle the nonempty shape, and let each smaller problem carry you toward the answer.