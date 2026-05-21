from __future__ import annotations

import asyncio
import html
import logging
import uuid

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputTextMessageContent,
    Message,
)

from .config import Config
from .languages import (
    display_language,
    normalize_language,
    parse_query,
    resolve_target,
    suggest_language,
)
from .providers import PROVIDER_LABELS, ProviderRegistry, TranslationError
from .storage import Storage

logger = logging.getLogger(__name__)

router = Router()

# Telegram fires an inline query on every keystroke. We wait briefly and only
# translate the query if no newer one from the same user has arrived.
_DEBOUNCE_SECONDS = 0.6
_latest_query: dict[int, str] = {}

# Accepted /provider arguments, mapped to registry keys.
_PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "google",
    "tllm": "google",
}

_HELP_TEXT = (
    "<b>LLM Translate</b>\n\n"
    "I translate messages inline — in any chat, including private chats with "
    "other people.\n\n"
    "<b>How to use</b>\n"
    "Type <code>@{username} your text</code> in the message box of any chat, "
    "then tap the result to send the translation.\n\n"
    "<b>Target language</b>\n"
    "{lang_status}\n"
    "• Override it for one message with a prefix:\n"
    "  <code>@{username} fr: good morning</code>\n\n"
    "<b>Translation engine</b>\n"
    "• You're using <b>{provider}</b> — switch with /provider.\n\n"
    "<b>Commands</b>\n"
    "/setlang &lt;language&gt; — set your default target language\n"
    "/provider &lt;name&gt; — choose your translation engine\n"
    "/lang — show your current default\n"
    "/help — show this message"
)


async def _send_help(
    message: Message, storage: Storage, registry: ProviderRegistry, config: Config
) -> None:
    me = await message.bot.me()
    user_id = message.from_user.id

    saved = await storage.get_target_lang(user_id)
    if saved:
        lang_status = (
            f"• You translate into <b>{display_language(saved)}</b> by default."
        )
    else:
        lang_status = (
            f"• You haven't set a default yet, so I use <b>"
            f"{config.default_target_lang}</b>. Change it with /setlang."
        )

    effective_name, _ = registry.resolve(await storage.get_provider(user_id))
    provider = PROVIDER_LABELS.get(effective_name, effective_name)

    await message.answer(
        _HELP_TEXT.format(
            username=me.username, lang_status=lang_status, provider=provider
        )
    )


async def _support_warning(
    label: str, provider, language: str
) -> str:
    """A note to append when ``provider`` may not support ``language``."""
    if await provider.supports(language):
        return ""
    return (
        f"\n\nNote: {label} may not support <b>{display_language(language)}</b>."
        " If translations fail, pick another language with /setlang."
    )


async def _provider_support_warning(
    user_id: int, language: str, storage: Storage, registry: ProviderRegistry
) -> str:
    effective_name, provider = registry.resolve(await storage.get_provider(user_id))
    label = PROVIDER_LABELS.get(effective_name, effective_name)
    return await _support_warning(label, provider, language)


async def _try_set_language(
    message: Message, text: str, storage: Storage, registry: ProviderRegistry
) -> bool:
    """Apply ``text`` as a language, or offer suggestions for a near-miss.

    Returns False when ``text`` is not a language and has no close matches.
    """
    target = resolve_target(text)
    if target is not None:
        await storage.set_target_lang(message.from_user.id, target)
        warning = await _provider_support_warning(
            message.from_user.id, target, storage, registry
        )
        await message.answer(
            f"Default target language set to "
            f"<b>{display_language(target)}</b>.{warning}"
        )
        return True

    suggestions = suggest_language(text)
    if suggestions:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=display_language(name),
                        callback_data=f"setlang:{name}",
                    )
                ]
                for name in suggestions
            ]
        )
        shown = html.escape(text.strip()[:50])
        await message.answer(
            f"I don't recognize <b>{shown}</b> as a language. Did you mean "
            "one of these? Otherwise send the language name again.",
            reply_markup=keyboard,
        )
        return True

    return False


@router.message(CommandStart())
async def cmd_start(
    message: Message, storage: Storage, registry: ProviderRegistry, config: Config
) -> None:
    await _send_help(message, storage, registry, config)


@router.message(Command("help"))
async def cmd_help(
    message: Message, storage: Storage, registry: ProviderRegistry, config: Config
) -> None:
    await _send_help(message, storage, registry, config)


@router.message(Command("setlang"))
async def cmd_setlang(
    message: Message,
    command: CommandObject,
    storage: Storage,
    registry: ProviderRegistry,
) -> None:
    if not command.args:
        await message.answer(
            "Usage: <code>/setlang &lt;language&gt;</code>\n"
            "Examples: <code>/setlang Spanish</code> or <code>/setlang es</code>"
        )
        return
    if not await _try_set_language(message, command.args, storage, registry):
        await message.answer(
            "I didn't recognize that language. Try a name like "
            "<code>Spanish</code> or a code like <code>es</code>."
        )


