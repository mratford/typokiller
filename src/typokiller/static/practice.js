import { applyKey } from './typing.js';

// Each menu item is [key, label, what choosing it does].
const MENU = [
  ['Practice', [
    ['Escape', 'resume', () => { screen = 'typing'; }],
    ['r', 'restart this Passage', () => { nextAttempt(); screen = 'typing'; }],
  ]],
  ['Session', [
    ['b', 'change Board', () => showBoards()],
    ['q', 'end Session', () => { screen = 'ended'; }],
    [',', 'settings', openSettings],
    ['?', 'all keys', () => { screen = 'help'; }],
  ]],
];
const ITEMS = MENU.flatMap(([, items]) => items);

// The values each choice setting can take. Enter on the settings page moves to the next one.
const CHOICES = { 'typing.wrong_key_mode': ['keep typing', 'locked until fixed'] };

// The screens shown before a Session starts: the Board list, the Keymap list, and
// the three steps of adding a Board.
const START = ['boards', 'keymaps', 'name', 'vil', 'vial'];

let session, passage;
let screen = 'boards'; // one of START, or 'typing', 'menu', 'help', 'settings' or 'ended'
let boards = []; // from the server, each with its Keymaps, last used first
let board = null; // the Board chosen on the start screen
let boardLabel = ''; // the status line's "Board · Letter layout"
let draft = {}; // the name and .vil of a Board being added

let seq = 0;
let ord = 0; // the current Attempt's order in the Session
let attemptSettings = []; // attemptSettings[ord] holds the settings Attempt ord is typed with
let typed = '';
let sel = 0; // the selected line of the list or menu on screen
let settings = null; // the settings file's values while the settings page is open
let message = '';
const heldIn = new Map(); // code -> the Attempt that recorded its keydown
let events = []; // not yet stored by the server
let finished = []; // ords of finished Attempts, not yet stored by the server

