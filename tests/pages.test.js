import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import { listLabels } from '../src/typokiller/static/lists.js';
import { pressed } from '../src/typokiller/static/analysis.js';

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
test('no text that a page shows holds a capitalised glossary term', async () => {
  const terms = /\b(Attempt|Board|Keymap|Letter layout|Keyboard export|Weakness model|Analysis method)s?\b/g;
  const folder = new URL('../src/typokiller/static/', import.meta.url);
  for (const file of await readdir(folder)) {
    const code = (await readFile(new URL(file, folder), 'utf8'))
      .replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--[\s\S]*?-->/g, '').replace(/(^|\s)\/\/.*/g, '');
    assert.deepEqual(code.match(terms), null, file);
  }
});
