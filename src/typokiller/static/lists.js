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
