# Lists and Recursion in Python

Lists and recursion fit together naturally. A list is either empty or it has a first item followed by a smaller list. That shape is exactly what a recursive function wants: handle the simple case directly, and hand the rest of the work to a smaller version of the same problem.

In this lesson you will practice slicing, building new lists, and writing recursive functions that walk through them.

## The Two Parts of Every Recursive Function

Every recursive function needs:

1. **A base case**: an input simple enough to answer immediately. For lists, this is usually the empty list.
2. **A recursive case**: a step that reduces the problem and calls the function again on something smaller.

If you forget the base case, the function calls itself until Python raises `RecursionError`. If the recursive call does not make the problem smaller, you get the same failure.

## Example 1: Summing a List

The simplest recursive list function adds up numbers. The sum of an empty list is 0. The sum of any other list is the first item plus the sum of the rest.

```python
def total(items):
    if not items:
        return 0
    first, *rest = items
    return first + total(rest)


def main():
    numbers = [4, 8, 15, 16, 23, 42]
    print("Numbers:", numbers)
    print("Total:", total(numbers))
    print("Empty total:", total([]))
    print("Matches sum():", total(numbers) == sum(numbers))


main()
```

The line `first, *rest = items` unpacks the list. The name `first` gets the first item, and `rest` gets a new list holding everything else. Each call works on a list one item shorter, so the recursion must eventually reach the empty list.

## Slicing as a Way to Shrink

Slicing is another way to get the smaller list. The expression `items[1:]` gives everything except the first item, and `items[:-1]` gives everything except the last. Slices always create new lists, so the original is never changed.

Recursion on slices is clear to read, but it copies the list at each step. For short lists this does not matter. For very long lists, a loop or an index-based approach is better.

## Example 2: Reversing and Checking Palindromes

Here are two functions that rely on slicing. The first reverses a list. The second checks whether a list reads the same in both directions by comparing the two ends and then examining the middle.

```python
def reverse(items):
    if len(items) <= 1:
        return items[:]
    return reverse(items[1:]) + [items[0]]


def is_palindrome(items):
    if len(items) <= 1:
        return True
    if items[0] != items[-1]:
        return False
    return is_palindrome(items[1:-1])


def main():
    data = [1, 2, 3, 4, 5]
    print("Original:", data)
    print("Reversed:", reverse(data))
    print("Unchanged:", data)

    candidates = [
        [1, 2, 3, 2, 1],
        list("racecar"),
        list("python"),
        [],
    ]
    for candidate in candidates:
        print(candidate, "->", is_palindrome(candidate))


main()
```

Notice that the base case uses `len(items) <= 1`. A palindrome check needs two base cases folded into one: an empty list and a single item are both trivially palindromes. In `reverse`, we return `items[:]`, a copy, so the caller always gets a fresh list.

## Building Lists Recursively

Many recursive functions do not just compute a single value. They build a new list. The pattern is the same: solve the small case, then combine the result of the smaller problem with the current item.

Two common building tools are:

- `[x] + other` to put an item at the front.
- `other + [x]` to put an item at the end.

You can also use the `+` operator to join the results of two recursive calls, which is the key idea behind many classic algorithms.

## Example 3: Flattening Nested Lists

Real data is often nested: lists inside lists, to any depth. A loop would need to know the depth in advance, but recursion handles any depth without extra effort.

```python
def flatten(nested):
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result


def depth(nested):
    if not isinstance(nested, list):
        return 0
    if not nested:
        return 1
    return 1 + max(depth(item) for item in nested)


def main():
    data = [1, [2, 3, [4, 5]], 6, [[7], 8], []]
    print("Nested:", data)
    print("Flat:", flatten(data))
    print("Depth:", depth(data))
    print("Depth of plain list:", depth([1, 2, 3]))


main()
```

Here the recursion happens inside a loop. For each item, we decide: is it a list (recurse) or a plain value (keep it)? The base case is implicit. A list with no nested lists simply never triggers a recursive call.

In `depth`, a non-list has depth 0, an empty list has depth 1, and any other list is one deeper than its deepest member.

## Divide and Conquer

Some recursive functions split a list into two halves rather than peeling off one item. This keeps the recursion shallow: a list of 1,000 items needs only about 10 levels of splitting instead of 1,000.

Merge sort is the classic example. Split the list in half, sort each half recursively, then merge the two sorted halves into one sorted list.

## Example 4: Merge Sort

```python
def merge(left, right):
    merged = []
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged


def merge_sort(items):
    if len(items) <= 1:
        return items[:]
    middle = len(items) // 2
    left = merge_sort(items[:middle])
    right = merge_sort(items[middle:])
    return merge(left, right)


def main():
    data = [38, 27, 43, 3, 9, 82, 10, 3]
    print("Before:", data)
    print("After: ", merge_sort(data))
    print("Same as sorted():", merge_sort(data) == sorted(data))

    words = ["pear", "apple", "fig", "banana", "cherry"]
    print(merge_sort(words))


main()
```

The `merge` helper is not recursive, but it is what makes the recursion useful. Each call to `merge_sort` trusts that its two smaller calls return sorted lists, and only has to combine them. This habit of trusting the recursive call is the most important mental skill in recursion.

## Generating Combinations of Lists

Recursion is also excellent at producing every possible arrangement of something. Generating all subsets of a list is a good example. For each item, there are two choices: leave it out or include it. The subsets of a list are the subsets of the rest, plus those same subsets with the first item added.

## Example 5: All Subsets and Permutations

```python
def subsets(items):
    if not items:
        return [[]]
    first = items[0]
    without_first = subsets(items[1:])
    with_first = [[first] + subset for subset in without_first]
    return without_first + with_first


def permutations(items):
    if len(items) <= 1:
        return [items[:]]
    result = []
    for index, item in enumerate(items):
        remaining = items[:index] + items[index + 1:]
        for perm in permutations(remaining):
            result.append([item] + perm)
    return result


def main():
    letters = ["a", "b", "c"]

    all_subsets = subsets(letters)
    print("Subsets of", letters, "- count:", len(all_subsets))
    for subset in all_subsets:
        print("  ", subset)

    all_perms = permutations(letters)
    print("Permutations of", letters, "- count:", len(all_perms))
    for perm in all_perms:
        print("  ", "".join(perm))


main()
```

A list of `n` items has `2**n` subsets and `n!` permutations, so these results grow quickly. Three letters give 8 subsets and 6 permutations, but twenty letters would give over a million subsets. Always be careful about input size when generating every possibility.

## Recursion Limits and Alternatives

Python limits recursion depth, by default to about 1,000 nested calls. A recursive sum over a list of 5,000 items would fail with `RecursionError`, even though the logic is correct. Python also does not optimize tail calls, so deep recursion is never free.

Keep these guidelines in mind:

- Use recursion when the data is naturally nested or the problem splits into smaller copies of itself.
- Use a loop or a built-in such as `sum`, `max`, or `sorted` when the task is flat and simple.
- Prefer divide and conquer when you can, because it keeps the depth small.
- Avoid changing a list while recursing over it. Build and return new lists instead.

## Practice Checklist

When you write your own recursive list function, ask yourself:

1. What is the smallest list, and what is its answer?
2. How do I make the list smaller on each call?
3. How do I combine the current item with the answer for the smaller list?
4. Can the input ever be deep or large enough to hit the recursion limit?

Once these four questions have clear answers, the code almost writes itself. Retype the examples above until the patterns feel familiar: base case first, shrink the problem, trust the recursive call, and combine the results.