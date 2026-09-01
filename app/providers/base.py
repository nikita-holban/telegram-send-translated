from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..history import Exchange


class TranslationError(Exception):
    """A translation failure with a message safe to show the user."""


class TranslationProvider(ABC):
    """A swappable translation backend."""

    @abstractmethod
    async def translate(
        self, text: str, target_lang: str, history: Sequence[Exchange] = ()
    ) -> str:
        """Translate ``text`` into ``target_lang`` (a canonical language name).

        ``history`` holds the user's recent exchanges, oldest first, offered as
        context. Backends without a notion of conversation may ignore it.
        """

    @abstractmethod
    async def supports(self, target_lang: str) -> bool:
        """Whether this backend can translate into ``target_lang``."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release any network resources."""
