import pytest

from app.providers import ProviderRegistry


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
