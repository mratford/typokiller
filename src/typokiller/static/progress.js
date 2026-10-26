import { esc, showChars } from './typing.js';

// The progress page (spec §11): one Board × Letter layout at a time. It shows the trend
// chart, a heat drawing of one layer of the Keymap, and the 10 weakest characters and pairs.
// The server makes the chart (a Vega-Lite spec, which vega-embed draws), the drawings and
// the lists; this module only shows them.

// vega-embed and the libraries it needs, from the CDN. They are loaded in this order when the
// page first opens, so the practice screen does not wait for them. vega-lite 6.4.1 is the
// version of Altair's schema.
const VEGA = ['vega@6.4.0/build/vega.min.js', 'vega-lite@6.4.1/build/vega-lite.min.js', 'vega-embed@7.3.0/build/vega-embed.min.js'];
let vegaLoading = null; // the promise of loading them
const loadVega = () => vegaLoading ??= VEGA.reduce((loaded, path) => loaded.then(() => new Promise(done => {
  document.head.append(Object.assign(document.createElement('script'),
    { src: `https://cdn.jsdelivr.net/npm/${path}`, onload: done, onerror: done }));
})), Promise.resolve());

let keymaps = []; // every Board × Letter layout, as { board, letter_layout, version }
let at = 0; // the index in keymaps of the one shown
let page = null; // from the server: { weeks, days, trend, names, layers, chars, pairs, unlocking }; null while it loads
let layer = 0;
let pair = 0; // the index of the selected pair, drawn as an arc

const el = () => document.getElementById('progress');

// Opens the page on the Board with the Letter layout of the Session.
export async function openProgress(board, letterLayout) {
  el().innerHTML = '<p>Loading…</p>';
  const listed = await fetch('/api/boards').then(r => r.json());
  keymaps = listed.boards.flatMap(b => b.keymaps.map(k => ({ board: b.name, ...k })));
  at = keymaps.findIndex(k => k.board === board && k.letter_layout === letterLayout);
  await load();
}

async function load() {
  page = null;
  layer = 0;
  pair = 0;
  draw();
  const asked = at;
  const [found] = await Promise.all([fetch(`/api/keymaps/${keymaps[at].version}/progress`).then(r => r.json()), loadVega()]);
  if (asked !== at) return; // h or l was pressed again meanwhile
  page = found;
  draw();
}

// h and l show the previous and next Board × Letter layout. A number shows that layer, and
// j and k select a pair. Esc (handled by practice.js) goes back to the menu.
export function progressKey(e) {
  if ((e.key === 'h' || e.key === 'l') && keymaps.length > 1) {
    at = (at + (e.key === 'l' ? 1 : keymaps.length - 1)) % keymaps.length;
    return load();
  }
  if (!page) return;
  if (/^[1-9]$/.test(e.key) && Number(e.key) <= page.layers.length) {
    layer = Number(e.key) - 1;
    drawKeymap();
  } else if (e.key === 'j' || e.key === 'k') {
    pair = Math.min(Math.max(pair + (e.key === 'j' ? 1 : -1), 0), Math.max(page.pairs.length - 1, 0));
    drawKeymap();
  }
}

// Draws the whole page. The chart is drawn only here, so it is not drawn again for each key.
function draw() {
  const k = keymaps[at];
  const count = keymaps.length > 1 ? ` (${at + 1} of ${keymaps.length})` : '';
  const hint = '<kbd>h</kbd>/<kbd>l</kbd> Board · Letter layout, a number picks the layer, '
    + '<kbd>j</kbd>/<kbd>k</kbd> select a pair, <kbd>Esc</kbd> goes back.';
  const u = page?.unlocking;
  const unlock = u ? `<p class="hint">${u.unlocked} of ${u.total} keys unlocked.`
    + (u.next ? ` Locked keys are dashed and faint; the ringed key, ${esc(showChars(u.next))}, unlocks next.` : '') + '</p>' : '';
  const body = page ? `${unlock}<div id="trend"></div><div id="weakness"></div>` : '<p>Loading…</p>';
  el().innerHTML = `<h4>Progress · ${esc(k.board)} · ${esc(k.letter_layout)}${count}</h4>${body}<div class="hint">${hint}</div>`;
  if (!page) return;
  const trend = document.getElementById('trend');
  if (!page.days) {
    trend.innerHTML = `<p class="hint">No finished Attempts in the last ${page.weeks} weeks.</p>`;
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

// The layer tabs, the heat drawing of the layer with the selected pair's arc, and the lists.
function drawKeymap() {
  const tabs = page.names.map((n, i) => `<span class="${i === layer ? 'on' : ''}"><kbd>${i + 1}</kbd> ${esc(n)}</span>`).join('');
  document.getElementById('weakness').innerHTML = `<div class="tabs">${tabs}</div><div class="split">`
    + `<div class="heat">${page.layers[layer]}</div>`
    + table('Weakest characters', page.chars, -1) + table('Weakest pairs', page.pairs, pair) + '</div>';
  const unit = page.pairs[pair]?.unit;
  [...el().querySelectorAll('.arc')].find(a => a.dataset.pair === unit)?.classList.add('on');
}
