# PROTOTYPE for #81: the keyboard picture in keybr's practice page

Throwaway. Not for main. Open `keyboard-picture-prototype.html` in a browser and type on the keyboard.

A rough copy of keybr's practice page with the Sweep free-range pictures that typokiller's
`drawing.py` makes. Four variants, switched with `?variant=A|B|C|D` or the arrow keys:

- A: the Sweep picture in place of keybr's own picture; keybr's "change view" button turns it off.
- B: the faint Sweep picture under the text, as in typokiller, and keybr's own picture below it.
- C: small pictures of every layer in place of keybr's picture; the layer of the next character is dark.
- D: keybr's own picture stays; the Sweep picture shows under the text only when the next
  character is not on the base layer.

`?text=symbols` gives a lesson with capitals, punctuation and digits, so that the layer changes.

To build again: `uv run python prototypes/81-keybr-keyboard-picture/gen.py > data.json` from the
repo root, then put the contents of `data.json` in place of `/*DATA*/` in `page.template.html`.
