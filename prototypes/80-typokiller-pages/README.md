# PROTOTYPE for #80: typokiller's pages after the cut

Throwaway. Not for main. Open `typokiller-pages-prototype.html` in a browser.

Three variants, switched with `?variant=A|B|C` or the arrow keys: A home menu, B analysis first
with a keyboards panel, C two columns. `?data=full|nolessons|nokeyboards` shows the empty states,
and `?page=keybr` shows a stand-in for keybr's page with the link to the analysis page.

Verdict: B, with letter labels in the keyboards panel and layer names kept in `typokiller.toml`.
See the resolution comment on #80.

To build again: `uv run python prototypes/80-typokiller-pages/gen.py > data.js` from the repo root,
then put the contents of `data.js` in place of `/*DATA*/` in `page.template.html`.
