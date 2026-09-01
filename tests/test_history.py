import time

from app.history import (
    MAX_ENTRY_CHARS,
    MAX_TOTAL_CHARS,
    MAX_USERS,
    HistoryStore,
    PendingResults,
)

WEEK = 7 * 24 * 60 * 60


def _age(store, user_id, target_lang, seconds):
    """Backdate a bucket's exchanges by ``seconds``, as if time had passed."""
    key = (user_id, target_lang)
    store._entries[key] = [
        type(exchange)(exchange.source, exchange.translation, exchange.at - seconds)
        for exchange in store._entries[key]
    ]


def test_unknown_user_has_no_history():
    assert HistoryStore().get(1, "French") == []


def test_records_in_chronological_order():
    store = HistoryStore()
    store.record(1, "French", "one", "un")
    store.record(1, "French", "two", "deux")
    assert [(e.source, e.translation) for e in store.get(1, "French")] == [
        ("one", "un"),
        ("two", "deux"),
    ]


def test_keeps_only_the_last_max_exchanges():
    store = HistoryStore(max_exchanges=10)
    for i in range(15):
        store.record(1, "French", f"source {i}", f"cible {i}")
    kept = store.get(1, "French")
    assert len(kept) == 10
    assert kept[0].source == "source 5"
    assert kept[-1].source == "source 14"


def test_target_languages_have_separate_history():
    store = HistoryStore()
    store.record(1, "French", "hello", "bonjour")
    store.record(1, "Spanish", "hello", "hola")
    assert [e.translation for e in store.get(1, "French")] == ["bonjour"]
    assert [e.translation for e in store.get(1, "Spanish")] == ["hola"]


def test_users_have_separate_history():
    store = HistoryStore()
    store.record(1, "French", "hello", "bonjour")
    assert store.get(2, "French") == []


def test_recent_gap_keeps_everything():
    store = HistoryStore(max_exchanges=10)
    for i in range(10):
        store.record(1, "French", f"source {i}", f"cible {i}")
    _age(store, 1, "French", WEEK - 60)
    assert len(store.get(1, "French")) == 10


def test_gap_over_a_week_keeps_only_three():
    store = HistoryStore(max_exchanges=10)
    for i in range(10):
        store.record(1, "French", f"source {i}", f"cible {i}")
    _age(store, 1, "French", WEEK + 60)
    kept = store.get(1, "French")
    assert [e.source for e in kept] == ["source 7", "source 8", "source 9"]


def test_stale_rule_does_not_discard_the_stored_exchanges():
    """A stale read is narrowed, not destructive — a new message restores it."""
    store = HistoryStore(max_exchanges=10)
    for i in range(10):
        store.record(1, "French", f"source {i}", f"cible {i}")
    _age(store, 1, "French", WEEK + 60)
    assert len(store.get(1, "French")) == 3
    store.record(1, "French", "fresh", "frais")
    assert len(store.get(1, "French")) == 10


def test_long_entries_are_clipped():
    store = HistoryStore()
    store.record(1, "French", "a" * 5000, "b" * 5000)
    exchange = store.get(1, "French")[0]
    assert len(exchange.source) == MAX_ENTRY_CHARS
    assert len(exchange.translation) == MAX_ENTRY_CHARS
    assert exchange.source.endswith("…")


def test_total_budget_drops_oldest_first():
    store = HistoryStore(max_exchanges=10)
    for i in range(10):
        store.record(1, "French", f"{i}" * MAX_ENTRY_CHARS, f"{i}" * MAX_ENTRY_CHARS)
    kept = store.get(1, "French")
    total = sum(len(e.source) + len(e.translation) for e in kept)
    assert total <= MAX_TOTAL_CHARS
    # The newest survive; only the oldest are dropped.
    assert kept[-1].source.startswith("9")
    assert len(kept) < 10


def test_least_recently_used_bucket_is_evicted():
    store = HistoryStore()
    for user_id in range(MAX_USERS + 5):
        store.record(user_id, "French", "hello", "bonjour")
    assert store.get(0, "French") == []
    assert len(store.get(MAX_USERS + 4, "French")) == 1


def test_reading_history_counts_as_use_for_eviction():
    store = HistoryStore()
    store.record(0, "French", "hello", "bonjour")
    for user_id in range(1, MAX_USERS):
        store.record(user_id, "French", "hello", "bonjour")
    store.get(0, "French")  # touch the oldest bucket
    store.record(MAX_USERS + 1, "French", "hello", "bonjour")
    assert len(store.get(0, "French")) == 1


def test_pending_claim_returns_the_parked_translation():
    pending = PendingResults()
    pending.park("abc", 1, "French", "hello", "bonjour")
    claimed = pending.claim("abc")
    assert claimed is not None
    assert (claimed.user_id, claimed.target_lang) == (1, "French")
    assert (claimed.source, claimed.translation) == ("hello", "bonjour")


def test_pending_claim_is_single_use():
    pending = PendingResults()
    pending.park("abc", 1, "French", "hello", "bonjour")
    assert pending.claim("abc") is not None
    assert pending.claim("abc") is None


def test_pending_claim_of_unknown_id_is_none():
    assert PendingResults().claim("never-parked") is None


def test_pending_entries_expire():
    pending = PendingResults(ttl_seconds=60)
    pending.park("abc", 1, "French", "hello", "bonjour")
    parked = pending._pending["abc"]
    pending._pending["abc"] = type(parked)(
        parked.user_id,
        parked.target_lang,
        parked.source,
        parked.translation,
        time.time() - 120,
    )
    assert pending.claim("abc") is None


def test_pending_is_bounded():
    pending = PendingResults(max_entries=3)
    for i in range(5):
        pending.park(f"id-{i}", 1, "French", "hello", "bonjour")
    assert pending.claim("id-0") is None
    assert pending.claim("id-4") is not None
