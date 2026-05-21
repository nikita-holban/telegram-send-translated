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
