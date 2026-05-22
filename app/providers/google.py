from __future__ import annotations

import logging

from google.cloud import translate_v3

from ..languages import to_language_code
from ..storage import Storage
from .base import TranslationError, TranslationProvider

logger = logging.getLogger(__name__)

# USD per million source characters for the translation-llm model.
_RATE_PER_M_CHARS = 300.0


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

    async def translate(self, text: str, target_lang: str) -> str:
        code = to_language_code(target_lang)
        if code is None:
            raise TranslationError(
                f'Google Translation LLM doesn\'t recognize "{target_lang}".'
            )
        if self._budget_usd is not None:
            chars_so_far = await self._storage.google_chars_used()
            projected_usd = (chars_so_far + len(text)) * _RATE_PER_M_CHARS / 1_000_000
            if projected_usd > self._budget_usd:
                spent_usd = chars_so_far * _RATE_PER_M_CHARS / 1_000_000
                raise TranslationError(
                    f"Google translation budget (${self._budget_usd:.2f}) reached. "
                    f"Spent so far: ${spent_usd:.2f}. Switch to the Anthropic provider."
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
