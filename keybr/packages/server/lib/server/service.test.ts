import assert from "node:assert/strict";
import { IncomingMessage, Server, ServerResponse } from "node:http";
import { Socket } from "node:net";
import { test } from "node:test";
import { Application } from "@fastr/core";
import { Container } from "@fastr/invert";
import { WebSocketServer } from "ws";
import { Service } from "./service.ts";

// The Host values that recording mode accepts: localhost, an IP address or a
// name that ends in .local, with or without the port. A page that uses DNS
// rebinding sends its own domain name, such as one of the refused values.
const accepted = [
  "localhost",
  "localhost:3000",
  "127.0.0.1:3000",
  "192.168.1.20",
  "192.168.1.20:3100",
  "[::1]",
  "[::1]:3000",
  "[fe80::1c2b:3aff:fe4d:5e6f]:3100",
  "marge.local",
  "Marge.local:3100",
];
const refused = [
  "example.com",
  "example.com:3000",
  "marge.local.example.com",
  "localhost.example.com",
  "local",
  ".local",
  "::1",
  "",
  undefined,
];

test("the server listens on all interfaces; in recording mode it refuses other Host values", (t) => {
  t.mock.property(process, "env", { ...process.env });
  const previous = new Map(
    ["SIGINT", "SIGTERM"].map((signal) => [
      signal,
      new Set(process.listeners(signal)),
    ]),
  );
  t.after(() => {
    for (const [signal, listeners] of previous) {
      for (const listener of process.listeners(signal))
        if (!listeners.has(listener)) process.removeListener(signal, listener);
    }
  });
  for (const enabled of [true, false]) {
    process.env.DETAILED_RECORDING = String(enabled);
    const server = new Server();
    const websocket = new WebSocketServer({ noServer: true });
    const listen = t.mock.method(server, "listen", () => server);
    new Service(server, websocket).start({
      app: new Application(new Container()),
      port: 3000,
    });
    assert.deepEqual(listen.mock.calls[0].arguments, [3000]);
    // The status and the body of an answer sent at once, or null. Without
    // recording, the Host is not checked.
    const answer = (host: string | undefined) => {
      const req = new IncomingMessage(new Socket());
      req.headers.host = host;
      const res = new ServerResponse(req);
      const end = t.mock.method(res, "end", () => res);
      server.emit("request", req, res);
      return end.mock.callCount() > 0
        ? [res.statusCode, ...end.mock.calls[0].arguments]
        : null;
    };
    for (const host of refused) {
      if (enabled)
        assert.deepEqual(answer(host), [403], String(host)); // empty
      else assert.notEqual(answer(host)?.[0], 403, String(host));
    }
    for (const host of accepted) assert.notEqual(answer(host)?.[0], 403, host);
    websocket.close();
  }
});
