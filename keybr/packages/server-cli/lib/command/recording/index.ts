import { existsSync } from "node:fs";
import { join } from "node:path";
import { RecordingStore } from "@keybr/recording-store";
import { Command } from "commander";

/** `keybr recording …`: personal detailed-recording maintenance. */
export function recordingCommand(dataDir: () => string) {
  const filename = () => join(dataDir(), "recordings.sqlite");
  return new Command("recording")
    .description("Manage the detailed recording database.")
    .addCommand(
      new Command("export")
        .argument("<file>")
        .description("Export a consistent recording SQLite snapshot.")
        .action((file: string) => {
          if (!existsSync(filename()))
            throw new Error("No recording database exists yet");
          const store = new RecordingStore(filename());
          try {
            store.export(file);
          } finally {
            store.close();
          }
        }),
    );
}
