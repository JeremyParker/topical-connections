"""Finds every way to solve a board, to make sure there's only one."""

from collections import defaultdict
from collections.abc import Iterable
from itertools import combinations

from .graph import GROUP_SIZE, Graph

Solution = frozenset[frozenset[int]]


def solutions(graph: Graph, word_ids: Iterable[int], limit: int = 2) -> set[Solution]:
    """Ways to split the words into groups, each from a different category.

    Stops after finding `limit`. Two solutions that differ only in what their
    groups are called count as one.
    """
    words = sorted(word_ids)
    members = defaultdict(list)
    for word in words:
        for category in graph.categories_of[word]:
            members[category].append(word)

    # Every possible group, filed under its lowest word
    groups: dict[int, list[tuple[frozenset[int], int]]] = defaultdict(list)
    for category, its_words in members.items():
        for combo in combinations(its_words, GROUP_SIZE):
            groups[combo[0]].append((frozenset(combo), category))

    found: set[Solution] = set()

    def search(remaining: frozenset[int], chosen: list[frozenset[int]], used: set[int]) -> None:
        if not remaining:
            found.add(frozenset(chosen))
            return
        # The lowest remaining word must be the lowest of whichever group it's in
        for group, category in groups[min(remaining)]:
            if len(found) >= limit:
                return
            if category not in used and group <= remaining:
                search(remaining - group, [*chosen, group], used | {category})

    search(frozenset(words), [], set())
    return found
