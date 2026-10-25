// Returns what has been typed in the Attempt after one more key. In "keep typing" mode
// a wrong character goes in like a right one; in "locked until fixed" mode it does not
// go in. Only Backspace removes characters.
export function applyKey(passage, typed, e, mode) {
  if (e.ctrlKey || e.metaKey) return typed;
  if (e.key === 'Backspace') return typed.slice(0, -1);
  if (mode === 'locked until fixed' && e.key !== passage[typed.length]) return typed;
  if (e.key.length === 1 && typed.length < passage.length) return typed + e.key;
  return typed;
}