const getJSON = url => fetch(url).then(r => r.json());
const getSettings = () => getJSON('/api/settings');
const send = (url, body, { method = 'POST', keepalive = false } = {}) =>
  fetch(url, { method, keepalive, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

// Moves the selection with j and k. Returns whether the key was j or k.
function moveSel(e, count) {
  if (e.key === 'j') sel = Math.min(sel + 1, count - 1);
  else if (e.key === 'k') sel = Math.max(sel - 1, 0);
  else return false;
  return true;
}

async function showBoards(id) {
  screen = 'boards';
  const listed = await getJSON('/api/boards');
  boards = listed.boards;
  sel = Math.max(0, boards.findIndex(b => b.id === (id ?? listed.last)));
  render();
}

// A new Session starts again from seq 0 and Attempt 0. The old Session's events
// are sent first; any that fail to send are lost.
async function startSession(keymap) {
  await flush();
  events = [];
  finished = [];
  attemptSettings = [await getSettings()];
  ({ session, passage } = await (await send('/api/sessions', { keymap_version: keymap.version })).json());
  boardLabel = `${board.name} · ${keymap.letter_layout}`;
  seq = 0;
  ord = 0;
  typed = '';
  message = '';
  heldIn.clear();
  screen = 'typing';
  render();
}

function chooseBoard(b) {
  board = b;
  if (b.keymaps.length > 1) { screen = 'keymaps'; sel = 0; }
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
  if (screen === 'name') {
    if (e.key === 'Escape') screen = 'boards';
    else if (e.key === 'Backspace') draft.name = draft.name.slice(0, -1);
    else if (e.key === 'Enter' && draft.name) screen = 'vil';
    else if (e.key.length === 1) draft.name += e.key;
  } else if (screen === 'vil' || screen === 'vial') {
    if (e.key === 'Escape') screen = 'boards';
    else if (e.key === 'Enter' && screen === 'vil') pickFile('.vil', text => { draft.vil = text; screen = 'vial'; });
    else if (e.key === 'Enter') pickFile('.json', async text => {
      const added = await (await send('/api/boards', { ...draft, vial: text })).json();
      await showBoards(added.board);
    });
  } else {
    const items = screen === 'boards' ? boards : board.keymaps;
    const choose = screen === 'boards' ? chooseBoard : startSession;
    if (moveSel(e, items.length)) return;
    if (e.key === 'Enter' && items[sel]) choose(items[sel]);
    else if (items[Number(e.key) - 1]) choose(items[Number(e.key) - 1]);
    else if (e.key === 'n' && screen === 'boards') { screen = 'name'; draft = { name: '' }; }
    else if (e.key === 'Escape') screen = 'boards';
  }
}

// Reads the settings file again, so each Attempt uses the settings as they are now.
// Keys typed before the file has been read use the previous Attempt's settings.
function nextAttempt() {
  ord++;
  typed = '';
  attemptSettings[ord] = attemptSettings[ord - 1];
  const attempt = ord;
  getSettings().then(s => { attemptSettings[attempt] = s; render(); });
}

const wrongKeyMode = () => attemptSettings[ord].typing.wrong_key_mode;

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
  const batch = {
    events: [...events], finished: [...finished],
    settings: Object.fromEntries(events.map(e => [e.attempt, attemptSettings[e.attempt]])),
  };
  try {
    const r = await send(`/api/sessions/${session}/batch`, batch, { keepalive });
    if (r.ok) {
      const sentEvents = new Set(batch.events);
      events = events.filter(e => !sentEvents.has(e));
      finished = finished.filter(o => !batch.finished.includes(o));
    }
  } catch {} // the next flush sends the same batch again
}

async function openSettings() {
  settings = await getSettings();
  sel = 0;
  screen = 'settings';
  render();
}

// One row per setting: [table, key, value].
const settingRows = () =>
  Object.entries(settings).flatMap(([table, values]) => Object.entries(values).map(([k, v]) => [table, k, v]));

function settingsKey(e) {
  const rows = settingRows();
  if (moveSel(e, rows.length)) return;
  if (e.key === 'Escape') { screen = 'menu'; sel = 0; }
  else if (e.key === 'Enter') {
    const [table, key, value] = rows[sel];
    const choices = CHOICES[`${table}.${key}`];
    settings[table][key] = choices[(choices.indexOf(value) + 1) % choices.length];
    send('/api/settings', settings, { method: 'PUT' });
    message = 'Settings saved. They apply from the next Attempt.';
  }
}

function menuKey(e) {
  if (screen === 'settings') settingsKey(e);
  else if (screen === 'help') { if (e.key === 'Escape') screen = 'menu'; }
  else if (moveSel(e, ITEMS.length)) return;
  else if (e.key === 'Enter') ITEMS[sel][2]();
  else ITEMS.find(([k]) => k === e.key)?.[2]();
}

// Keys used on the start screens and in the menu are not key events of any Attempt,
// so they are not recorded.
// An Attempt that is left without finishing (r, b, q, closing or reloading) stays abandoned.
addEventListener('keydown', e => {
  if (screen === 'ended') return;
  if (!e.metaKey) e.preventDefault(); // let Cmd shortcuts such as Cmd-R work
  if (START.includes(screen)) startKey(e);
  else if (screen !== 'typing') menuKey(e);
  else if (e.key === 'Escape') { screen = 'menu'; sel = 0; }
  else {
    record(e, ord);
    heldIn.set(e.code, ord);
    typed = applyKey(passage, typed, e, wrongKeyMode());
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
  const selKey = screen === 'menu' ? ITEMS[sel][0] : null;
  const groups = MENU.map(([name, items]) => `<div><h4>${name}</h4>${items.map(([k, l]) =>
    `<div class="item ${k === selKey ? 'sel' : ''}"><kbd>${label(k)}</kbd> ${l}</div>`).join('')}</div>`).join('');
  const hint = screen === 'menu'
    ? 'Press a letter, or <kbd>j</kbd>/<kbd>k</kbd> and <kbd>Enter</kbd>.'
    : 'While typing: only printable characters and <kbd>Backspace</kbd> change what you have typed; <kbd>Esc</kbd> opens this menu. Other keys are recorded and do nothing. <kbd>Esc</kbd> goes back.';
  return `<div class="menu"><div class="groups">${groups}</div><div class="hint">${hint}</div></div>`;
}

function settingsHTML() {
  const items = settingRows().map(([table, key, value], i) =>
    `<div class="item ${i === sel ? 'sel' : ''}">${table}.${key} = ${esc(String(value))}</div>`).join('');
  return `<div class="menu"><h4>Settings</h4>${items}<div class="hint"><kbd>j</kbd>/<kbd>k</kbd> select, <kbd>Enter</kbd> changes the value, <kbd>Esc</kbd> goes back. They are saved in typokiller.toml.</div></div>`;
}

function listHTML(title, labels) {
  const items = labels.map((l, i) =>
    `<div class="item ${i === sel ? 'sel' : ''}"><kbd>${i + 1}</kbd> ${esc(l)}</div>`).join('');
  return `<h4>${title}</h4>${items}`;
}

function startHTML() {
  const choose = 'Press a number, or <kbd>j</kbd>/<kbd>k</kbd> and <kbd>Enter</kbd>.';
  if (screen === 'boards') {
    return `${listHTML('Board', boards.map(b => b.name))}<p class="hint">${choose} <kbd>n</kbd> adds a Board.</p>`;
  }
  if (screen === 'keymaps') {
    return `${listHTML(`Keymap on ${esc(board.name)}`, board.keymaps.map(k => k.letter_layout))}`
      + `<p class="hint">${choose} <kbd>Esc</kbd> goes back.</p>`;
  }
  const step = screen === 'name' ? `Name: ${esc(draft.name)}<span class="cur"> </span>`
    : `Press <kbd>Enter</kbd> to choose the <code>${screen === 'vil' ? '.vil' : 'vial.json'}</code> file.`;
  return `<h4>New Board</h4><p class="p">${step}</p>`
    + '<p class="hint">A name that exists adds the <code>.vil</code> to that Board. <kbd>Esc</kbd> goes back.</p>';
}

function render() {
  const starting = START.includes(screen);
  const mode = starting ? 'start' : { typing: 'typing', ended: 'ended' }[screen] ?? 'paused';
  document.getElementById('app').innerHTML = `
    <main>${screen === 'ended' ? '<p>Session ended. Reload the page to start a new Session.</p>' : starting ? startHTML() : passageHTML()}</main>
    ${screen === 'settings' ? settingsHTML() : screen === 'menu' || screen === 'help' ? menuHTML() : ''}
    <div class="status"><span class="mode">${mode}</span><span>${starting ? 'choosing a Board' : esc(boardLabel)}</span><span class="grow">built-in Passage</span>
      ${!starting && wrongKeyMode() === 'locked until fixed' ? '<span>locked until fixed</span>' : ''}</div>
    <div class="msg">${esc(message)}</div>`;
}

showBoards();
