// The analysis page: one entry at a time, for a keyboard with a layout, or for the lessons with no
// keyboard on one layout. It shows the trend chart, the keyboard picture with heat for one layer,
// and the weakest characters and pairs. The server makes the chart (a Vega-Lite spec, which
// vega-embed draws), the pictures and the lists; this module only shows them.
// The keyboards panel over the bottom of the page lists the keyboards and their layouts, and
// adds keyboards, saves layouts and sets layer names.

import { listLabels } from './lists.js';

// vega-embed and the libraries it needs, from cdn.jsdelivr.net, loaded in this order. vega-lite 6.4.1 is
// the version of Altair's schema.
const VEGA = ['vega@6.4.0/build/vega.min.js', 'vega-lite@6.4.1/build/vega-lite.min.js', 'vega-embed@7.3.0/build/vega-embed.min.js'];
let vegaLoading = null; // the promise of loading them
const loadVega = () => vegaLoading ??= VEGA.reduce((loaded, path) => loaded.then(() => new Promise(done => {
  document.head.append(Object.assign(document.createElement('script'),
    { src: `https://cdn.jsdelivr.net/npm/${path}`, onload: done, onerror: done }));
})), Promise.resolve());

// Text for innerHTML, with &, < and > escaped.
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
// Typed characters as the page shows them: a space as ␣, a newline as ↵.
const showChars = text => text.replaceAll(' ', '␣').replaceAll('\n', '↵');

// What a key does to `view` ({ at, layer, pair }) on a page with `entries` entries, `layers`
// layers and `pairs` pairs: h and l move to the previous and next entry (the first after the
// last) and start on the first layer and pair, a number picks that layer, and j and k move the
// arc to the next and previous pair.
// null for any other key.
export function pressed(key, view, { entries, layers, pairs }) {
  if (key === 'h' || key === 'l') return { at: (view.at + (key === 'l' ? 1 : entries - 1)) % entries, layer: 0, pair: 0 };
  if (/^[1-9]$/.test(key) && Number(key) <= layers) return { ...view, layer: Number(key) - 1 };
  if (key === 'j' || key === 'k') {
    return { ...view, pair: Math.min(Math.max(view.pair + (key === 'j' ? 1 : -1), 0), Math.max(pairs - 1, 0)) };
  }
  return null;
}

// The keys of the keyboards panel. They are never labels of its lines.
export const PANEL_KEYS = 'jknvrb';

// The name in the text of a vial.json, or '' when it has none.
export const vialName = text => JSON.parse(text).name ?? '';

let page; // from the server: { entries, entry, weeks, days, trend, names, layers, chars, pairs }, or { message }; null when the request failed
let view = { at: 0, layer: 0, pair: 0 };
let asked = 0; // the number of requests so far
let boards = []; // from the server: [{ id, name, keymaps: [{ letter_layout, versions, saved, names, layer_names, layers }] }]
let letters = ''; // the letters that label the panel's lines
let boardsRead = null; // the promise of the last reading of the keyboards
let panel = null; // while the panel is open: { sel, layer, typed }, typed being the start of a label
let form = null; // while a form is open: { kind: 'add', step, vial, name }, { kind: 'save' } or { kind: 'names', text }
let message = ''; // the message line

// Reads the recordings again, and shows `entry`, or the first entry when it is undefined.
async function load(entry) {
  const mine = ++asked;
  const url = entry === undefined ? '/api/analysis' : `/api/analysis?entry=${encodeURIComponent(entry)}`;
  const [found] = await Promise.all([fetch(url).then(r => (r.ok ? r.json() : null), () => null), loadVega(), boardsRead]);
  if (mine !== asked) return; // h or l was pressed again meanwhile
  page = found;
  view = { at: page?.entries ? page.entries.indexOf(page.entry) : 0, layer: 0, pair: 0 };
  draw();
}

// Reads the keyboards and the letters of the labels again. When that fails, the analysis is
// still shown.
function loadBoards() {
  return boardsRead = fetch('/api/boards').then(r => r.json()).then(found => ({ boards, letters } = found), () => {});
}

// Draws the whole page. The chart is drawn only here, so it is not drawn again for each key.
function draw() {
  drawPanel();
  const el = document.getElementById('analysis');
  const none = boards.length ? '' : '<p>No keyboards yet. Press <kbd>b</kbd>, then <kbd>n</kbd> to add one.</p>';
  if (!page) {
    el.innerHTML = `<div class="message">${none}<p>The recorded lessons could not be read. Run <code>typokiller-service logs</code> to see why.</p></div>`;
    return;
  }
  if (page.message) {
    el.innerHTML = `<div class="message">${none}<p>${page.message}</p></div>`;
    return;
  }
  const count = page.entries.length > 1 ? ` (${view.at + 1} of ${page.entries.length})` : '';
  el.innerHTML = `${none}<h4>${esc(page.entry)}${count}</h4><div id="trend"></div><div id="weakness"></div>`;
  const trend = document.getElementById('trend');
  if (!page.days) {
    trend.innerHTML = `<p class="hint">No lessons in the last ${page.weeks} weeks.</p>`;
  } else if (!window.vegaEmbed) {
    trend.innerHTML = '<p class="hint">The chart needs vega-embed from cdn.jsdelivr.net, which did not load.</p>';
  } else {
    const dark = matchMedia('(prefers-color-scheme: dark)').matches;
    vegaEmbed(trend, page.trend, { actions: false, theme: dark ? 'dark' : undefined });
  }
  drawKeymap();
}

