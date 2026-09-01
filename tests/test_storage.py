import pytest

from app.storage import Storage


@pytest.fixture
async def storage():
    store = Storage(":memory:")
    await store.connect()
    yield store
    await store.close()


async def test_get_returns_none_when_unset(storage):
    assert await storage.get_target_lang(42) is None
    assert await storage.get_provider(42) is None


async def test_set_then_get(storage):
    await storage.set_target_lang(42, "French")
    assert await storage.get_target_lang(42) == "French"


async def test_set_overwrites_existing(storage):
    await storage.set_target_lang(42, "French")
    await storage.set_target_lang(42, "German")
    assert await storage.get_target_lang(42) == "German"


async def test_settings_are_per_user(storage):
    await storage.set_target_lang(1, "Spanish")
    await storage.set_target_lang(2, "Japanese")
    assert await storage.get_target_lang(1) == "Spanish"
    assert await storage.get_target_lang(2) == "Japanese"


async def test_provider_set_then_get(storage):
    await storage.set_provider(7, "google")
    assert await storage.get_provider(7) == "google"


async def test_provider_and_language_are_independent(storage):
    # A user may set a provider before ever setting a language.
    await storage.set_provider(9, "anthropic")
    assert await storage.get_provider(9) == "anthropic"
    assert await storage.get_target_lang(9) is None

    await storage.set_target_lang(9, "Korean")
    assert await storage.get_target_lang(9) == "Korean"
    assert await storage.get_provider(9) == "anthropic"


async def test_language_set_before_provider(storage):
    await storage.set_target_lang(11, "Polish")
    await storage.set_provider(11, "google")
    assert await storage.get_target_lang(11) == "Polish"
    assert await storage.get_provider(11) == "google"


async def _log_google_at(storage, timestamp: str, chars: int) -> None:
    """Insert a usage row with a chosen timestamp (log_google_usage stamps now())."""
    await storage._db.execute(
        "INSERT INTO usage_log (timestamp, provider, chars) VALUES (?, 'google', ?)",
        (timestamp, chars),
    )
    await storage._db.commit()


async def test_google_chars_sums_rows_at_or_after_start(storage):
    await _log_google_at(storage, "2026-08-01T00:00:00+00:00", 10)
    await _log_google_at(storage, "2026-08-15T12:00:00.500000+00:00", 7)
    assert await storage.google_chars_used_since("2026-08-01T00:00:00+00:00") == 17


async def test_google_chars_excludes_earlier_periods(storage):
    await _log_google_at(storage, "2026-07-31T23:59:59.999999+00:00", 5_000)
    await _log_google_at(storage, "2026-08-02T09:00:00+00:00", 12)
    assert await storage.google_chars_used_since("2026-08-01T00:00:00+00:00") == 12


async def test_google_chars_is_zero_for_an_empty_period(storage):
    await _log_google_at(storage, "2026-07-05T10:00:00+00:00", 500)
    assert await storage.google_chars_used_since("2026-08-01T00:00:00+00:00") == 0


async def test_google_chars_ignores_anthropic_rows(storage):
    await storage.log_anthropic_usage("claude-haiku-4-5", 100, 50)
    assert await storage.google_chars_used_since("2026-01-01T00:00:00+00:00") == 0


async def test_log_google_usage_is_counted_in_the_current_period(storage):
    await storage.log_google_usage(42)
    assert await storage.google_chars_used_since("2000-01-01T00:00:00+00:00") == 42
