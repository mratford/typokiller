import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { type AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test, type TestContext } from "node:test";
import { setImmediate } from "node:timers/promises";
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
  type KeyboardPictures,
  recordingConfigSchema,
  type RecordingRecord,
} from "@keybr/recording";
import { RecordingStore } from "@keybr/recording-store";
import { createTestServer } from "../test/request.ts";
import { RecordingController } from "./controller.ts";

const fixture = (path: string): unknown =>
  JSON.parse(
    readFileSync(
      new URL(`../../../../keybr-recording/fixtures/${path}`, import.meta.url),
      "utf8",
    ),
  );
const keyboardExport = (name: string) => fixture(`keyboards/${name}.json`);
/** typokiller's pictures of the keyboards in the "initial" export. */
const pictures = fixture("pictures/initial.json") as KeyboardPictures;

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

type Answer = { export: unknown; pictures?: unknown };

/**
 * A fake typokiller that answers `GET /api/keyboards/export` with `answer.export`
 * and `GET /api/keyboards/pictures` with `answer.pictures` (none by default),
 * or never answers when it is "no answer", and the keybr server that asks it.
 */
async function withTypokiller(t: TestContext, answer: Answer) {
  const requests: string[] = [];
  const typokiller = createServer((req, res) => {
    requests.push(req.url!);
    const body =
      req.url === "/api/keyboards/pictures"
        ? (answer.pictures ?? {})
        : answer.export;
    if (body === "no answer") return;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify(body));
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
  assert.deepEqual(
    requests,
    Array(3).fill(["/api/keyboards/export", "/api/keyboards/pictures"]).flat(),
  );
  assert.equal(errors.callCount(), 0);
});

test("config gives each layout typokiller's picture of its .vil, and none when typokiller sent none", async (t) => {
  const answer: Answer = { export: keyboardExport("initial"), pictures };
  const { config } = await withTypokiller(t, answer);
  const layouts = (await config()).keyboards.flatMap((k) => k.layouts);
  assert.equal(layouts.length, 4);
  for (const layout of layouts)
    assert.deepEqual(layout.picture, pictures[layout.vilHash]);
  // The pictures are not stored: an answer without them gives none.
  answer.pictures = {};
  for (const keyboard of (await config()).keyboards)
    for (const layout of keyboard.layouts)
      assert.equal(layout.picture, undefined);
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
  [
    "typokiller does not answer",
    { export: "no answer", pictures: "no answer" },
    /timeout/i,
  ],
  [
    "typokiller sends an invalid export",
    { export: { format: "other" } },
    /Invalid/,
  ],
] as const) {
  test(`when ${name}, config answers with the keyboards it has, with no pictures, and says they are outdated`, async (t) => {
    const answer: Answer = { export: keyboardExport("initial"), pictures };
    const { config, errors } = await withTypokiller(t, answer);
    const first = await config();
    Object.assign(answer, broken);
    // The keybr server stops on a promise that is resolved or rejected twice.
    const twice = t.mock.fn();
    process.on("multipleResolves", twice);
    t.after(() => process.off("multipleResolves", twice));
    const outdated = await config();
    await setImmediate();
    assert.equal(twice.mock.callCount(), 0);
    assert.deepEqual(outdated, {
      ...first,
      keyboards: first.keyboards.map((k) => ({
        ...k,
        layouts: k.layouts.map(({ picture, ...layout }) => layout),
      })),
      keyboardsOutdated: true,
    });
    assert.equal(errors.callCount(), 1);
    assert.match(String(errors.calls[0].arguments[0]), reason);
  });
}

for (const [name, broken] of [
  ["sends invalid pictures", { other: {} }],
  ["does not send the pictures", "no answer"],
] as const) {
  test(`when typokiller ${name}, config has the new keyboards with no pictures`, async (t) => {
    const answer: Answer = { export: keyboardExport("initial"), pictures };
    const { config, errors } = await withTypokiller(t, answer);
    const first = await config();
    answer.export = keyboardExport("updated");
    answer.pictures = broken;
    const updated = await config();
    assert.equal(updated.keyboardsOutdated, false);
    assert.equal(
      updated.keyboards.flatMap((k) => k.layouts).length,
      first.keyboards.flatMap((k) => k.layouts).length + 3,
    );
    for (const keyboard of updated.keyboards)
      for (const layout of keyboard.layouts)
        assert.equal(layout.picture, undefined);
    assert.equal(errors.callCount(), 1);
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
