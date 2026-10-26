// The spaces at the start of the line that begins at position i of the Passage.
const indentAt = (passage, i) => passage.slice(i).match(/^ */)[0];

// Returns what has been typed in the Attempt after one more key. In "keep typing" mode
// a wrong character goes in like a right one; in "locked until fixed" mode it does not
// go in. Only Backspace removes characters. Enter goes in only where the Passage has a
// newline, and the next line's indentation is then filled in without typing it.
export function applyKey(passage, typed, e, mode) {
  if (e.ctrlKey || e.metaKey) return typed;
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
