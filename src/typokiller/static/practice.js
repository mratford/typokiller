import { applyKey, esc, showChars } from './typing.js';
import { openProgress, progressKey } from './progress.js';

// Each menu item is [key, label, what choosing it does].
const MENU = [
  ['Practice', [
    ['Escape', 'resume', () => { screen = 'typing'; }],
    ['d', 'Drill', () => showDrill(drill?.endless ?? false)],
    ['s', 'skip this Passage', () => { moveOn(); screen = 'typing'; }],
    ['r', 'restart this Passage', () => { nextAttempt(); screen = 'typing'; }],
    ['m', 'Keymap on/off', toggleKeymap],
  ]],
  ['Sources', [
    ['o', 'open a Source or endless Drills', async () => { await showSources(); screen = 'sources'; }],
    ['l', 'new Lesson', openLessonForm],
    ['i', 'import a Source', () => { screen = 'import'; }],
  ]],
  ['Learning', [
    ['u', 'unlock the next key (free-range only)', unlockNext],
  ]],
  ['Session', [
    ['p', 'progress page', () => { screen = 'progress'; openProgress(board.name, keymap.letter_layout); }],
    ['b', 'change Board', () => showBoards()],
    ['q', 'end Session', () => { screen = 'ended'; }],
    [',', 'settings', openSettings],
    ['?', 'all keys', () => { screen = 'help'; }],
  ]],
];
const ITEMS = MENU.flatMap(([, items]) => items);

// The values each choice setting can take. Enter on the settings page moves to the next one.
const CHOICES = { 'typing.wrong_key_mode': ['keep typing', 'locked until fixed'], 'typing.show_keymap': [false, true] };

// The screens shown before a Session starts: the Board list, the Keymap list, and
// the three steps of adding a Board.
const START = ['boards', 'keymaps', 'name', 'vil', 'vial'];

let session;
let passage, nextPassage; // each { id, text, heading }; nextPassage is shown faint below, and
                          // a Lesson's heading above its Passage
let source = null; // the open Source: { id, title, at, total }, where `at` is its bookmark;
                   // null while the built-in Passage is typed
let drill = null; // while Drills are typed: { endless, generator, targets, back, done }, where `back`
                  // is [passage, nextPassage] to come back to after the Drills, and `done` says
                  // that passage was finished or skipped, so the Source then moves on from it
let unlocking = null; // the unlock state of a Letter layout being learned, from the server:
                      // { unlocked, total, next, introducing }; null for other Letter layouts
let sources = []; // from the server, unfinished first, the last opened first
let query = ''; // typed into the open text field of the import panel or the Lesson form
let spend = null; // for the Lesson form: { spent, cap } in pounds this month, and the last Lesson's language
let language = null; // the Lesson form's language, such as 'python': the last used, from the server at first
let results = []; // the Gutenberg search results
let screen = 'boards'; // one of START, or 'typing', 'menu', 'help', 'settings', 'sources', 'import',
                       // 'language', a key of FIELDS, 'results', 'article', 'progress' or 'ended'
let boards = []; // from the server, each with its Keymaps, last used first
let board = null; // the Board chosen on the start screen
let keymap = null; // the Session's Keymap, as the Board list gives it: { letter_layout, version, used }
let drawing = { layers: [], keys: {} }; // the Session's Keymap: an SVG drawing of each layer, and
                                        // the key to press for each character, as { layer, key }
let draft = {}; // the name and .vil of a Board being added

let seq = 0;
let ord = 0; // the current Attempt's order in the Session
let attempts = []; // attempts[ord] holds the Passage id Attempt ord types and its settings
let typed = '';
let sel = 0; // the selected line of the list or menu on screen
let settings = null; // the settings file's values while the settings page is open
let editing = null; // the text typed for the selected number setting while it is edited
let message = '';
let noticesSeen = null; // how many notices the server had at the last check; null before the first
const heldIn = new Map(); // code -> the Attempt that recorded its keydown
let summary = ''; // the last finished Attempt's numbers, shown on the message line before `message`
let summaryFor = null; // the ord of the finished Attempt whose numbers have not been asked for yet
let events = []; // not yet stored by the server
let finished = []; // ords of finished Attempts, not yet stored by the server

