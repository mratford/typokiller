import { type KeyboardPicture as Picture } from "@keybr/recording";
import { type CodePoint } from "@keybr/unicode";
import { type ReactNode } from "react";
import * as styles from "./KeyboardPicture.module.less";

/**
 * typokiller's picture of the layout chosen for recording. It shows the layer
 * of the next character, and outlines that character's key with the class
 * "next". A character with no key shows the base layer, with no key outlined.
 */
export function KeyboardPicture({
  picture,
  next,
}: {
  readonly picture: Picture;
  readonly next: CodePoint | undefined;
}): ReactNode {
  const key =
    next == null ? undefined : picture.keys[String.fromCodePoint(next)];
  const layer = key?.layer ?? 0;
  let svg = picture.layers[layer];
  if (key) {
    // typokiller draws each key as <g id="k{key}" class="...">.
    const at = `<g id="k${key.key}" class="`;
    svg = svg.replace(at, `${at}next `);
  }
  return (
    <div className={styles.root}>
      <p className={styles.names}>
        {picture.names.map((name, index) => (
          <span
            key={index}
            className={index === layer ? styles.shown : undefined}
          >
            {name}
          </span>
        ))}
      </p>
      <div
        className={styles.drawing}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  );
}
