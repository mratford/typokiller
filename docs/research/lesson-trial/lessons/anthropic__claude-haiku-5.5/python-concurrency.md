# Lesson: Concurrency in Python

Concurrency means running several tasks in overlapping time so that one task does not have to wait idle for another. Python offers three main tools for it: **threads**, **asyncio**, and **processes**. Each suits a different kind of work, and choosing the right one matters more than knowing the syntax of any single one.

## Two kinds of work

Before writing any concurrent code, ask what the program spends its time doing.

- **I/O-bound** work waits on something outside the CPU: a network reply, a disk read, a timer. While one task waits, another can run.
- **CPU-bound** work keeps the processor busy with calculation. Only separate processes can run this in true parallel in CPython, because the Global Interpreter Lock (GIL) lets only one thread execute Python bytecode at a time.

As a rule, use threads or asyncio for I/O-bound work and processes for CPU-bound work.

## Example 1: Threads and shared state

Threads share memory, which makes them easy to use and easy to break. Several threads adding to the same variable can interleave their steps and lose updates. A `Lock` makes each update happen as one unit.

```python
import threading

counter = 0
lock = threading.Lock()

def worker(n):
    global counter
    for _ in range(n):
        with lock:
            counter += 1

threads = [threading.Thread(target=worker, args=(100_000,)) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print("counter =", counter)
```

The output is always `counter = 400000`. Remove the `with lock:` line and the total may come out smaller, because the threads overwrite each other's updates. Keep the critical section as short as possible, since a lock held for a long time turns concurrent code back into serial code.

## Example 2: A thread pool for waiting work

`ThreadPoolExecutor` manages a fixed set of worker threads and hands them jobs. Here each job sleeps, standing in for a slow network request. Four jobs of half a second each finish in about half a second total instead of two seconds.

```python
import time
from concurrent.futures import ThreadPoolExecutor

def fake_download(name, seconds):
    time.sleep(seconds)
    return f"{name} done after {seconds}s"

start = time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as pool:
    jobs = [("a", 0.5), ("b", 0.5), ("c", 0.5), ("d", 0.5)]
    results = list(pool.map(lambda job: fake_download(*job), jobs))
elapsed = time.perf_counter() - start

for line in results:
    print(line)
print(f"total under 1.5s: {elapsed < 1.5}")
```

`pool.map` returns results in the order the jobs were submitted, even though they finish at different times. The `with` block waits for all jobs and then shuts the pool down cleanly.

## Example 3: asyncio and coroutines

asyncio runs many tasks on a single thread. A coroutine marks each point where it can pause with `await`, and the event loop switches to another task during that pause. This scales well to thousands of connections, because a suspended coroutine costs far less memory than a thread.

```python
import asyncio

async def fetch(name, delay):
    await asyncio.sleep(delay)
    return f"{name}:{delay}"

async def main():
    results = await asyncio.gather(
        fetch("x", 0.3), fetch("y", 0.2), fetch("z", 0.1)
    )
    print(results)

asyncio.run(main())
```

The output is `['x:0.3', 'y:0.2', 'z:0.1']`. The three waits overlap, so the program takes about 0.3 seconds instead of 0.6. Note that `asyncio.sleep` is used rather than `time.sleep`. The blocking `time.sleep` would freeze the whole event loop, and no other task could run.

## Example 4: Processes for CPU-bound work

Threads do not speed up pure calculation in CPython because of the GIL. `ProcessPoolExecutor` starts separate interpreter processes, each with its own GIL, so calculations truly run in parallel.

```python
from concurrent.futures import ProcessPoolExecutor

def count_primes(limit):
    count = 0
    for n in range(2, limit):
        if all(n % d for d in range(2, int(n**0.5) + 1)):
            count += 1
    return count

if __name__ == "__main__":
    limits = [20_000, 30_000, 40_000]
    with ProcessPoolExecutor() as pool:
        for limit, c in zip(limits, pool.map(count_primes, limits)):
            print(f"primes below {limit}: {c}")
```

The `if __name__ == "__main__":` guard is required. Worker processes import this file, and without the guard each one would try to start a pool of its own. Output:

```
primes below 20000: 2262
primes below 30000: 3245
primes below 40000: 4203
```

## Example 5: Producer and consumer with a queue

A `queue.Queue` is the safe way to pass work between threads. It handles its own locking. Setting `maxsize` makes the producer wait when the consumer falls behind, which keeps memory use bounded. A sentinel value tells the consumer that no more items are coming.

```python
import queue
import threading

q = queue.Queue(maxsize=5)
SENTINEL = None
total = 0

def producer():
    for i in range(1, 101):
        q.put(i)
    q.put(SENTINEL)

def consumer():
    global total
    while True:
        item = q.get()
        if item is SENTINEL:
            break
        total += item

p = threading.Thread(target=producer)
c = threading.Thread(target=consumer)
p.start()
c.start()
p.join()
c.join()
print("total =", total)
```

The output is `total = 5050`, the sum of 1 through 100. Because only the consumer touches `total`, no lock is needed here. Designing so that data has a single owner often removes the need for locks entirely.

## Choosing a tool

| Situation | Tool |
|---|---|
| Many waits on I/O, modest number of tasks | `ThreadPoolExecutor` or threads |
| Very many concurrent network connections | `asyncio` |
| Heavy calculation on several cores | `ProcessPoolExecutor` |
| Passing work between producers and consumers | `queue.Queue` |

## Key points

1. Identify whether the work is I/O-bound or CPU-bound before choosing a tool.
2. Shared mutable state between threads needs a lock or a queue.
3. Never call blocking functions such as `time.sleep` inside asyncio code; use `await asyncio.sleep` instead.
4. Guard process-pool entry points with `if __name__ == "__main__":`.
5. Prefer designs where each piece of data has one owner.