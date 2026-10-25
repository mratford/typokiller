# Error Handling in Python

Errors are part of normal programming. A file may be missing, a value may be invalid, or a service may be temporarily unavailable. Good error handling lets a program respond deliberately instead of stopping unexpectedly or silently producing a wrong result.

Python represents many failures as exceptions. When an operation raises an exception, normal execution stops. Python searches for a matching handler. If none is found, the program ends and displays a traceback.

The goal is not to catch every exception. It is to catch failures that your code understands and can handle meaningfully. Unexpected failures should usually remain visible so that you can investigate them.

## 1. Catch Specific Exceptions

A `try` statement marks an operation that might fail. An `except` clause handles a particular exception type. An optional `else` clause runs only when the `try` block finishes without raising an exception.

A `finally` clause runs when control leaves the statement, whether the operation succeeded or failed. It also runs before a pending `return` takes effect. This makes it useful for cleanup, although context managers are often better for managing resources.

This script processes several pairs of numeric strings:

```python
def show_quotient(numerator_text, denominator_text):
    print(f"Calculating {numerator_text} / {denominator_text}")

    try:
        numerator = float(numerator_text)
        denominator = float(denominator_text)
        result = numerator / denominator
    except ValueError as exc:
        print(f"Invalid number: {exc}")
    except ZeroDivisionError:
        print("The denominator must not be zero.")
    else:
        print(f"Result: {result:.2f}")
    finally:
        print("Calculation finished.")


def main():
    examples = [
        ("12", "3"),
        ("ten", "2"),
        ("8", "0"),
    ]

    for numerator, denominator in examples:
        show_quotient(numerator, denominator)
        print()


if __name__ == "__main__":
    main()
```

The first pair succeeds. The second causes `float()` to raise `ValueError`. The third reaches division and raises `ZeroDivisionError`.

The name after `as` refers to the exception object. Its string representation often contains useful information, but user-facing messages may need clearer wording.

Keep `try` blocks focused. If a large block performs many unrelated operations, the handler may accidentally catch a failure from the wrong place. Put work that should happen only after success in `else`, outside the protected block.

Exception classes form a hierarchy. A handler matches instances of its named class and subclasses. When using several handlers, place more specific exception types before broader ones.

## 2. Raise Exceptions for Invalid Values

Handling errors is only half the story. Your own functions should also report failures clearly.

Use `ValueError` when an argument has an acceptable type but an unacceptable value. Use `TypeError` when the argument has the wrong type. These conventions help callers predict how a function behaves.

Validate values near the point where they enter your program. Once validation succeeds, later code can work with a stronger assumption about the data.

The following script converts configuration text into a valid port number. It defines a custom exception so callers can recognize configuration problems without depending on the details of integer conversion.

```python
class ConfigurationError(ValueError):
    """A configuration value is invalid."""


def parse_port(text):
    if not isinstance(text, str):
        raise TypeError("Port text must be a string.")

    try:
        port = int(text)
    except ValueError as exc:
        raise ConfigurationError(
            f"Port must be an integer, not {text!r}."
        ) from exc

    if not 1 <= port <= 65535:
        raise ConfigurationError(
            f"Port must be between 1 and 65535, not {port}."
        )

    return port


def main():
    for text in ("8080", "eighty", "70000"):
        try:
            port = parse_port(text)
        except ConfigurationError as exc:
            print(f"Configuration problem: {exc}")
        else:
            print(f"Using port {port}")


if __name__ == "__main__":
    main()
```

The expression `raise ... from exc` explicitly connects the new exception to its cause. If the exception reaches a traceback, Python shows both the original conversion failure and the higher-level configuration error.

This technique is called exception chaining. It is useful when translating low-level failures into terms that fit your application.

Custom exception classes usually inherit from `Exception` or an appropriate existing subclass. Here, inheriting from `ValueError` means the error is both a configuration problem and an invalid-value problem.

Avoid using `assert` to validate external data. Assertions describe internal assumptions and can be disabled when Python runs with optimization. Required validation should use ordinary conditions and explicit exceptions.

