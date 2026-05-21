from __future__ import annotations

from ..config import Config
from .anthropic import AnthropicProvider
from .base import TranslationError, TranslationProvider
from .google import GoogleProvider

__all__ = [
    "AnthropicProvider",
    "GoogleProvider",
    "PROVIDER_LABELS",
    "ProviderRegistry",
    "TranslationError",
    "TranslationProvider",
    "build_registry",
]

# Human-readable provider names, keyed by the registry key stored per user.
PROVIDER_LABELS: dict[str, str] = {
    "anthropic": "Claude (Anthropic)",
    "google": "Google Translation LLM",
}


class ProviderRegistry:
    """The translation backends configured for this deployment."""

    def __init__(
        self, providers: dict[str, TranslationProvider], default_name: str
    ) -> None:
        if not providers:
            raise RuntimeError("No translation providers configured")
        self._providers = providers
        self._default_name = (
            default_name if default_name in providers else next(iter(providers))
        )

    @property
    def default_name(self) -> str:
        return self._default_name

    def names(self) -> list[str]:
        return list(self._providers)

    def resolve(self, name: str | None) -> tuple[str, TranslationProvider]:
        """Return ``(name, provider)``, falling back to the default backend."""
        if name and name in self._providers:
            return name, self._providers[name]
        return self._default_name, self._providers[self._default_name]

    async def aclose(self) -> None:
        for provider in self._providers.values():
            await provider.aclose()


def build_registry(config: Config) -> ProviderRegistry:
    """Instantiate every translation backend the config has credentials for."""
    providers: dict[str, TranslationProvider] = {}
    if config.anthropic_api_key:
        providers["anthropic"] = AnthropicProvider(
            config.anthropic_api_key, config.anthropic_model
        )
    if config.google_project_id:
        providers["google"] = GoogleProvider(
            config.google_project_id, config.google_location
        )
    if not providers:
        raise RuntimeError(
            "No translation provider configured. Set ANTHROPIC_API_KEY "
            "and/or GOOGLE_PROJECT_ID in your environment."
        )
    return ProviderRegistry(providers, config.default_provider)
