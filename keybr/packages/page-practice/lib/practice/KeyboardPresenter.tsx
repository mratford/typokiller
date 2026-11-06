import { keyboardProps, useKeyboard } from "@keybr/keyboard";
import {
  flatten,
  HeatmapLayer,
  KeyLayer,
  PointersLayer,
  TransitionsLayer,
  VirtualKeyboard,
  ZonesLayer,
} from "@keybr/keyboard-ui";
import { KeyboardPictureContext } from "@keybr/recording-browser";
import { useSettings } from "@keybr/settings";
import { type CodePoint } from "@keybr/unicode";
import { withDeferred } from "@keybr/widget";
import { memo, type ReactNode, useContext } from "react";
import { KeyboardPicture } from "./KeyboardPicture.tsx";
import { type LastLesson } from "./state/index.ts";

export const KeyboardPresenter = memo(function KeyboardPresenter({
  focus,
  depressedKeys,
  toggledKeys,
  suffix,
  lastLesson,
}: {
  readonly focus: boolean;
  readonly depressedKeys: readonly string[];
  readonly toggledKeys: readonly string[];
  readonly suffix: readonly CodePoint[];
  readonly lastLesson: LastLesson | null;
}): ReactNode {
  const { settings } = useSettings();
  const keyboard = useKeyboard();
  const colors = settings.get(keyboardProps.colors);
  const pointers = settings.get(keyboardProps.pointers);
  // typokiller's picture replaces keybr's own picture. keybr's finger colours
  // and its marks of the last lesson are then not shown.
  const picture = useContext(KeyboardPictureContext);
  if (picture) return <KeyboardPicture picture={picture} next={suffix[0]} />;
  return (
    <VirtualKeyboard keyboard={keyboard} height="16rem">
      <KeyLayer
        depressedKeys={depressedKeys}
        toggledKeys={toggledKeys}
        showColors={colors}
      />
      {focus && pointers && <PointersLayer suffix={suffix} />}
      {focus && lastLesson && (
        <HeatmapLayer histogram={flatten(lastLesson.misses)} modifier="m" />
      )}
      {focus && lastLesson && (
        <HeatmapLayer histogram={flatten(lastLesson.hits)} modifier="h" />
      )}
      {focus && lastLesson && (
        <TransitionsLayer histogram={lastLesson.misses2} modifier="m" />
      )}
      {focus && lastLesson && (
        <TransitionsLayer histogram={lastLesson.hits2} modifier="h" />
      )}
      {focus || <ZonesLayer />}
    </VirtualKeyboard>
  );
});

export const DeferredKeyboardPresenter = withDeferred(KeyboardPresenter);
