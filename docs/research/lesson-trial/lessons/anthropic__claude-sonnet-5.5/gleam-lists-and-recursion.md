# Lists and Recursion in Gleam

Gleam has no `for` or `while` loops. When you want to process every item in a list, you either use a function from the standard library or write a recursive function yourself. This lesson covers the basics of both, starting with how lists are built.

## How lists work

A Gleam list is a *singly linked list*. Each list is either empty, written `[]`, or a first element (the *head*) followed by another list (the *tail*). The `..` syntax lets you build and take apart lists at that boundary:

- `[1, 2, 3]` is the same as `[1, ..[2, 3]]`.
- `[first, ..rest]` in a pattern splits a list into its head and tail.
- Lists are immutable, so adding to the front never changes the original list.

Prepending to the front is fast, because it reuses the existing list. Appending to the back is slow, because the whole list must be copied. That shapes how we write list code: we work from the front and build results by prepending.

All elements in a list must have the same type, so `List(Int)` and `List(String)` are different types, but you can write one function that works for `List(a)` for any `a`.

## Your first recursive function

A recursive function calls itself on a smaller piece of its input. For lists the pattern is almost always the same:

1. Handle the empty list `[]`. This is the *base case*.
2. Handle `[first, ..rest]` by doing something with `first` and recursing on `rest`.

The compiler checks that your `case` covers every possibility, so you cannot forget the empty list.

```gleam
import gleam/int
import gleam/io

pub fn sum(numbers: List(Int)) -> Int {
  case numbers {
    [] -> 0
    [first, ..rest] -> first + sum(rest)
  }
}

pub fn length(items: List(a)) -> Int {
  case items {
    [] -> 0
    [_, ..rest] -> 1 + length(rest)
  }
}

pub fn main() -> Nil {
  let numbers = [1, 2, 3, 4, 5]
  io.println("Sum: " <> int.to_string(sum(numbers)))
  io.println("Length: " <> int.to_string(length(numbers)))
  io.println("Empty sum: " <> int.to_string(sum([])))
}
```

Trace `sum([1, 2, 3])` by hand: it becomes `1 + sum([2, 3])`, then `1 + 2 + sum([3])`, then `1 + 2 + 3 + sum([])`, and finally `1 + 2 + 3 + 0`, which is `6`. Each call waits for the next one to finish before it can add.

Notice that `length` uses `_` for the head. We do not care what the element is, only that one exists. The type variable `a` makes the function work on a list of anything.

## Tail recursion and accumulators

The version of `sum` above leaves an addition waiting after each recursive call. On a very long list, that means many pending operations. The Erlang runtime handles deep recursion well, but the idiomatic technique is *tail recursion*.

A call is in *tail position* when it is the very last thing the function does, with nothing left to compute afterward. The compiler turns tail calls into jumps, so they use constant stack space, just like a loop.

To get there, we add an extra parameter called an *accumulator* that carries the result so far. The public function stays simple, and a private helper does the looping.

```gleam
import gleam/int
import gleam/io
import gleam/string

pub fn sum(numbers: List(Int)) -> Int {
  sum_loop(numbers, 0)
}

fn sum_loop(numbers: List(Int), total: Int) -> Int {
  case numbers {
    [] -> total
    [first, ..rest] -> sum_loop(rest, total + first)
  }
}

pub fn reverse(items: List(a)) -> List(a) {
  reverse_loop(items, [])
}

fn reverse_loop(items: List(a), reversed: List(a)) -> List(a) {
  case items {
    [] -> reversed
    [first, ..rest] -> reverse_loop(rest, [first, ..reversed])
  }
}

pub fn map(items: List(a), with f: fn(a) -> b) -> List(b) {
  map_loop(items, f, [])
}

fn map_loop(items: List(a), f: fn(a) -> b, acc: List(b)) -> List(b) {
  case items {
    [] -> reverse(acc)
    [first, ..rest] -> map_loop(rest, f, [f(first), ..acc])
  }
}

fn show(numbers: List(Int)) -> String {
  "[" <> string.join(map(numbers, with: int.to_string), ", ") <> "]"
}

pub fn main() -> Nil {
  let big = [10, 20, 30, 40]
  io.println("Sum: " <> int.to_string(sum(big)))
  io.println("Reversed: " <> show(reverse(big)))
  io.println("Doubled: " <> show(map(big, with: fn(n) { n * 2 })))
}
```

Study `reverse_loop`. Each step takes the head off the input and puts it on the front of the accumulator, so the order flips. This is the classic reason accumulators come out backwards.

That is also why `map_loop` calls `reverse(acc)` at the end. Prepending builds the output in reverse order, and one final reverse fixes it. This build-then-reverse pattern is very common in Gleam.

