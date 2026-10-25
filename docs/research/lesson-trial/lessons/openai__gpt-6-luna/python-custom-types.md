# Defining and Using Your Own Data Types

A program often starts with simple values: numbers, strings, and lists. As it grows, you may find that a few values belong together and need their own rules. A `Point` might have an `x` and a `y`; a `Task` might have a title and a status. Defining a type lets you describe that data and the operations that make sense for it.

In Python, you define most custom types with a `class` statement. Calling the class creates an *instance* of that type. An instance stores its own data, while methods define operations that work with that data. Type hints can document the intended values and help tools check your code, but Python does not enforce them automatically at runtime.

## Start with a class

The first example defines a `Point`. Its `__init__` method runs when a new instance is created. The parameter `self` refers to that instance. Assigning `self.x` and `self.y` stores values on it, so each point has its own coordinates.

A method is a function defined inside a class. When you call `first.distance_to(second)`, Python passes `first` as `self`. The `math.hypot` function calculates the distance between two coordinate offsets.

```python
import math


class Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

    def distance_to(self, other: "Point") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


first = Point(1, 2)
second = Point(4, 6)

print(first.x, first.y)
print(first.distance_to(second))
```

The annotations say that the coordinates should be floats and that `distance_to` expects another `Point`. They do not stop a caller from passing, for example, a string. If invalid values would cause trouble, check them in your code. Whether to add checks depends on what your type promises and how it is used.

A class can also define `__repr__`, a method that returns a useful text representation for debugging. Python calls it when a representation of the object is requested, such as by `repr(point)`. You do not need to write one for every class, but a readable representation makes objects easier to inspect.

## Use a dataclass for data-focused types

When a class mainly holds data, writing `__init__` by hand can be repetitive. The standard-library `dataclasses` module can generate an initializer and other useful methods for you. Use `@dataclass` above a class and declare its fields with type annotations.

The next example uses a *frozen* dataclass. Frozen instances cannot normally have their fields reassigned after creation. This is useful for values that should stay stable, such as a rectangle's dimensions. The `__post_init__` method runs after the generated initializer, so it is a convenient place to check a rule that applies to every instance.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Rectangle:
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Rectangle dimensions must be positive")

    @property
    def area(self) -> float:
        return self.width * self.height


shape = Rectangle(3, 4)
print(shape)
print(shape.area)
```

The generated representation makes `print(shape)` informative. The `@property` decorator lets you access `area` like a field, with `shape.area`, while still calculating its value in a method. Use a property when an attribute-like value is derived from other data. If a calculation needs arguments or has noticeable side effects, an ordinary method is usually clearer.

The validation raises `ValueError`, a standard exception for a value that has the right general kind but is not allowed here. Since the dataclass is frozen, its fields cannot be reassigned in the usual way. This makes the dimensions reliable inputs for the area calculation.

## Put behavior and rules in the type

A useful custom type does more than collect fields. It can keep related behavior and rules together. For example, a task has a title and a status. Rather than letting every part of a program change the status however it likes, give the type a method that permits only the transitions you want.

An `Enum` represents a fixed set of named choices. It prevents status values from being arbitrary strings such as `"in progess"` with a typo. The `Task` below allows a task to move from `TODO` to `IN_PROGRESS`, and then to `DONE`. Trying an unsupported transition raises an error.

```python
from dataclasses import dataclass
from enum import Enum


class Status(Enum):
    TODO = "todo"
    IN_PROGRESS = "in progress"
    DONE = "done"


@dataclass
class Task:
    title: str
    status: Status = Status.TODO

    def start(self) -> None:
        if self.status is not Status.TODO:
            raise ValueError("Only a task to do can be started")
        self.status = Status.IN_PROGRESS

    def finish(self) -> None:
        if self.status is not Status.IN_PROGRESS:
            raise ValueError("Only an in-progress task can be finished")
        self.status = Status.DONE


task = Task("Write a lesson")
task.start()
task.finish()
print(task.title, task.status.value)
```

This dataclass is not frozen, because its status is meant to change. The transition methods make those changes explicit. Other code can still assign directly to `task.status`, so this design is a convention rather than a security boundary. If stronger control is important, you can use properties and private-by-convention attributes, but start with the simplest design that meets your needs.

The `is` comparisons are appropriate for enum members: each named member is a single constant. The `.value` attribute gets the associated string for display or storage. In your own programs, keep the enum member as long as possible; convert to its string value when you need to communicate with a format that requires text.

## Combine types to model a small domain

Types can contain instances of other types. This is called *composition*. A cart, for example, can be made of lines, and each line can refer to a product. Keeping those pieces separate gives each one a clear purpose: a product describes an item, a cart line records a quantity, and the cart manages its lines and calculates a total.

The final example also defines `__len__`. This special method lets `len(cart)` report the number of lines. Special methods connect your types to familiar Python operations. Add one when the operation has a clear, conventional meaning for your type; do not add special methods just to make a class look more elaborate.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    name: str
    price: float


@dataclass(frozen=True)
class CartLine:
    product: Product
    quantity: int

    @property
    def subtotal(self) -> float:
        return self.product.price * self.quantity


class Cart:
    def __init__(self) -> None:
        self.lines: list[CartLine] = []

    def add(self, product: Product, quantity: int = 1) -> None:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        self.lines.append(CartLine(product, quantity))

    def total(self) -> float:
        return sum(line.subtotal for line in self.lines)

    def __len__(self) -> int:
        return len(self.lines)


cart = Cart()
cart.add(Product("Notebook", 3.50), 2)
cart.add(Product("Pen", 1.25))
print(len(cart))
print(f"Total: ${cart.total():.2f}")
```

This example uses floats for prices to keep the lesson focused, but real financial software should usually use `decimal.Decimal` to avoid rounding surprises from binary floating-point arithmetic. The important design idea is that the cart uses `Product` and `CartLine` rather than storing unrelated values in parallel lists. Each line keeps its product and quantity together.

The `Cart` itself is a regular class because it has a changing list of lines and a small set of operations. The `Product` and `CartLine` are frozen dataclasses because they are simple records that should not change after creation. Choosing a regular class or a dataclass depends on the role of the type; neither is always the right answer.

## A practical design checklist

When you introduce a type, decide what one instance represents. Give it fields that describe that thing, then put closely related operations beside those fields. Add validation for rules that must always hold. Use an enum for a fixed set of alternatives, and use composition when one kind of object is naturally made from other objects.

Prefer a small, clear interface: the methods and properties that other code is meant to use. You do not need a class for every collection of values. A tuple, dictionary, or plain function may be enough for a short-lived or very simple case. A custom type becomes valuable when it gives data a meaningful name, keeps related behavior together, or makes invalid states harder to create.

As your program changes, you can add methods and checks to the type without repeating the same rules in every caller. That is the central benefit of defining your own data types: the program can express its ideas directly, and each type can help keep those ideas consistent.