import pytest

from app.history import Exchange
from app.providers import ProviderRegistry
from app.providers.anthropic import _build_messages


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
