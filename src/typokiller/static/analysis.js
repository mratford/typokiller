// The analysis page: one entry at a time, for a keyboard with a layout, or for the lessons with no
// keyboard on one layout. It shows the trend chart, the keyboard picture with heat for one layer,
// and the weakest characters and pairs. The server makes the chart (a Vega-Lite spec, which
// vega-embed draws), the pictures and the lists; this module only shows them.

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

let page; // from the server: { entries, entry, weeks, days, trend, names, layers, chars, pairs }, or { message }; null when the request failed
let view = { at: 0, layer: 0, pair: 0 };
let asked = 0; // the number of requests so far

// Reads the recordings again, and shows `entry`, or the first entry when it is undefined.
async function load(entry) {
  const mine = ++asked;
  const url = entry === undefined ? '/api/analysis' : `/api/analysis?entry=${encodeURIComponent(entry)}`;
  const [found] = await Promise.all([fetch(url).then(r => (r.ok ? r.json() : null), () => null), loadVega()]);
  if (mine !== asked) return; // h or l was pressed again meanwhile
  page = found;
  view = { at: page?.entries ? page.entries.indexOf(page.entry) : 0, layer: 0, pair: 0 };
  draw();
}

// Draws the whole page. The chart is drawn only here, so it is not drawn again for each key.
function draw() {
  const el = document.getElementById('analysis');
  if (!page) {
    el.innerHTML = '<p class="message">The recorded lessons could not be read. Run <code>typokiller-service logs</code> to see why.</p>';
    return;
  }
  if (page.message) {
    el.innerHTML = `<p class="message">${page.message}</p>`;
    for (const a of el.querySelectorAll('a.typing')) a.hostname = location.hostname;
    return;
  }
  const count = page.entries.length > 1 ? ` (${view.at + 1} of ${page.entries.length})` : '';
  const hint = '<kbd>h</kbd>/<kbd>l</kbd> keyboard and layout, a number picks the layer, '
    + '<kbd>j</kbd>/<kbd>k</kbd> select a pair.';
  el.innerHTML = `<h4>${esc(page.entry)}${count}</h4><div id="trend"></div><div id="weakness"></div><div class="hint">${hint}</div>`;
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
  const tabs = page.names.map((n, i) => `<span class="${i === view.layer ? 'on' : ''}"><kbd>${i + 1}</kbd> ${esc(n)}</span>`).join('');
  document.getElementById('weakness').innerHTML = `<div class="tabs">${tabs}</div><div class="split">`
    + `<div class="heat">${page.layers[view.layer] ?? ''}</div>`
    + table('Weakest characters', page.chars, -1) + table('Weakest pairs', page.pairs, view.pair) + '</div>';
  const unit = page.pairs[view.pair]?.unit;
  [...document.querySelectorAll('.arc')].find(a => a.dataset.pair === unit)?.classList.add('on');
}

// h and l read the recordings again, even with one entry.
function onKey(e) {
  if (!page?.entries || e.metaKey || e.ctrlKey || e.altKey) return;
  const next = pressed(e.key, view, { entries: page.entries.length, layers: page.layers.length, pairs: page.pairs.length });
  if (!next) return;
  view = next;
  if (e.key === 'h' || e.key === 'l') load(page.entries[view.at]);
  else drawKeymap();
}

if (globalThis.document) { // not in the tests
  addEventListener('keydown', onKey);
  load();
}
