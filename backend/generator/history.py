"""How recently each meaning was served, and how much that counts against it."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

LINK_MIN_GAP = 30  # days before the same word and meaning can be used again
LINK_HALF_LIFE = 90  # days for the penalty after that to halve
CATEGORY_HALF_LIFE = 14


@dataclass(frozen=True)
class Use:
    word_id: int
    category_id: int
    served: date | None  # None: approved, but not scheduled yet


class History:
    """Usage as seen from the date a new game would be served.

    Meanings are tracked by word and category, so a word can be reused at any
    time with a different category. Scheduled games in the future count too, and
    unscheduled ones count as if they'd be served the same day.
    """

    def __init__(self, uses: Iterable[Use], on: date):
        self._link_gap: dict[tuple[int, int], int] = defaultdict(lambda: 10**6)
        self._category_gap: dict[int, int] = defaultdict(lambda: 10**6)
        for use in uses:
            gap = 0 if use.served is None else abs((on - use.served).days)
            key = (use.word_id, use.category_id)
            self._link_gap[key] = min(self._link_gap[key], gap)
            self._category_gap[use.category_id] = min(self._category_gap[use.category_id], gap)

    def is_blocked(self, word_id: int, category_id: int) -> bool:
        return self._link_gap[word_id, category_id] < LINK_MIN_GAP

    def link_penalty(self, word_id: int, category_id: int) -> float:
        """From 0 (fresh) to 1 (just used)."""
        gap = self._link_gap[word_id, category_id]
        return 0.5 ** (max(0, gap - LINK_MIN_GAP) / LINK_HALF_LIFE)

    def category_penalty(self, category_id: int) -> float:
        return 0.5 ** (self._category_gap[category_id] / CATEGORY_HALF_LIFE)
