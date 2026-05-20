from __future__ import annotations

import asyncio
import logging
import uuid

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputTextMessageContent,
    Message,
)

from .config import Config
from .languages import parse_query, resolve_target
from .storage import Storage
from .translator import Translator

logger = logging.getLogger(__name__)

router = Router()

# Telegram fires an inline query on every keystroke. We wait briefly and only
# translate the query if no newer one from the same user has arrived.
_DEBOUNCE_SECONDS = 0.6
_latest_query: dict[int, str] = {}

_HELP_TEXT = (
    "<b>LLM Translate</b>\n\n"
    "I translate messages inline — in any chat, including private chats with "
    "other people.\n\n"
    "<b>How to use</b>\n"
    "Type <code>@{username} your text</code> in the message box of any chat, "
    "then tap the result to send the translation.\n\n"
    "<b>Target language</b>\n"
    "{status}\n"
    "• Override it for one message with a prefix:\n"
    "  <code>@{username} fr: good morning</code>\n\n"
    "<b>Commands</b>\n"
    "/setlang &lt;language&gt; — set your default target language\n"
    "/lang — show your current default\n"
    "/help — show this message"
)


async def _send_help(message: Message, storage: Storage, config: Config) -> None:
    me = await message.bot.me()
    saved = await storage.get_target_lang(message.from_user.id)
    if saved:
        status = f"• You translate into <b>{saved}</b> by default."
    else:
        status = (
            f"• You haven't set a default yet, so I use <b>"
            f"{config.default_target_lang}</b>. Change it with /setlang."
        )
    await message.answer(_HELP_TEXT.format(username=me.username, status=status))


@router.message(CommandStart())
async def cmd_start(message: Message, storage: Storage, config: Config) -> None:
    await _send_help(message, storage, config)


@router.message(Command("help"))
async def cmd_help(message: Message, storage: Storage, config: Config) -> None:
    await _send_help(message, storage, config)


@router.message(Command("setlang"))
async def cmd_setlang(
    message: Message, command: CommandObject, storage: Storage
) -> None:
    if not command.args:
        await message.answer(
            "Usage: <code>/setlang &lt;language&gt;</code>\n"
            "Examples: <code>/setlang Spanish</code> or <code>/setlang es</code>"
        )
        return
    target = resolve_target(command.args)
    if target is None:
        await message.answer(
            "I didn't recognize that language. Try a name like "
            "<code>Spanish</code> or a code like <code>es</code>."
        )
        return
    await storage.set_target_lang(message.from_user.id, target)
    await message.answer(f"Default target language set to <b>{target}</b>.")


@router.message(Command("lang"))
async def cmd_lang(message: Message, storage: Storage, config: Config) -> None:
    target = await storage.get_target_lang(message.from_user.id)
    if target:
        await message.answer(f"Your default target language is <b>{target}</b>.")
    else:
        await message.answer(
            f"You haven't set a default yet — I'm using "
            f"<b>{config.default_target_lang}</b>.\n"
            "Set your own with <code>/setlang &lt;language&gt;</code>."
        )


@router.inline_query()
async def inline_translate(
    inline_query: InlineQuery,
    translator: Translator,
    storage: Storage,
    config: Config,
) -> None:
    user_id = inline_query.from_user.id
    raw = inline_query.query

    if not raw.strip():
        await inline_query.answer(
            results=[],
            cache_time=0,
            is_personal=True,
            button=InlineQueryResultsButton(
                text="Set your default language",
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

    try:
        translated = await translator.translate(body, target)
    except Exception:
        logger.exception("Translation failed for user %s", user_id)
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="Translation failed",
                    description="Something went wrong. Tap to send the original text.",
                    input_message_content=InputTextMessageContent(
                        message_text=body, parse_mode=None
                    ),
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
        title=f"Translate to {target}",
        description=translated,
        input_message_content=InputTextMessageContent(
            message_text=translated, parse_mode=None
        ),
    )
    await inline_query.answer(results=[result], cache_time=0, is_personal=True)