function table(title, rows, selected) {
  const trs = rows.map((r, i) => `<tr class="${i === selected ? 'sel' : ''}"><td class="mono">${esc(showChars(r.unit))}</td>`
    + `<td>${Math.round(r.cost)} ms</td><td>${r.seen} seen</td></tr>`).join('');
  return `<div><h4>${title}</h4>${rows.length ? `<table>${trs}</table>` : '<p class="hint">None seen often enough yet.</p>'}</div>`;
}

// The layer tabs, the keyboard picture of the layer with the selected pair's arc, and the lists.
function drawKeymap() {
  document.getElementById('weakness').innerHTML = `<div class="tabs">${tabs(page.names, view.layer)}</div><div class="split">`
    + `<div class="heat">${page.layers[view.layer] ?? ''}</div>`
    + table('Weakest characters', page.chars, -1) + table('Weakest pairs', page.pairs, view.pair) + '</div>';
  const unit = page.pairs[view.pair]?.unit;
  [...document.querySelectorAll('.arc')].find(a => a.dataset.pair === unit)?.classList.add('on');
}

// The panel's lines: one for each keyboard and layout.
const lines = () => boards.flatMap(board => board.keymaps.map(keymap => ({ board, keymap })));
const panelLabels = all => listLabels(all.length, letters, PANEL_KEYS);

const tabs = (names, layer) => names.map((n, i) => `<span class="${i === layer ? 'on' : ''}"><kbd>${i + 1}</kbd> ${esc(n)}</span>`).join('');

// The panel, the status line with the keys, and the message line.
function drawPanel() {
  const keys = form ? '<kbd>Esc</kbd> stop'
    : panel ? 'label or <kbd>j</kbd>/<kbd>k</kbd> <kbd>Enter</kbd> analysis · a number: layer · <kbd>n</kbd> add a keyboard'
      + ' · <kbd>v</kbd> save a layout · <kbd>r</kbd> layer names · <kbd>b</kbd> close'
    : '<kbd>h</kbd>/<kbd>l</kbd> keyboard and layout · a number: layer · <kbd>j</kbd>/<kbd>k</kbd> pair'
      + ' · <kbd>b</kbd> keyboards · <kbd>t</kbd> typing page';
  document.getElementById('status').innerHTML = keys;
  document.getElementById('message').textContent = message;
  const el = document.getElementById('panel');
  el.hidden = !panel;
  if (!panel) return;
  const all = lines();
  const labels = panelLabels(all);
  const list = all.map(({ board, keymap }, i) => `<div class="${i === panel.sel ? 'item sel' : 'item'}"><kbd>${labels[i] ?? ''}</kbd>`
    + ` ${esc(board.name)} · ${esc(keymap.letter_layout)}</div>`).join('');
  const it = all[panel.sel];
  const about = it ? `<h4>${esc(it.board.name)} · ${esc(it.keymap.letter_layout)}</h4>`
    + `<div class="hint">${it.keymap.versions} saved ${it.keymap.versions > 1 ? 'versions' : 'version'}`
    + `${it.keymap.saved ? `, the newest from ${it.keymap.saved}` : ''}</div>`
    + `<div class="tabs">${tabs(it.keymap.names, panel.layer)}</div><div class="heat">${it.keymap.layers[panel.layer] ?? ''}</div>` : '';
  el.innerHTML = `<div class="panelgrid"><div><h4>keyboards and layouts</h4>${list}</div><div>${formHTML(it)}${about}</div></div>`;
}

function formHTML(it) {
  if (!form) return '';
  const cursor = '<span class="cursor"> </span>';
  if (form.kind === 'add') {
    const step = {
      vial: 'Press <kbd>Enter</kbd> to choose the keyboard\'s <code>vial.json</code>.',
      name: `Name: ${esc(form.name)}${cursor}<div class="hint">Change it, or press <kbd>Enter</kbd>.</div>`,
      vil: 'Press <kbd>Enter</kbd> to choose a layout saved in Vial (<code>.vil</code>).',
    }[form.step];
    return `<div class="form"><h4>add a keyboard · step ${['vial', 'name', 'vil'].indexOf(form.step) + 1} of 3</h4>${step}</div>`;
  }
  if (form.kind === 'save') {
    return `<div class="form"><h4>save a layout on ${esc(it.board.name)}</h4>Press <kbd>Enter</kbd> to choose a <code>.vil</code>.`
      + '<div class="hint">The same letters as a saved layout make a new version of it. Other letters make a new layout.</div></div>';
  }
  return `<div class="form"><h4>layer names, from layer 1</h4>${esc(form.text)}${cursor}`
    + '<div class="hint">Separate them with spaces. <kbd>Enter</kbd> saves.</div></div>';
}

