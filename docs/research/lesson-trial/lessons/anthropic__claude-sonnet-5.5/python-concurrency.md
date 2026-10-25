# Concurrency in Python

Concurrency means making progress on several tasks during the same period. Python gives you three main tools, and choosing the right one matters more than any syntax.

| Tool | Best for | Model |
|------|----------|-------|
| `threading` / `ThreadPoolExecutor` | I/O-bound work (network, disk, waiting) | Many threads in one process |
| `asyncio` | Many I/O-bound tasks with explicit switch points | One thread, cooperative tasks |
| `multiprocessing` / `ProcessPoolExecutor` | CPU-bound work (math, parsing, compression) | Separate processes |

Standard CPython has a global interpreter lock (GIL), so only one thread runs Python bytecode at a time. Threads still help when tasks spend their time waiting, because a waiting thread releases the GIL. For CPU-bound work, use processes so each one has its own interpreter. Python 3.14 also officially supports free-threaded builds, which run without the GIL, and adds `InterpreterPoolExecutor` for running code in separate interpreters. The examples below work on any standard build.

## Thread pools for waiting work

The `concurrent.futures` module gives threads and processes the same interface. You submit a function, and you get back a `Future`, an object that represents a result that will exist later.

In this example, each job simply sleeps to simulate a slow request. Four jobs that total 1.0 second of waiting finish in about 0.4 seconds, because the waits overlap.

```python
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def fetch(name, delay):
    time.sleep(delay)
    return f"{name} done after {delay:.1f}s"


def main():
    jobs = [("alpha", 0.3), ("beta", 0.1), ("gamma", 0.2), ("delta", 0.4)]
    start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch, name, delay) for name, delay in jobs]
        for future in as_completed(futures):
            print(future.result())

    elapsed = time.perf_counter() - start
    print(f"Total: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
```

Key points:

- The `with` block waits for all work to finish and then shuts the pool down cleanly.
- `as_completed` yields futures in the order they finish, not the order you submitted them.
- `future.result()` returns the value, or re-raises any exception the function raised in its thread.
- If you want results in submission order, use `pool.map(fetch_one, items)` instead.

## Protecting shared data with a lock

Threads share memory, which is convenient and dangerous. An operation like `value += 1` is really a read, an add, and a write. Two threads can interleave those steps and lose updates. This is a race condition.

A `threading.Lock` lets only one thread at a time into a protected section. Always use it with `with`, so it is released even if an exception occurs.

```python
import threading


class Counter:
    def __init__(self):
        self.value = 0
        self._lock = threading.Lock()

    def increment(self):
        with self._lock:
            self.value += 1


def work(counter, times):
    for _ in range(times):
        counter.increment()


def main():
    counter = Counter()
    threads = [
        threading.Thread(target=work, args=(counter, 50_000))
        for _ in range(4)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    print(f"Expected 200000, got {counter.value}")


if __name__ == "__main__":
    main()
```

Key points:

- `start()` begins a thread, and `join()` waits for it to finish.
- Keep the locked section as small as possible, since other threads wait while you hold it.
- Never acquire locks in different orders in different threads, or you risk a deadlock.
- When you can, avoid shared state entirely. Pass data through a `queue.Queue`, which is already thread-safe.

## asyncio for many cooperative tasks

With `asyncio`, one thread runs an event loop. Each task runs until it reaches an `await`, which hands control back so another task can run. Because switches happen only at `await`, you rarely need locks, and you can run thousands of tasks cheaply.

Modern code uses `asyncio.TaskGroup` for structured concurrency. All tasks created in the group must finish before the `async with` block exits. If one fails, the others are cancelled and the errors are raised together. Use `asyncio.timeout` to put a deadline on any awaited operation.

