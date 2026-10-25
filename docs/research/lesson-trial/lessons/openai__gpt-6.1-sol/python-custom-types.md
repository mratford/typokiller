# Defining and Using Your Own Data Types

Python provides useful built-in types, including integers, strings, lists, and dictionaries. These types describe the shape of a value, but they do not always explain its meaning. A pair of numbers might represent a screen position, a measurement, or a price range.

Your own data types give those values a clear identity. They can group related information, provide useful operations, and reject values that do not make sense. Instead of remembering which dictionary keys belong together, you can work with an object that represents a specific concept.

This lesson introduces ordinary classes, data classes, enumerations, and immutable value objects. Each example is a complete Python 3.14 script that runs independently.

## 1. Define a Class with State and Behavior

A class defines a new type. An instance is one particular object of that type. If `Rectangle` is a class, a rectangle with width 4 and height 3 is an instance.

Classes usually combine state and behavior. State is the information an object stores. Behavior consists of methods: functions defined inside the class that operate on its instances.

The `__init__` method initializes a new instance. Its first parameter, conventionally named `self`, refers to that instance. Assignments such as `self.width = width` store attributes on the object.

```python
import math


class Rectangle:
    def __init__(self, width: float, height: float) -> None:
        if not math.isfinite(width) or not math.isfinite(height):
            raise ValueError("dimensions must be finite")
        if width <= 0 or height <= 0:
            raise ValueError("dimensions must be positive")
        self.width = width
        self.height = height

    def area(self) -> float:
        return self.width * self.height

    def perimeter(self) -> float:
        return 2 * (self.width + self.height)

    def scaled(self, factor: float) -> "Rectangle":
        return Rectangle(self.width * factor, self.height * factor)

    def __repr__(self) -> str:
        return f"Rectangle(width={self.width!r}, height={self.height!r})"


def main() -> None:
    card = Rectangle(4.0, 3.0)
    poster = card.scaled(2.0)

    print(card)
    print(f"Area: {card.area():.1f}")
    print(f"Perimeter: {card.perimeter():.1f}")
    print(poster)

    try:
        Rectangle(-1.0, 2.0)
    except ValueError as error:
        print(f"Rejected: {error}")


if __name__ == "__main__":
    main()
```

Calling `Rectangle(4.0, 3.0)` creates and initializes an instance. Calling `card.area()` invokes a method, with Python supplying `card` as its `self` argument.

The `scaled` method returns a new rectangle rather than changing the original. That choice makes its behavior easier to follow. The initializer also validates the new dimensions, so invalid scaling results are rejected.

The special method `__repr__` provides a useful developer-facing representation. Without it, printing an ordinary instance usually reveals little about its contents.

Validation in `__init__` protects construction, but this class still allows later attribute assignment. A caller could set `card.width` to a negative number. If maintaining an invariant matters throughout an object's lifetime, consider controlled updates through properties or an immutable design.

## 2. Use a Data Class for Structured Records

Many custom types primarily hold related fields. Writing their initialization, representation, and equality methods by hand is repetitive. The `dataclasses` module generates those methods from annotated fields.

A data class remains a normal class. You can add validation and methods whenever the record needs behavior. The generated initializer calls `__post_init__`, which is a convenient place to check the initial field values.

This example represents a product and tracks tags attached to it.

```python
from dataclasses import dataclass, field


@dataclass
class Product:
    name: str
    unit_price_cents: int
    quantity: int = 0
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be blank")
        if self.unit_price_cents < 0:
            raise ValueError("price must not be negative")
        if self.quantity < 0:
            raise ValueError("quantity must not be negative")

    def stock_value_cents(self) -> int:
        return self.unit_price_cents * self.quantity

    def restock(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("restock amount must be positive")
        self.quantity += amount


def main() -> None:
    pencil = Product("Pencil", 75, quantity=12)
    notebook = Product("Notebook", 250)

    pencil.tags.append("stationery")
    pencil.restock(8)

    print(pencil)
    print(f"Stock value: {pencil.stock_value_cents()} cents")
    print(f"Notebook tags: {notebook.tags}")

    matching = Product("Notebook", 250)
    print(f"Equal records: {notebook == matching}")


if __name__ == "__main__":
    main()
```

The generated initializer accepts the fields in declaration order. Fields with defaults may be omitted, and keyword arguments make calls more readable.

The `default_factory=list` expression creates a separate list for each instance. This matters because mutable defaults must not accidentally become shared state. Adding a tag to the pencil does not change the notebook.

