import { join } from "node:path";
import { body, controller, http } from "@fastr/controller";
import { Context } from "@fastr/core";
import { BadRequestError, HttpError, NotFoundError } from "@fastr/errors";
import { inject, injectable } from "@fastr/invert";
import { Env } from "@keybr/config";
import { Logger } from "@keybr/logger";
import {
  type KeyboardPictures,
  keyboardPicturesSchema,
  maxBatchBytes,
  schemaVersion,
} from "@keybr/recording";
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
    const pictures = await updateKeyboards(store, typokillerUrl);
    ctx.response.body = {
      enabled: true,
      schemaVersion,
      applicationRevision: Env.getString("APPLICATION_REVISION", "local"),
      // Imported from typokiller; snapshots stay on the server. The pictures
      // are not stored in the database.
      keyboards: store.keyboards().map((keyboard) => ({
        ...keyboard,
        layouts: keyboard.layouts.map((layout) => ({
          ...layout,
          picture: pictures?.[layout.vilHash],
        })),
      })),
      keyboardsOutdated: pictures == null,
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
 * Gets the keyboard export and then the keyboard pictures from typokiller at
 * `url` (`TYPOKILLER_URL`), within 2 seconds. Imports the keyboards and returns
 * the pictures. Returns no pictures when `url` is empty. Writes the reason to
 * the log when a request fails or keybr rejects its answer. When the export
 * fails, the import changes nothing and the result is null: the keyboards are
 * outdated. When only the pictures fail, the result has no pictures.
 */
async function updateKeyboards(
  store: RecordingStore,
  url: string,
): Promise<KeyboardPictures | null> {
  if (!url) return {};
  const signal = AbortSignal.timeout(2000);
  const get = async (path: string) => {
    const response = await fetch(new URL(path, url), { signal });
    if (!response.ok) throw new Error(`HTTP status ${response.status}`);
    return response.json();
  };
  try {
    store.importKeyboards(await get("/api/keyboards/export"));
  } catch (error) {
    Logger.error(
      error as Error,
      `Cannot update the keyboards from typokiller at ${url}`,
    );
    return null;
  }
  try {
    return keyboardPicturesSchema.parse(await get("/api/keyboards/pictures"));
  } catch (error) {
    Logger.error(
      error as Error,
      `Cannot get the keyboard pictures from typokiller at ${url}`,
    );
    return {};
  }
}
