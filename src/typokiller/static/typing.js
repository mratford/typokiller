// Text for innerHTML, with &, < and > escaped.
export const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
// Typed characters as the page shows them outside the Passage text: a space as ␣, a newline as ↵.
export const showChars = text => text.replaceAll(' ', '␣').replaceAll('\n', '↵');

// The HTML of the text of a Passage after `typed` has been typed (null for a preview, which has no
// cursor or typing). Each character is a span: ok, bad (it shows the wrong key) or cur. A space is
// shown as ␣ and a newline as ↵ in a span with class mark, followed by the line break. A space
// is followed by <wbr>, because ␣ is not a space and the browser would not wrap the line there.
export function textHTML(text, typed = null) {
  let h = '';
  for (let j = 0; j < text.length; j++) {
    const white = text[j] === ' ' || text[j] === '\n';
    let cls = white ? 'mark' : '', shown = showChars(text[j]);
    if (j === typed?.length) cls += ' cur';
    else if (j < typed?.length && typed[j] === text[j]) cls += ' ok';
    else if (j < typed?.length) { cls = 'bad'; shown = showChars(typed[j]); }
    h += `<span class="${cls.trim()}">${esc(shown)}</span>${text[j] === '\n' ? '\n' : white ? '<wbr>' : ''}`;
  }
  return h;
}

// The message for a request that failed, such as "Could not clone <url>: 405 Method Not Allowed".
// `answer` is the server's answer, or null when there was none. The server's `detail` is used
// when it is text: a 422 answer has a list there, and an error page from a proxy is not JSON.
export async function requestError(failed, answer) {
  if (!answer) return `${failed}: the server did not answer.`;
  const detail = (await answer.json().catch(() => null))?.detail;
  return `${failed}: ${typeof detail === 'string' ? detail : `${answer.status} ${answer.statusText}`}`;
}

// The spaces at the start of the line that begins at position i of the Passage.
const indentAt = (passage, i) => passage.slice(i).match(/^ */)[0];

// Returns what has been typed in the Attempt after one more key. In "keep typing" mode
// a wrong character goes in like a right one; in "locked until fixed" mode it does not
// go in. A repeat of a held key changes nothing. Only Backspace removes characters. Enter
// goes in only where the Passage has a newline, and the next line's indentation is then
// filled in without typing it.
// `apply_key` in analysis.py replays these rules on the stored key events, so the
// two must change together.
export function applyKey(passage, typed, e, mode) {
  if (e.ctrlKey || e.metaKey || e.repeat) return typed;
  if (e.key === 'Backspace') {
    // Backspace after filled-in indentation removes it together with the newline.
    const newline = typed.lastIndexOf('\n');
    if (newline >= 0 && typed.slice(newline + 1) === indentAt(passage, newline + 1)) return typed.slice(0, newline);
    return typed.slice(0, -1);
  }
  if (e.key === 'Enter') {
    return passage[typed.length] === '\n' ? typed + '\n' + indentAt(passage, typed.length + 1) : typed;
  }
  if (mode === 'locked until fixed' && e.key !== passage[typed.length]) return typed;
  if (e.key.length === 1 && typed.length < passage.length) return typed + e.key;
  return typed;
}

// The labels of a list of `count` items, made from `letters`. `keys` are the keys that the list
// already uses, such as j and k: they are never labels. No label
// is the start of another, so an item is chosen as soon as its label is typed. The first items get
// one-letter labels, and each of the other letters starts two-letter labels. With n letters, a list
// of more than n × n items has no labels after the first n × n.
export function listLabels(count, letters, keys) {
  const free = [...letters].filter(l => !keys.includes(l));
  const n = free.length;
  // The most one-letter labels that leave enough two-letter labels: single + (n - single) × n >= count.
  // When count <= n, this is n or more, so every label is one letter.
  const single = Math.max(0, Math.floor((n * n - count) / (n - 1)));
  return [...free.slice(0, single), ...free.slice(single).flatMap(a => free.map(b => a + b))].slice(0, count);
}
