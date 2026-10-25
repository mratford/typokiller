import { applyKey } from './typing.js';

// Each menu item is [key, label, what choosing it does].
const MENU = [
  ['Practice', [
    ['Escape', 'resume', () => { menu = null; }],
    ['r', 'restart this Passage', () => { nextAttempt(); menu = null; }],
  ]],
  ['Session', [
    ['q', 'end Session', () => { ended = true; menu = null; }],
    ['?', 'all keys', () => { menu = 'help'; }],
  ]],
];
const ITEMS = MENU.flatMap(([, items]) => items);

const { session, passage } = await (await fetch('/api/sessions', { method: 'POST' })).json();

let seq = 0;
let ord = 0; // the current Attempt's order in the Session
let typed = '';
let menu = null; // null while typing, else 'menu' or 'help'
let sel = 0;
let message = '';
let ended = false;
const heldIn = new Map(); // code -> the Attempt that recorded its keydown
let events = []; // not yet stored by the server
let finished = []; // ords of finished Attempts, not yet stored by the server

function nextAttempt() {
  ord++;
  typed = '';
}

function record(e, attempt) {
  events.push({
    seq: seq++, attempt, t: e.timeStamp, type: e.type, code: e.code, key: e.key,
    shift: e.shiftKey, ctrl: e.ctrlKey, alt: e.altKey, meta: e.metaKey, repeat: e.repeat,
  });
}

// Sends everything the server has not confirmed yet. Batches may overlap or repeat;
// the server ignores what it already has. `keepalive` lets the last batch finish
// after the page closes; Chrome limits such requests to 64 KB.
async function flush(keepalive = false) {
  if (!events.length && !finished.length) return;
  const batch = { events: [...events], finished: [...finished] };
  try {
    const r = await fetch(`/api/sessions/${session}/batch`, {
      method: 'POST', keepalive, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(batch),
    });
    if (r.ok) {
      const sentEvents = new Set(batch.events);
      events = events.filter(e => !sentEvents.has(e));
      finished = finished.filter(o => !batch.finished.includes(o));
    }
  } catch {} // the next flush sends the same batch again
}

function menuKey(e) {
  if (menu === 'help') { if (e.key === 'Escape') menu = 'menu'; }
  else if (e.key === 'j') sel = Math.min(sel + 1, ITEMS.length - 1);
  else if (e.key === 'k') sel = Math.max(sel - 1, 0);
  else if (e.key === 'Enter') ITEMS[sel][2]();
  else ITEMS.find(([k]) => k === e.key)?.[2]();
}

// Keys used in the menu are not key events of any Attempt, so they are not recorded.
// An Attempt that is left without finishing (r, q, closing or reloading) stays abandoned.
addEventListener('keydown', e => {
  if (ended) return;
  if (!e.metaKey) e.preventDefault(); // let Cmd shortcuts such as Cmd-R work
  if (menu) menuKey(e);
  else if (e.key === 'Escape') { menu = 'menu'; sel = 0; }
  else {
    record(e, ord);
    heldIn.set(e.code, ord);
    typed = applyKey(passage, typed, e);
    if (typed === passage) {
      finished.push(ord);
      message = '✓ finished';
      nextAttempt();
    }
  }
  render();
});

// A keyup belongs to the Attempt of its keydown, even if a new Attempt has started.
addEventListener('keyup', e => {
  if (!heldIn.has(e.code)) return;
  record(e, heldIn.get(e.code));
  heldIn.delete(e.code);
});

addEventListener('pagehide', () => flush(true));
setInterval(flush, 1000);

const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const label = k => (k === 'Escape' ? 'Esc' : k);

function passageHTML() {
  let h = '';
  for (let j = 0; j < passage.length; j++) {
    let cls = '', shown = passage[j];
    if (j === typed.length) cls = 'cur';
    else if (j < typed.length && typed[j] === passage[j]) cls = 'ok';
    else if (j < typed.length) { cls = 'bad'; shown = typed[j] === ' ' ? '·' : typed[j]; }
    h += `<span class="${cls}">${esc(shown)}</span>`;
  }
  return `<div class="p">${h}</div>`;
}

function menuHTML() {
  const selKey = menu === 'menu' ? ITEMS[sel][0] : null;
  const groups = MENU.map(([name, items]) => `<div><h4>${name}</h4>${items.map(([k, l]) =>
    `<div class="item ${k === selKey ? 'sel' : ''}"><kbd>${label(k)}</kbd> ${l}</div>`).join('')}</div>`).join('');
  const hint = menu === 'menu'
    ? 'Press a letter, or <kbd>j</kbd>/<kbd>k</kbd> and <kbd>Enter</kbd>.'
    : 'While typing: only printable characters and <kbd>Backspace</kbd> change what you have typed; <kbd>Esc</kbd> opens this menu. Other keys are recorded and do nothing. <kbd>Esc</kbd> goes back.';
  return `<div class="menu"><div class="groups">${groups}</div><div class="hint">${hint}</div></div>`;
}

function render() {
  const mode = ended ? 'ended' : menu ? 'paused' : 'typing';
  document.getElementById('app').innerHTML = `
    <main>${ended ? '<p>Session ended. Reload the page to start a new Session.</p>' : passageHTML()}</main>
    ${menu ? menuHTML() : ''}
    <div class="status"><span class="mode">${mode}</span><span>no Board yet</span><span class="grow">built-in Passage</span></div>
    <div class="msg">${esc(message)}</div>`;
}

render();
