# Concurrency with processes

Concurrency lets a program make progress on more than one task at a time. On the Erlang target, Gleam uses lightweight Erlang processes. These are not operating-system threads: the runtime can create many of them, schedule them, and move between them.

Processes communicate by sending messages. They do not share ordinary mutable variables, so a worker cannot reach into another process and change its local state. This makes the flow of information explicit: send a message, then handle the message where it is received.

The examples use `gleam_erlang`'s `process` module. Each one starts a worker, sends messages without reading from the terminal, and finishes promptly. The `process.self()` call gives a process identifier for the current process. A worker can use that identifier to send a result back.

## Start a worker and receive a result

`process.spawn` starts a function in a separate process. The main process can continue running while the worker does its work. Here, the worker computes a value and sends it to the main process. The main process waits for a message with `process.receive_timeout`.

```gleam
import gleam/erlang/process

pub fn main() -> Nil {
  let parent = process.self()

  let _worker = process.spawn(fn() {
    let answer = 6 * 7
    process.send(parent, answer)
  })

  let assert Ok(answer) = process.receive_timeout(1_000)
  let assert answer == 42
  Nil
}
```

The timeout is expressed in milliseconds. If no message arrives within the allotted time, `receive_timeout` returns an error instead of waiting forever. The `assert Ok(answer)` pattern is useful in a small demonstration where a message is expected. In a real application, handle the error deliberately: a timeout may be a normal outcome, not a reason to crash.

The worker identifier is bound to `_worker` because the example does not need to use it again. Keeping a process identifier can be useful when a program needs to send more messages to a worker or monitor its lifetime.

## A mailbox can hold more than one message

A process has a mailbox: a queue of messages sent to it. A single worker can send several messages, and the receiver can take them one at a time. Messages from one sender arrive in the order they were sent. That ordering is useful, but it does not mean that messages from different workers have a predictable order.

```gleam
import gleam/erlang/process

pub fn main() -> Nil {
  let parent = process.self()

  let _worker = process.spawn(fn() {
    process.send(parent, "first")
    process.send(parent, "second")
  })

  let assert Ok(first) = process.receive_timeout(1_000)
  let assert Ok(second) = process.receive_timeout(1_000)
  let assert first == "first"
  let assert second == "second"
  Nil
}
```

Each receive takes one matching message from the mailbox. These receives are separate waits: the first message is not returned as a pair with the second. If the second message does not arrive before its timeout, the second receive reports that outcome independently.

In larger programs, choose message shapes that make their meaning clear. A message might be a number, a string, or a value of a custom type. A custom type is especially helpful when a process handles several kinds of requests, because the receiver can use `case` to respond to each variant.

## Several workers and completion order

A program can start multiple workers. Their completion order depends on scheduling and on the work each one performs. Do not assume that the first worker started will send the first result.

This example starts two workers and receives two integers. It adds them rather than depending on which result arrives first. Both workers send to the same parent process, and each sends exactly one message.

```gleam
import gleam/erlang/process

pub fn main() -> Nil {
  let parent = process.self()

  let _first_worker = process.spawn(fn() {
    process.send(parent, 10)
  })

  let _second_worker = process.spawn(fn() {
    process.send(parent, 32)
  })

  let assert Ok(first_result) = process.receive_timeout(1_000)
  let assert Ok(second_result) = process.receive_timeout(1_000)
  let total = first_result + second_result
  let assert total == 42
  Nil
}
```

The two results can arrive in either order, but their sum is the same. This is a basic pattern for collecting independent results. Real programs also need to identify which result belongs to which task. One approach is to send a tuple containing an identifier and a result, then inspect the identifier when receiving it.

Concurrency does not automatically make a program faster. Starting workers has a cost, and tasks that must happen in sequence cannot be made independent just by spawning processes. Use separate processes when work can proceed independently, or when separate responsibilities benefit from clear message boundaries.

## Handle a timeout

Waiting is also part of concurrent programming. A message might never arrive because a worker failed, took too long, or had nothing to report. A timeout gives the receiver a way to stop waiting and choose what to do next.

This example intentionally starts no worker. The receive times out quickly, and the program handles the error rather than asserting that a message must exist.

```gleam
import gleam/erlang/process

pub fn main() -> Nil {
  case process.receive_timeout(10) {
    Ok(message) -> {
      let _unused = message
      Nil
    }
    Error(Nil) -> Nil
  }
}
```

The `case` makes both outcomes visible. In the successful branch, this example ignores the message because none is expected; in an application, that branch would usually process it. In the error branch, the program chooses to continue. Another program might retry, record a failure, or return an error to its caller.

Use short timeouts in tests and demonstrations so they finish quickly. For production work, choose a timeout that fits the operation, and make the timeout behavior part of the design rather than an afterthought.

## Keep message protocols simple

A process is easiest to reason about when its messages form a small protocol. For example, a worker might accept a request and return a response. Decide what each message means, who is allowed to send it, and what the receiver does if it arrives late or is unexpected.

A few practical habits help:

- Keep each worker's responsibility focused.
- Send results back explicitly instead of relying on shared state.
- Do not rely on an ordering between different senders.
- Include an identifier when results from several workers must be matched to tasks.
- Handle timeouts and failures intentionally.

These examples use simple values to focus on spawning and messaging. As a program grows, custom message types make protocols safer and easier to read. The central idea remains the same: a process owns its own work, and messages are the way processes coordinate.