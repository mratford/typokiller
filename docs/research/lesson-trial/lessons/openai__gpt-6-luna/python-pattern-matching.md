# Pattern matching

Python's `match` statement compares a value against a series of patterns and runs the first matching `case` suite. It was added in Python 3.10. It is useful when a value can have several shapes, such as a command, a message, or a record. Pattern matching can check structure and bind parts of a value to names at the same time.

A `match` statement is not a C-style switch statement. Cases do not fall through: after a pattern matches and its optional guard succeeds, Python runs that case's suite and leaves the `match` statement. If no case matches, nothing happens. Include a final catch-all case when the code should handle every possible value.

## Literal patterns and the wildcard

A literal pattern matches a value such as an integer, string, `True`, `False`, or `None`. The wildcard pattern `_` matches anything and does not bind a name. Put more specific patterns before broader ones, or the broader case may make later cases unreachable in practice.

```python
def describe(value):
    match value:
        case 0:
            return "zero"
        case "ready":
            return "ready"
        case None:
            return "missing"
        case _:
            return "something else"


for item in (0, "ready", None, 7):
    print(describe(item))
```

This script prints one description for each item. A literal pattern for an ordinary value uses equality to check for a match. The patterns `True`, `False`, and `None` are special: they match those exact singleton values. For example, `case True` does not also match the integer `1`.

The names in a pattern usually capture values rather than refer to existing variables. A pattern like `case name:` matches anything and binds it to `name`, so it is not a test for a variable that happens to be called `name`. Use a literal, a class pattern, or a qualified constant such as `Colors.red` when you want to test a particular value. A dotted name is looked up; a bare name is a capture.

## Sequence patterns

A sequence pattern describes the shape of a sequence. For example, `[first, second]` matches a sequence with exactly two items and binds them to `first` and `second`. Brackets and parentheses can be used for sequence patterns; the pattern does not require the input to use the same kind of brackets. Strings and bytes are not matched as sequences by sequence patterns, so a string such as `"go"` will not match `["g", "o"]`.

A starred name collects remaining items into a list. It can appear only once in a sequence pattern. A guard adds a condition after the structure has matched. The `if` condition is checked only after the pattern succeeds.

```python
def describe_packet(packet):
    match packet:
        case ["move", x, y] if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return f"move to ({x}, {y})"
        case ["say", *words]:
            return "say: " + " ".join(words)
        case ["quit"] | ("quit",):
            return "quit"
        case _:
            return "unknown packet"


packets = [
    ["move", 3, 4],
    ("say", "hello", "there"),
    ["quit"],
    ["move", "left", 4],
]

for packet in packets:
    print(describe_packet(packet))
```

The `|` operator in a pattern means “or.” Each alternative in an OR pattern must bind the same names. In the `quit` case, neither alternative binds a name, so they are valid together. The order of cases matters: if an earlier case accepts a value, later cases are not tried.

The `say` pattern accepts a sequence beginning with `"say"` and captures any remaining items in `words`. It also accepts a packet containing only `"say"`; in that case, `words` is empty. If that is not valid for an application, add a guard such as `if words`.

## Mapping patterns

A mapping pattern matches required keys and their values. It does not require an exact set of keys: extra keys are allowed. This makes it handy for reading dictionaries that may contain additional fields.

```python
def describe_message(message):
    match message:
        case {"kind": "user", "name": str(name), "active": True}:
            return f"active user: {name}"
        case {"kind": "score", "value": value} if isinstance(value, int) and value >= 90:
            return "high score"
        case {"kind": "score", "value": value} if isinstance(value, int):
            return "ordinary score"
        case {"kind": kind}:
            return f"other message: {kind}"
        case _:
            return "invalid message"


messages = [
    {"kind": "user", "name": "Ari", "active": True, "id": 12},
    {"kind": "score", "value": 95},
    {"kind": "score", "value": 62},
    {"kind": "notice"},
    [],
]

for message in messages:
    print(describe_message(message))
```

The pattern `str(name)` is a class pattern: it requires a string and binds that string to `name`. In contrast, the pattern `"kind": kind` captures whatever value is stored under the `"kind"` key. The final `case _` handles values that do not match any mapping pattern.

The two score cases use guards to check the captured value. The `isinstance` test comes first because `and` evaluates from left to right: the comparison with `90` is reached only when `value` is an integer. Guards are ordinary Python expressions, so they can perform checks that are awkward to express in the pattern itself. Prefer guards without side effects, since readers should not have to wonder whether a condition changes program state.

## Class patterns

A class pattern checks whether an object is an instance of a class and can match selected attributes. Dataclasses work well with positional class patterns: a dataclass supplies the field order through `__match_args__`. Keyword patterns name attributes explicitly and can be easier to read if the class has many fields.

```python
from dataclasses import dataclass


@dataclass
class Point:
    x: int
    y: int


def describe_point(point):
    match point:
        case Point(0, 0):
            return "origin"
        case Point(x, y) if x == y:
            return f"diagonal point ({x}, {y})"
        case Point(x=0, y=y):
            return f"on the vertical axis at {y}"
        case Point(x=x, y=y):
            return f"point ({x}, {y})"
        case _:
            return "not a point"


for point in (Point(0, 0), Point(3, 3), Point(0, 5), "point"):
    print(describe_point(point))
```

`Point(0, 0)` checks the class and both positional attributes. The second case captures both coordinates and then uses a guard to check whether they are equal. The keyword form, `Point(x=0, y=y)`, checks the `x` attribute and captures `y`. The final class pattern captures any point that has not matched earlier. A string is not a `Point`, so it reaches the wildcard case.

Class patterns can also be nested. For example, a pattern can check that a message has an `author` attribute whose value matches a particular class pattern. Use nesting when it makes the expected structure clearer, and break complex decisions into helper functions when a pattern becomes difficult to scan.

## Bindings, order, and style

When a pattern matches, any names it captures become available in that case suite. For example, in `[first, second]`, the names are not tests against earlier values: they are assigned from the matched sequence. Do not rely on a name's value after a case that did not match. Treat captured names as local to the successful case.

Patterns are declarative: they describe a shape to check, rather than a series of operations to perform. They cannot contain arbitrary expressions such as function calls or arithmetic calculations in place of patterns. Use a guard for a condition, or calculate a value before the `match` if that makes the logic more readable.

Choose the pattern form that communicates the decision:

- Use literal patterns for a small set of known values.
- Use sequence patterns when position and length matter.
- Use mapping patterns when keys matter and extra keys may be present.
- Use class patterns when the object's type and attributes matter.
- Use guards for additional conditions.
- Use `_` as a final catch-all when all other inputs need a defined result.

A good `match` statement makes the alternatives visible at a glance. Keep cases ordered from specific to general, give captured values clear names, and make the fallback behavior intentional.