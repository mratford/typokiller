# Pattern Matching in Python

Structural pattern matching lets you choose behavior based on both the value and the shape of an object. Introduced in Python 3.10, it is available in Python 3.14 through the `match` and `case` statements.

A pattern can recognize a literal value, unpack a sequence, inspect selected dictionary entries, or extract attributes from an object. Patterns can also bind names for use in the selected case.

This makes matching useful when a program handles several kinds of structured data. Instead of repeatedly testing types, checking lengths, and assigning temporary variables, you can often express the expected structure directly.

The examples below are complete scripts. Each uses only the standard library and runs without input.

## 1. Start with literals and alternatives

A `match` statement evaluates its subject once, then tries cases from top to bottom. The first successful case runs. Python does not continue into later cases, so there is no need for a `break` statement.

Literal patterns match particular values. A vertical bar combines alternatives, and an underscore provides a wildcard that accepts anything.

```python
def describe_status(code):
    match code:
        case 200:
            return "Request succeeded."
        case 201 | 202:
            return "Request accepted or resource created."
        case 400:
            return "The request was invalid."
        case 401 | 403:
            return "Access was denied."
        case 404:
            return "The resource was not found."
        case _:
            return "No specific message is available."


def main():
    codes = [200, 201, 403, 404, 503]
    for code in codes:
        print(f"{code}: {describe_status(code)}")


if __name__ == "__main__":
    main()
```

Here, `201 | 202` means that either literal is acceptable. It does not calculate a bitwise result inside the pattern. Likewise, `_` is special pattern syntax: it matches without binding a variable.

An unconditional wildcard belongs last. Placing it earlier would make following cases unreachable, which Python rejects.

Literal patterns generally use equality comparisons. The singleton literals `None`, `True`, and `False` use identity comparisons instead. This distinction matters when values have unusual equality behavior, though ordinary application code rarely needs to think about it.

Matching does not require a default case. If nothing matches, execution simply continues after the entire `match` statement. For a function that promises to return a description, however, a final wildcard makes the intended behavior explicit.

Use literal matching when the alternatives are naturally a small, readable set. A dictionary lookup may be simpler if every value merely maps to a fixed string. Matching becomes more valuable when cases also unpack data.

## 2. Unpack sequences and add guards

Sequence patterns describe ordered structures. They can require a particular length, match fixed elements, and capture the remaining values.

A bare name in a pattern normally captures a value. It does not compare against an existing variable with the same name. This is one of the most important rules to remember.

A guard adds an ordinary Boolean condition after a structural pattern. The guard runs only when that pattern has matched and its names have been bound.

```python
def run_command(command):
    match command:
        case ["move", int(x), int(y)] if x >= 0 and y >= 0:
            return f"Moving to ({x}, {y})."
        case ["move", _, _]:
            return "Coordinates must be nonnegative integers."
        case ["say", str(message)]:
            return f"Message: {message}"
        case ["sum", *numbers] if all(
            type(number) is int for number in numbers
        ):
            return f"Total: {sum(numbers)}"
        case ["quit"]:
            return "Stopping."
        case []:
            return "The command is empty."
        case _:
            return "The command is not recognized."


def main():
    commands = [
        ["move", 4, 7],
        ("move", -1, 7),
        ["say", "Hello"],
        ["sum", 3, 5, 8],
        ["quit"],
        [],
        "quit",
    ]
    for command in commands:
        print(f"{command!r} -> {run_command(command)}")


if __name__ == "__main__":
    main()
```

Although the patterns use square brackets, they match both lists and tuples. Sequence patterns describe supported sequence structure rather than demanding the exact container type suggested by their punctuation.

Strings, bytes, and bytearrays do not match sequence patterns. Consequently, the final string `"quit"` does not match the one-element pattern `["quit"]`. Iterators and generators also do not become sequence matches merely because they can produce elements.

The pattern `int(x)` checks whether a value is an instance of `int` and captures that value as `x`. It does not convert the value. Similarly, `str(message)` checks and captures a string.

Because `bool` is a subclass of `int`, `int(x)` also accepts Boolean values. The sum guard deliberately uses `type(number) is int` to require exact integers instead. Choose the rule that fits your data.

The starred capture `*numbers` collects unmatched elements into a list. It can capture zero elements, so `["sum"]` produces a total of zero. Only one starred capture is allowed in a sequence pattern.

Case order matters here. A valid move receives special handling before the broader three-element move pattern reports invalid coordinates.

## 3. Match mappings without requiring every key

