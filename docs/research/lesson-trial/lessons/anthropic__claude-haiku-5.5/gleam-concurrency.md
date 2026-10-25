# Lesson: Concurrency in Gleam

Gleam runs on the BEAM, the virtual machine behind Erlang and Elixir. The BEAM is built for huge numbers of lightweight **processes**. These are not operating system threads. Creating one is cheap, and a Gleam program can run thousands of them at once.

Concurrency in Gleam follows a few rules:

- Each process has its own memory. Processes never share variables.
- Processes communicate only by sending messages.
- A process handles one message at a time, so its own state is never accessed concurrently.

Because of these rules, you don't need locks or mutexes. If you're used to threads with shared memory, this model can feel strange at first, but it removes an entire category of bugs.

In this lesson you'll use the `gleam/erlang/process` module from `gleam_erlang`. Every example is a complete program that runs without input.

## Starting a process

`process.start(running, linked)` runs a function in a new process and returns its `Pid`, the process identifier. The second argument controls linking. `False` means the new process is unlinked, so if it crashes, your main process keeps running. `True` links the two processes so that a crash propagates.

Messages travel through a `Subject`. You create one with `process.new_subject()`, send to it with `process.send`, and read from it with `process.receive(subject, timeout_ms)`. That call returns `Ok(message)` or `Error(Nil)` if nothing arrives in time.

Here is the smallest useful example:

```gleam
import gleam/erlang/process
import gleam/io

pub fn main() -> Nil {
  let inbox = process.new_subject()
  let _pid =
    process.start(fn() { process.send(inbox, "hello from a process") }, False)
  let assert Ok(message) = process.receive(inbox, 1000)
  io.println(message)
}
```

The main process creates `inbox`, starts a second process that sends a string into it, and then waits up to one second for the reply. The `_pid` name tells the reader, and the compiler, that we don't need the process identifier.

## Fan-out: many workers, one collector

Real programs often split work across several processes and gather the results. The workers finish in an unpredictable order, so the collector has to handle that. A common technique is to tag each result with an identifier and sort at the end.

```gleam
import gleam/erlang/process
import gleam/int
import gleam/io
import gleam/list

fn square_worker(reply: process.Subject(#(Int, Int)), n: Int) -> Nil {
  process.send(reply, #(n, n * n))
}

pub fn main() -> Nil {
  let results = process.new_subject()
  let numbers = [1, 2, 3, 4, 5]

  list.each(numbers, fn(n) {
    let _pid = process.start(fn() { square_worker(results, n) }, False)
    Nil
  })

  let collected =
    list.map(numbers, fn(_) {
      let assert Ok(result) = process.receive(results, 1000)
      result
    })

  let sorted =
    list.sort(collected, fn(a, b) { int.compare(a.0, b.0) })

  list.each(sorted, fn(pair) {
    io.println(
      int.to_string(pair.0) <> " squared is " <> int.to_string(pair.1),
    )
  })
}
```

Notice the important detail: each worker sends `#(n, n * n)`, so the pair carries its own identity. Without that, the output order would depend on scheduling and could change from run to run. Sorting by `pair.0` makes the output deterministic even though the work ran in parallel.

Also notice that `list.each` expects its function to return `Nil`, so we add an explicit `Nil` after `process.start`. The `let _pid` line discards the value we don't need.

## Processes as actors: state in a loop

Since a process can't see another process's variables, long-lived state lives inside a process that loops and receives messages. This pattern is the basis of Gleam's actor abstraction. Here we write it by hand so you can see the mechanics.

Each message is a value of a custom type. The loop receives one message, handles it, and calls itself with the updated state. Because the call is in tail position, it runs in constant memory.

```gleam
import gleam/erlang/process.{type Subject}
import gleam/int
import gleam/io

pub type Msg {
  Increment
  Get(reply: Subject(Int))
  Stop
}

fn run(inbox: Subject(Msg), count: Int) -> Nil {
  case process.receive_forever(inbox) {
    Increment -> run(inbox, count + 1)
    Get(reply) -> {
      process.send(reply, count)
      run(inbox, count)
    }
    Stop -> Nil
  }
}

fn start_counter() -> Subject(Msg) {
  // A Subject can only be received from by the process that created it,
  // so the counter creates its own inbox and sends it back to us.
  let setup = process.new_subject()
  let _pid =
    process.start(
      fn() {
        let inbox = process.new_subject()
        process.send(setup, inbox)
        run(inbox, 0)
      },
      False,
    )
  let assert Ok(inbox) = process.receive(setup, 1000)
  inbox
}

pub fn main() -> Nil {
  let counter = start_counter()

  process.send(counter, Increment)
  process.send(counter, Increment)
  process.send(counter, Increment)

  let reply = process.new_subject()
  process.send(counter, Get(reply))
  let assert Ok(total) = process.receive(reply, 1000)
  io.println("count: " <> int.to_string(total))

  process.send(counter, Stop)
}
```

Pay attention to the handshake in `start_counter`. The inbox has to be created inside the counter process, because only the creating process can receive from a subject. The counter sends its inbox back through a setup subject, and the caller then uses it to send messages.

The `Get` message includes a `reply` subject. This is the standard way to ask a question: you include a return address in the request. The counter never needs to know who is asking, only where to send the answer.

## Timeouts

Waiting forever is risky. A worker might crash, or a network call might hang. `process.receive` with a timeout lets you decide what to do when a reply is late.

```gleam
import gleam/erlang/process
import gleam/io

pub fn main() -> Nil {
  let inbox = process.new_subject()

  let _pid =
    process.start(
      fn() {
        process.sleep(300)
        process.send(inbox, "slow result")
      },
      False,
    )

  case process.receive(inbox, 100) {
    Ok(message) -> io.println(message)
    Error(Nil) -> io.println("no reply within 100ms")
  }

  case process.receive(inbox, 1000) {
    Ok(message) -> io.println(message)
    Error(Nil) -> io.println("gave up")
  }
}
```

The first `receive` gives up after 100 milliseconds and returns `Error(Nil)`. The worker is still sleeping, so the second `receive` waits up to a full second and gets the message. A timeout doesn't cancel the worker. It only stops your process from waiting. If the worker's result is no longer needed, you can design it to ignore late messages, or link it to a supervisor.

## Key ideas to remember

- **Processes are cheap and isolated.** Spawn them freely, and never expect them to share variables.
- **Messages are the only channel.** Send plain values, and include reply subjects when you need an answer.
- **Subjects belong to their creator.** Only the process that calls `new_subject` can receive from it.
- **Order is not guaranteed.** Tag results with identifiers and sort when output must be stable.
- **Always consider timeouts.** `receive` with a limit lets you recover from slow or dead workers.

## Exercises

1. Change the fan-out example so each worker computes the square of a larger number, and observe that the sorted output is stable.
2. Extend the counter with a `Reset` message that sets the count back to zero.
3. Write a process that receives a list of numbers in one message and replies with their sum.

For larger systems, the `gleam_otp` package provides actors, supervisors, and tasks built on these same primitives. Understanding the underlying messages and processes, as you've done here, makes those higher-level tools much easier to use correctly.