# Lesson: Error Handling in Python

Programs fail. A user types letters where a number belongs, a file is missing, or a network request times out. Python reports these problems as **exceptions**. If you do nothing, the program stops with a traceback. Error handling lets your code notice the problem, respond to it, and keep running when it makes sense to do so.

In this lesson you will learn to:

- catch exceptions with `try` and `except`
- use `else` and `finally` to control what runs
- raise your own exceptions and chain them
- handle several errors at once with exception groups

## 1. Catching an exception with try and except

Put the code that might fail inside a `try` block. Put the response inside an `except` block that names the exception you expect.

```python
values = ["42", "3.14", "hello", "7"]

total = 0
for text in values:
    try:
        number = int(text)
    except ValueError:
        print(f"skipping {text!r}: not an integer")
    else:
        total += number
        print(f"added {number}")

print("total:", total)
```

Running this prints:

```
added 42
skipping '3.14': not an integer
skipping 'hello': not an integer
added 7
total: 49
```

Notice three things:

1. `int("3.14")` fails because `"3.14"` is not a whole-number string. The program does not crash. It prints a message and moves on.
2. The `else` block runs only when the `try` block finishes with no exception. Keep the success path there, not inside `try`. This way, an error raised by the success code is not accidentally caught.
3. You name the exception type, `ValueError`. Avoid a bare `except:` with no type. It catches everything, including `KeyboardInterrupt`, which makes bugs hard to find and programs hard to stop.

## 2. Several except clauses and finally

You can write several `except` clauses, each for a different exception type. Python checks them from top to bottom and runs the first one that matches. The `finally` block runs every time, whether or not an exception happened, and whether or not the function returned early. It is the right place for cleanup.

```python
def safe_divide(a, b):
    try:
        result = a / b
    except ZeroDivisionError:
        print("cannot divide by zero")
        return None
    except TypeError as exc:
        print("bad operand types:", exc)
        return None
    else:
        print("division ok")
        return result
    finally:
        print(f"attempted {a!r} / {b!r}")

print(safe_divide(10, 4))
print(safe_divide(1, 0))
print(safe_divide("x", 2))
```

The output is:

```
division ok
attempted 10 / 4
2.5
cannot divide by zero
attempted 1 / 0
None
bad operand types: unsupported operand type(s) for /: 'str' and 'int'
attempted 'x' / 2
None
```

The `as exc` form binds the exception object to a name, so you can print its message or inspect it. The `finally` line runs even after a `return`, which is why "attempted" appears after "division ok" and before the printed result.

Use `finally` for cleanup such as closing a file or releasing a lock. For file handling, though, the `with` statement is usually a cleaner choice.

## 3. Raising your own exceptions

Use `raise` to signal a problem yourself. Define your own exception class when the built-in types do not describe your situation well. Subclass `Exception`, and give the class a docstring that says what it means.

When you turn one exception into another, use `raise ... from ...`. This records the original error as the `__cause__` of the new one. The traceback then shows both, so the real source of the failure is not lost.

```python
class ConfigError(Exception):
    """Raised when a configuration value is missing or invalid."""

def read_port(settings):
    try:
        raw = settings["port"]
    except KeyError as exc:
        raise ConfigError("port is missing") from exc
    try:
        port = int(raw)
    except ValueError as exc:
        raise ConfigError(f"port must be a number, got {raw!r}") from exc
    if not 1 <= port <= 65535:
        raise ConfigError(f"port out of range: {port}")
    return port

for settings in [{"port": "8080"}, {}, {"port": "eighty"}, {"port": "70000"}]:
    try:
        print("port:", read_port(settings))
    except ConfigError as exc:
        cause = type(exc.__cause__).__name__ if exc.__cause__ else "none"
        print(f"config error: {exc} (cause: {cause})")
```

Output:

```
port: 8080
config error: port is missing (cause: KeyError)
config error: port must be a number, got 'eighty' (cause: ValueError)
config error: port out of range: 70000 (cause: none)
```

The custom `ConfigError` gives callers one exception type to catch, no matter which low-level problem happened inside. The `from exc` keeps the details for debugging. The last case has no cause, because the range check raised the error directly.

## 4. Handling several errors at once with exception groups

Sometimes one operation finds many problems. Rather than stopping at the first, you can collect them into an `ExceptionGroup`, which Python 3.11 added. The `except*` syntax then handles each kind of error in the group. Every matching `except*` clause runs for the errors it matches.

```python
def validate_all(items):
    problems = []
    for item in items:
        if not isinstance(item, int):
            problems.append(TypeError(f"not an int: {item!r}"))
        elif item < 0:
            problems.append(ValueError(f"negative: {item}"))
    if problems:
        raise ExceptionGroup("validation failed", problems)
    return sum(items)

try:
    validate_all([1, -2, "x", 4, -5])
except* ValueError as group:
    print("value problems:", [str(e) for e in group.exceptions])
except* TypeError as group:
    print("type problems:", [str(e) for e in group.exceptions])

print("validation finished")
```

Output:

```
value problems: ['negative: -2', 'negative: -5']
type problems: ["not an int: 'x'"]
validation finished
```

Exception groups are useful when you process a batch of records and want to report every bad one, not just the first. Use plain `except` for single errors and `except*` when you expect several at once.

## 5. Guidelines

- **Catch specific exceptions.** Name the type you expect. A bare `except:` hides bugs.
- **Keep try blocks small.** Wrap only the line or two that can fail. A large `try` can catch errors you did not mean to handle.
- **Put success code in else.** Keep the `try` block limited to the risky call.
- **Use finally for cleanup.** It runs even when a `return` or an unhandled error skips the rest of the block.
- **Raise early with clear messages.** Include the bad value in the message, as `ConfigError` did above.
- **Chain with from.** When you translate one error into another, keep the original with `raise ... from exc`.
- **Do not swallow errors silently.** If you catch an exception, handle it, log it, or re-raise it. An empty `except` block makes failures invisible.

## Practice

Write a script that reads a list of strings such as `["12", "x", "7", "-3"]`. Convert each to an integer with `try` and `except ValueError`, collect the valid numbers, and print their sum. Then raise a `ValueError` with a clear message for any negative number, using `raise ... from` where you translate an error. Check that your output matches what you expect.