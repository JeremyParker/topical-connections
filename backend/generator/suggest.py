"""Where a few more words would help the generator most."""

from dataclasses import dataclass

from .graph import GROUP_SIZE, Graph


@dataclass(frozen=True)
class Suggestions:
    almost_usable: list[int]  # categories one word short of being usable
    isolated: list[int]  # usable, but sharing no words with another usable category


def suggest(graph: Graph) -> Suggestions:
    usable = set(graph.usable())

    def by_connections(c: int) -> tuple[int, str]:
        return -len(usable & graph.shared[c].keys()), graph.categories[c].name.lower()

    return Suggestions(
        # Those that share words with usable categories first: they'd add most overlap
        almost_usable=sorted(
            (c for c, links in graph.by_category.items() if len(links) == GROUP_SIZE - 1),
            key=by_connections,
        ),
        isolated=sorted(
            (c for c in usable if not usable & graph.shared[c].keys()),
            key=by_connections,
        ),
    )
