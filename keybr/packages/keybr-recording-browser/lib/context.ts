import { type KeyboardPicture } from "@keybr/recording";
import { createContext } from "react";
import { type RecorderOptions } from "./recorder.ts";

/** Disabled by default; the storage integration supplies a record sink and context. */
export const RecordingContext = createContext<RecorderOptions | null>(null);

/**
 * typokiller's picture of the layout chosen for recording, or null when no
 * layout is chosen or typokiller sent no picture for it.
 */
export const KeyboardPictureContext = createContext<KeyboardPicture | null>(
  null,
);
