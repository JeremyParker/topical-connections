"""Samples random games from the graph and keeps the best."""

import random
import time
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from .graph import GROUP_SIZE, GROUPS, Category, Graph, Link
from .history import History
from .solver import solutions

WORD_TRIES = 8  # attempts at choosing words for each set of categories
POOL_PER_GAME = 20  # games to find for each one wanted, to have a choice


@dataclass(frozen=True)
class Group:
    category: Category
    links: tuple[Link, ...]
    difficulty: int


@dataclass(frozen=True)
class Game:
    groups: tuple[Group, ...]
    scores: dict[str, float]
    decoys: dict[int, list[int]]  # word -> the other groups' categories it fits
    red_herrings: dict[int, list[int]]  # category that isn't in the game -> words that fit it

    @property
    def score(self) -> float:
        return round(sum(self.scores.values()), 1)

    @property
    def word_ids(self) -> frozenset[int]:
        return frozenset(link.word_id for g in self.groups for link in g.links)


@dataclass(frozen=True)
class Result:
    games: list[Game]
    stats: dict[str, int]
    problem: str | None  # why there are no games, for contributors to act on


def generate(
    graph: Graph,
    history: History,
    count: int,
    *,
    rng: random.Random | None = None,
    avoid: Collection[frozenset[int]] = (),
    seconds: float = 3.0,
    max_attempts: int = 20_000,
) -> Result:
    """Returns up to `count` varied games, best first, never repeating the exact
    set of words of any in `avoid`."""
    rng = rng or random.Random()
    stats: Counter[str] = Counter()
    pools = available_links(graph, history)
    if problem := why_impossible(graph, pools):
        return Result([], dict(stats), problem)

    seen = set(avoid)
    pool: list[Game] = []
    deadline = time.monotonic() + seconds
    while (
        len(pool) < count * POOL_PER_GAME
        and stats["attempts"] < max_attempts
        and time.monotonic() < deadline
    ):
        stats["attempts"] += 1
        categories = pick_categories(graph, history, pools, rng)
        if categories is None:
            stats["no_matching_categories"] += 1
            continue
        for _ in range(WORD_TRIES):
            picked = pick_words(graph, history, pools, categories, rng)
            if picked is None:
                stats["not_enough_words"] += 1
                continue
            words = frozenset(link.word_id for links in picked.values() for link in links)
            if words in seen:
                stats["repeats"] += 1
                continue
            if len(solutions(graph, words)) != 1:
                stats["ambiguous"] += 1
                continue
            seen.add(words)
            pool.append(evaluate(graph, history, picked))
            break

    stats["valid_games"] = len(pool)
    problem = None
    if not pool:
        problem = "Every game tried was ambiguous, a repeat, or short of words. " + (
            "Try adding more words to categories, and more categories."
        )
    return Result(choose_varied(pool, count), dict(stats), problem)


def available_links(graph: Graph, history: History) -> dict[int, list[Link]]:
    """The links of each usable category that weren't served too recently."""
    pools = {}
    for category in graph.usable():
        links = [
            link
            for link in graph.by_category[category]
            if not history.is_blocked(link.word_id, category)
        ]
        if len(links) >= GROUP_SIZE:
            pools[category] = links
    return pools


def why_impossible(graph: Graph, pools: dict[int, list[Link]]) -> str | None:
    usable = len(graph.usable())
    if usable < GROUPS:
        return (
            f"Games need {GROUPS} categories with at least {GROUP_SIZE} words. There are {usable}."
        )
    if len(pools) < GROUPS:
        return "Too many words were served recently. Add more words, or wait."
    topical = sum(graph.categories[c].is_topical for c in pools)
    if topical == 0:
        return f"Games need a topical category with at least {GROUP_SIZE} available words."
    if topical == len(pools):
        return (
            f"Games need a category that isn't topical, with at least {GROUP_SIZE} available words."
        )
    return None


def pick_categories(
    graph: Graph, history: History, pools: dict[int, list[Link]], rng: random.Random
) -> list[int] | None:
    """Favors categories that share words, so that the groups overlap."""
    chosen: list[int] = []
    while len(chosen) < GROUPS:
        options = [c for c in pools if c not in chosen]
        kinds = {graph.categories[c].is_topical for c in chosen}
        if len(chosen) == GROUPS - 1 and len(kinds) == 1:
            # Every game mixes topical and non-topical
            options = [c for c in options if graph.categories[c].is_topical not in kinds]
        if not options:
            return None

        levels = {graph.categories[c].difficulty for c in chosen}
        weights = []
        for c in options:
            if chosen:
                overlap = sum(min(3, graph.shared[c][other]) for other in chosen)
            else:
                overlap = min(5, len(graph.shared[c]))
            weight = 0.3 + overlap
            if graph.categories[c].difficulty not in levels:
                weight *= 1.5
            weights.append(weight * (1.05 - history.category_penalty(c)))
        chosen.append(rng.choices(options, weights)[0])
    return chosen


