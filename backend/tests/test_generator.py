import random
import time
from datetime import date, timedelta
from itertools import combinations, permutations

import pytest

from generator.generate import generate, to_json
from generator.graph import Category, Graph, Link
from generator.history import LINK_MIN_GAP, History, Use
from generator.solver import solutions
from generator.suggest import suggest

TODAY = date(2027, 1, 1)
FRESH = History([], TODAY)


def make_graph(**categories):
    """make_graph(fish="bass sole") makes a topical category when its name starts
    with a capital. Difficulties cycle through 0-3."""
    words, cats, links = {}, {}, []
    for i, (name, members) in enumerate(categories.items(), 1):
        cats[i] = Category(i, name, i % 4, name[0].isupper())
        for text in members.split():
            word = next((w for w, t in words.items() if t == text), len(words) + 1)
            words[word] = text
            links.append(Link(len(links) + 1, word, i))
    return Graph(words, cats, links)


def ids(graph, text):
    by_text = {t: w for w, t in graph.words.items()}
    return [by_text[t] for t in text.split()]


def synthetic(rng, n_categories=20, n_words=100, per_category=8):
    words = {w: f"w{w}" for w in range(1, n_words + 1)}
    cats = {
        c: Category(c, f"c{c}", rng.randrange(4), c % 2 == 0) for c in range(1, n_categories + 1)
    }
    pairs = [(w, c) for c in cats for w in rng.sample(list(words), per_category)]
    return Graph(words, cats, [Link(i, w, c) for i, (w, c) in enumerate(pairs, 1)])


def brute_force(graph, words):
    """An independent, slow count of the ways to solve a board."""
    found = set()
    members = {c: [w for w in words if c in graph.categories_of[w]] for c in graph.categories}
    for cats in combinations([c for c in members if len(members[c]) >= 4], 4):
        a, b, c, d = cats
        for ga in combinations(members[a], 4):
            for gb in combinations(members[b], 4):
                if set(ga) & set(gb):
                    continue
                for gc in combinations(members[c], 4):
                    if set(gc) & (set(ga) | set(gb)):
                        continue
                    gd = set(words) - set(ga) - set(gb) - set(gc)
                    if gd <= set(members[d]):
                        found.add(frozenset(map(frozenset, (ga, gb, gc, gd))))
    return found


A, B, C, D = "a1 a2 a3 a4", "b1 b2 b3 b4", "c1 c2 c3 c4", "d1 d2 d3 d4"
BOARD = f"{A} {B} {C} {D}"


def test_solver_one_solution():
    graph = make_graph(a=A, b=B, c=C, d=D)
    assert len(solutions(graph, ids(graph, BOARD))) == 1


def test_solver_decoy_is_still_one_solution():
    graph = make_graph(a=f"{A} b1", b=B, c=C, d=D)
    assert len(solutions(graph, ids(graph, BOARD))) == 1


def test_solver_finds_a_swap():
    graph = make_graph(a=f"{A} b1", b=f"{B} a1", c=C, d=D)
    assert len(solutions(graph, ids(graph, BOARD))) == 2


def test_solver_finds_a_three_way_swap():
    graph = make_graph(a=f"{A} b1", b=f"{B} c1", c=f"{C} a1", d=D)
    assert len(solutions(graph, ids(graph, BOARD))) == 2


def test_solver_considers_categories_outside_the_game():
    graph = make_graph(a=A, b=B, c=C, d=D, x="a1 a2 b1 b2", y="a3 a4 b3 b4")
    assert len(solutions(graph, ids(graph, BOARD))) == 2


def test_solver_uses_each_category_once():
    # All of a and b fit x, but it can only be one of the groups
    graph = make_graph(a=A, b=B, c=C, d=D, x=f"{A} {B}")
    assert len(solutions(graph, ids(graph, BOARD))) == 1


def test_solver_synonym_categories_are_one_solution():
    graph = make_graph(a=A, a_again=A, b=B, c=C, d=D)
    assert len(solutions(graph, ids(graph, BOARD))) == 1


def test_solver_no_solution():
    graph = make_graph(a=A, b=B, c=C, d="d1 d2 d3")
    assert solutions(graph, ids(graph, f"{A} {B} {C} d1 d2 d3 a1")[:15]) == set()


@pytest.mark.parametrize("seed", range(25))
def test_solver_agrees_with_brute_force(seed):
    rng = random.Random(seed)
    graph = make_graph(a=A, b=B, c=C, d=D)
    links = list(graph.links)
    cats = dict(graph.categories) | {5: Category(5, "x", 0, True), 6: Category(6, "y", 0, True)}
    for word in graph.words:
        for c in cats:
            if c not in graph.categories_of[word] and rng.random() < 0.15:
                links.append(Link(len(links) + 1, word, c))
    graph = Graph(graph.words, cats, links)
    expected = brute_force(graph, list(graph.words))
    assert solutions(graph, graph.words, limit=10**6) == expected


@pytest.mark.parametrize("seed", range(10))
def test_generated_games_are_valid(seed):
    rng = random.Random(seed)
    graph = synthetic(rng)
    result = generate(graph, FRESH, 10, rng=rng)
    assert len(result.games) == 10
    assert len({g.word_ids for g in result.games}) == 10
    for game in result.games:
        assert len(game.word_ids) == 16
        assert len({g.category.id for g in game.groups}) == 4
        assert {g.category.is_topical for g in game.groups} == {True, False}
        for group in game.groups:
            assert len(group.links) == 4
            assert all(x.category_id == group.category.id for x in group.links)
        intended = frozenset(frozenset(x.word_id for x in g.links) for g in game.groups)
        assert solutions(graph, game.word_ids, limit=10) == {intended}
        assert 0 <= game.score <= 100
        for word, others in game.decoys.items():
            assert graph.categories_of[word].issuperset(others)
    assert [g.score for g in result.games] == sorted((g.score for g in result.games), reverse=True)


