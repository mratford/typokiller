// Returns what has been typed in the Attempt after one more key. A wrong character
// goes in like a right one; only Backspace removes characters.
export function applyKey(passage, typed, e) {
  if (e.ctrlKey || e.metaKey) return typed;
  if (e.key === 'Backspace') return typed.slice(0, -1);
  if (e.key.length === 1 && typed.length < passage.length) return typed + e.key;
  return typed;
}
