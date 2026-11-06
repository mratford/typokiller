import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";
import { RecordingStore } from "@keybr/recording-store";
import { recordingCommand } from "./index.ts";

test("export writes a copy of the recording database", async (t) => {
  const dir = mkdtempSync(join(tmpdir(), "keybr-cli-recording-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const run = (...args: string[]) =>
    recordingCommand(() => dir)
      .exitOverride()
      .parseAsync(args, { from: "user" });

  await assert.rejects(run("export", join(dir, "none.sqlite")), /No recording/);
  const store = new RecordingStore(join(dir, "recordings.sqlite"));
  store.importKeyboards(
    JSON.parse(
      readFileSync(
        new URL(
          "../../../../keybr-recording/fixtures/keyboards/initial.json",
          import.meta.url,
        ),
        "utf8",
      ),
    ),
  );
  store.close();

  const output = join(dir, "export.sqlite");
  await run("export", output);
  assert.ok(existsSync(output));
  const db = new DatabaseSync(output, { readOnly: true });
  t.after(() => db.close());
  assert.equal(db.prepare("SELECT count(*) AS n FROM snapshots").get()!.n, 7);
});
