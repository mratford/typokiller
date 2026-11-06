import { test } from "node:test";
import { equal } from "rich-assert";
import { ThemePrefs } from "./prefs.ts";

test("a new browser gets the typokiller theme", () => {
  equal(ThemePrefs.deserialize(null).color, "typokiller");
});

test("a user who chose another theme keeps it", () => {
  equal(ThemePrefs.deserialize('{"color":"system"}').color, "system");
});