## 3. Handle File Errors and Release Resources

File operations have several distinct failure modes. A path might not exist, access might be denied, or the contents might not have the expected format.

These failures do not necessarily call for the same response. A missing optional settings file might justify defaults. A damaged file should usually produce a visible error rather than quietly disappear.

Use a `with` statement to manage open files. The file is closed when the block ends, including when reading or parsing raises an exception.

This example creates its own temporary files, so it runs without requiring any existing data:

```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory


def load_settings(path):
    try:
        with path.open("r", encoding="utf-8") as source:
            settings = json.load(source)
    except FileNotFoundError:
        return {"theme": "light"}
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path.name}, line {exc.lineno}."
        ) from exc

    if not isinstance(settings, dict):
        raise ValueError("Settings must be a JSON object.")

    return settings


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        valid = root / "valid.json"
        broken = root / "broken.json"
        missing = root / "missing.json"

        valid.write_text('{"theme": "dark"}', encoding="utf-8")
        broken.write_text('{"theme": }', encoding="utf-8")

        for path in (valid, missing, broken):
            try:
                settings = load_settings(path)
            except (OSError, ValueError) as exc:
                print(f"{path.name}: {exc}")
            else:
                print(f"{path.name}: {settings}")


if __name__ == "__main__":
    main()
```

There are two context managers here. The inner one closes the file. The outer one removes the temporary directory and its contents when the demonstration finishes.

The missing file gets a documented default. Invalid JSON becomes a descriptive `ValueError`, with its original cause preserved. Valid JSON still needs validation: JSON can represent a list, string, or number, not just a dictionary.

The caller handles `OSError` for other filesystem failures. `FileNotFoundError` is an `OSError` subclass, but the function has already handled that particular case.

A tuple in an `except` clause groups exception types that need the same response. This is different from catching everything indiscriminately.

## 4. Retry Only Failures That May Be Temporary

Some failures are transient. A busy service might accept a request on the next attempt. Other failures, such as an invalid password or malformed request, will not improve through repetition.

A retry policy should identify retryable failures, limit attempts, and preserve the final cause. In production, retries often include delays and increasing backoff. This demonstration uses a simulated operation, so it finishes immediately.

```python
class TemporaryFailure(Exception):
    """The operation may succeed on another attempt."""


class ServiceUnavailable(Exception):
    """All allowed attempts failed."""


def simulated_request(attempt):
    if attempt < 3:
        raise TemporaryFailure("Service is busy.")

    return "Request accepted."


def request_with_retry(max_attempts):
    if max_attempts < 1:
        raise ValueError("At least one attempt is required.")

    for attempt in range(1, max_attempts + 1):
        try:
            return simulated_request(attempt)
        except TemporaryFailure as exc:
            print(f"Attempt {attempt} failed: {exc}")

            if attempt == max_attempts:
                raise ServiceUnavailable(
                    f"Failed after {max_attempts} attempts."
                ) from exc


def main():
    for limit in (2, 3):
        try:
            result = request_with_retry(limit)
        except ServiceUnavailable as exc:
            print(f"Giving up: {exc}")
        else:
            print(result)


if __name__ == "__main__":
    main()
```

Only `TemporaryFailure` triggers another attempt. An unrelated programming error is not hidden by the retry loop.

Before retrying real operations, consider side effects. Repeating a read is often safe. Repeating a payment or submission may duplicate work unless the system supports an idempotency mechanism.

## Practical Rules

Avoid a bare `except:` clause. It also catches exceptions such as `KeyboardInterrupt` and `SystemExit`, which usually should propagate.

Catching `Exception` is narrower, but still broad. Reserve it for deliberate boundaries, such as a task runner that must report one task's failure and continue.

Do not catch an exception merely to ignore it. Choose an intentional response: recover, supply a justified default, retry, translate the exception, or report the failure.

Inside a handler, a bare `raise` re-raises the current exception while preserving its traceback. Use it when you need to record context but cannot actually recover.

Finally, test failure paths as carefully as successful ones. Reliable error handling makes expected problems understandable while keeping unexpected bugs visible.