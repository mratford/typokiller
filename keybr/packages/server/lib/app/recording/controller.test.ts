import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { type AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test, type TestContext } from "node:test";
import { request } from "@fastr/client";
import { start } from "@fastr/client-testlib";
import { allToRoutes } from "@fastr/controller";
import { Application } from "@fastr/core";
import { HttpError } from "@fastr/errors";
import { Container } from "@fastr/invert";
import { Router } from "@fastr/middleware-router";
import { Logger } from "@keybr/logger";
import {
  fixtureSnapshots,
  type KeyboardCatalogue,
  recordingConfigSchema,
  type RecordingRecord,
} from "@keybr/recording";
import { RecordingStore } from "@keybr/recording-store";
import { createTestServer } from "../test/request.ts";
import { RecordingController } from "./controller.ts";

const keyboardExport = (name: string): unknown =>
  JSON.parse(
    readFileSync(
      new URL(
        `../../../../keybr-recording/fixtures/keyboards/${name}.json`,
        import.meta.url,
      ),
      "utf8",
    ),
  );

test("recording routes are independent of login, bounded, versioned, transactional and opt-in", async (t) => {
  const dir = mkdtempSync(join(tmpdir(), "keybr-recording-route-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  t.mock.property(process, "env", {
    ...process.env,
    DETAILED_RECORDING: "false",
  });
  const container = new Container();
  container.bind("dataDir").toValue(dir);
  const app = new Application(container)
    .use(async (ctx, next) => {
      try {
        await next();
      } catch (error) {
        ctx.response.status = error instanceof HttpError ? error.status : 500;
        ctx.response.body = { error: String(error) };
      }
    })
    .use(
      new Router().registerAll(allToRoutes(RecordingController)).middleware(),
    );
  const client = request.use(start(createTestServer(app.callback())));
  assert.deepEqual(
    await (await client.GET("/_/recording/config").send()).body.json(),
    { enabled: false },
  );
  assert.equal(
    (await client.POST("/_/recording/batches").send({})).status,
    404,
  );
  assert.equal(existsSync(join(dir, "recordings.sqlite")), false);
  process.env.DETAILED_RECORDING = "true";
  const configResponse = await client.GET("/_/recording/config").send();
  assert.equal(configResponse.headers.get("Cache-Control"), "no-store");
  const config = recordingConfigSchema.parse(await configResponse.body.json());
  assert.deepEqual(config, {
    enabled: true,
    schemaVersion: 1,
    applicationRevision: "local",
    keyboards: [],
    keyboardsOutdated: false,
    analysisUrl: null,
  });
  const record: RecordingRecord = {
    schemaVersion: 1,
    attemptId: crypto.randomUUID(),
    sequence: 0,
    observedAt: 0,
    type: "start",
    context: {
      text: "abc",
      applicationRevision: "test",
      board: null,
      keymap: null,
      settings: { typing: {}, exercise: {}, layout: {} },
    },
  };
  const batch = {
    schemaVersion: 1,
    records: [record],
    recovery: [],
    snapshots: fixtureSnapshots,
  };
  const posted = await client.POST("/_/recording/batches").send(batch);
  assert.equal(posted.status, 200);
  assert.deepEqual(await posted.body.json(), {
    records: [{ attemptId: record.attemptId, sequence: 0 }],
    recovery: [],
  });
  assert.equal(
    (await client.POST("/_/recording/batches").send(batch)).status,
    200,
  );
  assert.equal(
    (
      await client
        .POST("/_/recording/batches")
        .send({ ...batch, records: [{ ...record, observedAt: 99 }] })
    ).status,
    409,
  );
  for (const invalid of [
    {},
    { ...batch, schemaVersion: 2 },
    { ...batch, records: [{ ...record, sequence: 1 }] },
    { ...batch, records: [{ ...record, attemptId: "invalid" }] },
    { ...batch, records: Array(129).fill(record) },
  ]) {
    assert.equal(
      (await client.POST("/_/recording/batches").send(invalid)).status,
      400,
    );
  }
  assert.equal(
    (
      await client
        .POST("/_/recording/batches")
        .send({ padding: "a".repeat(300000) })
    ).status,
    413,
  );
  assert.equal(
    (
      await client
        .POST("/_/recording/batches")
        .header("Content-Type", "application/json")
        .send("{broken")
    ).status,
    400,
  );
  t.mock.method(RecordingStore.prototype, "append", () => {
    throw new TypeError("Unexpected store bug");
  });
  assert.equal(
    (await client.POST("/_/recording/batches").send(batch)).status,
    500,
  );
});

test("config lists imported keyboards, whose snapshots Attempts can reference without resending", async (t) => {
  const dir = mkdtempSync(join(tmpdir(), "keybr-recording-keyboards-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  t.mock.property(process, "env", {
    ...process.env,
    DETAILED_RECORDING: "true",
    APPLICATION_REVISION: "rev-1",
  });
  const importer = new RecordingStore(join(dir, "recordings.sqlite"));
  importer.importKeyboards(keyboardExport("initial"));
  importer.close();
  const container = new Container();
  container.bind("dataDir").toValue(dir);
  const app = new Application(container).use(
    new Router().registerAll(allToRoutes(RecordingController)).middleware(),
  );
  const client = request.use(start(createTestServer(app.callback())));
  const config = recordingConfigSchema.parse(
    await (await client.GET("/_/recording/config").send()).body.json(),
  );
  assert.ok(config.enabled);
  assert.equal(config.applicationRevision, "rev-1");
  assert.deepEqual(
    config.keyboards.map((board) => board.name),
    ["Q4", "Sofle", "Sweep"],
  );
  const layout = config.keyboards[2].layouts[0];
  const startRecord = (keymap: { id: string; version: string }) => ({
    schemaVersion: 1,
    snapshots: [],
    recovery: [],
    records: [
      {
        schemaVersion: 1,
        attemptId: crypto.randomUUID(),
        sequence: 0,
        observedAt: 0,
        type: "start",
        context: {
          text: "abc",
          applicationRevision: "rev-1",
          board: layout.board,
          keymap,
          settings: { typing: {}, exercise: {}, layout: {} },
        },
      },
    ],
  });
  assert.equal(
    (await client.POST("/_/recording/batches").send(startRecord(layout.keymap)))
      .status,
    200,
  );
  assert.equal(
    (
      await client
        .POST("/_/recording/batches")
        .send(startRecord({ ...layout.keymap, version: "unknown" }))
    ).status,
    400,
  );
});

