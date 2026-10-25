# Concurrency in Gleam

Concurrency lets a program manage several activities independently. A server might handle requests while another process refreshes cached data. A command-line tool might start independent calculations and collect their results.

On the Erlang target, Gleam uses lightweight Erlang processes. These are not operating system processes, and creating one is much cheaper than launching a separate program. Each process has its own execution flow and communicates through messages.

This lesson uses `gleam/erlang/process` from `gleam_erlang`. Each example is a complete module that you can run independently.

## Processes, messages, and subjects

A process is an independent unit of execution. The Erlang runtime schedules processes and can run them across multiple CPU cores.

Concurrency and parallelism are related but different. Concurrency means that activities can make progress independently. Parallelism means that activities actually execute at the same time. Your program should remain correct whether its processes run simultaneously or take turns.

A subject is a typed destination for messages. You create one with `process.new_subject`, send to it with `process.send`, and receive from it with `process.receive`.

The process that creates a subject owns it. Other processes can send messages to that subject, but receiving belongs to its owner. This gives us a useful pattern: create the reply subject in the parent, then pass it to a worker.

## 1. Start a worker and receive its message

Our first worker sends a greeting to its parent.

```gleam
import gleam/erlang/process
import gleam/io

pub fn main() -> Nil {
  let replies = process.new_subject()

  let _worker = process.spawn(fn() {
    process.send(replies, "Hello from the worker!")
  })

  let assert Ok(message) =
    process.receive(replies, within: 2000)

  io.println(message)
}
```

`process.spawn` starts a new process and returns its process identifier. We bind that identifier to `_worker` because this example does not need to use it.

The anonymous function runs in the worker. It captures `replies`, giving the worker a destination for its message.

The parent then waits for a message on that subject. The `within` argument is a timeout in milliseconds. Receiving returns a `Result`: `Ok(message)` when a message arrives, or `Error(Nil)` when the timeout expires.

Here, `let assert` states that the demonstration expects a successful reply. If that expectation fails, the parent crashes instead of continuing with an invalid assumption. Later, we will handle a timeout explicitly.

Notice that we do not add a sleep. The receive operation provides the synchronization we need. If the worker sends first, the message waits for the parent. If the parent receives first, it waits for the worker.

## 2. Collect replies from independent workers

Independent work can be started before the parent waits for results. The next example launches two calculations and receives both replies through one subject.

Each reply carries a label. The label identifies the work without relying on arrival order.

```gleam
import gleam/erlang/process
import gleam/int
import gleam/io

type Reply {
  Completed(label: String, value: Int)
}

fn print_reply(reply: Reply) -> Nil {
  let Completed(label, value) = reply
  io.println(label <> ": " <> int.to_string(value))
}

pub fn main() -> Nil {
  let replies = process.new_subject()

  let _first = process.spawn(fn() {
    process.send(replies, Completed("first", 20 + 22))
  })

  let _second = process.spawn(fn() {
    process.send(replies, Completed("second", 6 * 7))
  })

  let assert Ok(first_reply) =
    process.receive(replies, within: 2000)

  let assert Ok(second_reply) =
    process.receive(replies, within: 2000)

  print_reply(first_reply)
  print_reply(second_reply)
}
```

Both workers compute `42`, but the order of the printed labels is not guaranteed. Starting the first worker before the second does not guarantee that its reply arrives first.

This is an important habit in concurrent programming: distinguish the order in which work is requested from the order in which work completes.

The custom `Reply` type makes the message structure explicit. Gleam infers that `replies` carries values of this type, so sending an unrelated value would be a type error.

The two calculations here are deliberately tiny. Spawning workers for such small operations would usually cost more than it saves. Real candidates include sufficiently large independent calculations or activities that spend time waiting on external systems.

Also notice that each receive has its own timeout. Two receives with a timeout of two seconds do not establish a single two-second deadline for the entire operation.

## 3. Build a request-and-reply protocol

A worker does not have to exit after one task. It can receive requests repeatedly, keeping its state and behavior behind a message protocol.

