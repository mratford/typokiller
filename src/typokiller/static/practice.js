import { applyKey } from './typing.js';

// Each menu item is [key, label, what choosing it does].
const MENU = [
  ['Practice', [
    ['Escape', 'resume', () => { menu = null; }],
    ['r', 'restart this Passage', () => { nextAttempt(); menu = null; }],
  ]],
  ['Session', [
    ['b', 'change Board', () => { menu = null; showBoards(); }],
    ['q', 'end Session', () => { ended = true; menu = null; }],
    ['?', 'all keys', () => { menu = 'help'; }],
  ]],
];
const ITEMS = MENU.flatMap(([, items]) => items);

let session, passage;
let start = 'boards'; // null while typing, else the start screen: 'boards', 'keymaps', 'name', 'vil' or 'vial'
let boards = []; // from the server, each with its Keymaps, last used first
let board = null; // the Board chosen on the start screen
let current = ''; // the status line's "Board · Letter layout"
let draft = {}; // the name and .vil of a Board being added
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

const json = r => r.json();
const post = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

async function showBoards(id) {
  start = 'boards';
  const listed = await fetch('/api/boards').then(json);
  boards = listed.boards;
  sel = Math.max(0, boards.findIndex(b => b.id === (id ?? listed.last)));
  render();
}

// A new Session starts again from seq 0 and Attempt 0. The old Session's events
// are sent first; any that fail to send are lost.
async function startSession(keymap) {
  await flush();
  ({ session, passage } = await post('/api/sessions', { keymap_version: keymap.version }).then(json));
  current = `${board.name} · ${keymap.letter_layout}`;
  seq = 0;
  ord = 0;
  typed = '';
  message = '';
  heldIn.clear();
  start = null;
  render();
}

function chooseBoard(b) {
  board = b;
  if (b.keymaps.length > 1) { start = 'keymaps'; sel = 0; }
  else startSession(b.keymaps[0]);
}

// Opens the browser's file picker. Chrome allows this only while a key press is
// being handled, so each file needs its own key press.
function pickFile(accept, then) {
  const input = Object.assign(document.createElement('input'), { type: 'file', accept });
  input.onchange = async () => { await then(await input.files[0].text()); render(); };
  input.click();
}

function startKey(e) {
  if (start === 'name') {
    if (e.key === 'Escape') start = 'boards';
    else if (e.key === 'Backspace') draft.name = draft.name.slice(0, -1);
    else if (e.key === 'Enter' && draft.name) start = 'vil';
    else if (e.key.length === 1) draft.name += e.key;
  } else if (start === 'vil' || start === 'vial') {
    if (e.key === 'Escape') start = 'boards';
    else if (e.key === 'Enter' && start === 'vil') pickFile('.vil', text => { draft.vil = text; start = 'vial'; });
    else if (e.key === 'Enter') pickFile('.json', async text => {
      const added = await post('/api/boards', { ...draft, vial: text }).then(json);
      await showBoards(added.board);
    });
  } else {
    const items = start === 'boards' ? boards : board.keymaps;
    const choose = start === 'boards' ? chooseBoard : startSession;
    if (e.key === 'j') sel = Math.min(sel + 1, items.length - 1);
    else if (e.key === 'k') sel = Math.max(sel - 1, 0);
    else if (e.key === 'Enter' && items[sel]) choose(items[sel]);
    else if (items[Number(e.key) - 1]) choose(items[Number(e.key) - 1]);
    else if (e.key === 'n' && start === 'boards') { start = 'name'; draft = { name: '' }; }
    else if (e.key === 'Escape') start = 'boards';
  }
}

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

// Keys used on the start screens and in the menu are not key events of any Attempt,
// so they are not recorded.
// An Attempt that is left without finishing (r, q, closing or reloading) stays abandoned.
addEventListener('keydown', e => {
  if (ended) return;
  if (!e.metaKey) e.preventDefault(); // let Cmd shortcuts such as Cmd-R work
  if (start) startKey(e);
  else if (menu) menuKey(e);
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

function listHTML(title, labels) {
  const items = labels.map((l, i) =>
    `<div class="item ${i === sel ? 'sel' : ''}"><kbd>${i + 1}</kbd> ${esc(l)}</div>`).join('');
  return `<h4>${title}</h4>${items}`;
}

function startHTML() {
  const choose = 'Press a number, or <kbd>j</kbd>/<kbd>k</kbd> and <kbd>Enter</kbd>.';
  if (start === 'boards') {
    return `${listHTML('Board', boards.map(b => b.name))}<p class="hint">${choose} <kbd>n</kbd> adds a Board.</p>`;
  }
  if (start === 'keymaps') {
    return `${listHTML(`Keymap on ${esc(board.name)}`, board.keymaps.map(k => k.letter_layout))}`
      + `<p class="hint">${choose} <kbd>Esc</kbd> goes back.</p>`;
  }
  const step = start === 'name' ? `Name: ${esc(draft.name)}<span class="cur"> </span>`
    : `Press <kbd>Enter</kbd> to choose the <code>${start === 'vil' ? '.vil' : 'vial.json'}</code> file.`;
  return `<h4>New Board</h4><p class="p">${step}</p>`
    + '<p class="hint">A name that exists adds the <code>.vil</code> to that Board. <kbd>Esc</kbd> goes back.</p>';
}

function render() {
  const mode = ended ? 'ended' : start ? 'start' : menu ? 'paused' : 'typing';
  document.getElementById('app').innerHTML = `
    <main>${ended ? '<p>Session ended. Reload the page to start a new Session.</p>' : start ? startHTML() : passageHTML()}</main>
    ${menu ? menuHTML() : ''}
    <div class="status"><span class="mode">${mode}</span><span>${start ? 'choosing a Board' : esc(current)}</span><span class="grow">built-in Passage</span></div>
    <div class="msg">${esc(message)}</div>`;
}

showBoards();