def test_same_seed_gives_same_games():
    graph = synthetic(random.Random(1))
    runs = [generate(graph, FRESH, 5, rng=random.Random(9), seconds=60) for _ in range(2)]
    assert runs[0].games == runs[1].games


def test_prefers_overlap():
    # Compared with boards whose words were chosen without regard to overlap
    graph = synthetic(random.Random(3), n_words=70)
    best = generate(graph, FRESH, 10, rng=random.Random(1)).games
    assert min(len(g.decoys) for g in best) >= 3


def test_ambiguous_only_graph_gives_no_games():
    graph = make_graph(A1=f"{A} b1", b=f"{B} a1", c=C, d=D)
    result = generate(graph, FRESH, 5, seconds=0.5, max_attempts=200)
    assert result.games == [] and "ambiguous" in result.problem
    assert result.stats["ambiguous"] > 0


def test_avoids_known_games():
    graph = make_graph(A1=A, b=B, c=C, d=D)
    first = generate(graph, FRESH, 5, seconds=0.5, max_attempts=200)
    assert len(first.games) == 1
    again = generate(
        graph, FRESH, 5, avoid={first.games[0].word_ids}, seconds=0.5, max_attempts=200
    )
    assert again.games == []


@pytest.mark.parametrize(
    "categories,message",
    [
        ({}, "There are 0"),
        ({"A1": A, "b": B, "c": C, "d": "d1 d2 d3"}, "There are 3"),
        ({"a": A, "b": B, "c": C, "d": D}, "need a topical"),
        ({"A1": A, "B1": B, "C1": C, "D1": D}, "isn't topical"),
    ],
)
def test_explains_impossible_graphs(categories, message):
    assert message in generate(make_graph(**categories), FRESH, 1).problem


def test_history_blocks_only_the_same_meaning():
    history = History([Use(1, 10, TODAY - timedelta(days=1))], TODAY)
    assert history.is_blocked(1, 10)
    assert not history.is_blocked(1, 11)
    assert history.link_penalty(1, 11) < 0.001


def test_history_fades():
    def penalties(days):
        history = History([Use(1, 10, TODAY - timedelta(days=days))], TODAY)
        return history.link_penalty(1, 10), history.category_penalty(10)

    ages = [penalties(d) for d in (0, 40, 120, 1000)]
    for older, newer in zip(ages[1:], ages, strict=False):
        assert older[0] < newer[0] and older[1] < newer[1]
    assert ages[0] == (1, 1) and ages[-1][0] < 0.01
    used = History([Use(1, 10, TODAY - timedelta(days=LINK_MIN_GAP))], TODAY)
    assert not used.is_blocked(1, 10)


def test_history_counts_scheduled_and_unscheduled_games():
    assert History([Use(1, 10, TODAY + timedelta(days=5))], TODAY).is_blocked(1, 10)
    assert History([Use(1, 10, None)], TODAY).is_blocked(1, 10)
    old_and_new = [Use(1, 10, TODAY - timedelta(days=900)), Use(1, 10, TODAY)]
    for uses in permutations(old_and_new):
        assert History(uses, TODAY).is_blocked(1, 10)


def test_generated_games_respect_history():
    graph = synthetic(random.Random(5))
    blocked = {(x.word_id, x.category_id) for x in graph.links if x.id % 4 == 0}
    history = History([Use(w, c, TODAY - timedelta(days=3)) for w, c in blocked], TODAY)
    games = generate(graph, history, 10, rng=random.Random(1)).games
    assert games
    for game in games:
        for group in game.groups:
            assert not blocked & {(x.word_id, x.category_id) for x in group.links}


def test_decoys_and_red_herrings():
    graph = make_graph(A1=f"{A} b1", b=B, c=C, d=D, herring="a1 b2 c1", nothing="a2 b3")
    game = generate(graph, FRESH, 1, seconds=0.5, max_attempts=500).games[0]
    data = to_json(graph, game)
    if "b1" in [w["text"] for g in data["groups"] if g["name"] == "b" for w in g["words"]]:
        assert {"word": "b1", "also_fits": ["A1"]} in data["decoys"]
    assert [h["name"] for h in data["red_herrings"]] == ["herring"]
    assert sorted(data["red_herrings"][0]["words"]) == ["a1", "b2", "c1"]


def test_group_difficulty_is_its_hardest_word():
    graph = make_graph(A1=A, b=B, c=C, d=D)
    links = [Link(x.id, x.word_id, x.category_id, 3 if x.id == 1 else None) for x in graph.links]
    graph = Graph(graph.words, graph.categories, links)
    game = generate(graph, FRESH, 1, seconds=0.5, max_attempts=50).games[0]
    assert {g.category.name: g.difficulty for g in game.groups}["A1"] == 3


def test_large_graph_is_fast():
    graph = synthetic(random.Random(1), n_categories=600, n_words=3000, per_category=10)
    start = time.monotonic()
    result = generate(graph, FRESH, 20, rng=random.Random(1))
    assert len(result.games) == 20
    assert time.monotonic() - start < 6


def test_suggestions():
    graph = make_graph(a=f"{A} b1", b=B, lonely=C, far="z1 z2 z3", near="a1 b1 z4", tiny="q")
    names = {c.id: c.name for c in graph.categories.values()}
    found = suggest(graph)
    assert [names[c] for c in found.almost_usable] == ["near", "far"]
    assert [names[c] for c in found.isolated] == ["lonely"]
