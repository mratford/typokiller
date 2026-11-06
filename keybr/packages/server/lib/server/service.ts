import { Server, ServerResponse } from "node:http";
import { userInfo } from "node:os";
import { type Application } from "@fastr/core";
import { injectable } from "@fastr/invert";
import { Env } from "@keybr/config";
import { Logger } from "@keybr/logger";
import { WebSocketServer } from "ws";
import { type Closer, createCloser } from "./closer.ts";

const { pid } = process;
const { username } = userInfo();

// In recording mode, the Host that a request may name: localhost, an IPv4
// address, an IPv6 address in brackets or a name that ends in .local, with or
// without the port. A web page that uses DNS rebinding (its own domain name,
// pointed at this computer) sends that domain name as the Host. A domain name
// on the internet is not an IP address and does not end in .local, so the page
// is refused. typokiller uses the same rule (`ALLOWED_HOST` in
// src/typokiller/app.py).
const allowedHost =
  /^(localhost|\d+\.\d+\.\d+\.\d+|\[[0-9a-f:.]+\]|([a-z0-9-]+\.)+local)(:\d+)?$/i;

@injectable({ singleton: true })
export class Service {
  readonly #server: Server;
  readonly #webSocketServer: WebSocketServer;
  readonly #closer: Closer;

  constructor(server: Server, webSocketServer: WebSocketServer) {
    this.#server = server;
    this.#webSocketServer = webSocketServer;
    this.#closer = createCloser(this.#server, this.#webSocketServer);
  }

  start({ app, port }: { app: Application; port: number }) {
    const application = app.callback();
    const recording = Env.getBoolean("DETAILED_RECORDING", false);
    const callback: typeof application = (req, res) => {
      if (recording && !allowedHost.test(req.headers.host ?? "")) {
        res.statusCode = 403;
        res.end();
        return;
      }
      application(req, res);
    };
    this.#server.on("request", callback);
    this.#server.on("upgrade", (req, socket, head) => {
      if (head.length > 0) {
        // Unread head back to the request stream.
        socket.unshift(head);
      }
      const res = new ServerResponse(req);
      res.shouldKeepAlive = false;
      callback(req, res);
    });
    this.#server.listen(port);
    process.on("SIGINT", () => {
      this.stop();
    });
    process.on("SIGTERM", () => {
      this.stop();
    });
    Logger.info("Server started", { pid, port, username });
  }

  stop() {
    const graceful = () => {
      Logger.info("Server stopped gracefully", { pid });
      process.exit(0);
    };

    const forceful = () => {
      Logger.info("Server stopped forcefully", { pid });
      process.exit(0);
    };

    Logger.info("Stopping server...", { pid });

    // Stop accepting new connections.
    this.#closer(false, graceful);

    // There may be open keep-alive connections, force shutdown.
    setTimeout(forceful, 1000);
  }
}