By default, data classes compare instances of the same class using their fields. The two notebook objects compare equal even though they are distinct objects. Equality answers whether their recorded values match; identity, tested with `is`, answers whether they are the very same object.

The annotations describe intended types, but they do not enforce those types at runtime. Validation here checks selected business rules. It is not a complete runtime type checker. Integer cents also keep this example's price calculations exact without introducing floating-point rounding.

## 3. Represent a Fixed Set of Choices with an Enum

Some values should come from a small, fixed vocabulary. A task status, for example, should not be an arbitrary string.

An enumeration defines named members of a distinct type. Using members such as `Status.RUNNING` avoids scattered string literals and makes valid choices easy to discover.

An enum defines the available states, but it does not automatically define valid transitions. The surrounding class must enforce those rules.

```python
from dataclasses import dataclass, field
from enum import Enum, auto


class Status(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETE = auto()


@dataclass
class Task:
    title: str
    status: Status = field(default=Status.PENDING, init=False)

    def start(self) -> None:
        if self.status is not Status.PENDING:
            raise ValueError("only a pending task can start")
        self.status = Status.RUNNING

    def finish(self) -> None:
        if self.status is not Status.RUNNING:
            raise ValueError("only a running task can finish")
        self.status = Status.COMPLETE

    def describe(self) -> str:
        match self.status:
            case Status.PENDING:
                return f"{self.title}: waiting"
            case Status.RUNNING:
                return f"{self.title}: in progress"
            case Status.COMPLETE:
                return f"{self.title}: finished"
        raise ValueError("unknown status")


def main() -> None:
    task = Task("Write release notes")
    print(task.describe())

    task.start()
    print(task.describe())

    task.finish()
    print(task.describe())

    try:
        task.start()
    except ValueError as error:
        print(f"Rejected: {error}")


if __name__ == "__main__":
    main()
```

The `auto()` helper supplies distinct member values. Here, their exact numeric values are irrelevant; the meaningful interface consists of the member names.

Enum members can be compared with `is` because each member has a unique identity. The `match` statement selects a description based on the current member.

The field option `init=False` keeps status out of the generated initializer. Every task therefore begins pending through normal construction. As with the earlier mutable classes, direct attribute assignment can still bypass the transition methods.

This separation is useful: the enum describes which states exist, while the task methods describe what actions are allowed.

## 4. Build Immutable Value Objects

A value object represents something whose meaning comes from its contents. Coordinates, dates, and measurements often fit this pattern. Two points with the same coordinates should usually compare equal.

A frozen data class prevents normal reassignment of its fields. Combined with suitable immutable fields, it makes a convenient value object. Operations can return new values instead of changing existing ones.

Special methods also let your type participate in familiar Python syntax. Define them only when the operation has a clear meaning.

```python
from dataclasses import dataclass
from types import NotImplementedType


@dataclass(frozen=True)
class Point:
    x: int
    y: int

    def __add__(self, other: object) -> "Point | NotImplementedType":
        if not isinstance(other, Point):
            return NotImplemented
        return Point(self.x + other.x, self.y + other.y)

    def manhattan_distance(self, other: "Point") -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)


def main() -> None:
    origin = Point(0, 0)
    step = Point(2, 3)
    destination = origin + step

    print(f"Origin: {origin}")
    print(f"Destination: {destination}")
    print(f"Distance: {origin.manhattan_distance(destination)}")

    labels = {origin: "start", destination: "finish"}
    print(f"Lookup: {labels[Point(2, 3)]}")

    visited = {origin, destination, Point(2, 3)}
    print(f"Unique points: {len(visited)}")


if __name__ == "__main__":
    main()
```

The `__add__` method implements `+`. Returning `NotImplemented` for an unsupported operand lets Python try the other operand's reflected operation before reporting an error. It is a special return value, not an exception to raise.

Because this data class is frozen and uses the default equality behavior, it receives a generated hash method. Its integer fields are hashable, so points work as dictionary keys and set elements. An equal point retrieves the same dictionary entry.

Frozen does not mean deeply immutable. If a frozen class contains a list, the list can still change internally. Prefer immutable field values when stable equality and hashing are required.

## Choosing the Right Design

Start with the simplest type that communicates your intent. Use a plain class when custom behavior dominates. Use a data class when named fields and value-based equality are central. Use an enum for a closed set of named choices.

Combine these tools rather than forcing every concept into one pattern. A data class can contain enum members, and a larger object can contain several smaller value objects.

Finally, decide what equality, mutation, and validation should mean before adding convenience methods. A good custom type does more than shorten code: it makes valid operations obvious and mistakes harder to express.