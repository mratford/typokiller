# Concurrency in Gleam

Gleam on the Erlang target runs on the BEAM, which makes concurrency cheap. A program can run thousands of lightweight **processes**. Each has its own memory and its own mailbox, and processes talk only by sending immutable messages. There are no shared variables and no locks.

This lesson covers four ideas:

1. Spawning a process and sending it a message.
2. Fanning work out to many processes and collecting the results.
3. Holding state in an actor.
4. Handling timeouts.

All the examples use `gleam_erlang` (the `gleam/erlang/process` module) and `gleam_otp` (the `gleam/otp/actor` module).

## Processes and Subjects

`process.spawn` starts a new process that runs a function. The function returns `Nil`, so a process cannot hand back a result the way a normal function call does. Results travel by message instead.

Messages go through a `Subject(message)`. A subject is typed, so the compiler checks that you only send the right kind of message. The process that creates a subject is the one that receives from it. Any process holding the subject can send to it.

```gleam
import gleam/erlang/process
import gleam/io

pub fn main() -> Nil {
  let subject = process.new_subject()

  let _pid =
    process.spawn(fn() { process.send(subject, "hello from another process") })

  case process.receive(subject, 1000) {
    Ok(message) -> io.println(message)
    Error(Nil) -> io.println("timed out")
  }
}
```

Points to notice:

- `process.new_subject()` is called in `main`, so `main` owns the mailbox for that subject.
- The spawned closure captures `subject` and sends one string.
- `process.receive(subject, 1000)` waits up to 1000 milliseconds. It returns `Ok(message)` on success and `Error(Nil)` if nothing arrived in time.

## Fan Out and Collect

Because processes are cheap, you can start one per piece of work. All the workers can share one subject for replies. The parent then receives once per worker.

Replies arrive in whatever order the workers finish, so if order matters, include an identifier in each message and sort afterward.

```gleam
import gleam/erlang/process.{type Subject}
import gleam/int
import gleam/io
import gleam/list

fn start_worker(n: Int, replies: Subject(#(Int, Int))) -> Nil {
  let _pid = process.spawn(fn() { process.send(replies, #(n, n * n)) })
  Nil
}

fn wait_for_one(replies: Subject(#(Int, Int))) -> #(Int, Int) {
  let assert Ok(result) = process.receive(replies, 1000)
  result
}

pub fn main() -> Nil {
  let replies = process.new_subject()
  let inputs = list.range(1, 5)

  list.each(inputs, fn(n) { start_worker(n, replies) })

  let results =
    inputs
    |> list.map(fn(_) { wait_for_one(replies) })
    |> list.sort(fn(a, b) { int.compare(a.0, b.0) })

  list.each(results, fn(pair) {
    let #(n, squared) = pair
    io.println(int.to_string(n) <> " squared is " <> int.to_string(squared))
  })
}
```

The shape here is common:

1. Create one reply subject.
2. Start one worker per input, each holding the subject.
3. Receive exactly as many messages as workers.
4. Sort by the identifier carried in each message.

The `let assert Ok(result)` crashes if a reply is late. That is acceptable in a short demonstration. Real code should decide what to do on a timeout.

## Actors: Processes with State

A bare process that loops while holding state is awkward to write by hand. The `gleam/otp/actor` module wraps the pattern. An actor has:

- an initial state,
- a handler function that receives each message together with the current state,
- a return value that says what to do next: `actor.continue(new_state)` or `actor.stop()`.

To ask an actor a question, include a `Subject` for the reply inside the message. `process.call` builds the reply subject, sends your message, and waits for the answer.

```gleam
import gleam/erlang/process.{type Subject}
import gleam/int
import gleam/io
import gleam/otp/actor

pub type Message {
  Add(Int)
  Get(Subject(Int))
  Shutdown
}

fn handle(state: Int, message: Message) -> actor.Next(Int, Message) {
  case message {
    Add(amount) -> actor.continue(state + amount)
    Get(reply) -> {
      process.send(reply, state)
      actor.continue(state)
    }
    Shutdown -> actor.stop()
  }
}

pub fn main() -> Nil {
  let assert Ok(started) =
    actor.new(0)
    |> actor.on_message(handle)
    |> actor.start

  let counter = started.data

  process.send(counter, Add(5))
  process.send(counter, Add(10))
  process.send(counter, Add(27))

  let total = process.call(counter, 1000, fn(reply) { Get(reply) })
  io.println("Total: " <> int.to_string(total))

  process.send(counter, Shutdown)
}
```

Details worth remembering:

- `actor.new(0)` sets the initial state. `actor.on_message(handle)` installs the handler. `actor.start` launches the process.
- `actor.start` returns a `Result`. On success, `started.data` is the `Subject(Message)` used to talk to the actor.
- Messages from one sender are delivered in the order they were sent, so the three `Add` messages are all handled before the `Get`.
- The message type is a custom type. This makes the actor's protocol explicit, and the compiler checks every case.

## Timeouts and Slow Workers

Every receive takes a timeout in milliseconds. A timeout is not an exception. It is an `Error(Nil)` that you handle like any other value. This makes it straightforward to write code that gives up, retries, or falls back to a default.

A message that arrives after you stopped waiting is not lost. It stays in the mailbox, and a later receive on the same subject will find it.

```gleam
import gleam/erlang/process
import gleam/io

pub fn main() -> Nil {
  let subject = process.new_subject()

  let _pid =
    process.spawn(fn() {
      process.sleep(200)
      process.send(subject, "slow result")
    })

  case process.receive(subject, 50) {
    Ok(message) -> io.println("Early: " <> message)
    Error(Nil) -> io.println("Not ready yet, doing something else")
  }

  case process.receive(subject, 1000) {
    Ok(message) -> io.println("Later: " <> message)
    Error(Nil) -> io.println("Gave up")
  }
}
```

The first receive waits only 50 ms, while the worker sleeps for 200 ms, so the first case reports that nothing is ready. The second receive waits long enough and gets the message.

`process.sleep` pauses only the calling process. Other processes keep running, which is why a sleeping worker never blocks `main`.

## Summary

- Processes are cheap and isolated. Start them with `process.spawn`.
- Processes communicate with typed `Subject` values using `process.send` and `process.receive`.
- A receive can time out and returns `Result(message, Nil)`, so you handle slowness explicitly.
- For fan-out, share one reply subject, receive once per worker, and tag messages so you can sort them.
- For long-lived state, use an actor: a handler function from `(state, message)` to `actor.Next`, started with `actor.new`, `actor.on_message` and `actor.start`.
- For request and reply, put a `Subject` in the message and use `process.call`.

A good exercise is to extend the counter actor with a `Subtract(Int)` message and a `Reset` message. Then fan out several processes that all send `Add` to the same counter, and check that the total is correct. The actor handles one message at a time, so the updates never race.