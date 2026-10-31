import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { applyKey, listLabels, MENU, previousAt, requestError, showChars, textHTML } from '../src/typokiller/static/typing.js';

const key = (k, mods = {}) => ({ key: k, ctrlKey: false, metaKey: false, ...mods });

test('a wrong character goes in and the cursor moves on', () => {
  assert.equal(applyKey('cat', 'c', key('x')), 'cx');
});

test('a repeat keydown changes nothing, not even Backspace', () => {
  assert.equal(applyKey('cat', 'c', key('a', { repeat: true })), 'c');
  assert.equal(applyKey('cat', 'cx', key('Backspace', { repeat: true })), 'cx');
});

test('nothing goes in at the end of the text', () => {
  assert.equal(applyKey('cat', 'cat', key('s')), 'cat');
});

test('locked until fixed: a wrong character does not go in, the right one does', () => {
  assert.equal(applyKey('cat', 'c', key('x'), 'locked until fixed'), 'c');
  assert.equal(applyKey('cat', 'c', key('a'), 'locked until fixed'), 'ca');
});

test('Backspace removes one character but not before the start of the Attempt', () => {
  assert.equal(applyKey('cat', 'cx', key('Backspace')), 'c');
  assert.equal(applyKey('cat', '', key('Backspace')), '');
});

test('other keys change nothing', () => {
  for (const k of ['Shift', 'Tab', 'Enter', 'ArrowLeft', 'Escape']) assert.equal(applyKey('cat', 'c', key(k)), 'c');
  assert.equal(applyKey('cat', 'c', key('w', { ctrlKey: true })), 'c');
  assert.equal(applyKey('cat', 'c', key('a', { metaKey: true })), 'c');
});

test('nothing goes in after the end of the Passage', () => {
  assert.equal(applyKey('cat', 'cax', key('t')), 'cax');
});

test('Enter at a newline goes in and fills in the next line\'s indentation; Enter elsewhere does nothing', () => {
  const code = 'if x:\n    y\nz';
  assert.equal(applyKey(code, 'if x:', key('Enter')), 'if x:\n    ');
  assert.equal(applyKey(code, 'if x:\n    y', key('Enter')), 'if x:\n    y\n');
  assert.equal(applyKey(code, 'if x', key('Enter')), 'if x');
});

test('Backspace after the filled-in indentation removes it with the newline', () => {
  const code = 'if x:\n    y';
  assert.equal(applyKey(code, 'if x:\n    ', key('Backspace')), 'if x:');
  assert.equal(applyKey(code, 'if x:\n    y', key('Backspace')), 'if x:\n    ');
});

test('showChars shows a space as ␣ and a newline as ↵', () => {
  assert.equal(showChars(' e\n'), '␣e↵');
});

test('textHTML shows a space as ␣ and a newline as ↵, also under the cursor and as a wrong key', () => {
  assert.equal(textHTML('a b\nc', 'a'),
    '<span class="ok">a</span><span class="mark cur">␣</span><wbr><span class="">b</span><span class="mark">↵</span>\n<span class="">c</span>');
  assert.equal(textHTML('a b\nc', 'a b\n'),
    '<span class="ok">a</span><span class="mark ok">␣</span><wbr><span class="ok">b</span><span class="mark ok">↵</span>\n<span class="cur">c</span>');
  assert.equal(textHTML('a b\nc', 'axb '),
    '<span class="ok">a</span><span class="bad">x</span><wbr><span class="ok">b</span><span class="bad">␣</span>\n<span class="cur">c</span>');
  assert.equal(textHTML('a b'), '<span class="">a</span><span class="mark">␣</span><wbr><span class="">b</span>');
});

test('requestError says why a request failed: no answer, the detail text, or the status', async () => {
  const failed = 'Could not import the symbol docs';
  const answer = (body, status = 405, statusText = 'Method Not Allowed') => new Response(body, { status, statusText });
  assert.equal(await requestError(failed, null), 'Could not import the symbol docs: the server did not answer.');
  assert.equal(await requestError(failed, answer('{"detail": "Not a git repo."}')), 'Could not import the symbol docs: Not a git repo.');
  assert.equal(await requestError(failed, answer('{"detail": [{"msg": "Field required"}]}', 422, 'Unprocessable Entity')),
    'Could not import the symbol docs: 422 Unprocessable Entity');
  assert.equal(await requestError(failed, answer('<html>')), 'Could not import the symbol docs: 405 Method Not Allowed');
});

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

const menuItem = k => MENU.flatMap(([, items]) => items).find(([key]) => key === k);

test('in the menu, s and S keep the menu open; Esc, r, m and u go back to typing', () => {
  assert.deepEqual([menuItem('s')[2], menuItem('S')[2]], ['menu', 'menu']);
  assert.deepEqual(['Escape', 'r', 'm', 'u'].map(k => menuItem(k)[2]), ['typing', 'typing', 'typing', 'typing']);
  assert.deepEqual([menuItem('s')[1], menuItem('S')[1]],
    ['skip this part (the menu stays open)', 'go back one part (the menu stays open)']);
});

test('S goes back one part, but not from the first part, during a drill, or with no text open', () => {
  assert.equal(previousAt({ at: 112 }, false), 111);
  assert.equal(previousAt({ at: 0 }, false), null);
  assert.equal(previousAt({ at: 112 }, true), null);
  assert.equal(previousAt(null, false), null);
});

// The screen uses plain words, not the glossary terms of CONTEXT.md (see "Words on screen" in AGENTS.md).
test('no text that the page shows holds a capitalised glossary term', async () => {
  const terms = /\b(Passage|Attempt|Source|Target|Session|Board|Keymap|Drill|Lesson|Letter layout)s?\b/g;
  for (const file of ['practice.js', 'progress.js', 'typing.js', 'send.html']) {
    const code = (await readFile(new URL(`../src/typokiller/static/${file}`, import.meta.url), 'utf8'))
      .replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*/g, '');
    assert.deepEqual(code.match(terms), null, file);
  }
});
