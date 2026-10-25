# Lists and Recursion in Python

A list holds an ordered sequence of values. Recursion is when a function calls itself on a smaller piece of its input. The two fit together well: many list problems break down into "handle the first item, then solve the rest."

## Basic list operations

Lists are mutable, so you can change them in place. Slicing creates a new list and leaves the original unchanged.

```python
numbers = [4, 8, 15, 16, 23, 42]

print(numbers[0])       # first item: 4
print(numbers[-1])      # last item: 42
print(numbers[1:4])     # slice: [8, 15, 16]
print(numbers[1:])      # everything after the first: [8, 15, 16, 23, 42]

numbers.append(7)       # add to the end
numbers[0] = 5          # replace an item in place
print(numbers)          # [5, 8, 15, 16, 23, 42, 7]
print(len(numbers))     # 7
```

The expression `numbers[1:]` is the key tool for recursion. It gives you "the rest of the list" as a new list.

## The base case and the recursive case

Every recursive function needs two parts:

1. **Base case:** a simple input the function answers directly, without calling itself.
2. **Recursive case:** a step that handles part of the input and calls the function on a smaller input.

If you leave out the base case, the function calls itself forever and Python raises `RecursionError`.

Here is a sum computed recursively:

```python
def total(values):
    if not values:              # base case: empty list sums to 0
        return 0
    return values[0] + total(values[1:])   # first item plus the sum of the rest

print(total([1, 2, 3, 4]))     # 10
```

Trace it: `total([1,2,3,4])` returns `1 + total([2,3,4])`, which returns `2 + total([3,4])`, and so on until `total([])` returns `0`. Then the results add back up.

## Searching a list recursively

Recursion can also decide whether something is present. This version checks the first item, then searches the rest.

```python
def contains(values, target):
    if not values:              # base case: nothing left to search
        return False
    if values[0] == target:     # found it
        return True
    return contains(values[1:], target)   # search the remainder

words = ["apple", "banana", "cherry"]
print(contains(words, "banana"))  # True
print(contains(words, "grape"))   # False
```

This works, but slicing copies the list on every call, so it costs time proportional to the square of the list length. For real work, a loop or the `in` operator is faster. Recursion is most useful when the structure of the problem is itself recursive.

## Recursion on nested lists

Lists can contain other lists. Recursion handles arbitrary depth without you knowing the depth in advance. A flattening function shows this well:

```python
def flatten(items):
    result = []
    for item in items:
        if isinstance(item, list):
            result.extend(flatten(item))   # recurse into nested list
        else:
            result.append(item)            # plain value: keep it
    return result

nested = [1, [2, 3, [4, 5]], 6, [[7], 8]]
print(flatten(nested))   # [1, 2, 3, 4, 5, 6, 7, 8]
```

Here the base case is implicit: a plain value is appended directly and no call is made. Each nested list makes one smaller call.

## Recursion with two lists: merge sort

Merge sort is a classic recursive algorithm. It splits a list in half, sorts each half recursively, then merges the sorted halves.

```python
def merge(left, right):
    merged = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1
    merged.extend(left[i:])     # one side may have leftovers
    merged.extend(right[j:])
    return merged

def merge_sort(values):
    if len(values) <= 1:        # base case: 0 or 1 items are already sorted
        return values
    mid = len(values) // 2
    left = merge_sort(values[:mid])
    right = merge_sort(values[mid:])
    return merge(left, right)

data = [38, 27, 43, 3, 9, 82, 10]
print(merge_sort(data))    # [3, 9, 10, 27, 38, 43, 82]
print(data)                # original list is unchanged
```

Each call halves the input, so the recursion depth is about log2(n). That is why merge sort is efficient even on large lists.

## Practice

Try writing these yourself before looking at a solution:

- A recursive `count_items(values)` that returns the length of a list without using `len`.
- A recursive `reverse(values)` that returns a new reversed list.
- A recursive `max_value(values)` that finds the largest number in a non-empty list.

## Key points

- Slice with `values[1:]` to get "the rest" for recursive calls.
- Always write a base case that stops the recursion.
- Recursion depth is limited in Python, so prefer loops for very long lists.
- Recursive functions shine on nested data and divide-and-conquer problems like merge sort.