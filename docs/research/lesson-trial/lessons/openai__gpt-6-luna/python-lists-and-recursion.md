# Working with Lists and Recursion

Lists are one of Python's most useful ways to keep a sequence of values. They can grow or shrink, and their elements can be changed after the list is created. Recursion is a way to solve a problem by having a function call itself on a smaller version of that problem. Lists and recursion work well together, especially when a list contains other lists.

## Create, read, and change lists

Write a list with square brackets, separating its items with commas. A list can contain values of different types, though keeping related values together usually makes a program easier to understand.

Python counts list positions from zero. The first item is at index `0`, the second at index `1`, and the last item is at index `len(items) - 1`. Negative indexes count from the end: `-1` means the last item. An index that does not exist raises `IndexError`.

A slice selects a range of items. The start index is included, but the stop index is not. Leaving out the start or stop selects through the beginning or end of the list. A slice makes a new list, so changing the slice does not change the original list.

```python
def main():
    colors = ["red", "green", "blue", "gold"]

    print(colors[0])
    print(colors[-1])
    print(colors[1:3])

    colors[1] = "lime"
    print(colors)


if __name__ == "__main__":
    main()
```

The assignment to `colors[1]` replaces an item in the existing list. Lists are mutable: their contents can change without creating a new list. Use `len(colors)` to find the number of items, and use `value in colors` to test whether a value occurs in the list.

## Add, remove, and process items

Use `append` to add one item at the end of a list. Use `extend` to add all the items from another iterable. These operations are different: `append` adds its argument as one item, while `extend` adds each item in its argument.

Use `insert(index, value)` to place an item at a particular position. Use `pop()` to remove and return the last item, or `pop(index)` to remove an item at a chosen position. Use `remove(value)` to remove the first matching value. If there is no matching value, `remove` raises `ValueError`.

```python
def main():
    scores = [12, 18, 15]

    scores.append(20)
    scores.extend([9, 14])
    scores.insert(1, 16)

    last_score = scores.pop()
    scores.remove(9)

    print(scores)
    print(last_score)
    print(sum(scores))
    print(max(scores))


if __name__ == "__main__":
    main()
```

A list method that changes a list usually returns `None`, rather than the changed list. For example, `scores.sort()` sorts `scores` in place. By contrast, `sorted(scores)` returns a new sorted list and leaves `scores` unchanged. This distinction matters: assigning the result of `scores.sort()` to a variable gives that variable the value `None`.

A loop is often the clearest way to process every item. A list comprehension is a compact way to make a new list from an existing one. In the next example, the comprehension keeps only the values that meet a condition and transforms each kept value.

```python
def main():
    temperatures = [12, 19, 7, 23, 16]
    warm_fahrenheit = [
        celsius * 9 / 5 + 32
        for celsius in temperatures
        if celsius >= 15
    ]

    print(warm_fahrenheit)


if __name__ == "__main__":
    main()
```

The `if` clause filters items; it does not change the original list. The expression before `for` determines what goes into the new list. Use a comprehension when the transformation is simple. For more complicated work, a named loop or function can be easier to read.

## Aliases and copies

A variable holds a reference to a list. If you assign that variable to another name, both names refer to the same list. Changing the list through either name is visible through the other.

A shallow copy makes a new outer list. You can make one with `items.copy()` or `items[:]`. After a shallow copy, adding or replacing an item in the copy does not change the original outer list. But if the items are themselves mutable objects, both lists still refer to those same inner objects.

```python
def main():
    original = [3, 6, 9]
    alias = original
    copy = original.copy()

    alias.append(12)
    copy[0] = 100

    print(original)
    print(alias)
    print(copy)


if __name__ == "__main__":
    main()
```

Here, `original` and `alias` show the same change because they refer to the same list. `copy` has its own outer list, so replacing its first item leaves `original` alone. Keep this behavior in mind when passing lists to functions: a function can change a list supplied by its caller. If the function should not change the caller's list, make a suitable copy or return a new list instead.

## Understand recursion

A recursive function calls itself. Each call works on a smaller part of the problem, until it reaches a base case that can be answered without another recursive call. Both pieces are essential. Without a base case, calls continue until Python raises `RecursionError`. Without progress toward the base case, the function never finishes.

Consider summing a list. The sum of an empty list is zero. For a non-empty list, its sum is the first item plus the sum of the remaining items. The function below uses an index to track which item to process next.

```python
def recursive_sum(values, index=0):
    if index == len(values):
        return 0
    return values[index] + recursive_sum(values, index + 1)


def main():
    values = [4, 7, 2, 9]
    print(recursive_sum(values))


if __name__ == "__main__":
    main()
```

When `index` reaches the list length, the base case returns `0`. On the way back out of the calls, each earlier call adds its item to the result. For this function, the index must start at zero and increase by one on every call. That steady progress ensures the base case is reached for a finite list.

This version uses an index instead of making a new slice at every call. A version that calls itself with `values[1:]` can be easy to describe, but each slice creates a new list. Repeated slicing can do extra work and use extra memory. Index-based recursion avoids that copying, although it still uses one function call per item.

## Recursion with nested lists

A nested list is a list that contains other lists. A recursive function can handle it by checking each item: if the item is a list, process its contents; otherwise, add it to the result. This matches the structure of the data.

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
    nested = [1, [2, 3], [], [4, [5, 6]]]
    print(flatten(nested))


if __name__ == "__main__":
    main()
```

The empty inner list needs no special case. Its loop has no items, so the call returns immediately. Each call to `visit` handles one list and, when needed, asks another call to handle a smaller nested list. The outer function returns a new flat list; it does not rearrange the nested input.

This example assumes that nested lists eventually contain values that are not lists. If a list contains itself, the recursion will not reach an end. It also assumes the nesting is not deeper than Python's recursion limit. Recursion is useful for naturally nested or divide-and-conquer problems, but it is not the best tool for every long sequence. For simple work over thousands of list items, a loop is usually safer: Python does not automatically turn recursive calls into a loop.

## Choose a clear approach

Before writing a recursive function, identify its base case and explain how each call makes progress toward it. Test the smallest cases first, such as an empty list, then a one-item list, then a larger example. For list operations, also decide whether the function should change the original list or return a new one.

Use ordinary loops for straightforward repetition and recursion when the data or problem is naturally defined in smaller parts of the same kind. In either case, make the behavior clear: know which list is being changed, which values are returned, and how the work ends.