from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from google.cloud import translate_v3

from ..history import Exchange
from ..languages import to_language_code
from ..storage import Storage
from .base import TranslationError, TranslationProvider

logger = logging.getLogger(__name__)

# USD per million source characters for the translation-llm model.
_RATE_PER_M_CHARS = 300.0


def _utcnow() -> datetime:
    # Indirection so tests can pin the clock across a month boundary.
    return datetime.now(timezone.utc)


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month_start(now: datetime) -> datetime:
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return _month_start(now).replace(year=year, month=month)


class GoogleProvider(TranslationProvider):
    """Translation backed by Google Cloud Translation LLM (Translation v3).

    Authentication uses Application Default Credentials — set
    GOOGLE_APPLICATION_CREDENTIALS to a service-account key file.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        storage: Storage,
        budget_usd: float | None = None,
    ) -> None:
        self._client = translate_v3.TranslationServiceAsyncClient()
        self._parent = f"projects/{project_id}/locations/{location}"
        self._model = f"{self._parent}/models/general/translation-llm"
        self._supported: set[str] | None = None
        self._storage = storage
        self._budget_usd = budget_usd

    async def translate(
        self, text: str, target_lang: str, history: Sequence[Exchange] = ()
    ) -> str:
        # ``history`` is ignored: translate_text takes standalone contents and
        # has no way to carry conversational context.
        code = to_language_code(target_lang)
        if code is None:
            raise TranslationError(
                f'Google Translation LLM doesn\'t recognize "{target_lang}".'
            )
        if self._budget_usd is not None:
            now = _utcnow()
            chars_so_far = await self._storage.google_chars_used_since(
                _month_start(now).isoformat()
            )
            projected_usd = (chars_so_far + len(text)) * _RATE_PER_M_CHARS / 1_000_000
            if projected_usd > self._budget_usd:
                spent_usd = chars_so_far * _RATE_PER_M_CHARS / 1_000_000
                resets = _next_month_start(now).strftime("%Y-%m-%d")
                raise TranslationError(
                    f"Google translation budget (${self._budget_usd:.2f}/month) reached. "
                    f"Spent this month: ${spent_usd:.2f}. Resets {resets}. "
                    "Switch to the Anthropic provider."
                )
        response = await self._client.translate_text(
            request={
                "parent": self._parent,
                "contents": [text],
                "mime_type": "text/plain",
                "target_language_code": code,
                "model": self._model,
            }
        )
        await self._storage.log_google_usage(len(text))
        return response.translations[0].translated_text

    async def _supported_codes(self) -> set[str]:
        if self._supported is None:
            try:
                response = await self._client.get_supported_languages(
                    request={"parent": self._parent, "model": self._model}
                )
                self._supported = {
                    lang.language_code.lower()
                    for lang in response.languages
                    if lang.support_target
                }
            except Exception:
                logger.warning(
                    "Could not fetch Google supported languages", exc_info=True
                )
                self._supported = set()
        return self._supported

    async def supports(self, target_lang: str) -> bool:
        code = to_language_code(target_lang)
        if code is None:
            return False
        supported = await self._supported_codes()
        if not supported:
            # Couldn't verify — don't block; translation errors surface later.
            return True
        primary = code.lower().split("-")[0]
        return any(s.split("-")[0] == primary for s in supported)

    async def aclose(self) -> None:
        try:
            await self._client.transport.close()
        except Exception:
            logger.debug("Error closing Google client", exc_info=True)