// Opens the browser's file picker and gives the text of the chosen file to `then`. The browser
// allows this only while a key press is being handled.
function pickFile(accept, then) {
  const input = Object.assign(document.createElement('input'), { type: 'file', accept });
  input.onchange = async () => then(await input.files[0].text());
  input.click();
}

// Sends a change to the server, then reads the keyboards again and closes the form.
// `done` gives the message from the server's answer.
async function send(method, url, body, done) {
  const answer = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then(r => (r.ok ? r.text() : null), () => null);
  message = answer === null ? 'Nothing saved. Run typokiller-service logs to see why.' : done(answer && JSON.parse(answer));
  form = null;
  await loadBoards();
  draw();
}

// The new text of a line being typed.
const edit = (text, key) => (key === 'Backspace' ? text.slice(0, -1) : key.length === 1 ? text + key : text);

// What a key does while a form is open. True when the form takes the key.
function formKey(key, it) {
  const taken = key.length === 1 || ['Escape', 'Enter', 'Backspace'].includes(key);
  if (key === 'Escape') {
    form = null;
    message = 'Nothing saved.';
    return taken;
  }
  switch (form.kind) {
    case 'add':
      if (form.step === 'name' && key !== 'Enter') form.name = edit(form.name, key);
      else if (form.step === 'name') form.step = form.name.trim() ? 'vil' : 'name';
      else if (key === 'Enter' && form.step === 'vial') {
        pickFile('.json', text => { form = { ...form, step: 'name', vial: text, name: vialName(text) }; drawPanel(); });
      } else if (key === 'Enter') {
        const name = form.name.trim();
        pickFile('.vil', vil => send('POST', '/api/boards', { name, vial: form.vial, vil }, a => `Added ${name} · ${a.letter_layout}.`));
      }
      break;
    case 'save':
      if (key === 'Enter') {
        pickFile('.vil', vil => send('POST', `/api/boards/${it.board.id}/keymaps`, { vil }, a => `Saved ${it.board.name} · ${a.letter_layout}.`));
      }
      break;
    case 'names':
      if (key !== 'Enter') form.text = edit(form.text, key);
      else {
        const layers = form.text.split(' ').filter(Boolean);
        send('PUT', '/api/layers', { board: it.board.name, letter_layout: it.keymap.letter_layout, layers }, () => 'Layer names saved.');
      }
  }
  return taken;
}

// What a key does while the panel is open. True when the panel takes the key.
function panelKey(key) {
  const all = lines();
  const it = all[panel.sel];
  const labels = panelLabels(all);
  const typed = panel.typed + key;
  panel.typed = labels.some(l => l.startsWith(typed) && l !== typed) ? typed : '';
  if (panel.typed) return true;
  const chosen = key === 'Enter' && it ? panel.sel : labels.indexOf(typed);
  if (chosen >= 0) {
    const entry = `${all[chosen].board.name} · ${all[chosen].keymap.letter_layout}`;
    if (page?.entries?.includes(entry)) {
      panel = null;
      load(entry);
    } else {
      panel = { ...panel, sel: chosen, layer: 0 };
      message = 'No lessons on this layout yet.';
    }
  } else if (key === 'j' || key === 'k') {
    panel = { ...panel, sel: Math.min(Math.max(panel.sel + (key === 'j' ? 1 : -1), 0), Math.max(all.length - 1, 0)), layer: 0 };
  } else if (/^[1-9]$/.test(key) && it && Number(key) <= it.keymap.layers.length) panel.layer = Number(key) - 1;
  else if (key === 'n') form = { kind: 'add', step: 'vial', name: '' };
  else if (key === 'v' && it) form = { kind: 'save' };
  else if (key === 'r' && it) form = { kind: 'names', text: it.keymap.layer_names.join(' ') };
  else if (key === 'Escape' || key === 'b') panel = null;
  else return false;
  return true;
}

// What a key does on the page, with the panel closed. True when the page takes the key.
// h and l read the recordings again, even with one entry. Esc does nothing.
function pageKey(key) {
  if (key === 'b') {
    panel = { sel: 0, layer: 0, typed: '' };
    return true;
  }
  if (key === 't') {
    location.href = '/typing'; // the server redirects the browser to keybr
    return true;
  }
  const next = page?.entries && pressed(key, view, { entries: page.entries.length, layers: page.layers.length, pairs: page.pairs.length });
  if (!next) return false;
  view = next;
  if (key === 'h' || key === 'l') load(page.entries[view.at]);
  else drawKeymap();
  return true;
}

function onKey(e) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  message = '';
  if (form ? formKey(e.key, lines()[panel.sel]) : panel ? panelKey(e.key) : pageKey(e.key)) e.preventDefault();
  drawPanel();
}

if (globalThis.document) { // not in the tests
  addEventListener('keydown', onKey);
  loadBoards();
  load();
}
