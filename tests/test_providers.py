from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.history import Exchange
from app.providers import ProviderRegistry
from app.providers import google as google_mod
from app.providers.anthropic import _build_messages
from app.providers.base import TranslationError
from app.providers.google import GoogleProvider, _month_start, _next_month_start


def _registry():
    """A registry with two stub backends; resolution never touches them."""
    anthropic = object()
    google = object()
    registry = ProviderRegistry(
        {"anthropic": anthropic, "google": google}, "anthropic"
    )
    return registry, anthropic, google


def test_resolve_known_name():
    registry, anthropic, google = _registry()
    assert registry.resolve("google") == ("google", google)
    assert registry.resolve("anthropic") == ("anthropic", anthropic)


def test_resolve_unknown_falls_back_to_default():
    registry, anthropic, _ = _registry()
    assert registry.resolve("bogus") == ("anthropic", anthropic)


def test_resolve_none_falls_back_to_default():
    registry, anthropic, _ = _registry()
    assert registry.resolve(None) == ("anthropic", anthropic)


def test_names():
    registry, _, _ = _registry()
    assert set(registry.names()) == {"anthropic", "google"}


def test_default_falls_back_when_unconfigured():
    google = object()
    # The requested default isn't configured; the registry picks what exists.
    registry = ProviderRegistry({"google": google}, "anthropic")
    assert registry.default_name == "google"
    assert registry.resolve(None) == ("google", google)


def test_empty_registry_rejected():
    with pytest.raises(RuntimeError):
        ProviderRegistry({}, "anthropic")


def _exchange(source, translation):
    return Exchange(source, translation, 0.0)


def test_build_messages_without_history_is_a_single_turn():
    messages = _build_messages("hello", "French")
    assert messages == [
        {"role": "user", "content": "Target language: French\n\nText:\nhello"}
    ]


def test_build_messages_replays_history_as_alternating_turns():
    history = [_exchange("one", "un"), _exchange("two", "deux")]
    messages = _build_messages("three", "French", history)

    assert [m["role"] for m in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == "un"
    assert messages[3]["content"] == "deux"
    # The text to translate is always the final turn.
    assert messages[-1]["content"] == "Target language: French\n\nText:\nthree"


def test_build_messages_labels_past_turns_with_the_target_language():
    messages = _build_messages("two", "Spanish", [_exchange("one", "uno")])
    assert messages[0]["content"] == "Target language: Spanish\n\nText:\none"


class _FakeStorage:
    """Records the period it was asked about and reports a fixed usage figure."""

    def __init__(self, chars: int = 0) -> None:
        self._chars = chars
        self.asked_start: str | None = None
        self.logged: list[int] = []

    async def google_chars_used_since(self, start: str) -> int:
        self.asked_start = start
        return self._chars

    async def log_google_usage(self, chars: int) -> None:
        self.logged.append(chars)


class _FakeTranslateClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def translate_text(self, request):
        self.calls.append(request)
        translation = SimpleNamespace(translated_text="bonjour")
        return SimpleNamespace(translations=[translation])


def _google(storage, budget_usd):
    """A GoogleProvider with the network client stubbed out.

    __init__ builds a real TranslationServiceAsyncClient, which needs
    credentials, so the instance is assembled field by field instead.
    """
    provider = object.__new__(GoogleProvider)
    provider._storage = storage
    provider._budget_usd = budget_usd
    provider._parent = "projects/p/locations/global"
    provider._model = f"{provider._parent}/models/general/translation-llm"
    provider._supported = None
    provider._client = _FakeTranslateClient()
    return provider


def _pin_clock(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(google_mod, "_utcnow", lambda: when)


def test_month_start_floors_to_the_first():
    now = datetime(2026, 9, 15, 13, 45, 30, 123456, tzinfo=timezone.utc)
    assert _month_start(now) == datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_next_month_start_rolls_over_december():
    now = datetime(2026, 12, 24, 9, 0, tzinfo=timezone.utc)
    assert _next_month_start(now) == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_next_month_start_from_a_31st():
    now = datetime(2026, 8, 31, 18, 25, tzinfo=timezone.utc)
    assert _next_month_start(now) == datetime(2026, 9, 1, tzinfo=timezone.utc)


async def test_budget_counts_only_the_current_month(monkeypatch):
    _pin_clock(monkeypatch, datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc))
    storage = _FakeStorage(chars=1_000)
    await _google(storage, budget_usd=5.0).translate("hello", "French")
    assert storage.asked_start == "2026-09-01T00:00:00+00:00"


async def test_budget_allows_request_under_the_cap(monkeypatch):
    _pin_clock(monkeypatch, datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc))
    storage = _FakeStorage(chars=1_000)  # $0.30 of $5.00
    provider = _google(storage, budget_usd=5.0)

    assert await provider.translate("hello", "French") == "bonjour"
    assert len(provider._client.calls) == 1
    assert storage.logged == [5]


async def test_budget_blocks_request_over_the_cap(monkeypatch):
    _pin_clock(monkeypatch, datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc))
    storage = _FakeStorage(chars=20_000)  # $6.00 of $5.00
    provider = _google(storage, budget_usd=5.0)

    with pytest.raises(TranslationError) as excinfo:
        await provider.translate("hello", "French")

    message = str(excinfo.value)
    assert "$5.00/month" in message
    assert "$6.00" in message
    assert "Resets 2026-10-01" in message
    # Nothing was sent, so nothing was billed or logged.
    assert provider._client.calls == []
    assert storage.logged == []


async def test_spend_from_last_month_does_not_block_this_month(monkeypatch):
    # Same storage, same figures — only the clock moves across the boundary.
    storage = _FakeStorage(chars=20_000)

    _pin_clock(monkeypatch, datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc))
    with pytest.raises(TranslationError):
        await _google(storage, budget_usd=5.0).translate("hello", "French")
    assert storage.asked_start == "2026-08-01T00:00:00+00:00"

    _pin_clock(monkeypatch, datetime(2026, 9, 1, 0, 1, tzinfo=timezone.utc))
    fresh = _FakeStorage(chars=0)  # the new month starts empty
    assert await _google(fresh, budget_usd=5.0).translate("hello", "French") == "bonjour"
    assert fresh.asked_start == "2026-09-01T00:00:00+00:00"


async def test_no_budget_configured_skips_the_usage_query(monkeypatch):
    _pin_clock(monkeypatch, datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc))
    storage = _FakeStorage(chars=10_000_000)
    provider = _google(storage, budget_usd=None)

    assert await provider.translate("hello", "French") == "bonjour"
    assert storage.asked_start is None