The `with f` in `map` is a *label*. It gives the argument a name at the call site, so `map(big, with: fn(n) { n * 2 })` reads clearly.

## Matching more than the head

Patterns can look at several elements at once. You can match exact lengths, such as `[a, b]`, or a minimum number of elements, such as `[a, b, ..rest]`. You can also add a *guard* with `if` to test a condition.

Here is a function that removes consecutive duplicates, along with one that pairs up neighbors:

```gleam
import gleam/int
import gleam/io
import gleam/string

pub fn dedupe(items: List(a)) -> List(a) {
  case items {
    [first, second, ..rest] if first == second -> dedupe([second, ..rest])
    [first, ..rest] -> [first, ..dedupe(rest)]
    [] -> []
  }
}

pub fn describe(items: List(String)) -> String {
  case items {
    [] -> "nobody"
    [one] -> one
    [one, two] -> one <> " and " <> two
    [first, ..rest] ->
      first <> " and " <> int.to_string(count(rest)) <> " others"
  }
}

fn count(items: List(a)) -> Int {
  case items {
    [] -> 0
    [_, ..rest] -> 1 + count(rest)
  }
}

pub fn main() -> Nil {
  let messy = [1, 1, 2, 3, 3, 3, 4, 1, 1]
  let clean = dedupe(messy)
  io.println(string.inspect(clean))

  io.println(describe([]))
  io.println(describe(["Ada"]))
  io.println(describe(["Ada", "Grace"]))
  io.println(describe(["Ada", "Grace", "Linus", "Margaret"]))
}
```

Order matters in a `case`. Gleam tries patterns from top to bottom, so in `dedupe` the guarded clause must come before the general `[first, ..rest]` clause. In `describe`, the specific shapes `[one]` and `[one, two]` come before the general one.

Notice that `dedupe` is not tail recursive, since it wraps the recursive call in a new list. That is fine for modest lists, and it keeps the code readable.

## Using the standard library

Writing your own recursion is the best way to learn, but in everyday code you will usually reach for the `gleam/list` module. It provides tested, efficient versions of the common patterns:

- `list.map` transforms every element.
- `list.filter` keeps elements that pass a test.
- `list.fold` combines all elements into one value, using an accumulator just like our `sum_loop`.
- `list.first` and `list.rest` return a `Result`, because the list might be empty.
- `list.reverse`, `list.append`, `list.length`, `list.contains`, and many more.

Combine them with the pipe operator `|>`, which passes the value on its left as the first argument of the function on its right. This produces readable, top-to-bottom data pipelines.

```gleam
import gleam/int
import gleam/io
import gleam/list
import gleam/string

pub fn main() -> Nil {
  let numbers = [1, 2, 3, 4, 5, 6]

  let total =
    numbers
    |> list.filter(int.is_even)
    |> list.map(fn(n) { n * n })
    |> list.fold(0, fn(acc, n) { acc + n })

  io.println("Sum of even squares: " <> int.to_string(total))

  let words = ["gleam", "is", "a", "friendly", "language"]

  let long_words =
    words
    |> list.filter(fn(word) { string.length(word) > 2 })
    |> list.map(string.uppercase)

  io.println(string.join(long_words, " "))

  case list.first(words) {
    Ok(word) -> io.println("First word: " <> word)
    Error(Nil) -> io.println("No words")
  }

  case list.first([]) {
    Ok(n) -> io.println("Got " <> int.to_string(n))
    Error(Nil) -> io.println("The list was empty")
  }
}
```

In the pipeline, the even numbers are `2`, `4` and `6`. Their squares are `4`, `16` and `36`, and the fold adds them up to `56`.

`list.fold(0, fn(acc, n) { acc + n })` is the general form of our `sum_loop`. The first argument is the starting accumulator, and the function receives the accumulator and the next element, returning the new accumulator. Once you see that, you can write almost any list reduction as a fold.

Because `list.first` returns `Result(a, Nil)`, the compiler forces you to deal with the empty list. There is no hidden crash waiting for you.

## When to write your own recursion

Prefer the standard library when it fits. Write explicit recursion when:

- you need to look at several elements at once, as in `dedupe`;
- you need to stop early, before reaching the end of the list;
- the logic does not match `map`, `filter` or `fold` cleanly.

## Summary

- A list is `[]` or a head followed by a tail, and prepending with `[x, ..list]` is cheap.
- Recursive list functions handle `[]` first, then `[first, ..rest]`.
- Tail recursion with an accumulator runs in constant stack space. Accumulators built by prepending come out reversed, so reverse at the end.
- Patterns can match several elements and use `if` guards, and their order matters.
- `gleam/list` plus the pipe operator covers most everyday work.

Try rewriting `dedupe` with an accumulator, or implement `filter` yourself using the `map_loop` pattern. Writing these by hand makes the standard library feel much less mysterious.