const getJSON = url => fetch(url).then(r => r.json());
const getSettings = () => getJSON('/api/settings');
const send = (url, body, { method = 'POST', keepalive = false } = {}) =>
  fetch(url, { method, keepalive, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const sendJSON = (...args) => send(...args).then(r => r.json());
const chooseHint = 'Press a number, or <kbd>j</kbd>/<kbd>k</kbd> and <kbd>Enter</kbd>.';

// Moves the selection with j and k. Returns whether the key was j or k.
function moveSel(e, count) {
  if (e.key === 'j') sel = Math.min(sel + 1, count - 1);
  else if (e.key === 'k') sel = Math.max(sel - 1, 0);
  else return false;
  return true;
}

// Chooses from a numbered list by its number, or with j/k and Enter.
function listKey(e, items, choose) {
  if (moveSel(e, items.length)) return;
  const item = e.key === 'Enter' ? items[sel] : items[Number(e.key) - 1];
  if (item) choose(item);
}

// The text in a form after one more key.
const edit = (text, e) =>
  e.key === 'Backspace' ? text.slice(0, -1) : e.key.length === 1 && !e.metaKey && !e.ctrlKey ? text + e.key : text;

async function showSources() {
  sources = await getJSON('/api/sources');
  sel = 0;
}

// The Source a new Session resumes: the last opened one that is not finished.
const resume = () => sources.find(s => s.at < s.total);

// Shows what the server serves: a Passage and the one after it. After a Source's
// last Passage comes the built-in one, and a finished Source is closed.
const show = served => ({ source, passages: [passage, nextPassage] } = served);

const openSource = async (id, at) => show(await sendJSON(`/api/sources/${id}/bookmark`, { at }, { method: 'PUT' }));

// Finishing or skipping a Passage moves the bookmark on. The next Passage is
// shown at once, and the server then sends the one after it.
function advance() {
  if (!source) return;
  const { id, at, title } = source;
  passage = nextPassage;
  openSource(id, at + 1).then(() => { if (!source) message = `Finished ${title}.`; render(); });
}

// One Drill, or endless Drills with the Targets ranked again before each one. The
// server makes a Drill from the key events it has stored, so they are sent first.
// While Introduction Drills are due, the server makes one. With `introduction`, the page
// asks only for an Introduction Drill: if none is due any more, the Passage comes back.
// The Passage is null until the Drill comes, and keys typed meanwhile do nothing, not even Esc.
async function showDrill(endless, introduction = false) {
  drill = { endless, generator: null, targets: [], back: drill?.back ?? [passage, nextPassage], done: drill?.done ?? false };
  passage = null;
  screen = 'typing';
  render();
  await flush();
  const made = await sendJSON(`/api/sessions/${session}/drills`, { introduction });
  await setUnlocking(made.unlocking);
  if (!made.id) return moveOn();
  passage = { id: made.id, text: made.text };
  nextPassage = endless ? null : drill.back[drill.done ? 1 : 0];
  drill.generator = made.generator;
  drill.targets = made.targets;
  nextAttempt();
  render();
}

// After a finished or skipped Passage: the next Passage, and an Attempt at it. After
// one Drill, the Passage it interrupted comes back from its start. After an unlock,
// Introduction Drills come first until the new key has been seen often enough; a
// finished or skipped Passage moves the Source on after them.
function moveOn() {
  if (drill?.endless) return showDrill(true);
  if (unlocking?.introducing) {
    drill ??= { back: [passage, nextPassage], done: true };
    return showDrill(false, true);
  }
  if (drill) {
    [passage, nextPassage] = drill.back;
    if (drill.done) advance();
    drill = null;
  } else advance();
  nextAttempt();
}

// Keeps the unlock state from the server. The Keymap drawings show the locked keys, so
// they are fetched again after an unlock.
async function setUnlocking(state) {
  if (state?.unlocked !== unlocking?.unlocked) drawing = await getJSON(`/api/sessions/${session}/keymap`);
  unlocking = state;
}

// u unlocks the next key at once. A notice from the server says which key, and
// Introduction Drills of it come after this Attempt.
async function unlockNext() {
  const r = await send(`/api/sessions/${session}/unlocks`, {});
  const answer = await r.json();
  if (r.ok) await setUnlocking(answer);
  else message = answer.detail;
  screen = 'typing';
}

async function chooseSource(s) {
  drill = null;
  await openSource(s.id, s.at < s.total ? s.at : 0); // a finished Source opens from the start
  nextAttempt();
  screen = 'typing';
  render();
}

async function search() {
  const r = await fetch(`/api/gutenberg?q=${encodeURIComponent(query)}`);
  if (!r.ok) { message = (await r.json()).detail; render(); return; }
  results = await r.json();
  sel = 0;
  screen = 'results';
  render();
}

async function importBook(book) {
  message = `Importing ${book.title}…`;
  render();
  const r = await send('/api/gutenberg', { number: book.number, title: book.title });
  if (!r.ok) { message = `Could not import ${book.title}.`; render(); return; }
  const imported = await r.json();
  message = `Imported ${book.title}: ${imported.passages} Passages, ${imported.skipped} paragraphs skipped.`;
  await chooseSource({ id: imported.source, at: 0, total: imported.passages });
}

// The server clones the repo in the background, and a notice says when it is done.
function importCode() {
  send('/api/code', { url: query });
  message = `Cloning ${query} in the background.`;
  screen = 'typing';
}

// The Lesson languages: [the key that chooses it, its name, the server's name for it].
const LANGUAGES = [['p', 'Python', 'python'], ['g', 'Gleam', 'gleam']];
const lessonLanguage = () => LANGUAGES.find(l => l[2] === language);

// l opens the Lesson form. It asks for the language first (Enter chooses the last used), then
// the topic, and shows what Lessons cost this month.
async function openLessonForm() {
  spend = await getJSON('/api/lessons/spend');
  language ??= spend.language;
  screen = 'language';
}

function languageKey(e) {
  const chosen = LANGUAGES.find(([k, , l]) => (e.key === 'Enter' ? l === language : k === e.key));
  if (chosen) { language = chosen[2]; query = ''; screen = 'lesson'; }
}

// The server writes the Lesson in the background, after the ones asked for before it, and a
// notice says when it is ready. A request that could make this month's cost more than the cap is refused.
async function requestLesson() {
  const topic = query.trim();
  if (!topic) return;
  const r = await send('/api/lessons', { topic, language });
  if (!r.ok) { message = (await r.json()).detail; render(); return; }
  message = `Writing a ${lessonLanguage()[1]} Lesson on ${topic} in the background.`;
  screen = 'typing';
  render();
}

// The import panel's choices: [key, label, the screen it opens].
const IMPORTS = [
  ['g', 'Project Gutenberg book', 'gutenberg'],
  ['c', 'Code from a git repo', 'code'],
  ['a', 'Article from the browser', 'article'],
];

// The text fields of the import panel, by screen: the title and what Enter does.
// Text can be pasted into them.
const FIELDS = {
  gutenberg: { enter: search, enterHint: 'searches',
    title: 'Gutenberg: search title and author, or paste a book number or URL' },
  code: { enter: importCode, enterHint: 'clones it in the background', title: 'Code: type or paste a git URL' },
  lesson: { enter: requestLesson, enterHint: 'asks for it; it is written in the background',
    get title() {
      return `New ${lessonLanguage()[1]} Lesson: type a topic · £${spend.spent.toFixed(2)} of £${spend.cap} this month`;
    } },
};

async function showBoards(id) {
  screen = 'boards';
  const listed = await getJSON('/api/boards');
  boards = listed.boards;
  await showSources();
  sel = Math.max(0, boards.findIndex(b => b.id === (id ?? listed.last)));
  render();
}

// A new Session starts again from seq 0 and Attempt 0. The old Session's events
// are sent first; any that fail to send are lost.
async function startSession(chosen) {
  await flush();
  events = [];
  finished = [];
  const settings = await getSettings();
  const started = await sendJSON('/api/sessions', { keymap_version: chosen.version });
  session = started.session;
  drawing = await getJSON(`/api/sessions/${session}/keymap`);
  unlocking = drawing.unlocking;
  show(started);
  const resumed = resume();
  if (resumed) await openSource(resumed.id, resumed.at);
  attempts = [{ passage: passage.id, settings }];
  keymap = chosen;
  seq = 0;
  ord = 0;
  typed = '';
  message = '';
  summary = '';
  summaryFor = null;
  heldIn.clear();
  drill = null;
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
    else if (e.key === 'Enter' && draft.name) screen = 'vil';
    else draft.name = edit(draft.name, e);
  } else if (screen === 'vil' || screen === 'vial') {
    if (e.key === 'Escape') screen = 'boards';
    else if (e.key === 'Enter' && screen === 'vil') pickFile('.vil', text => { draft.vil = text; screen = 'vial'; });
    else if (e.key === 'Enter') pickFile('.json', async text => {
      const added = await sendJSON('/api/boards', { ...draft, vial: text });
      await showBoards(added.board);
    });
  } else if (e.key === 'n' && screen === 'boards') { screen = 'name'; draft = { name: '' }; }
  else if (e.key === 'Escape') screen = 'boards';
  else if (screen === 'boards') listKey(e, boards, chooseBoard);
  else listKey(e, board.keymaps, startSession);
}

// Starts an Attempt at the current Passage. Reads the settings file again, so each
// Attempt uses the settings as they are now. Keys typed before the file has been
// read use the previous Attempt's settings.
function nextAttempt() {
  ord++;
  typed = '';
  const attempt = { passage: passage.id, settings: attempts[ord - 1].settings };
  attempts[ord] = attempt;
  getSettings().then(s => { attempt.settings = s; render(); });
}

const wrongKeyMode = () => attempts[ord].settings.typing.wrong_key_mode;

// m turns the Keymap drawing on or off at once, and saves it in the settings file for the
// next Attempts. The current Attempt records the new value only if none of its key events
// have been sent yet. That small error in the data is accepted.
function toggleKeymap() {
  const old = attempts[ord].settings;
  const shown = !old.typing.show_keymap;
  attempts[ord].settings = { ...old, typing: { ...old.typing, show_keymap: shown } };
  saveSetting(['typing', 'show_keymap'], shown);
  screen = 'typing';
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
  const batch = {
    events: [...events], finished: [...finished],
    attempts: Object.fromEntries(events.map(e => [e.attempt, attempts[e.attempt]])),
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

// One row per setting: [its path of TOML keys, such as ['typing', 'wrong_key_mode'], value].
// A table inside a table, such as the layer names of a Keymap, gives a row for each of its values.
const settingRows = (values = settings, path = []) => Object.entries(values).flatMap(([k, v]) =>
  v?.constructor === Object ? settingRows(v, [...path, k]) : [[[...path, k], v]]);

// Saves one setting of a table, such as ['typing', 'show_keymap'], in the settings file.
// The server changes only that value, so the rest of the file stays as it is.
const saveSetting = ([table, key], value) => send('/api/settings', { [table]: { [key]: value } }, { method: 'PUT' });

// Enter moves a choice setting to its next value, or edits a number setting:
// type the new number, then Enter saves it. Other values, such as the layer names of a Keymap,
// are edited in the file.
function settingsKey(e) {
  const rows = settingRows();
  const [path, value] = rows[sel];
  const [table, key] = path;
  const choices = CHOICES[path.join('.')];
  if (editing !== null && e.key !== 'Enter') { editing = edit(editing, e); return; }
  if (editing === null && (moveSel(e, rows.length) || e.key !== 'Enter' || !(choices || typeof value === 'number'))) return;
  if (choices) settings[table][key] = choices[(choices.indexOf(value) + 1) % choices.length];
  else if (editing === null) { editing = String(value); return; }
  else if (editing.trim() && !isNaN(editing)) settings[table][key] = Number(editing);
  editing = null;
  saveSetting(path, settings[table][key]);
  message = 'Settings saved. They apply from the next Attempt.';
}

// Esc in any panel goes back to the menu.
async function menuKey(e) {
  if (e.key === 'Escape' && screen !== 'menu') { screen = 'menu'; sel = 0; editing = null; }
  else if (screen === 'settings') settingsKey(e);
  else if (screen === 'sources') listKey(e, openItems(), s => s === ENDLESS ? showDrill(true) : chooseSource(s));
  else if (screen === 'import') {
    const choice = IMPORTS.find(([k]) => k === e.key);
    if (choice) { screen = choice[2]; query = ''; }
  }
  else if (screen === 'language') languageKey(e);
  else if (FIELDS[screen]) { if (e.key === 'Enter') FIELDS[screen].enter(); else query = edit(query, e); }
  else if (screen === 'results') listKey(e, results, importBook);
  else if (screen === 'progress') progressKey(e);
  else if (screen === 'menu' && !moveSel(e, ITEMS.length)) {
    await (e.key === 'Enter' ? ITEMS[sel] : ITEMS.find(([k]) => k === e.key))?.[2]();
  }
  render();
}

// Keys used on the start screens and in the menu are not key events of any Attempt,
// so they are not recorded.
// An Attempt that is left without finishing (d, s, r, o, b, q, closing or reloading) stays
// abandoned. Only finishing and s move the Source's bookmark on.
addEventListener('keydown', e => {
  if (screen === 'ended') return;
  if (!e.metaKey) e.preventDefault(); // let Cmd shortcuts such as Cmd-R work
  if (START.includes(screen)) startKey(e);
  else if (screen !== 'typing') menuKey(e);
  else if (!passage) return; // a Drill is being made: no key does anything until it comes
  else if (e.key === 'Escape') { screen = 'menu'; sel = 0; }
  else {
    record(e, ord);
    heldIn.set(e.code, ord);
    typed = applyKey(passage.text, typed, e, wrongKeyMode());
    if (typed === passage.text) {
      finished.push(ord);
      summaryFor = ord;
      // Firefox loses some keyups, so the summary is asked for after a second at the latest.
      setTimeout(finishedOrd => { if (summaryFor === finishedOrd) showSummary(); }, 1000, ord);
      summary = '✓ finished';
      message = '';
      moveOn();
    }
  }
  render();
});

// A keyup belongs to the Attempt of its keydown, even if a new Attempt has started.
addEventListener('keyup', e => {
  if (!heldIn.has(e.code)) return;
  record(e, heldIn.get(e.code));
  heldIn.delete(e.code);
  if (summaryFor !== null && ![...heldIn.values()].includes(summaryFor)) showSummary();
});

const percent = x => `${Math.round(x * 100)}%`;

// Shows a finished Attempt's summary on the message line, after its last keyup, so that
// the server has all its key events. Typing the next Passage goes on meanwhile.
async function showSummary() {
  const attempt = summaryFor;
  summaryFor = null;
  await flush();
  const s = await getJSON(`/api/sessions/${session}/attempts/${attempt}/summary`);
  summary = `✓ ${Math.round(s.wpm)} wpm (median ${Math.round(s.median_wpm)})`
    + ` · ${percent(s.accuracy)} first time (median ${percent(s.median_accuracy)})`
    + (s.slowest_pairs.length ? ` · slowest pairs: ${s.slowest_pairs.map(showChars).join(' ')}` : '');
  await setUnlocking(s.unlocking);
  render();
}

// Pasting into a text field of the import panel.
addEventListener('paste', e => {
  if (!FIELDS[screen]) return;
  query += e.clipboardData.getData('text');
  render();
});

// Shows the notices that the server added since the last check on the message line.
// Notices from before the page loaded are not shown.
async function checkNotices() {
  const notices = await getJSON('/api/notices');
  if (noticesSeen !== null && notices.length > noticesSeen) {
    message = notices.slice(noticesSeen).join(' · ');
    render();
  }
  noticesSeen = notices.length;
}

addEventListener('pagehide', () => flush(true));
checkNotices();
setInterval(() => { flush(); checkNotices(); }, 1000);

const label = k => (k === 'Escape' ? 'Esc' : k);

function passageHTML() {
  if (!passage) return '<p>Making a Drill…</p>';
  const text = passage.text;
  let h = '';
  for (let j = 0; j < text.length; j++) {
    // A newline is shown as a space before the line break, so the cursor or a wrong key there can be seen.
    const newline = text[j] === '\n';
    let cls = '', shown = newline ? ' ' : text[j];
    if (j === typed.length) cls = 'cur';
    else if (j < typed.length && typed[j] === text[j]) cls = 'ok';
    else if (j < typed.length) { cls = 'bad'; shown = showChars(typed[j]); }
    h += `<span class="${cls}">${esc(shown)}</span>${newline ? '\n' : ''}`;
  }
  const heading = passage.heading ? `<h3 class="heading">${esc(passage.heading)}</h3>` : '';
  return `${heading}<div class="p">${h}</div>${nextPassage ? `<div class="p next">${esc(nextPassage.text)}</div>` : ''}`;
}

// A Passage taller than the screen scrolls to keep the cursor's line a third of the way down.
function scrollToCursor() {
  const main = document.querySelector('main'), cur = main.querySelector('.cur');
  if (cur) main.scrollTop = cur.offsetTop - main.clientHeight / 3;
}

function menuHTML() {
  const selKey = screen === 'menu' ? ITEMS[sel][0] : null;
  const groups = MENU.map(([name, items]) => `<div><h4>${name}</h4>${items.map(([k, l]) =>
    `<div class="item ${k === selKey ? 'sel' : ''}"><kbd>${label(k)}</kbd> ${l}</div>`).join('')}</div>`).join('');
  const hint = screen === 'menu'
    ? 'Press a letter, or <kbd>j</kbd>/<kbd>k</kbd> and <kbd>Enter</kbd>.'
    : 'While typing: only printable characters, <kbd>Backspace</kbd>, and <kbd>Enter</kbd> at the end of a line change what you have typed. After <kbd>Enter</kbd> the next line\'s indentation is filled in. <kbd>Esc</kbd> opens this menu. Other keys are recorded and do nothing. <kbd>Esc</kbd> goes back.';
  return `<div class="menu"><div class="groups">${groups}</div><div class="hint">${hint}</div></div>`;
}

// The `o` list: the Sources, then endless Drills.
const ENDLESS = {};
const openItems = () => [...sources, ENDLESS];

const sourceLabel = s => `${s.title} · ${s.at < s.total ? `§${s.at + 1} of ${s.total}` : 'finished, opens from the start'}`;

function sourcesHTML() {
  const labels = openItems().map(s => s === ENDLESS ? 'Endless Drills, with the Targets ranked again after each one' : sourceLabel(s));
  return `<div class="menu">${listHTML('Open a Source', labels)}`
    + `<div class="hint">${chooseHint}${sources.length ? '' : ' No Sources yet: <kbd>i</kbd> in the menu imports one.'} <kbd>Esc</kbd> goes back.</div></div>`;
}

// A panel of choices, each [key, label], with the one of the key `selected` marked.
const choicesHTML = (title, choices, hint, selected) => `<div class="menu"><h4>${title}</h4>`
  + choices.map(([k, l]) => `<div class="item ${k === selected ? 'sel' : ''}"><kbd>${k}</kbd> ${l}</div>`).join('')
  + `<div class="hint">${hint}<kbd>Esc</kbd> goes back.</div></div>`;

function importHTML() {
  if (screen === 'import') return choicesHTML('Import a Source', IMPORTS, '');
  if (screen === 'language') {
    const hint = '<kbd>Enter</kbd> chooses the last used. ';
    return choicesHTML('New Lesson: choose the language', LANGUAGES, hint, lessonLanguage()[0]);
  }
  const field = FIELDS[screen];
  if (field) {
    return `<div class="menu"><h4>${field.title}</h4><div class="p">${esc(query)}<span class="cur"> </span></div>`
      + `<div class="hint"><kbd>Enter</kbd> ${field.enterHint}. <kbd>Esc</kbd> goes back.</div></div>`;
  }
  const labels = results.map(r => `${r.title} · ${r.authors} · #${r.number}`);
  return `<div class="menu">${listHTML(`Gutenberg books for "${esc(query)}"`, labels)}`
    + `<div class="hint">${results.length ? '<kbd>Enter</kbd> imports and opens it.' : 'No books found.'} <kbd>Esc</kbd> goes back.</div></div>`;
}

// The article bookmarklet sends the selected text, or else the page's `article` or
// `body`, to this typokiller's /send page. It opens that page in a new window with
// the text after `#`, so it needs no request from the article's page to this server.
// The browser percent-decodes the URL before it runs it, so `#` is written `%23`.
const BOOKMARKLET = 'javascript:(() => {'
  + " const text = getSelection().toString() || (document.querySelector('article') || document.body).innerText;"
  + ' const article = JSON.stringify({ title: document.title || location.host, text });'
  + ` window.open('${location.origin}/send%23' + encodeURIComponent(article)); })()`;

function articleHTML() {
  return `<div class="menu"><h4>Article: send a web page from the browser</h4>`
    + `<p>Drag this link to the bookmarks bar of the browser that you read in: <a href="${esc(BOOKMARKLET)}">typokiller article</a></p>`
    + '<p>On an article, select the text to type, or select nothing to send the whole article. Then click the bookmark. '
    + 'A small typokiller window opens, saves the text, shows "Saved" and closes. The article is then first in '
    + '<kbd>o</kbd>, and this page shows a notice.</p>'
    + `<div class="hint">The bookmark sends to ${esc(location.origin)}. If the address of typokiller changes, drag the link again. `
    + '<kbd>Esc</kbd> goes back.</div></div>';
}

const PANELS = {
  menu: menuHTML, help: menuHTML, settings: settingsHTML, sources: sourcesHTML,
  import: importHTML, gutenberg: importHTML, code: importHTML, language: importHTML, lesson: importHTML, results: importHTML, article: articleHTML,
};

function settingsHTML() {
  const items = settingRows().map(([path, value], i) => {
    const shown = i === sel && editing !== null ? `${esc(editing)}<span class="cur"> </span>` : esc(String(value));
    return `<div class="item ${i === sel ? 'sel' : ''}">${esc(path.join('.'))} = ${shown}</div>`;
  }).join('');
  return `<div class="menu"><h4>Settings</h4>${items}<div class="hint"><kbd>j</kbd>/<kbd>k</kbd> select, <kbd>Enter</kbd> changes the value, <kbd>Esc</kbd> goes back. They are saved in typokiller.toml.</div></div>`;
}

function listHTML(title, labels) {
  const items = labels.map((l, i) =>
    `<div class="item ${i === sel ? 'sel' : ''}"><kbd>${i + 1}</kbd> ${esc(l)}</div>`).join('');
  return `<h4>${title}</h4>${items}`;
}

function startHTML() {
  const resumed = resume();
  const resumes = resumed ? `Resumes ${esc(sourceLabel(resumed))}.` : 'No Source to resume: types the built-in Passage.';
  if (screen === 'boards') {
    return `${listHTML('Board', boards.map(b => b.name))}<p class="hint">${chooseHint} <kbd>n</kbd> adds a Board.</p><p>${resumes}</p>`;
  }
  if (screen === 'keymaps') {
    return `${listHTML(`Keymap on ${esc(board.name)}`, board.keymaps.map(k => k.letter_layout))}`
      + `<p class="hint">${chooseHint} <kbd>Esc</kbd> goes back.</p><p>${resumes}</p>`;
  }
  const step = screen === 'name' ? `Name: ${esc(draft.name)}<span class="cur"> </span>`
    : `Press <kbd>Enter</kbd> to choose the <code>${screen === 'vil' ? '.vil' : 'vial.json'}</code> file.`;
  return `<h4>New Board</h4><p class="p">${step}</p>`
    + '<p class="hint">A name that exists adds the <code>.vil</code> to that Board. <kbd>Esc</kbd> goes back.</p>';
}

// The key to press for the next character of the Passage, as { layer, key }, if the Keymap has one.
const nextKey = () => drawing.keys[passage?.text[typed.length]];

// The Keymap drawn faintly under the Passage while typing, when the setting is on. It shows the
// layer of the next character; render() outlines the key to press.
function keymapHTML() {
  if (screen !== 'typing' || !passage || !attempts[ord].settings.typing.show_keymap) return '';
  return `<div class="drawing">${drawing.layers[nextKey()?.layer ?? 0] ?? ''}</div>`;
}

// The status line's Drill part: the Targets, a space shown as ·.
const drillLabel = () => (drill.generator === 'introduction' ? 'Introduction Drill' : drill.endless ? 'Endless Drills' : 'Drill')
  + (drill.targets.length ? ` · Targets: ${drill.targets.map(t => showChars(t.unit)).join(' ')}` : '');

// The status line's unlock progress on a Letter layout being learned, such as "10/30 keys · next o".
const unlockLabel = () => `${unlocking.unlocked}/${unlocking.total} keys`
  + (unlocking.next ? ` · next ${showChars(unlocking.next)}` : '');

function render() {
  const starting = START.includes(screen);
  const mode = starting ? 'start' : { typing: drill ? 'drill' : 'typing', ended: 'ended' }[screen] ?? 'paused';
  // The progress page draws itself in its own element, so that its chart is not drawn again on each render.
  document.getElementById('app').hidden = screen === 'progress';
  document.getElementById('progress').hidden = screen !== 'progress';
  document.getElementById('app').innerHTML = `
    <main>${screen === 'ended' ? '<p>Session ended. Reload the page to start a new Session.</p>' : starting ? startHTML() : passageHTML()}</main>
    ${keymapHTML()}${PANELS[screen]?.() ?? ''}
    <div class="status"><span class="mode">${mode}</span><span>${starting ? 'choosing a Board' : esc(`${board.name} · ${keymap.letter_layout}`)}</span>
      <span class="grow">${starting ? '' : esc(drill ? drillLabel() : source ? sourceLabel(source) : 'built-in Passage')}</span>
      ${!starting && unlocking ? `<span>${esc(unlockLabel())}</span>` : ''}
      ${!starting && wrongKeyMode() === 'locked until fixed' ? '<span>locked until fixed</span>' : ''}</div>
    <div class="msg">${esc([summary, message].filter(Boolean).join(' · '))}</div>`;
  document.getElementById(`k${nextKey()?.key}`)?.classList.add('next');
  scrollToCursor();
}

showBoards();
