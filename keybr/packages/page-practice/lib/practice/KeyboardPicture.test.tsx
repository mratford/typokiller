import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { FakeIntlProvider } from "@keybr/intl";
import {
  KeyboardContext,
  keyboardProps,
  KeyboardProvider,
  Layout,
  loadKeyboard,
} from "@keybr/keyboard";
import { CustomTextLesson } from "@keybr/lesson";
import { FakePhoneticModel } from "@keybr/phonetic-model";
import { type KeyboardPictures } from "@keybr/recording";
import { KeyboardPictureContext } from "@keybr/recording-browser";
import {
  FakeSettingsContext,
  Settings,
  SettingsContext,
} from "@keybr/settings";
import { act, fireEvent, render } from "@testing-library/react";
import { Controller } from "./Controller.tsx";
import { KeyboardPresenter } from "./KeyboardPresenter.tsx";
import { Progress } from "./state/index.ts";

declare function flushAnimationFrames(): Promise<void>;

const fixture = (path: string) =>
  JSON.parse(
    readFileSync(
      new URL(`../../../keybr-recording/fixtures/${path}`, import.meta.url),
      "utf8",
    ),
  );
// typokiller's picture of the Sweep free-range layout, from the shared fixture.
const sweep = (fixture("pictures/initial.json") as KeyboardPictures)[
  fixture("keyboards/initial.json").boards[0].keymaps[1].sourceHash
];

function keyboard(next: string | null, picture: typeof sweep | null = sweep) {
  const r = render(
    <FakeSettingsContext>
      <KeyboardProvider>
        <KeyboardPictureContext value={picture}>
          <KeyboardPresenter
            focus={true}
            depressedKeys={[]}
            toggledKeys={[]}
            suffix={next == null ? [] : [next.codePointAt(0)!]}
            lastLesson={null}
          />
        </KeyboardPictureContext>
      </KeyboardProvider>
    </FakeSettingsContext>,
  );
  const shown = r.container.querySelector(".shown")?.textContent;
  const outlined = [...r.container.querySelectorAll(".next")].map((g) => g.id);
  return { r, shown, outlined };
}

test("the picture shows the layer of the next character and outlines its key", (t) => {
  const symbol = keyboard("(");
  t.after(() => symbol.r.unmount());
  assert.deepEqual(sweep.keys["("], { layer: 1, key: "5,2" });
  // The layer names are on one line, and the shown layer is marked.
  assert.equal(
    symbol.r.container.querySelector(".names")?.textContent,
    sweep.names.join(""),
  );
  assert.equal(symbol.shown, "Space");
  assert.deepEqual(symbol.outlined, ["k5,2"]);
  // typokiller's picture replaces keybr's own.
  assert.equal(symbol.r.container.querySelectorAll("svg.keymap").length, 1);
  assert.equal(symbol.r.container.querySelector("svg.keyboard"), null);

  const letter = keyboard("a");
  t.after(() => letter.r.unmount());
  assert.equal(letter.shown, "L0");
  assert.deepEqual(letter.outlined, ["k5,3"]);
});

test("a character with no key, or no next character, shows the base layer with no key outlined", (t) => {
  for (const next of ["é", null]) {
    const page = keyboard(next);
    t.after(() => page.r.unmount());
    assert.equal(page.shown, "L0");
    assert.deepEqual(page.outlined, []);
  }
});

class FixedLesson extends CustomTextLesson {
  override generate() {
    return "abcdefghij";
  }
}

function practice() {
  const settings = new Settings().set(keyboardProps.layout, Layout.EN_US);
  const keyboard = loadKeyboard(Layout.EN_US);
  const progress = new Progress(
    settings,
    new FixedLesson(settings, keyboard, new FakePhoneticModel()),
  );
  return render(
    <FakeIntlProvider>
      <SettingsContext value={{ settings, updateSettings() {} }}>
        <KeyboardContext value={keyboard}>
          <KeyboardPictureContext value={sweep}>
            <Controller progress={progress} onResult={() => {}} />
          </KeyboardPictureContext>
        </KeyboardContext>
      </SettingsContext>
    </FakeIntlProvider>,
  );
}

test("the normal view shows the picture of the chosen layout, and the compact view no picture", async (t) => {
  window.localStorage.clear();
  t.after(() => window.localStorage.clear());
  const r = practice();
  t.after(() => r.unmount());
  await act(flushAnimationFrames);
  assert.equal(r.container.querySelector(".shown")?.textContent, "L0");
  assert.deepEqual(
    [...r.container.querySelectorAll(".next")].map((g) => g.id),
    [`k${sweep.keys.a.key}`],
  );
  fireEvent.click(r.getByTitle("Switch the current interface layout."));
  await act(flushAnimationFrames);
  assert.equal(r.container.querySelector("svg.keymap"), null);
  assert.equal(r.container.querySelector("svg.keyboard"), null);
});

test("a chosen layout with no picture keeps keybr's own picture", (t) => {
  const { r } = keyboard("a", null);
  t.after(() => r.unmount());
  assert.ok(r.container.querySelector("svg.keyboard"));
  assert.equal(r.container.querySelector("svg.keymap"), null);
});
