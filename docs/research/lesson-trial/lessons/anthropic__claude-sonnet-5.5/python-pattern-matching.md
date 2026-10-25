# Structural Pattern Matching in Python

Python's `match` statement lets you compare a value against a series of *patterns* and run the block for the first one that fits. It looks like a `switch` from other languages, but it is far more powerful: patterns can take apart sequences, mappings, and objects, and bind pieces of them to names in one step.

This lesson covers four ideas: literal and alternative patterns, sequence patterns, mapping patterns, and class patterns with guards.

## The Basics: Literals, Alternatives, and the Wildcard

The simplest `match` compares a value against literals. Each `case` is tried from top to bottom. The first match wins, and the rest are skipped. The underscore `_` is the wildcard: it matches anything and binds nothing, so it makes a good default.

Use `|` to combine alternatives in one case. Use `as` to capture the value that matched.

```python
def describe_status(code):
    match code:
        case 200:
            return "OK"
        case 301 | 302 | 307:
            return "Redirect"
        case 404:
            return "Not Found"
        case 500 | 502 | 503 as err:
            return f"Server error {err}"
        case _:
            return "Unknown"


def classify_command(text):
    match text.lower():
        case "quit" | "exit":
            return "leaving"
        case "help":
            return "showing help"
        case "":
            return "empty input"
        case other:
            return f"unrecognized: {other}"


for code in (200, 302, 404, 503, 999):
    print(code, "->", describe_status(code))

for text in ("Quit", "help", "", "dance"):
    print(repr(text), "->", classify_command(text))
```

Notice the last case in `classify_command`. A bare name such as `other` is a *capture pattern*: it matches anything and binds the value to that name. Because it always matches, it must come last. Python raises a `SyntaxError` if an irrefutable pattern is followed by other cases.

A key rule: a bare name in a pattern always *captures*, it never compares. If you want to compare against a constant stored in a variable, use a dotted name such as `Color.RED`, which is treated as a value to look up.

## Sequence Patterns

Patterns can describe the shape of lists and tuples. Square brackets and parentheses both work and match any sequence except strings and bytes. You can bind elements to names, and use a starred name to soak up the rest.

```python
def summarize(items):
    match items:
        case []:
            return "empty"
        case [only]:
            return f"one item: {only}"
        case [first, second]:
            return f"two items: {first} and {second}"
        case [first, *middle, last]:
            return f"{first} ... {last} with {len(middle)} in between"


def handle_command(words):
    match words:
        case ["go", direction]:
            return f"moving {direction}"
        case ["pick", "up", *things]:
            return "picking up " + ", ".join(things)
        case ["drop", item] | ["throw", item]:
            return f"getting rid of {item}"
        case ["say", *message] if message:
            return "saying: " + " ".join(message)
        case _:
            return "I do not understand"


print(summarize([]))
print(summarize([7]))
print(summarize([7, 8]))
print(summarize([1, 2, 3, 4, 5]))
print(summarize("ab"[:0] or ()))

for line in (
    "go north",
    "pick up lamp key map",
    "drop sword",
    "throw ball",
    "say hello there",
    "say",
    "dance",
):
    print(line, "=>", handle_command(line.split()))
```

Two details deserve attention. First, `case ["say", *message] if message:` uses a *guard*, an `if` condition after the pattern. The pattern must match and the guard must be true. Second, in `case ["drop", item] | ["throw", item]`, every alternative must bind the same set of names.

Because strings are excluded from sequence patterns, `match "abc": case [a, b, c]:` does not match. This prevents surprising behavior when a function accepts either a string or a list.

## Mapping Patterns

Mapping patterns match dictionaries. They check that the listed keys exist and match the sub-patterns, and they ignore any extra keys. This makes them ideal for JSON-like data, where records often carry more fields than you care about.

Use `**rest` to capture the remaining items.

```python
def handle_event(event):
    match event:
        case {"type": "click", "pos": (x, y)}:
            return f"click at {x},{y}"
        case {"type": "key", "key": "q"}:
            return "quit key pressed"
        case {"type": "key", "key": str(k)}:
            return f"key {k}"
        case {"type": "user", "name": name, **extra}:
            return f"user {name} with extras {sorted(extra)}"
        case {"type": t}:
            return f"unhandled event type {t}"
        case _:
            return "not an event"


events = [
    {"type": "click", "pos": (10, 20)},
    {"type": "key", "key": "q"},
    {"type": "key", "key": "z"},
    {"type": "user", "name": "Ada", "age": 36, "admin": True},
    {"type": "scroll", "delta": -3},
    {"kind": "mystery"},
    42,
]

for ev in events:
    print(handle_event(ev))
```

Look at `str(k)` in the third case. This is a *class pattern* used as a type check: it matches only if the value is a `str`, and the single positional sub-pattern `k` captures the value itself. The built-in types `int`, `float`, `str`, `bool`, `list`, `dict`, `tuple`, `set`, `bytes`, and a few others work this way.

