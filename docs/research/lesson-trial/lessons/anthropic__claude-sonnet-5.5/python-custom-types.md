# Defining and Using Your Own Data Types in Python

Built-in types like `int`, `str`, and `dict` carry you a long way, but real programs model real things: points, invoices, playing cards, temperatures. When you define your own type, you give a concept a name, a shape, and behavior. Your code then reads like the problem it solves.

In this Lesson you will meet four tools: plain classes, dataclasses, enums, and named behavior through methods and special methods. Each example is a complete script you can type and run.

## Why Define a Type?

Consider representing a point as a tuple: `(3, 4)`. Which is x and which is y? Can you add two of them? Can you print them nicely? A tuple cannot answer these questions, but a custom type can.

A custom type bundles two things:

- **Data**: the values that describe one instance (attributes).
- **Behavior**: the operations that make sense for that data (methods).

## A Plain Class

The `class` statement defines a new type. The `__init__` method runs when you create an instance, and `self` refers to the instance being built.

```python
class Account:
    """A simple bank account."""

    def __init__(self, owner, balance=0):
        self.owner = owner
        self.balance = balance

    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("deposit must be positive")
        self.balance += amount

    def withdraw(self, amount):
        if amount > self.balance:
            raise ValueError("insufficient funds")
        self.balance -= amount

    def __repr__(self):
        return f"Account(owner={self.owner!r}, balance={self.balance})"


def main():
    acct = Account("Ada", 100)
    acct.deposit(50)
    acct.withdraw(30)
    print(acct)

    try:
        acct.withdraw(1000)
    except ValueError as err:
        print("Error:", err)

    print(isinstance(acct, Account))


main()
```

Notice a few things. Methods validate their input, so the object protects its own rules. The `__repr__` method returns an unambiguous string used by `print` fallbacks and by the interactive prompt. Define it on almost every class; it makes debugging far easier.

Also note `isinstance`, which checks whether a value belongs to a type. Prefer it over comparing `type(x)` directly, because it respects inheritance.

## Dataclasses: Less Boilerplate

Many classes just hold data. Writing `__init__`, `__repr__`, and `__eq__` by hand is repetitive. The `dataclasses` module generates them from type-annotated fields.

```python
from dataclasses import dataclass, field


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int = 0
    patch: int = 0

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass
class Project:
    name: str
    tags: list[str] = field(default_factory=list)
    version: Version = Version(1)

    def add_tag(self, tag):
        if tag not in self.tags:
            self.tags.append(tag)


def main():
    v1 = Version(1, 2, 3)
    v2 = Version(1, 10)
    print(v1, v2)
    print(v1 < v2)
    print(v1 == Version(1, 2, 3))

    proj = Project("trainer")
    proj.add_tag("python")
    proj.add_tag("typing")
    proj.add_tag("python")
    print(proj)

    versions = [v2, v1, Version(0, 9)]
    print([str(v) for v in sorted(versions)])


main()
```

Key points about this example:

- `frozen=True` makes instances immutable. Assigning to a field raises an error, and the instance becomes hashable, so it can be a dictionary key or set member.
- `order=True` generates comparison methods that compare fields in order. That is why `sorted` works on versions.
- A mutable default such as a list must use `field(default_factory=list)`. Writing `tags: list = []` would be rejected, because every instance would otherwise share one list.
- The default `Version(1)` is safe as a shared default because it is frozen.

Type annotations in dataclasses are not enforced at runtime. They document intent and help tools, but Python will not stop you from passing a string where an `int` is declared.

## Enums: A Fixed Set of Choices

When a value must be one of a few known options, use an `Enum`. Compared with bare strings or numbers, enums prevent typos and make intent clear.

```python
from enum import Enum, auto


class Status(Enum):
    PENDING = auto()
    ACTIVE = auto()
    DONE = auto()


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


def describe(status):
    match status:
        case Status.PENDING:
            return "waiting to start"
        case Status.ACTIVE:
            return "in progress"
        case Status.DONE:
            return "finished"


def main():
    s = Status.ACTIVE
    print(s)
    print(s.name, s.value)
    print(describe(s))

    print(Priority(3))
    print(Priority["LOW"])
    print(Priority.HIGH.value > Priority.LOW.value)

    for status in Status:
        print(status.name.lower())


main()
```

Members have a `name` and a `value`. You can look one up by value, `Priority(3)`, or by name, `Priority["LOW"]`. Iterating over the class yields every member in definition order. Use `auto()` when the actual values do not matter, and explicit values when they carry meaning, such as a priority level.

Compare members with `is` or `==`. Do not compare an enum member to a raw number; `Priority.LOW == 1` is `False` for a plain `Enum`.

## Special Methods: Making Types Feel Native

Python lets your types work with operators and built-in functions through special methods, often called dunder methods because of the double underscores. Implement the ones that make sense and your type blends into the language.

```python
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Vector:
    x: float
    y: float

    def __add__(self, other):
        if not isinstance(other, Vector):
            return NotImplemented
        return Vector(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        if not isinstance(other, Vector):
            return NotImplemented
        return Vector(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar):
        if not isinstance(scalar, (int, float)):
            return NotImplemented
        return Vector(self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    def __abs__(self):
        return math.hypot(self.x, self.y)

    def __bool__(self):
        return bool(self.x or self.y)

    def __iter__(self):
        yield self.x
        yield self.y


def main():
    a = Vector(3, 4)
    b = Vector(1, 2)

    print(a + b)
    print(a - b)
    print(a * 2)
    print(3 * b)
    print(abs(a))
    print(bool(Vector(0, 0)))

    x, y = a
    print(x, y)

    try:
        a + 5
    except TypeError as err:
        print("TypeError:", err)


main()
```

Here is what each piece does:

- `__add__`, `__sub__`, and `__mul__` power the `+`, `-`, and `*` operators.
- Returning `NotImplemented`, rather than raising an error, tells Python to try the other operand's method and, failing that, raise a clean `TypeError`.
- `__rmul__ = __mul__` makes `3 * b` work as well as `b * 3`.
- `__abs__` supports the built-in `abs`, `__bool__` controls truthiness, and `__iter__` allows unpacking into `x, y`.

Because `Vector` is a frozen dataclass, it already has a good `__repr__`, equality, and hashing for free.

## Choosing the Right Tool

A short guide:

- Use a **dataclass** when the type mainly holds values. This is the most common case.
- Use a **plain class** when you need custom construction logic or hidden internal state, such as the `Account` above.
- Use an **Enum** when a value comes from a closed set of named options.
- Add **special methods** when operators or built-ins should work naturally with your type.

A few habits will serve you well:

1. Give each type a single, clear responsibility and a noun for a name.
2. Validate inputs at the boundary, in `__init__` or in methods, so invalid objects never exist.
3. Prefer immutability (`frozen=True`) when the values should not change. Immutable objects are easier to reason about and safe to share.
4. Always provide a useful `__repr__`. Dataclasses do this for you.

## Practice Ideas

Try extending the examples on your own:

- Add an `interest` method to `Account` and a transaction history list.
- Create a `Task` dataclass that uses both `Status` and `Priority`, then sort a list of tasks by priority.
- Give `Vector` a `dot` method and a `__neg__` method.

Defining your own types is where programming starts to feel like modeling. Name the concepts in your problem, give them data and behavior, and the rest of your code becomes shorter and clearer.