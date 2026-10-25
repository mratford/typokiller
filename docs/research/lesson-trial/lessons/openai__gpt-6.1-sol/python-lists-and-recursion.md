# Working with Lists and Recursion in Python

Lists store ordered collections of values. Recursion solves a problem by calling the same function on a smaller version of that problem. Together, they provide a useful way to explore sequences, nested structures, sorting, and combinations.

A recursive function needs two things: a stopping rule and a step that moves toward that rule. Without a stopping rule, calls continue until Python raises `RecursionError`. Without progress, even a function with a stopping rule can keep calling itself forever.

This lesson uses four complete scripts. Each script runs independently, uses only standard Python features, and demonstrates a different relationship between lists and recursion.

## 1. Process a List One Position at a Time

A list supports indexing, iteration, slicing, and mutation. For example, `values[0]` reads its first item, while `values.append(10)` adds an item at the end.

A recursive list operation often separates the current item from the remaining work. To add a list of numbers, we can describe the result as the current number plus the sum of everything after it.

The empty remainder contributes zero. That gives us a natural base case.

```python
def recursive_sum(values):
    def visit(index):
        if index == len(values):
            return 0
        return values[index] + visit(index + 1)

    return visit(0)


def iterative_sum(values):
    total = 0
    for value in values:
        total += value
    return total


def main():
    numbers = [4, 7, -2, 9]
    original = numbers.copy()

    print("Numbers:", numbers)
    print("Recursive total:", recursive_sum(numbers))
    print("Iterative total:", iterative_sum(numbers))
    print("Empty total:", recursive_sum([]))

    assert recursive_sum(numbers) == sum(numbers)
    assert recursive_sum([]) == 0
    assert numbers == original


if __name__ == "__main__":
    main()
```

The inner function, `visit`, remembers `values` from its enclosing scope. Its argument is an index rather than a new list. Every call increases the index by one, so it eventually reaches the list's length.

For the four-item example, the calls reach indices zero through four. At index four, the function returns zero. The waiting calls then return their own results, working backward until the original call finishes.

This approach avoids repeatedly copying the remaining items. Writing a recursive call with `values[1:]` can look elegant, but each slice creates another list. Repeated slicing adds unnecessary copying and can turn a linear operation into quadratic work.

The index-based version takes linear time and uses linear call-stack space. The loop also takes linear time, but uses constant extra space. For ordinary addition, the built-in `sum` is usually the clearest choice. Recursion here teaches the structure of a solution rather than improving the practical implementation.

## 2. Flatten a Nested List

Recursion becomes more compelling when the data itself is recursive. A nested list can contain ordinary values and other lists, which can contain still more lists.

Flattening converts that structure into a single list of leaf values. The rule is simple: if an item is a list, explore it; otherwise, append it to the result.

```python
def flatten(values):
    result = []

    def visit(items):
        for item in items:
            if isinstance(item, list):
                visit(item)
            else:
                result.append(item)

    visit(values)
    return result


def main():
    nested = [1, [2, [], [3, 4]], 5, ["six", [7]]]
    flat = flatten(nested)

    print("Nested:", nested)
    print("Flat:", flat)

    assert flat == [1, 2, 3, 4, 5, "six", 7]
    assert flatten([]) == []
    assert flatten([[], [[]]]) == []

    flat.append(8)
    assert nested == [1, [2, [], [3, 4]], 5, ["six", [7]]]


if __name__ == "__main__":
    main()
```

Here, the stopping behavior is built into the loop. An empty list has no items to visit. A non-list item is appended without another recursive call.

The traversal preserves left-to-right order. It completely explores one nested list before continuing with the next item in the surrounding list.

Notice that strings remain whole. Although a string is iterable, the function only descends into actual lists. This avoids accidentally breaking `"six"` into separate characters.

The returned outer list is new, but its leaf values are not copied. If a leaf is a mutable object such as a dictionary, both structures still refer to that same object. Creating a new container does not automatically create independent copies of everything inside it.