Order matters here. The specific `"q"` case comes before the general `str(k)` case; reversing them would make the specific case unreachable.

## Class Patterns, Dataclasses, and Guards

Class patterns look like constructor calls: `Point(x=0, y=0)`. Python checks `isinstance` and then looks up the named attributes. For dataclasses, positional sub-patterns work too, because dataclasses automatically define `__match_args__`, which tells Python the order of the fields.

Patterns nest freely, so you can destructure a whole tree in a single `case`.

```python
from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float


@dataclass
class Circle:
    center: Point
    radius: float


@dataclass
class Rect:
    top_left: Point
    width: float
    height: float


def describe(shape):
    match shape:
        case Circle(center=Point(x=0, y=0), radius=r):
            return f"circle at the origin, radius {r}"
        case Circle(Point(x, y), r) if r > 100:
            return f"huge circle at {x},{y}"
        case Circle(_, r):
            return f"circle with radius {r}"
        case Rect(Point(x, y), w, h) if w == h:
            return f"square of side {w} at {x},{y}"
        case Rect(_, w, h):
            return f"rectangle {w} by {h}"
        case Point(x, 0):
            return f"point on the x axis at {x}"
        case Point(0, y):
            return f"point on the y axis at {y}"
        case Point():
            return "point somewhere else"
        case _:
            return "not a shape"


def area(shape):
    match shape:
        case Circle(_, r):
            return round(3.14159 * r * r, 2)
        case Rect(_, w, h):
            return w * h
        case _:
            raise TypeError(f"no area for {shape!r}")


shapes = [
    Circle(Point(0, 0), 5),
    Circle(Point(3, 4), 250),
    Circle(Point(1, 1), 2),
    Rect(Point(0, 0), 4, 4),
    Rect(Point(2, 3), 4, 6),
    Point(7, 0),
    Point(0, 9),
    Point(2, 2),
    "banana",
]

for s in shapes:
    print(describe(s))

print(area(Circle(Point(0, 0), 2)))
print(area(Rect(Point(0, 0), 3, 5)))
```

In `Circle(center=Point(x=0, y=0), radius=r)`, the literals `0` match by equality, so `Point(0.0, 0.0)` would also match. The guard in the second case, `if r > 100`, runs only after the structure matched and `r` was bound. If the guard fails, Python simply moves on to the next case.

For plain classes that are not dataclasses, you can still use keyword patterns such as `Point(x=1)`. To allow positional sub-patterns, define `__match_args__ = ("x", "y")` on the class.

## A Practical Example: A Tiny Expression Evaluator

Pattern matching shines when processing tree-shaped data. Here, expressions are nested tuples, and one function evaluates them by recursion.

```python
def evaluate(expr, env=None):
    env = env or {}
    match expr:
        case int() | float():
            return expr
        case str(name):
            return env[name]
        case ("neg", operand):
            return -evaluate(operand, env)
        case ("add", left, right):
            return evaluate(left, env) + evaluate(right, env)
        case ("sub", left, right):
            return evaluate(left, env) - evaluate(right, env)
        case ("mul", left, right):
            return evaluate(left, env) * evaluate(right, env)
        case ("div", left, right):
            divisor = evaluate(right, env)
            if divisor == 0:
                raise ZeroDivisionError("division by zero in expression")
            return evaluate(left, env) / divisor
        case ("let", str(name), value, body):
            new_env = {**env, name: evaluate(value, env)}
            return evaluate(body, new_env)
        case _:
            raise ValueError(f"bad expression: {expr!r}")


program = ("let", "x", 5, ("mul", ("add", "x", 3), ("neg", 2)))
print(evaluate(program))
print(evaluate(("div", 10, 4)))

try:
    evaluate(("div", 1, ("sub", 2, 2)))
except ZeroDivisionError as exc:
    print("error:", exc)

try:
    evaluate(("pow", 2, 3))
except ValueError as exc:
    print("error:", exc)
```

Each `case` reads almost like a grammar rule. The alternative `int() | float()` checks types without binding anything, and `("let", str(name), value, body)` both validates and unpacks a four-part tuple in one line.

## Quick Reference

- `case 1 | 2:` matches either literal.
- `case _:` is the wildcard and never binds.
- `case name:` captures anything, so place it last.
- `case [a, *rest]:` matches sequences, but not strings.
- `case {"k": v, **rest}:` matches mappings with at least those keys.
- `case Cls(attr=p)` or `Cls(p)` matches by type and attributes.
- `case pattern if condition:` adds a guard.
- `case pattern as name:` binds the whole match.
- Dotted names such as `Color.RED` compare by value; bare names capture.

Use pattern matching when the *shape* of data drives your logic. For a simple two-way choice, a plain `if` is still clearer.