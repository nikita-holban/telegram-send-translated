from __future__ import annotations

import anthropic

from ..storage import Storage
from .base import TranslationProvider

# Static instructions only — the variable target language and text go in the
# user message. Kept short on purpose; it is well below the prompt-caching
# minimum, so no cache_control is applied (it would be a silent no-op).
_SYSTEM_PROMPT = (
    "You are a translation engine. Translate the user's text into the "
    "requested target language, automatically detecting the source language. "
    "Output only the translation itself — no quotes, no preamble, no notes, "
    "no alternatives. Preserve the original tone, register, emoji, line "
    "breaks and punctuation. If the text is already in the target language, "
    "return it unchanged."
)


class AnthropicProvider(TranslationProvider):
    """Translation backed by the Anthropic Messages API (Claude)."""

    def __init__(self, api_key: str, model: str, storage: Storage) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._storage = storage

    async def translate(self, text: str, target_lang: str) -> str:
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Target language: {target_lang}\n\nText:\n{text}",
                }
            ],
        )
        await self._storage.log_anthropic_usage(
            self._model, message.usage.input_tokens, message.usage.output_tokens
        )
        parts = [block.text for block in message.content if block.type == "text"]
        return "".join(parts).strip()

    async def supports(self, target_lang: str) -> bool:
        # The LLM handles any language name we accept.
        return True

    async def aclose(self) -> None:
        await self._client.close()
