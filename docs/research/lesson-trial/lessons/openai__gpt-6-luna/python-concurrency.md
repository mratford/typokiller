# Concurrency

Concurrency lets a program make progress on more than one task during the same period of time. A web service might answer one request while waiting for another, or a program might download several files without waiting for each download to finish before starting the next. Concurrency is useful when tasks spend time waiting. Parallelism is different: it means tasks are actually running at the same time, often on separate CPU cores.

Python offers several ways to coordinate concurrent work. Threads are a natural fit for tasks that wait on input or output. `asyncio` can coordinate many waiting tasks in a single thread. Processes can run CPU-heavy work in separate interpreters. The right choice depends on the task, and concurrent code requires extra care: tasks may finish in an unexpected order, share mutable data, or fail independently.

## Threads for waiting tasks

A thread is a separate path of execution inside a process. Threads share that process's memory, so they can access the same objects. This makes sharing data convenient, but it also means that changes must be coordinated.

For ordinary tasks such as network requests, file access, or waiting for a response from another service, `concurrent.futures.ThreadPoolExecutor` is a practical starting point. It manages a set of worker threads and provides a way to submit tasks and collect their results.

In the example, each task simulates waiting by sleeping briefly. The executor runs tasks using a pool of three threads. `map` gives results in the same order as the input, even if the tasks finish in a different order. This is useful when a later step expects the original order.

```python
import time
from concurrent.futures import ThreadPoolExecutor


def fetch_record(record_id):
    time.sleep(0.02)
    return f"record {record_id}"


def main():
    record_ids = [1, 2, 3, 4, 5]

    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(fetch_record, record_ids))

    for record in records:
        print(record)


if __name__ == "__main__":
    main()
```

The `with` block ensures that the executor shuts down when the block finishes. The main thread waits for submitted work to complete before leaving the block. This is safer than starting threads manually and forgetting to join them.

The worker function receives a single item and returns a result. Keeping worker functions focused makes concurrent programs easier to test. For example, a real `fetch_record` might make a network request, while the rest of the program would still handle results in the same way.

Threads are not automatically faster. Starting workers and exchanging results has a cost, and a task that finishes almost immediately may not benefit from a pool. Threads also do not guarantee that Python code which uses the CPU will run faster on multiple cores. In standard CPython builds, the global interpreter lock (GIL) limits simultaneous execution of Python bytecode in multiple threads. Threads are most useful when workers spend much of their time waiting.

## Protecting shared data

Because threads share memory, two workers can access the same mutable object. If one worker changes that object while another reads or changes it, the outcome may depend on timing. Such an error is a race condition: the program's result depends on the order in which concurrent actions happen.

A lock protects a critical section, the part of the program that must not be changed by multiple workers at once. A worker must acquire the lock before entering that section. A `with` statement releases the lock automatically, even if an exception occurs.

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


counter = 0
counter_lock = Lock()


def add_many_times(repetitions):
    global counter

    for _ in range(repetitions):
        with counter_lock:
            counter += 1


def main():
    global counter

    worker_count = 8
    repetitions = 1000

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [
            pool.submit(add_many_times, repetitions)
            for _ in range(worker_count)
        ]

        for future in futures:
            future.result()

    print(counter)


if __name__ == "__main__":
    main()
```

`counter += 1` looks like one operation, but it involves reading a value, calculating a new value, and storing it. Without protection, workers could interfere with one another. The lock makes each increment a single protected action. The result is always `8000`.

Calling `future.result()` waits for that task to finish. It also raises an exception if the task failed, so errors are not silently lost. Collecting results or exceptions is an important part of managing concurrent work.

Locks should cover only the shared operation that needs protection. Holding a lock while doing slow work can prevent other threads from making progress. Avoid acquiring several locks in different orders: two workers can then each hold one lock while waiting for the other, a situation called deadlock.

## Asyncio for many waiting tasks

`asyncio` is a library for writing concurrent programs with `async` and `await`. It usually runs many tasks in one thread. When a task reaches an `await` point and must wait, it yields control so that another task can run. This is called cooperative scheduling: tasks need to reach an appropriate yield point for other work to proceed.

This model works well for large numbers of tasks that spend much of their time waiting, such as network clients. It does not make CPU-heavy work run in parallel. A long computation that never yields can keep other asyncio tasks from running.

The next script creates three tasks. Each waits for a different duration, then returns its name. `asyncio.gather` waits for all of them and returns results in the order in which the tasks were passed to it, not in the order in which they finished.

```python
import asyncio


async def visit(name, delay):
    await asyncio.sleep(delay)
    return f"finished {name}"


async def main():
    tasks = [
        asyncio.create_task(visit("alpha", 0.03)),
        asyncio.create_task(visit("beta", 0.01)),
        asyncio.create_task(visit("gamma", 0.02)),
    ]

    results = await asyncio.gather(*tasks)

    for result in results:
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

An `async def` function returns a coroutine when called; it does not immediately run to completion. `asyncio.create_task` schedules each coroutine to run. `await asyncio.gather(...)` lets the event loop manage the tasks while they wait, and resumes `main` when the gathered tasks finish.

Use `asyncio.run` at the program's entry point to create and manage the event loop. Within an asynchronous function, use `await` to wait for another coroutine. Avoid using a blocking function such as `time.sleep` in an event loop: it blocks the thread and prevents other tasks from running. Use `await asyncio.sleep(...)` for a delay in asynchronous code.

## Processes for CPU-heavy work

A process has its own memory space and Python interpreter. A process pool can run CPU-heavy tasks on separate cores, avoiding the limits of threads in standard CPython builds. Processes have more startup and data-transfer costs than threads, so they are usually a poor choice for tiny tasks or large amounts of shared data.

This example calculates sums of squares for several ranges. `ProcessPoolExecutor` sends each input to a worker process and collects the results. The function must be defined at the top level of the module so worker processes can import it. The `if __name__ == "__main__"` guard is essential on platforms that start processes by importing the main module.

```python
from concurrent.futures import ProcessPoolExecutor


def sum_squares(limit):
    return sum(value * value for value in range(limit))


def main():
    limits = [100_000, 120_000, 140_000, 160_000]

    with ProcessPoolExecutor(max_workers=2) as pool:
        totals = list(pool.map(sum_squares, limits))

    for limit, total in zip(limits, totals):
        print(limit, total)


if __name__ == "__main__":
    main()
```

Process pools are convenient when a task can be described as a function and its arguments, with a result returned to the caller. Workers do not automatically share ordinary Python objects with the main process. That separation can help prevent accidental interference, but it means data must be sent between processes. Keep inputs and results reasonably small.

## Choosing a model

Start by asking what your tasks spend their time doing. If they mostly wait for network, file, or other input/output operations, consider threads or `asyncio`. Threads often fit existing synchronous code. `asyncio` can be efficient when many tasks follow the same asynchronous pattern, but the surrounding libraries should also support asynchronous operations.

If tasks mainly perform calculations, consider a process pool. Measure performance rather than assuming concurrency will help: scheduling, communication, and startup costs can outweigh the work itself. A simple sequential version is often easier to understand and may already be fast enough.

Finally, make task boundaries clear. Decide how results are collected, how exceptions are reported, and when all work should stop. Limit the number of active workers when too many tasks could exhaust a resource. Keep shared state small, protect necessary changes, and prefer passing values between tasks over having them modify the same objects. These habits make concurrent programs easier to reason about and more reliable.