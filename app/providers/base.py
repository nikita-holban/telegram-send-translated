from __future__ import annotations

from abc import ABC, abstractmethod


class TranslationError(Exception):
    """A translation failure with a message safe to show the user."""


class TranslationProvider(ABC):
    """A swappable translation backend."""

    @abstractmethod
    async def translate(self, text: str, target_lang: str) -> str:
        """Translate ``text`` into ``target_lang`` (a canonical language name)."""

    @abstractmethod
    async def supports(self, target_lang: str) -> bool:
        """Whether this backend can translate into ``target_lang``."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release any network resources."""
