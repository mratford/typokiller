import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyKey } from '../src/typokiller/static/typing.js';

const key = (k, mods = {}) => ({ key: k, ctrlKey: false, metaKey: false, ...mods });

test('a wrong character goes in and the cursor moves on', () => {
  assert.equal(applyKey('cat', 'c', key('x')), 'cx');
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
