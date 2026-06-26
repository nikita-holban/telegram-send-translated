from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from . import handlers
from .config import load_config
from .providers import build_registry
from .storage import Storage


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config()

    storage = Storage(config.db_path)
    await storage.connect()
    registry = build_registry(config, storage)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(handlers.router)

    await bot.set_my_commands([
        BotCommand(command="setlang", description="Set your default target language"),
        BotCommand(command="provider", description="Choose your translation engine"),
        BotCommand(command="lang", description="Show your current default language"),
        BotCommand(command="help", description="How to use this bot"),
    ])

    if config.webhook_url:
        await bot.set_webhook(
            url=config.webhook_url,
            secret_token=config.webhook_secret,
            drop_pending_updates=True,
        )
        app = web.Application()
        SimpleRequestHandler(dispatcher=dispatcher, bot=bot).register(app, path=config.webhook_path)
        setup_application(app, dispatcher, registry=registry, storage=storage, config=config)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", config.webhook_port).start()
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
            await registry.aclose()
            await storage.close()
            await bot.session.close()
    else:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await dispatcher.start_polling(
                bot,
                registry=registry,
                storage=storage,
                config=config,
            )
        finally:
            await registry.aclose()
            await storage.close()
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
