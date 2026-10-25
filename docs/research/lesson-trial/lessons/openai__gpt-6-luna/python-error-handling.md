# Error Handling in Python

Errors are part of ordinary program behavior. A file may be missing, text may not contain a number, or a calculation may be impossible. Good error handling lets a program respond to such situations clearly instead of crashing unexpectedly.

Python reports errors with **exceptions**. When an exception is raised, Python looks for code that knows how to handle it. If no suitable handler is found, the program stops and displays a traceback. A traceback is useful during development: it shows the exception type and where the problem occurred.

The goal is not to prevent every exception. It is to handle expected problems at the point where the program can make a sensible choice, while allowing unexpected problems to remain visible.

## Catch specific exceptions

Use `try` and `except` when you expect an operation might fail and have a useful response. Catch the narrowest exception that fits the problem. For example, converting text with `int()` can raise `ValueError` if the text is not a valid integer.

```python
def parse_count(text):
    try:
        return int(text)
    except ValueError:
        return None


for text in ("12", "many"):
    count = parse_count(text)
    if count is None:
        print(f"Not a whole number: {text}")
    else:
        print(f"Count: {count}")
```

The risky operation is inside the `try` block; the response is inside the matching `except` block. Returning `None` is a simple way for this function to report that conversion did not work. The caller checks for that result before using it.

Do not use a bare `except:` for routine recovery. It can catch exceptions such as `KeyboardInterrupt` that are not ordinary input errors. Similarly, avoid catching `Exception` unless you are deliberately handling a broad range of failures, such as at an application boundary where you can report or log them. A handler should not hide a problem it cannot actually fix.

## Handle different outcomes

A `try` statement can have several parts:

- `except` handles a matching exception.
- `else` runs only if the `try` block finishes without an exception.
- `finally` runs whether or not an exception occurred.

Keep the `try` block small. If it contains unrelated work, an exception from that work might be mistaken for the failure you intended to handle.

```python
def show_ten_divided_by(text):
    try:
        number = int(text)
        result = 10 / number
    except ValueError:
        print(f"Not an integer: {text}")
    except ZeroDivisionError:
        print("Cannot divide by zero.")
    else:
        print(f"Result: {result}")
    finally:
        print(f"Finished: {text}")


for text in ("2", "0", "two"):
    show_ten_divided_by(text)
```

Here, `ValueError` and `ZeroDivisionError` describe different problems, so they get separate responses. The `else` block is a good place for code that should run only after the risky operations succeeded. The `finally` block runs for every value, including when an exception was handled. It is often useful for cleanup, though Python's `with` statement is usually clearer for managing resources such as files.

## Raise exceptions for invalid operations

A function can raise an exception when it cannot fulfill its purpose. Use `raise` with an appropriate exception type, and include a message that explains the problem. Built-in exceptions are often sufficient: for example, `ValueError` commonly indicates that an argument has the right general type but an unacceptable value.

```python
def require_positive(number):
    if number <= 0:
        raise ValueError("number must be positive")
    return number


for value in (5, 0):
    try:
        result = require_positive(value)
    except ValueError as error:
        print(f"Invalid value: {error}")
    else:
        print(f"Accepted: {result}")
```

Raising an exception is different from returning a special value such as `None`. Choose the approach that best communicates the function's contract. If invalid input is an expected result that callers can easily check, a return value may be appropriate. If the function cannot do its job, an exception can make that failure harder to overlook.

Do not use exceptions for ordinary branching when a simple condition is clearer. For instance, check whether a value meets a known condition directly instead of deliberately causing an error and catching it.

## Define an exception for your program

When a program has a meaningful failure that callers may want to handle separately, define a custom exception. Custom exceptions usually inherit from `Exception` or from a more specific built-in exception.

If you catch a low-level exception and raise a more meaningful one, use `raise ... from ...` to preserve the original cause. This is called exception chaining. The original error remains available for debugging, while the new exception describes the problem in terms useful to the caller.

```python
class InvalidPort(ValueError):
    pass


def parse_port(text):
    try:
        port = int(text)
    except ValueError as error:
        raise InvalidPort(f"port must be an integer: {text!r}") from error

    if not 1 <= port <= 65535:
        raise InvalidPort(f"port is outside the valid range: {port}")

    return port


for text in ("8080", "service", "70000"):
    try:
        port = parse_port(text)
    except InvalidPort as error:
        print(f"Invalid port: {error}")
    else:
        print(f"Port: {port}")
```

The caller can handle `InvalidPort` without needing to know which conversion or range check failed. The first failure retains its original `ValueError` as the cause. The range failure does not need a chained exception because no earlier exception caused it.

Custom exceptions should have clear names and usually need little extra code. Create them to express useful distinctions, not merely to give every possible error a new class.

## Use context managers for cleanup

Some operations need cleanup whether they succeed or fail. A file should be closed after use, even if reading or processing its contents raises an exception. The `with` statement manages this cleanup automatically.

```python
import json
import tempfile
from pathlib import Path


with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "settings.json"
    path.write_text('{"retries": }', encoding="utf-8")

    try:
        with path.open(encoding="utf-8") as file:
            settings = json.load(file)
    except json.JSONDecodeError as error:
        print(f"Invalid JSON on line {error.lineno}, column {error.colno}.")
    else:
        print(settings)
```

This example deliberately writes invalid JSON so the handler runs. `json.load()` raises `JSONDecodeError` when it cannot parse the file, and the handler reports where parsing failed. The file is still closed when its `with` block exits. Likewise, `TemporaryDirectory` removes its temporary directory when its block exits, including when an exception occurs.

Use context managers instead of manually writing cleanup in `finally` when a resource supports them. The context manager handles the cleanup consistently and makes the code easier to read.

## Write useful handlers

A good handler should do something useful: recover, provide a clear message, choose a safe fallback, or re-raise the error with additional context. Avoid silently ignoring exceptions. An empty handler can make a program appear successful even though its work failed.

If you cannot recover, let the exception propagate. If you need to add context, raise an appropriate exception and chain the original one. If you catch an exception only to log it, make sure it is not then accidentally swallowed when the program should stop.

Finally, remember that errors are not all alike. Invalid input may be expected and recoverable. A programming mistake may indicate a bug that should be fixed, not hidden. Catch the exceptions you understand, keep their handling close to the relevant operation, and let other failures remain visible.