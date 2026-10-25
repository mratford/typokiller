# Defining Your Own Data Types in Python

Python ships with types like `int`, `str`, and `list`. Real programs often need types that describe their own concepts, such as a point on a grid, a bank account, or a playing card. In Python you create these with **classes**. A class is a blueprint, and each object made from it is an **instance**.

This Lesson walks through the basics: defining a class, writing methods, using special methods that make your type behave like built-in types, and building small types with `dataclasses`. Type the examples as you go. Each one is a complete script you can run.

## Defining a Class

A class begins with the `class` keyword. The `__init__` method runs when you create an instance and sets up its starting state. The first parameter, conventionally named `self`, refers to the instance being created.

```python
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def describe(self):
        return f"Point at ({self.x}, {self.y})"


p = Point(3, 4)
q = Point(-1, 7)

print(p.describe())
print(q.describe())
print(p.x + q.x)
```

Each instance stores its own `x` and `y` attributes. Methods such as `describe` receive `self` automatically, so `p.describe()` is the same as calling `Point.describe(p)`.

## Methods That Change State

Methods can also update an instance. Here a simple bank account tracks a balance and refuses withdrawals that would overdraw it.

```python
class Account:
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


acct = Account("Ada", 100)
acct.deposit(50)
acct.withdraw(30)
print(acct.owner, acct.balance)

try:
    acct.withdraw(1000)
except ValueError as err:
    print("Error:", err)
```

Putting the validation inside the type means every caller gets the same rules. The rest of the program does not need to remember them.

## Special Methods: Making Your Type Behave Naturally

Methods whose names begin and end with double underscores are **special methods**. Python calls them for operators and built-in functions. Defining `__add__` lets `+` work on your objects, `__repr__` controls how the object prints in a debugger, and `__eq__` controls `==`.

```python
class Vector:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __add__(self, other):
        return Vector(self.x + other.x, self.y + other.y)

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

    def __repr__(self):
        return f"Vector({self.x}, {self.y})"


a = Vector(1, 2)
b = Vector(3, 4)
total = a + b
print(total)
print(total == Vector(4, 6))
print(a == b)
```

The `__repr__` method should return a string that looks like the code that would recreate the object. It is what you see when you print a list of your objects, so writing it makes debugging much easier.

## Using dataclasses

Many types only hold data. Writing `__init__`, `__repr__`, and `__eq__` by hand for each one is repetitive. The `dataclasses` module from the standard library generates them from annotated fields.

```python
from dataclasses import dataclass


@dataclass
class Card:
    rank: str
    suit: str
    value: int = 0


hand = [Card("A", "spades", 11), Card("7", "hearts", 7)]
print(hand[0])
print(hand[0] == Card("A", "spades", 11))
total = sum(card.value for card in hand)
print("Total:", total)
```

The decorator `@dataclass` reads the annotations `rank`, `suit`, and `value`, then writes an `__init__`, a readable `__repr__`, and an `__eq__` for you. Fields can have default values, as `value` does here.

## Frozen Types and Immutability

Sometimes a value should never change after creation, such as a coordinate or a configuration setting. Pass `frozen=True` to `@dataclass`. Attempting to assign to a field then raises an error.

```python
from dataclasses import dataclass, FrozenInstanceError


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lon: float


home = Coordinate(51.5, -0.12)
print(home)

try:
    home.lat = 10.0
except FrozenInstanceError:
    print("Coordinates are read-only")

places = {home: "London"}
print(places[Coordinate(51.5, -0.12)])
```

Frozen dataclasses are also hashable, so you can use them as dictionary keys or store them in sets. Mutable objects cannot do this safely, because their hash could change after insertion.

## Key Points

- A class defines a type, and `__init__` sets up each new instance.
- Methods take `self` as their first parameter and can read or change instance state.
- Special methods such as `__add__`, `__eq__`, and `__repr__` let your types work with operators and built-in functions.
- `@dataclass` removes boilerplate for data-holding types.
- `@dataclass(frozen=True)` creates immutable, hashable types suitable for dictionary keys.

Practice by defining a class for a playing card deck, a temperature that supports comparison, or a shopping cart with methods to add and total items.