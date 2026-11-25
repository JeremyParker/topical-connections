"""The word graph, held in memory and indexed both ways."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

GROUPS = 4
GROUP_SIZE = 4


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    difficulty: int
    is_topical: bool


@dataclass(frozen=True)
class Link:
    id: int
    word_id: int
    category_id: int
    difficulty_override: int | None = None


@dataclass
class Graph:
    words: dict[int, str]
    categories: dict[int, Category]
    links: list[Link]
    by_category: dict[int, list[Link]] = field(init=False)
    categories_of: dict[int, set[int]] = field(init=False)
    # For each category, how many words it shares with each other category
    shared: dict[int, Counter[int]] = field(init=False)

    def __post_init__(self):
        self.by_category = {c: [] for c in self.categories}
        self.categories_of = {w: set() for w in self.words}
        for link in self.links:
            self.by_category[link.category_id].append(link)
            self.categories_of[link.word_id].add(link.category_id)
        self.shared = defaultdict(Counter)
        for categories in self.categories_of.values():
            for a in categories:
                for b in categories:
                    if a != b:
                        self.shared[a][b] += 1

    def difficulty(self, link: Link) -> int:
        if link.difficulty_override is not None:
            return link.difficulty_override
        return self.categories[link.category_id].difficulty

    def usable(self) -> list[int]:
        return [c for c, links in self.by_category.items() if len(links) >= GROUP_SIZE]