```python
import asyncio


async def worker(name, delay):
    await asyncio.sleep(delay)
    print(f"{name} finished")
    return name.upper()


async def main():
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(worker("one", 0.3)),
            group.create_task(worker("two", 0.1)),
            group.create_task(worker("three", 0.2)),
        ]

    print("Results:", [task.result() for task in tasks])

    try:
        async with asyncio.timeout(0.2):
            await worker("slow", 1.0)
    except TimeoutError:
        print("slow worker timed out")


if __name__ == "__main__":
    asyncio.run(main())
```

Key points:

- `async def` defines a coroutine, and calling it does nothing until it is awaited or wrapped in a task.
- `asyncio.run()` starts the event loop, runs the coroutine, and closes the loop.
- Use `asyncio.sleep`, never `time.sleep`, inside coroutines. A blocking call freezes every task.
- To call unavoidable blocking code from async code, use `await asyncio.to_thread(function, arg)`.

## Process pools for CPU-bound work

If your tasks are busy computing rather than waiting, threads on a standard build will not run them in parallel. A `ProcessPoolExecutor` starts worker processes that each run on their own core.

Arguments and results are sent between processes by pickling, so the worker function must be defined at the top level of the module. The `if __name__ == "__main__":` guard is required. Child processes may import your script, and without the guard they would try to start pools of their own. Python 3.14 changed the default start method on Linux to `forkserver`, so the guard matters on every major platform.

```python
import time
from concurrent.futures import ProcessPoolExecutor


def count_primes(limit):
    count = 0
    for n in range(2, limit):
        if all(n % d for d in range(2, int(n**0.5) + 1)):
            count += 1
    return count


def main():
    limits = [20_000, 30_000, 40_000, 50_000]
    start = time.perf_counter()

    with ProcessPoolExecutor() as pool:
        results = list(pool.map(count_primes, limits))

    for limit, result in zip(limits, results):
        print(f"Primes below {limit}: {result}")

    elapsed = time.perf_counter() - start
    print(f"Finished in {elapsed:.2f}s")


if __name__ == "__main__":
    main()
```

Key points:

- With no `max_workers` argument, the pool uses one worker per CPU core.
- `pool.map` returns results in input order, even though the work runs in parallel.
- Starting processes and pickling data has a cost, so a process pool pays off only when each task does a meaningful amount of work.
- Processes do not share memory. Send results back as return values rather than modifying globals.

## Choosing the right tool

Ask what your program spends its time doing:

1. **Waiting on a few slow calls?** Use a `ThreadPoolExecutor`. It is the simplest change to existing blocking code.
2. **Waiting on hundreds or thousands of connections?** Use `asyncio`, which scales better than threads, provided your libraries are async-aware.
3. **Crunching numbers?** Use a `ProcessPoolExecutor`, or try a free-threaded build if your dependencies support it.
4. **Mixing them?** You can. An async program can hand blocking work to threads with `asyncio.to_thread` and CPU-heavy work to processes with `loop.run_in_executor`.

## Common pitfalls

- **Forgetting the main guard.** Process pools without `if __name__ == "__main__":` can fail or spawn endlessly.
- **Blocking the event loop.** One `time.sleep(5)` inside a coroutine stalls every task.
- **Unsynchronized shared state.** If several threads modify the same object, protect it with a lock or use a queue.
- **Swallowed exceptions.** An exception in a worker appears only when you call `result()`, so always collect your results.
- **Too many workers.** More threads or processes is not always faster. Measure before tuning.

## Practice ideas

Try modifying the examples to build your muscle memory and understanding:

- Change `ThreadPoolExecutor` to use `pool.map` and compare the output order.
- Remove the lock from the counter and see whether you get a wrong total. The result depends on your Python build and timing, which is exactly why races are hard to catch.
- Make one task in the `TaskGroup` raise a `ValueError` and watch how the group reacts.
- Time the prime counter with a plain `for` loop and compare it with the process pool.

Concurrency rewards small, measured steps. Start with the simplest tool that fits your workload, keep shared state to a minimum, and always let the `with` blocks clean up for you.