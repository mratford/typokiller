# Error Handling in Python

Programs fail. Files go missing, users type nonsense, networks drop. Error handling is how your code notices a problem and responds sensibly instead of crashing. In this lesson you will learn how to catch exceptions, clean up after yourself, raise your own errors, and define custom exception types.

## Exceptions in Brief

When Python hits a problem it cannot ignore, it raises an *exception*. If nothing handles it, the program stops and prints a traceback. Common built-in exceptions include `ValueError` (right type, bad value), `TypeError` (wrong type), `KeyError` (missing dictionary key), `IndexError` (bad list position), and `ZeroDivisionError`.

The basic tool is the `try` statement. Code that might fail goes in the `try` block, and the `except` block says what to do if it does.

## Example 1: try, except, else, finally

A `try` statement can have four parts:

- `try`: the code that might fail.
- `except`: runs if a matching exception is raised.
- `else`: runs only if no exception happened.
- `finally`: always runs, error or not.

```python
def parse_ratio(text):
    """Turn a string like '3/4' into a float."""
    try:
        top, bottom = text.split("/")
        result = int(top) / int(bottom)
    except ValueError:
        print(f"  '{text}' is not in the form number/number")
        return None
    except ZeroDivisionError:
        print(f"  '{text}' divides by zero")
        return None
    else:
        print(f"  '{text}' parsed fine")
        return result
    finally:
        print(f"  done with '{text}'")


def main():
    for item in ["3/4", "5/0", "hello", "1/2/3"]:
        print(f"Trying {item!r}")
        value = parse_ratio(item)
        print(f"  value = {value}")


main()
```

Notice that `finally` runs even though the function returns from inside the other blocks. Also notice that `"1/2/3"` fails at the unpacking step, which raises a `ValueError`, so the first handler catches it.

## Catch Specific Exceptions

Always name the exception you expect. A bare `except:` or a broad `except Exception:` can hide real bugs, such as a typo that raises `NameError`. Catch only what you know how to handle, and let everything else propagate.

You can catch several types in one clause by using a tuple, and you can keep the exception object with `as` to inspect it:

```python
def read_setting(settings, key):
    try:
        return int(settings[key])
    except (KeyError, ValueError) as err:
        print(f"  problem with {key!r}: {type(err).__name__}: {err}")
        return 0


def main():
    settings = {"width": "80", "height": "tall"}
    for key in ["width", "height", "depth"]:
        print(f"{key} -> {read_setting(settings, key)}")


main()
```

The `as err` name exists only inside the `except` block. Printing `type(err).__name__` is a handy way to show what kind of error occurred.

## Raising Your Own Exceptions

Use `raise` when your code detects a problem it cannot fix. Choose the built-in type that best describes the problem, and write a clear message.

```python
def set_age(age):
    if not isinstance(age, int):
        raise TypeError(f"age must be an int, got {type(age).__name__}")
    if age < 0 or age > 150:
        raise ValueError(f"age out of range: {age}")
    return age


def main():
    for candidate in [30, -5, "ten", 200]:
        try:
            print(f"Accepted age {set_age(candidate)}")
        except (TypeError, ValueError) as err:
            print(f"Rejected {candidate!r}: {err}")


main()
```

Raising early, close to the cause, makes bugs far easier to track down than letting bad data travel deep into the program.

## Custom Exceptions and Chaining

For larger programs, define your own exception classes. Inherit from `Exception`, and often create one base class for your whole module so callers can catch everything related to it at once.

When you catch a low-level error and raise a higher-level one, use `raise ... from err`. This keeps the original error attached as the cause, so the full story is preserved.

```python
class ConfigError(Exception):
    """Base class for configuration problems."""


class MissingOptionError(ConfigError):
    def __init__(self, name):
        super().__init__(f"missing required option: {name}")
        self.name = name


class BadOptionError(ConfigError):
    pass


def get_port(config):
    try:
        raw = config["port"]
    except KeyError:
        raise MissingOptionError("port") from None
    try:
        return int(raw)
    except ValueError as err:
        raise BadOptionError(f"port must be a number, got {raw!r}") from err


def main():
    configs = [{"port": "8080"}, {}, {"port": "eighty"}]
    for config in configs:
        try:
            print(f"Port: {get_port(config)}")
        except MissingOptionError as err:
            print(f"Missing: {err.name}")
        except ConfigError as err:
            print(f"Config problem: {err}")
            print(f"  caused by: {err.__cause__!r}")


main()
```

Here `from None` hides the irrelevant `KeyError` because `MissingOptionError` says everything needed. In the other case, `from err` keeps the `ValueError` available as `__cause__`. Handlers are checked in order, so the specific `MissingOptionError` comes before its parent `ConfigError`.

## Cleaning Up with `with`

The `finally` block guarantees cleanup, but for resources like files, locks, and connections, a `with` statement is cleaner. It calls cleanup code automatically, even when an error occurs. You can write your own using `contextlib`.

```python
from contextlib import contextmanager


@contextmanager
def opened(name):
    print(f"open {name}")
    try:
        yield name
    finally:
        print(f"close {name}")


def main():
    try:
        with opened("data.txt") as handle:
            print(f"working with {handle}")
            raise RuntimeError("something broke mid-task")
    except RuntimeError as err:
        print(f"caught: {err}")


main()
```

The output shows `close data.txt` printed before the error is caught. The resource was released no matter what.

## Exception Groups

Python 3.11 added `ExceptionGroup` and the `except*` syntax for situations where several errors happen at once, such as concurrent tasks. Each `except*` clause handles the matching members of the group.

```python
def main():
    try:
        raise ExceptionGroup(
            "batch failed",
            [ValueError("bad value"), TypeError("bad type"), ValueError("another")],
        )
    except* ValueError as group:
        print(f"ValueErrors: {[str(e) for e in group.exceptions]}")
    except* TypeError as group:
        print(f"TypeErrors: {[str(e) for e in group.exceptions]}")


main()
```

You will rarely need this in everyday scripts, but it is good to recognize when reading modern async code.

## Good Habits

- Catch the narrowest exception type that makes sense.
- Keep `try` blocks small, wrapping only the lines that can fail.
- Never silence errors with `except: pass`. At minimum, log or report them.
- Use `else` for code that should run only on success.
- Use `with` for resources, and `finally` for other cleanup.
- Write error messages that say what was wrong and what value caused it.
- Prefer built-in exception types, and create custom ones only when callers need to tell your errors apart.

## Practice Ideas

1. Write a function that asks for a number from a list of strings and keeps going past bad entries, counting how many failed.
2. Add a custom `ValidationError` to a function that checks usernames.
3. Wrap a `with` block around a made-up resource and confirm the cleanup message always prints.

Handling errors well is less about preventing every failure and more about failing clearly, safely, and in a way that lets the rest of your program carry on or stop gracefully.