Mapping patterns are useful for dictionary-shaped records, including data decoded from JSON. They require specified keys but normally ignore additional keys.

You can combine literal keys with nested patterns for their values. A double-star capture collects entries that were not explicitly matched.

```python
def describe_event(event):
    match event:
        case {
            "type": "purchase",
            "item": str(item),
            "quantity": int(quantity),
            **extra,
        } if quantity > 0:
            fields = ", ".join(sorted(extra)) or "none"
            return (
                f"Purchase: {quantity} x {item}; "
                f"extra fields: {fields}."
            )
        case {"type": "purchase"}:
            return "The purchase record is incomplete or invalid."
        case {"type": "message", "text": str(text)}:
            return f"Message: {text}"
        case {"type": str(kind)}:
            return f"Unknown event type: {kind}."
        case _:
            return "The value is not a recognized event."


def main():
    events = [
        {
            "type": "purchase",
            "item": "notebook",
            "quantity": 3,
            "currency": "USD",
        },
        {"type": "purchase", "item": "pen", "quantity": 0},
        {"type": "message", "text": "Package shipped", "urgent": True},
        {"type": "refund"},
        {"text": "Missing event type"},
        None,
    ]
    for event in events:
        print(describe_event(event))


if __name__ == "__main__":
    main()
```

The first case requires three keys and suitable values. Its guard then checks the quantity. If the guard is false, Python continues trying later cases, so a zero quantity reaches the invalid-purchase message.

The message case accepts an additional `urgent` key without mentioning it. This behavior makes mapping patterns convenient for records that may gain optional fields over time.

The `**extra` capture is a new dictionary containing unmatched entries. If you need an exact set of keys, capture the extras and use a guard requiring that dictionary to be empty. You cannot write `**_` to discard extras; simply omit the double-star capture when they do not matter.

Patterns are not a replacement for complete validation. For example, this purchase pattern accepts `True` as a quantity because of the integer subclass rule. Real validation may also need limits, allowed item names, or relationships between fields.

Keep those additional rules explicit rather than assuming a successful structural match proves every business requirement.

## 4. Match classes and nested structures

Class patterns inspect objects using their types and attributes. Dataclasses are particularly convenient because they generate support for positional patterns.

The following script represents arithmetic expressions as small immutable objects. A recursive evaluator matches each node and evaluates its children.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Number:
    value: int


@dataclass(frozen=True)
class Add:
    left: object
    right: object


@dataclass(frozen=True)
class Multiply:
    left: object
    right: object


def evaluate(expression):
    match expression:
        case Number(value=int(value)):
            return value
        case Add(left=left, right=right):
            return evaluate(left) + evaluate(right)
        case Multiply(left, right):
            return evaluate(left) * evaluate(right)
        case _:
            raise TypeError(f"Unsupported expression: {expression!r}")


def describe(expression):
    match expression:
        case Add(Number(value=0), other) | Add(other, Number(value=0)):
            return f"Addition with zero; other value is {evaluate(other)}."
        case _:
            return f"Expression value: {evaluate(expression)}."


def main():
    expressions = [
        Add(Number(2), Multiply(Number(3), Number(4))),
        Add(Number(0), Number(9)),
        Multiply(Add(Number(1), Number(2)), Number(5)),
    ]
    for expression in expressions:
        print(describe(expression))


if __name__ == "__main__":
    main()
```

Keyword class patterns, such as `Add(left=left, right=right)`, name the attributes they inspect. They are often the clearest choice because the meaning does not depend on remembering field order.

Positional patterns, such as `Multiply(left, right)`, use the class's `__match_args__` attribute. Dataclasses generate this tuple for their ordinary initialization fields. Other classes can define it themselves.

A class pattern does not construct a new object or call its initializer. It checks the subject's type and reads the relevant attributes. Type annotations alone do not enforce runtime field types, which is why the `Number` case explicitly checks its value.

The alternative pattern in `describe` recognizes zero on either side of addition. Every branch of an alternative must bind the same set of names. Both branches bind `other`, making it safe to use in the selected case body.

## Practical habits

Prefer patterns that reveal structure at a glance. Put specific cases before broad ones, and keep guards focused on conditions that patterns cannot express directly.

Remember that bare names capture, while qualified names can represent constants. An enum member written as `Status.READY`, for example, can be used as a value pattern.

Finally, use captured variables inside the case that establishes them. Do not depend on partial bindings left behind by unsuccessful matches. Clear case-local logic makes pattern matching easier to read, test, and maintain.