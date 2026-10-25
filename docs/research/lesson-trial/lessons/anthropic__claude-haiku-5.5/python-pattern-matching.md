# Pattern Matching in Python

Python 3.10 added the `match` statement, and Python 3.14 supports it fully. It lets you compare a value against a series of **patterns** and pull out the parts you need in one step. It is more powerful than a chain of `if`/`elif` tests, because a pattern can check the *shape* of a value as well as its contents.

A `match` statement has a subject (the value you examine) and one or more `case` blocks. Python tries the cases from top to bottom and runs the first one that matches. Only one block runs.

## Literal and OR Patterns

The simplest pattern is a literal, such as a number, string, or `None`. Use `|` to match any of several alternatives. The wildcard `_` matches anything and is usually the last case.

```python
def describe(command):
    match command:
        case "quit" | "exit":
            return "leaving"
        case "help":
            return "showing help"
        case _:
            return f"unknown: {command}"


for cmd in ["quit", "help", "dance"]:
    print(describe(cmd))
```

Output:

```
leaving
showing help
unknown: dance
```

Be careful with names. A bare name in a pattern, such as `case x:`, is a **capture pattern**. It matches anything and binds the value to `x`. It does not compare against an existing variable. To compare against a constant, use a dotted name like `Color.RED`, or use a literal.

## Class Patterns and Guards

A class pattern checks that a value is an instance of a class and then checks its attributes. For dataclasses, positional patterns work too, because dataclasses generate a `__match_args__` attribute that lists their fields in order.

A **guard** is an `if` clause after a pattern. The case matches only when the pattern matches *and* the guard is true.

```python
from dataclasses import dataclass


@dataclass
class Point:
    x: int
    y: int


def where(p):
    match p:
        case Point(x=0, y=0):
            return "origin"
        case Point(x=0, y=y):
            return f"on y-axis at {y}"
        case Point(x, y) if x == y:
            return f"on diagonal at {x}"
        case Point(x, y):
            return f"at ({x}, {y})"
        case _:
            return "not a point"


print(where(Point(0, 0)))
print(where(Point(0, 5)))
print(where(Point(3, 3)))
print(where(Point(1, 2)))
print(where("hello"))
```

Output:

```
origin
on y-axis at 5
on diagonal at 3
at (1, 2)
not a point
```

Order matters. The `Point(x, y)` case with the guard comes before the plain `Point(x, y)` case. If you swapped them, the diagonal check would never run.

## Sequence and Mapping Patterns

A sequence pattern uses square brackets or parentheses. It matches lists and tuples of a specific length. A starred name such as `*rest` collects any remaining items into a list. Strings and bytes are deliberately *not* treated as sequences by these patterns, so `"abc"` will not match `[a, b, c]`.

A mapping pattern uses braces. It matches a dictionary that contains the listed keys. Extra keys are ignored unless you capture them with `**rest`. Keys in a mapping pattern must be literals or dotted names, and a mapping pattern does not require the dictionary to have *only* those keys.

```python
def summarize(data):
    match data:
        case []:
            return "empty"
        case [first]:
            return f"one item: {first}"
        case [first, *rest]:
            return f"first={first}, {len(rest)} more"


def config(settings):
    match settings:
        case {"host": host, "port": port, **extra}:
            return f"{host}:{port} extras={sorted(extra)}"
        case {"host": host}:
            return f"{host}:80 (default port)"
        case _:
            return "no host"


print(summarize([]))
print(summarize([7]))
print(summarize([1, 2, 3, 4]))
print(config({"host": "example.com", "port": 8080, "debug": True}))
print(config({"host": "localhost"}))
print(config({"port": 9000}))
```

Output:

```
empty
one item: 7
first=1, 3 more
example.com:8080 extras=['debug']
localhost:80 (default port)
no host
```

The ordering of cases matters again. The mapping case that requires `port` comes first, so a dictionary with both keys is handled there. The second case then catches dictionaries that have only `host`.

## Nested Patterns with `as`

Patterns can be nested to any depth. The `as` keyword binds the whole matched part to a name, which is useful when you want both the pattern's pieces and the original value. Nested patterns let you match a tree-shaped structure in a single case, which makes them a good fit for small evaluators and parsers.

```python
def evaluate(node):
    match node:
        case int(n):
            return n
        case ("add", left, right):
            return evaluate(left) + evaluate(right)
        case ("mul", left, right):
            return evaluate(left) * evaluate(right)
        case ("neg", operand):
            return -evaluate(operand)
        case _:
            raise ValueError(f"bad node: {node!r}")


def first_number(items):
    match items:
        case [int() as n, *_]:
            return f"starts with the number {n}"
        case [*_]:
            return "does not start with a number"


tree = ("add", 2, ("mul", 3, ("neg", 4)))
print(evaluate(tree))
print(first_number([10, "x", "y"]))
print(first_number(["a", 10]))
```

Output:

```
-10
starts with the number 10
does not start with a number
```

Here `int(n)` is a class pattern that matches any integer and binds it to `n`. The tree `("add", 2, ("mul", 3, ("neg", 4)))` evaluates to 2 + 3 × (−4), which is −10.

## Practice Tips

- Put specific patterns before general ones. A wildcard or a capture pattern without a guard matches everything, so it should be last.
- Use guards for conditions that a pattern alone cannot express.
- Remember that `match` is a statement, not an expression. Each `case` block must do its work inside the block, or return from the function.
- When matching a dictionary, decide whether you want extra keys. Use `**rest` to capture them, or leave them out to ignore them.
- Pattern matching is for shape and structure. For simple equality checks on one value, an `if` statement is still clearer.

Pattern matching takes some getting used to, but it rewards careful reading. Once you can see the shape of your data in a `case` line, you can write code that describes its meaning directly.