@router.message(Command("provider"))
async def cmd_provider(
    message: Message,
    command: CommandObject,
    storage: Storage,
    registry: ProviderRegistry,
    config: Config,
) -> None:
    available = registry.names()
    if not command.args:
        effective_name, _ = registry.resolve(
            await storage.get_provider(message.from_user.id)
        )
        current = PROVIDER_LABELS.get(effective_name, effective_name)
        options = "\n".join(
            f"• <code>{name}</code> — {PROVIDER_LABELS.get(name, name)}"
            for name in available
        )
        await message.answer(
            f"Your translation engine: <b>{current}</b>.\n\n"
            f"Available:\n{options}\n\n"
            "Switch with <code>/provider &lt;name&gt;</code>, "
            "e.g. <code>/provider google</code>."
        )
        return

    key = _PROVIDER_ALIASES.get(command.args.strip().lower())
    if key is None or key not in available:
        options = ", ".join(f"<code>{name}</code>" for name in available)
        await message.answer(
            f"I don't know that translation engine. Available: {options}."
        )
        return

    await storage.set_provider(message.from_user.id, key)
    label = PROVIDER_LABELS.get(key, key)
    saved_lang = (
        await storage.get_target_lang(message.from_user.id)
        or config.default_target_lang
    )
    _, provider = registry.resolve(key)
    warning = await _support_warning(label, provider, saved_lang)
    await message.answer(f"Translation engine set to <b>{label}</b>.{warning}")


@router.message(Command("lang"))
async def cmd_lang(message: Message, storage: Storage, config: Config) -> None:
    target = await storage.get_target_lang(message.from_user.id)
    if target:
        await message.answer(
            f"Your default target language is <b>{display_language(target)}</b>."
        )
    else:
        await message.answer(
            f"You haven't set a default yet — I'm using "
            f"<b>{config.default_target_lang}</b>.\n"
            "Set your own with <code>/setlang &lt;language&gt;</code>."
        )


@router.callback_query(F.data.startswith("setlang:"))
async def on_setlang_choice(
    callback: CallbackQuery, storage: Storage, registry: ProviderRegistry
) -> None:
    name = callback.data.split(":", 1)[1]
    target = normalize_language(name) or name
    await storage.set_target_lang(callback.from_user.id, target)
    warning = await _provider_support_warning(
        callback.from_user.id, target, storage, registry
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"Default target language set to "
            f"<b>{display_language(target)}</b>.{warning}"
        )
    await callback.answer()


@router.message(F.chat.type == "private", F.text)
async def on_plain_text(
    message: Message, storage: Storage, registry: ProviderRegistry, config: Config
) -> None:
    """Treat a bare private message as a language, so users can re-enter one."""
    text = message.text.strip()
    if not text or text.startswith("/"):
        return
    if not await _try_set_language(message, text, storage, registry):
        await _send_help(message, storage, registry, config)


def _error_result(body: str, description: str) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title="Translation failed",
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=body, parse_mode=None
        ),
    )


@router.inline_query()
async def inline_translate(
    inline_query: InlineQuery,
    registry: ProviderRegistry,
    storage: Storage,
    config: Config,
) -> None:
    user_id = inline_query.from_user.id
    raw = inline_query.query

    if not raw.strip():
        saved = await storage.get_target_lang(user_id)
        if saved:
            button_text = f"Default: {display_language(saved)} — tap to change"
        else:
            button_text = "Set your default language"
        await inline_query.answer(
            results=[],
            cache_time=0,
            is_personal=True,
            button=InlineQueryResultsButton(
                text=button_text,
                start_parameter="setlang",
            ),
        )
        return

    _latest_query[user_id] = inline_query.id
    await asyncio.sleep(_DEBOUNCE_SECONDS)
    if _latest_query.get(user_id) != inline_query.id:
        return

    override, body = parse_query(raw)
    if not body:
        return
    target = (
        override
        or await storage.get_target_lang(user_id)
        or config.default_target_lang
    )
    _, provider = registry.resolve(await storage.get_provider(user_id))

    try:
        translated = await provider.translate(body, target)
    except TranslationError as exc:
        await inline_query.answer(
            results=[_error_result(body, str(exc))],
            cache_time=0,
            is_personal=True,
        )
        return
    except Exception:
        logger.exception("Translation failed for user %s", user_id)
        await inline_query.answer(
            results=[
                _error_result(
                    body, "Something went wrong. Tap to send the original text."
                )
            ],
            cache_time=0,
            is_personal=True,
        )
        return

    # A newer keystroke may have superseded this query while translating.
    if _latest_query.get(user_id) != inline_query.id:
        return

    result = InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title=f"Translate to {display_language(target)}",
        description=translated,
        input_message_content=InputTextMessageContent(
            message_text=translated, parse_mode=None
        ),
    )
    await inline_query.answer(results=[result], cache_time=0, is_personal=True)
