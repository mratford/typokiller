import { join } from "node:path";
import { body, controller, http } from "@fastr/controller";
import { Context } from "@fastr/core";
import { BadRequestError, HttpError, NotFoundError } from "@fastr/errors";
import { inject, injectable } from "@fastr/invert";
import { Env } from "@keybr/config";
import { Logger } from "@keybr/logger";
import { maxBatchBytes, schemaVersion } from "@keybr/recording";
import {
  RecordingConflict,
  RecordingStore,
  RecordingValidationError,
} from "@keybr/recording-store";

@injectable({ singleton: true })
@controller()
export class RecordingController {
  #store?: RecordingStore;
  constructor(@inject("dataDir") readonly dataDir: string) {}

  @http.GET("/_/recording/config")
  async config(ctx: Context) {
    ctx.response.headers.set("Cache-Control", "no-store");
    if (!Env.getBoolean("DETAILED_RECORDING", false)) {
      ctx.response.body = { enabled: false };
      return;
    }
    const store = this.#open();
    const typokillerUrl = Env.getString("TYPOKILLER_URL", "");
    const updated = await updateKeyboards(store, typokillerUrl);
    ctx.response.body = {
      enabled: true,
      schemaVersion,
      applicationRevision: Env.getString("APPLICATION_REVISION", "local"),
      // Imported from typokiller; snapshots stay on the server.
      keyboards: store.keyboards(),
      keyboardsOutdated: !updated,
      analysisUrl: typokillerUrl
        ? new URL("/analysis", typokillerUrl).href
        : null,
    };
  }

  #open() {
    return (this.#store ??= new RecordingStore(
      join(this.dataDir, "recordings.sqlite"),
    ));
  }

  @http.POST("/_/recording/batches")
  append(
    ctx: Context,
    @body.json(null, { maxLength: maxBatchBytes }) value: unknown,
  ) {
    if (!Env.getBoolean("DETAILED_RECORDING", false)) throw new NotFoundError();
    const store = this.#open();
    try {
      ctx.response.body = store.append(value);
      ctx.response.headers.set("Cache-Control", "no-store");
    } catch (error) {
      if (error instanceof RecordingConflict)
        throw new HttpError(409, error.message);
      if (
        error instanceof RecordingValidationError ||
        error instanceof RangeError ||
        (error instanceof Error && error.name === "ZodError")
      )
        throw new BadRequestError(error.message);
      throw error;
    }
  }
}

/**
 * Gets the keyboard export from typokiller at `url` (`TYPOKILLER_URL`) and
 * imports it. Does nothing when `url` is empty. Returns false, and writes the
 * reason to the log, when typokiller does not answer within 2 seconds or the
 * import rejects the answer. The import changes nothing then.
 */
async function updateKeyboards(
  store: RecordingStore,
  url: string,
): Promise<boolean> {
  if (!url) return true;
  try {
    const response = await fetch(new URL("/api/keyboards/export", url), {
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) throw new Error(`HTTP status ${response.status}`);
    store.importKeyboards(await response.json());
    return true;
  } catch (error) {
    Logger.error(
      error as Error,
      `Cannot update the keyboards from typokiller at ${url}`,
    );
    return false;
  }
}
