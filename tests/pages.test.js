import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import { listLabels } from '../src/typokiller/static/lists.js';
import { PANEL_KEYS, pressed, vialName } from '../src/typokiller/static/analysis.js';

test('with no more items than letters, every label is one letter, in the order of the letters', () => {
  assert.deepEqual(listLabels(3, 'sadflewcmpgh', 'jk'), ['s', 'a', 'd']);
  assert.equal(listLabels(12, 'sadflewcmpgh', 'jk').join(''), 'sadflewcmpgh');
});

test('with more items than letters, no label is the start of another, and the first items have one letter', () => {
  const labels = listLabels(19, 'sadflewcmpgh', 'jk');
  assert.deepEqual(labels.slice(0, 11), [...'sadflewcmpg']);
  assert.deepEqual(labels.slice(11), ['hs', 'ha', 'hd', 'hf', 'hl', 'he', 'hw', 'hc']);
});

test('the keys that the list uses are never labels, even when the letters have them', () => {
  assert.deepEqual(listLabels(3, 'jsknad', 'jkn'), ['s', 'a', 'd']);
});

test('the keys of the keyboards panel are never labels of its lines', () => {
  const labels = listLabels(20, 'sadflewcmpghjknvrb', PANEL_KEYS);
  assert.deepEqual(labels.filter(l => [...PANEL_KEYS].some(key => l.includes(key))), []);
  assert.deepEqual(labels.slice(10), ['g', 'hs', 'ha', 'hd', 'hf', 'hl', 'he', 'hw', 'hc', 'hm']);
});

test('the name of a new keyboard comes from its vial.json, and the Sofle\'s has none', async () => {
  const names = {};
  for (const board of ['cheapino', 'q4', 'sofle', 'sweep']) {
    names[board] = vialName(await readFile(new URL(`fixtures/boards/${board}/vial.json`, import.meta.url), 'utf8'));
  }
  assert.deepEqual(names, { cheapino: 'Cheapino V2', q4: 'Keychron Q4', sofle: '', sweep: 'Ferris Sweep' });
});

test('on the analysis page, h and l move between the entries, a number picks the layer, and j and k move the arc', () => {
  const counts = { entries: 3, layers: 2, pairs: 2 };
  const view = { at: 0, layer: 1, pair: 0 };
  assert.deepEqual(pressed('l', view, counts), { at: 1, layer: 0, pair: 0 });
  assert.deepEqual(pressed('h', view, counts), { at: 2, layer: 0, pair: 0 }); // from the first to the last
  assert.deepEqual(pressed('h', view, { ...counts, entries: 1 }), { at: 0, layer: 0, pair: 0 }); // the same entry, read again
  assert.deepEqual(pressed('1', view, counts), { at: 0, layer: 0, pair: 0 });
  assert.equal(pressed('3', view, counts), null); // there is no layer 3
  assert.deepEqual(pressed('j', view, counts), { at: 0, layer: 1, pair: 1 });
  assert.deepEqual(pressed('j', { ...view, pair: 1 }, counts), { at: 0, layer: 1, pair: 1 }); // the last pair
  assert.deepEqual(pressed('k', view, counts), view);
  assert.equal(pressed('x', view, counts), null);
});

// The screen uses plain words, not the glossary terms of CONTEXT.md (see "Words on screen" in AGENTS.md).
const terms = /\b(Attempt|Board|Keymap|Letter layout|Keyboard export|Weakness model|Analysis method)s?\b/g;

test('no text that a page shows holds a capitalised glossary term', async () => {
  const folder = new URL('../src/typokiller/static/', import.meta.url);
  for (const file of await readdir(folder)) {
    const code = (await readFile(new URL(file, folder), 'utf8'))
      .replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--[\s\S]*?-->/g, '').replace(/(^|\s)\/\/.*/g, '');
    assert.deepEqual(code.match(terms), null, file);
  }
});

// The README's user part, before "## Development", uses the plain words of the screen.
test('the user part of the README holds no capitalised glossary term, and names keybr only in the credit', async () => {
  const readme = await readFile(new URL('../README.md', import.meta.url), 'utf8');
  const [user, development] = readme.split('\n## Development\n');
  assert.ok(development, 'the README has a part "## Development"');
  assert.deepEqual(user.match(terms), null);
  assert.doesNotMatch(user.split('\n\n').slice(2).join('\n\n'), /keybr/i); // after the title and the credit
});