/**
 * A fake typokiller that answers `GET /api/keyboards/export` with `answer.export`,
 * or never answers when it is "no answer", and the keybr server that asks it.
 */
async function withTypokiller(t: TestContext, answer: { export: unknown }) {
  const requests: string[] = [];
  const typokiller = createServer((req, res) => {
    requests.push(req.url!);
    if (answer.export === "no answer") return;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify(answer.export));
  });
  await new Promise<void>((resolve) =>
    typokiller.listen(0, "127.0.0.1", resolve),
  );
  t.after(() => {
    typokiller.closeAllConnections();
    typokiller.close();
  });
  const dir = mkdtempSync(join(tmpdir(), "keybr-recording-typokiller-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { port } = typokiller.address() as AddressInfo;
  t.mock.property(process, "env", {
    ...process.env,
    DETAILED_RECORDING: "true",
    TYPOKILLER_URL: `http://127.0.0.1:${port}`,
  });
  const errors = t.mock.method(Logger, "error", () => {});
  const container = new Container();
  container.bind("dataDir").toValue(dir);
  const app = new Application(container).use(
    new Router().registerAll(allToRoutes(RecordingController)).middleware(),
  );
  const client = request.use(start(createTestServer(app.callback())));
  const config = async () => {
    const response = await client.GET("/_/recording/config").send();
    assert.equal(response.status, 200);
    const config = recordingConfigSchema.parse(await response.body.json());
    assert.ok(config.enabled);
    return config;
  };
  return { requests, config, errors: errors.mock };
}

test("config gets the keyboards from typokiller each time", async (t) => {
  const answer = { export: keyboardExport("initial") };
  const { requests, config, errors } = await withTypokiller(t, answer);
  const layouts = (config: { keyboards: KeyboardCatalogue }) =>
    config.keyboards.map(
      (k) => `${k.name}: ${k.layouts.map((l) => l.letterLayout).join(", ")}`,
    );
  const first = await config();
  assert.deepEqual(layouts(first), [
    "Q4: QWERTY",
    "Sofle: free-range",
    "Sweep: free-range, QWERTY",
  ]);
  assert.equal(first.keyboardsOutdated, false);
  assert.match(first.analysisUrl!, /^http:\/\/127\.0\.0\.1:\d+\/analysis$/);
  // The same export again adds nothing.
  assert.deepEqual(await config(), first);
  answer.export = keyboardExport("updated");
  // The new Sweep definition makes three new layouts. They come first, and the
  // two older ones stay.
  assert.deepEqual(layouts(await config()), [
    "Q4: QWERTY",
    "Sofle: free-range",
    "Sweep: free-range, free-range, QWERTY, free-range, QWERTY",
  ]);
  assert.deepEqual(requests, Array(3).fill("/api/keyboards/export"));
  assert.equal(errors.callCount(), 0);
});

test("a new keyboard from typokiller appears in the config", async (t) => {
  const initial = keyboardExport("initial") as {
    boards: { sourceId: number; name: string }[];
  };
  const answer = { export: initial };
  const { config } = await withTypokiller(t, answer);
  await config();
  answer.export = {
    ...initial,
    boards: [
      ...initial.boards,
      { ...initial.boards[2], sourceId: 4, name: "Q5" },
    ],
  };
  assert.deepEqual(
    (await config()).keyboards.map((k) => k.name),
    ["Q4", "Q5", "Sofle", "Sweep"],
  );
});

for (const [name, broken, reason] of [
  ["typokiller does not answer", "no answer", /timeout/i],
  ["typokiller sends an invalid export", { format: "other" }, /Invalid/],
] as const) {
  test(`when ${name}, config answers with the keyboards it has and says they are outdated`, async (t) => {
    const answer: { export: unknown } = { export: keyboardExport("initial") };
    const { config, errors } = await withTypokiller(t, answer);
    const first = await config();
    answer.export = broken;
    const outdated = await config();
    assert.deepEqual(outdated, { ...first, keyboardsOutdated: true });
    assert.equal(errors.callCount(), 1);
    assert.match(String(errors.calls[0].arguments[0]), reason);
  });
}

test("without TYPOKILLER_URL, config does not ask typokiller", async (t) => {
  const answer = { export: keyboardExport("initial") };
  const { requests, config } = await withTypokiller(t, answer);
  delete process.env.TYPOKILLER_URL;
  assert.deepEqual(await config(), {
    enabled: true,
    schemaVersion: 1,
    applicationRevision: "local",
    keyboards: [],
    keyboardsOutdated: false,
    analysisUrl: null,
  });
  assert.deepEqual(requests, []);
});