The following worker maintains a running total. Each addition includes a reply subject, so the caller receives the updated value. A separate stop message requests an orderly shutdown.

```gleam
import gleam/erlang/process.{type Subject}
import gleam/int
import gleam/io

type Request {
  Add(amount: Int, reply_to: Subject(Int))
  Stop(reply_to: Subject(Nil))
}

fn counter(requests: Subject(Request), total: Int) -> Nil {
  case process.receive(requests, within: 2000) {
    Ok(Add(amount, reply_to)) -> {
      let next_total = total + amount
      process.send(reply_to, next_total)
      counter(requests, next_total)
    }

    Ok(Stop(reply_to)) -> {
      process.send(reply_to, Nil)
    }

    Error(Nil) -> Nil
  }
}

pub fn main() -> Nil {
  let ready = process.new_subject()

  let _worker = process.spawn(fn() {
    let requests = process.new_subject()
    process.send(ready, requests)
    counter(requests, 0)
  })

  let assert Ok(requests) =
    process.receive(ready, within: 2000)

  let replies = process.new_subject()

  process.send(requests, Add(10, replies))
  let assert Ok(first) =
    process.receive(replies, within: 2000)

  process.send(requests, Add(5, replies))
  let assert Ok(second) =
    process.receive(replies, within: 2000)

  io.println(int.to_string(first))
  io.println(int.to_string(second))

  let stopped = process.new_subject()
  process.send(requests, Stop(stopped))
  let assert Ok(Nil) =
    process.receive(stopped, within: 2000)

  io.println("Counter acknowledged shutdown.")
}
```

The worker creates its own request subject because it will receive those requests. It sends that subject back through `ready`. This small startup handshake gives the parent a typed address for the worker.

State is represented by the `total` argument. After an addition, the worker calls `counter` with the new total. This tail-recursive loop does not accumulate stack frames as requests are handled.

Only the worker handles its total, and it processes one request at a time. The parent cannot mutate that total directly. This avoids the shared-memory locking pattern common in other concurrency models.

The stop acknowledgement confirms that the stop branch was reached. It is not a general process-monitoring mechanism. In production systems, lifecycle tracking requires more than an application-level reply.

For this short demonstration, an idle timeout ends the loop. A real service should choose its idle behavior deliberately rather than accidentally treating inactivity as failure.

## 4. Handle a timeout without crashing

A timeout is an outcome to handle, not proof that a worker has failed. It means that no matching message was received during the specified wait.

This example first checks an empty subject without waiting. It then starts a worker and handles the later receive explicitly.

```gleam
import gleam/erlang/process
import gleam/io

pub fn main() -> Nil {
  let replies = process.new_subject()

  case process.receive(replies, within: 0) {
    Ok(message) -> io.println(message)
    Error(Nil) -> io.println("No reply is available yet.")
  }

  let _worker = process.spawn(fn() {
    process.send(replies, "The worker has replied.")
  })

  case process.receive(replies, within: 2000) {
    Ok(message) -> io.println(message)
    Error(Nil) -> io.println("The reply deadline expired.")
  }
}
```

The first receive has a zero timeout, so it checks for an available message without waiting. No worker has been started yet, so that subject is empty.

The second receive allows time for the worker to reply. Unlike the earlier assertions, its `case` expression defines behavior for both outcomes.

Importantly, a receive timeout does not cancel the worker. A late reply can still arrive afterward. Retrying a request can therefore duplicate work unless the protocol is designed to prevent it.

For multiple outstanding requests, include request identifiers in messages and replies. For work that changes external state, decide whether retries are safe before adding them.

## Practical habits

Keep messages small and meaningful. Prefer explicit custom types to loosely structured messages.

Do not depend on timing, spawn order, or sleeps for correctness. Use replies and acknowledgements to express dependencies.

Remember that spawning a process does not automatically supervise it. Larger Erlang-target applications commonly use OTP actors and supervisors to organize state, detect failures, and apply restart policies.

Finally, bound both waiting and work. A timeout limits how long a caller waits, but it does not limit how many workers you create or how many requests accumulate. Good concurrency design includes protocols, resource limits, and a clear plan for failure.