from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass

# Each side of a stored exchange is clipped to this many characters. History
# carries referential context — pronouns, terminology, topic — and a clipped
# long message still carries it, while an unclipped one would dominate the
# request it is meant to inform.
MAX_ENTRY_CHARS = 300

# Total characters of context sent with a translation, oldest dropped first.
# A clipped exchange is at most 2 * MAX_ENTRY_CHARS, so the newest one always
# fits and history is never emptied by this budget alone.
MAX_TOTAL_CHARS = 2000

# Distinct (user, target language) buckets kept before the least recently used
# is evicted. Exchanges are never expired by age — the staleness rule needs
# them to survive a week — so this is what bounds memory on a long-running
# process.
MAX_USERS = 5000

# How long a translation offered inline stays claimable.
PENDING_TTL_SECONDS = 300

# Inline results awaiting a tap. Most are never tapped, so this is sized for
# in-flight queries rather than for history.
MAX_PENDING = 200


@dataclass(frozen=True)
class Exchange:
    """One translation the user actually sent."""

    source: str
    translation: str
    at: float


@dataclass(frozen=True)
class PendingTranslation:
    """A translation offered inline, not yet known to have been sent."""

    user_id: int
    target_lang: str
    source: str
    translation: str
    at: float


def _clip(text: str) -> str:
    if len(text) <= MAX_ENTRY_CHARS:
        return text
    return text[: MAX_ENTRY_CHARS - 1].rstrip() + "…"


def _within_budget(exchanges: list[Exchange]) -> list[Exchange]:
    """The newest exchanges that fit MAX_TOTAL_CHARS, oldest dropped first."""
    kept: list[Exchange] = []
    total = 0
    for exchange in reversed(exchanges):
        total += len(exchange.source) + len(exchange.translation)
        if total > MAX_TOTAL_CHARS:
            break
        kept.append(exchange)
    kept.reverse()
    return kept


class HistoryStore:
    """Recent translation exchanges per user, held in memory only.

    Keyed by (user_id, target language) so exchanges from one target language
    are never offered as context for another — which also gives the ``xx:``
    inline override its own bucket.
    """

    def __init__(
        self,
        max_exchanges: int = 10,
        stale_after_seconds: float = 7 * 24 * 60 * 60,
        stale_exchanges: int = 3,
    ) -> None:
        self._max_exchanges = max_exchanges
        self._stale_after = stale_after_seconds
        self._stale_exchanges = stale_exchanges
        self._entries: OrderedDict[tuple[int, str], list[Exchange]] = OrderedDict()

    def record(
        self, user_id: int, target_lang: str, source: str, translation: str
    ) -> None:
        key = (user_id, target_lang)
        exchanges = self._entries.setdefault(key, [])
        exchanges.append(Exchange(_clip(source), _clip(translation), time.time()))
        if len(exchanges) > self._max_exchanges:
            del exchanges[: len(exchanges) - self._max_exchanges]
        self._entries.move_to_end(key)
        while len(self._entries) > MAX_USERS:
            self._entries.popitem(last=False)

    def get(self, user_id: int, target_lang: str) -> list[Exchange]:
        """This user's recent exchanges for ``target_lang``, oldest first."""
        key = (user_id, target_lang)
        exchanges = self._entries.get(key)
        if not exchanges:
            return []
        self._entries.move_to_end(key)

        # A long silence usually means an unrelated conversation, so only a
        # little context carries across the gap.
        if time.time() - exchanges[-1].at > self._stale_after:
            if self._stale_exchanges <= 0:
                return []
            exchanges = exchanges[-self._stale_exchanges :]

        return _within_budget(list(exchanges))


class PendingResults:
    """Translations offered inline, awaiting confirmation that one was sent.

    The bot answers an inline query long before it learns whether the user
    tapped the result, so each translation is parked under its result id and
    only promoted into history once a chosen_inline_result update arrives.
    """

    def __init__(
        self,
        ttl_seconds: float = PENDING_TTL_SECONDS,
        max_entries: int = MAX_PENDING,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._pending: OrderedDict[str, PendingTranslation] = OrderedDict()

    def park(
        self,
        result_id: str,
        user_id: int,
        target_lang: str,
        source: str,
        translation: str,
    ) -> None:
        self._prune()
        self._pending[result_id] = PendingTranslation(
            user_id, target_lang, source, translation, time.time()
        )
        self._pending.move_to_end(result_id)
        while len(self._pending) > self._max_entries:
            self._pending.popitem(last=False)

    def claim(self, result_id: str) -> PendingTranslation | None:
        """Take the translation for ``result_id``, or None if never parked."""
        self._prune()
        return self._pending.pop(result_id, None)

    def _prune(self) -> None:
        # Entries are appended in time order, so expiry walks from the front.
        cutoff = time.time() - self._ttl
        while self._pending:
            result_id, pending = next(iter(self._pending.items()))
            if pending.at >= cutoff:
                break
            del self._pending[result_id]