def pick_words(
    graph: Graph,
    history: History,
    pools: dict[int, list[Link]],
    categories: list[int],
    rng: random.Random,
) -> dict[int, list[Link]] | None:
    """Favors words that also fit other categories, especially in this game."""
    picked: dict[int, list[Link]] = {}
    used: set[int] = set()
    # Categories with the least choice go first
    for category in sorted(categories, key=lambda c: len(pools[c])):
        options = [link for link in pools[category] if link.word_id not in used]
        if len(options) < GROUP_SIZE:
            return None
        picked[category] = []
        for _ in range(GROUP_SIZE):
            weights = []
            for link in options:
                others = graph.categories_of[link.word_id] - {category}
                in_game = len(others.intersection(categories))
                weight = 1 + 2 * in_game + 0.5 * min(3, len(others))
                weights.append(weight * (1.05 - history.link_penalty(link.word_id, category)))
            link = rng.choices(options, weights)[0]
            options.remove(link)
            used.add(link.word_id)
            picked[category].append(link)
    return picked


def evaluate(graph: Graph, history: History, picked: dict[int, list[Link]]) -> Game:
    """Scores a game out of 100."""
    groups = [
        Group(
            category=graph.categories[c],
            links=tuple(links),
            # A group is as hard as its hardest word
            difficulty=max(graph.difficulty(link) for link in links),
        )
        for c, links in picked.items()
    ]
    groups.sort(key=lambda g: (g.difficulty, g.category.difficulty, g.category.id))

    decoys: dict[int, list[int]] = {}
    fits: dict[int, list[int]] = {}
    for category, links in picked.items():
        for link in links:
            for other in sorted(graph.categories_of[link.word_id] - {category}):
                if other in picked:
                    decoys.setdefault(link.word_id, []).append(other)
                else:
                    fits.setdefault(other, []).append(link.word_id)
    # Three words that seem to belong together, but have no fourth group to form
    red_herrings = {c: words for c, words in fits.items() if len(words) >= GROUP_SIZE - 1}

    topical = sum(g.category.is_topical for g in groups)
    links = [link for links in picked.values() for link in links]
    staleness = (
        sum(history.link_penalty(link.word_id, link.category_id) for link in links) / len(links)
        + sum(history.category_penalty(c) for c in picked) / len(picked)
    ) / 2
    scores = {
        "decoys": 6.0 * min(5, len(decoys)),
        "red_herrings": 10.0 * min(2, len(red_herrings)),
        "difficulty": 5.0 * len({g.difficulty for g in groups}),
        "topical_mix": 15.0 if topical == GROUPS // 2 else 8.0,
        "freshness": round(15.0 * (1 - staleness), 1),
    }
    return Game(tuple(groups), scores, decoys, red_herrings)


def choose_varied(pool: list[Game], count: int) -> list[Game]:
    """Takes the best game, then repeatedly the best that isn't too like those taken."""
    remaining = sorted(pool, key=lambda g: g.score, reverse=True)
    most_alike = [0] * len(remaining)
    chosen: list[Game] = []
    while remaining and len(chosen) < count:
        best = max(range(len(remaining)), key=lambda i: remaining[i].score - 4 * most_alike[i])
        game = remaining.pop(best)
        most_alike.pop(best)
        chosen.append(game)
        for i, other in enumerate(remaining):
            most_alike[i] = max(most_alike[i], len(game.word_ids & other.word_ids))
    return sorted(chosen, key=lambda g: g.score, reverse=True)


def to_json(graph: Graph, game: Game) -> dict[str, Any]:
    """A self-contained copy of the game, unaffected by later edits."""
    return {
        "groups": [
            {
                "category_id": g.category.id,
                "name": g.category.name,
                "difficulty": g.difficulty,
                "is_topical": g.category.is_topical,
                "words": [
                    {"word_id": x.word_id, "link_id": x.id, "text": graph.words[x.word_id]}
                    for x in g.links
                ],
            }
            for g in game.groups
        ],
        "scores": game.scores,
        "decoys": [
            {
                "word": graph.words[word],
                "also_fits": [graph.categories[c].name for c in categories],
            }
            for word, categories in game.decoys.items()
        ],
        "red_herrings": [
            {"name": graph.categories[c].name, "words": [graph.words[w] for w in words]}
            for c, words in game.red_herrings.items()
        ],
    }