This function assumes there are no cycles. Python allows a list to contain itself, directly or indirectly. Such a structure has no final nesting level, so this traversal would eventually raise `RecursionError`. Supporting cycles requires an explicit policy, usually involving object identities and a record of active containers.

## 3. Divide a List and Merge the Results

Another recursive pattern is divide and conquer. Instead of processing one item per call, split the problem into smaller parts, solve those parts, and combine their answers.

Merge sort follows this pattern. A list with fewer than two items is already sorted. For a larger list, sort its two halves and merge them into one ordered result.

```python
def merge_sort(values):
    if len(values) < 2:
        return values.copy()

    middle = len(values) // 2
    left = merge_sort(values[:middle])
    right = merge_sort(values[middle:])

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


def main():
    numbers = [8, 3, 5, 3, -1, 9, 0]
    ordered = merge_sort(numbers)

    print("Original:", numbers)
    print("Sorted:", ordered)

    assert ordered == sorted(numbers)
    assert numbers == [8, 3, 5, 3, -1, 9, 0]
    assert merge_sort([]) == []
    assert merge_sort([6]) == [6]


if __name__ == "__main__":
    main()
```

The merge step maintains two indices. Each comparison selects the smaller remaining front item. Once either half is exhausted, the remaining items from the other half can be added directly.

Using `<=` chooses the left item when two values compare equally. This preserves their relative order, making this merge sort stable.

Slicing is reasonable in this teaching implementation because the splits are balanced. The algorithm takes O(n log n) time, rather than repeatedly copying almost the entire list at each step. It uses O(n) peak auxiliary storage, and its recursive depth is O(log n).

The elements must support the comparisons used by the function. Mixing unrelated types, such as integers and strings, generally raises `TypeError`.

For everyday sorting, prefer `sorted(values)` for a new list or `values.sort()` to modify the existing list. Python's built-in sorting tools are optimized and support convenient options such as `key` and `reverse`.

## 4. Build Lists with Backtracking

Recursion can also explore choices. To generate every subset of a list, consider each item in turn. Each item has two possibilities: leave it out or include it.

Backtracking keeps one working list, temporarily changes it, explores a branch, and then restores its earlier state.

```python
def subsets(values):
    results = []
    path = []

    def visit(index):
        if index == len(values):
            results.append(path.copy())
            return

        visit(index + 1)

        path.append(values[index])
        visit(index + 1)
        path.pop()

    visit(0)
    return results


def main():
    items = ["red", "green", "blue"]
    choices = subsets(items)

    for choice in choices:
        print(choice)

    assert len(choices) == 8
    assert choices[0] == []
    assert choices[-1] == items
    assert subsets([]) == [[]]

    choices[0].append("extra")
    assert choices[1] == ["blue"]


if __name__ == "__main__":
    main()
```

The first recursive call explores exclusion. The second explores inclusion after appending the current item. Finally, `pop` undoes that append.

The copy at the base case is essential. Appending `path` itself would store repeated references to one mutable list. Later changes would affect every stored reference. Copying captures each completed selection in its own list.

For n input positions, there are 2 ** n subsets. Storing them requires O(n * 2 ** n) space overall, and copying the selections gives the same time bound. Keep inputs small. Repeated input values can also produce equal-looking subsets because the choices concern positions, not unique values.

## Choosing Recursion Deliberately

Use recursion when it makes the problem's structure clearer: nested data, balanced subdivisions, or branching choices. Prefer loops for straightforward scans of long, flat lists.

Python limits recursion depth and does not optimize away recursive calls. Raising that limit is not a general solution to deeply nested input. An explicit stack is often safer.

Before finishing a recursive function, check its base case, progress, mutation, and copying behavior. Then test empty lists, single items, repeated values, and nested empty structures. These small cases often expose mistakes before larger examples hide them.