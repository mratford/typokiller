# Concurrency in Python

Concurrency lets a program manage several activities during overlapping periods of time. A server can wait for one client while handling another. A command-line tool can start several downloads rather than waiting for each download separately.

Concurrency is not the same as parallelism. Concurrent tasks make progress during overlapping periods; parallel tasks execute at the same instant. A program can be concurrent on a single processor, while parallel execution requires multiple execution resources.

Python 3.14 provides several standard-library tools for concurrent programming. This lesson introduces threads, locks, asynchronous tasks, and worker processes. Each tool solves a different coordination problem.

The examples use short delays or local calculations instead of external services. Every script runs independently and needs no input.

## Choose a model for the work

Begin by asking what makes a task slow.

An I/O-bound task spends much of its time waiting for something outside the processor: a network response, a disk operation, or a database query. Threads and asynchronous programming often help with this kind of work.

A CPU-bound task spends most of its time executing calculations. Worker processes are a common choice for running Python calculations in parallel.

In a standard CPython build, the global interpreter lock, or GIL, usually prevents multiple threads from executing Python code simultaneously within one interpreter. Threads can still overlap waiting operations. Python 3.14 also supports optional free-threaded builds, but this lesson does not depend on one.

Choose the simplest model that fits the task. Adding concurrency to tiny, independent calculations can make them slower because scheduling and coordination have costs.

## 1. Overlap waiting with a thread pool

A thread pool maintains a limited number of worker threads. Submit work to the pool, then collect its results.

Here, each job sleeps briefly to represent an operation that spends most of its time waiting. Sleeping is useful for a demonstration because it does not require a network connection or a local data file.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep


def read_sensor(sensor_id: int) -> tuple[int, int]:
    sleep(0.05 * (4 - sensor_id))
    return sensor_id, 20 + sensor_id


def main() -> None:
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(read_sensor, sensor_id)
            for sensor_id in range(1, 4)
        ]

        readings = {}
        for future in as_completed(futures):
            sensor_id, temperature = future.result()
            readings[sensor_id] = temperature

    for sensor_id in sorted(readings):
        print(f"Sensor {sensor_id}: {readings[sensor_id]} C")


if __name__ == "__main__":
    main()
```

Calling `submit()` schedules a function call and immediately returns a `Future`. A future represents a result that may not be available yet.

The `as_completed()` iterator yields futures as they finish, rather than in submission order. Calling `result()` retrieves a completed result. If the worker raised an exception, `result()` raises that exception in the calling thread.

The main thread stores results and sorts them before printing. This separates unpredictable completion order from predictable presentation order.

The executor's context manager waits for its work to finish and releases its resources. Avoid creating a new thread for every item in an unbounded stream; a fixed worker count limits simultaneous activity.

## 2. Protect shared state with a lock

Threads share the memory of their process. That makes communication convenient, but it also allows tasks to interfere with one another.

Suppose several workers update a shared counter. An operation such as `counter += 1` should not be treated as a portable synchronization mechanism. A correct program should not depend on the GIL, interpreter implementation details, or lucky scheduling.

A lock establishes a critical section: a region that only one participating thread may enter at a time.

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


def main() -> None:
    total = 0
    lock = Lock()

    def add_batch(batch_size: int) -> None:
        nonlocal total
        for _ in range(batch_size):
            with lock:
                total += 1

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(add_batch, 1000)
            for _ in range(4)
        ]
        for future in futures:
            future.result()

    print(f"Total: {total}")
    assert total == 4000


if __name__ == "__main__":
    main()
```

The `with lock:` statement acquires the lock and releases it when the block ends, even if an exception occurs. All workers use the same lock to protect the same variable.

Keep critical sections short. Holding a lock while sleeping or performing a slow request can prevent other workers from making useful progress.

Locks also introduce the possibility of deadlock. For example, two threads can each hold one lock while waiting forever for the other. Prefer simple ownership rules, and use a consistent acquisition order when multiple locks are unavoidable.

Often, the best shared-state design is to avoid shared mutation. Workers can return independent results, leaving one coordinating thread to combine them.

## 3. Coordinate asynchronous tasks

The `asyncio` module supports cooperative concurrency. An event loop runs tasks, and each task gives other tasks a chance to run when it reaches an operation that suspends it.

Calling an asynchronous function creates a coroutine object. It does not automatically execute the function's body. The coroutine must be awaited or scheduled as a task.

This example starts three operations in a task group.

```python
import asyncio


async def prepare_item(name: str, delay: float) -> str:
    print(f"Starting {name}")
    await asyncio.sleep(delay)
    return f"{name} is ready"


async def main() -> None:
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(prepare_item("tea", 0.15)),
            group.create_task(prepare_item("toast", 0.10)),
            group.create_task(prepare_item("fruit", 0.05)),
        ]

    for task in tasks:
        print(task.result())


if __name__ == "__main__":
    asyncio.run(main())
```

The task group waits for its tasks before its context exits normally. Results are printed in list order, even though the tasks finish in a different order.

`asyncio.sleep()` suspends the current task without blocking the event loop. Replacing it with `time.sleep()` would block the loop and prevent other tasks on that loop from progressing during the sleep.

Async code does not automatically make blocking libraries nonblocking. Use asynchronous APIs where available. For a blocking I/O function that must be called from async code, `asyncio.to_thread()` can run that function in a worker thread.

A `TaskGroup` also provides structured failure handling. If a child task raises an exception other than cancellation, the group normally cancels its remaining tasks and later raises an exception group.

Cancellation is a request, not an instant shutdown. Use `try` and `finally` to release resources, and generally allow cancellation exceptions to propagate.

## 4. Run calculations in worker processes

Processes have separate memory spaces and independent Python interpreters. A process pool can therefore execute Python calculations in parallel even when the main interpreter uses the GIL.

There is a tradeoff: starting processes and transferring data cost more than scheduling ordinary function calls. Give each worker enough work to justify that overhead.

```python
from concurrent.futures import ProcessPoolExecutor


def sum_squares(limit: int) -> int:
    return sum(number * number for number in range(limit))


def main() -> None:
    limits = [100_000, 120_000, 140_000, 160_000]

    with ProcessPoolExecutor(max_workers=2) as executor:
        totals = list(executor.map(sum_squares, limits))

    for limit, total in zip(limits, totals):
        print(f"Sum of squares below {limit}: {total}")


if __name__ == "__main__":
    main()
```

Save this script in a Python file before running it. Worker processes need to import the module containing the worker function.

The main guard prevents newly started interpreters from recursively creating more pools. Keep process-pool worker functions at module scope, and pass arguments and results that can be serialized with `pickle`.

Unlike `as_completed()`, `executor.map()` returns results in input order. An early slow job can therefore delay access to later results.

This small example demonstrates the structure, not a guaranteed speed improvement. Measure realistic workloads before choosing processes.

## Build reliable concurrent programs

Concurrency makes execution order less predictable, so correctness must come from explicit rules rather than timing assumptions. A delay is not a reliable way to ensure another task has finished.

Bound concurrency to avoid exhausting memory, file descriptors, or remote-service capacity. Set timeouts for operations that might wait indefinitely, and distinguish a waiting timeout from actually stopping the underlying work.

Always observe task results so failures are not silently ignored. Keep resource ownership clear, use context managers for cleanup, and test failure paths as carefully as successful ones.

Start with a sequential implementation. Then identify independent work, choose an appropriate concurrency model, and measure the result. The goal is not the largest number of workers; it is a program that remains correct, understandable, and responsive.