# Telegram LLM Translation Bot(@SendTranslatedBot)

[![Tests](https://github.com/nikita-holban/telegram-translate/actions/workflows/tests.yml/badge.svg)](https://github.com/nikita-holban/telegram-translate/actions/workflows/tests.yml)
[![Deploy](https://github.com/nikita-holban/telegram-translate/actions/workflows/deploy.yml/badge.svg)](https://github.com/nikita-holban/telegram-translate/actions/workflows/deploy.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

You can try it here: [@SendTranslatedBot](https://t.me/SendTranslatedBot)

A Telegram **inline** bot that translates text with an LLM (Anthropic Claude).
While chatting with anyone — including a private chat with another person —
type `@yourbot some text` and tap the result to send the translation.

## How it works

- **Inline mode**: the bot only sees the text you type after its username, so
  it never reads anyone's chat. You pick the translated result and send it
  yourself.
- **Target language**: each user sets a default with `/setlang`. Any single
  query can override it with a prefix, e.g. `@yourbot fr: good morning`.
- Telegram's inline API does not expose *which* chat a query came from, so
  settings are per **user**, not per chat. The `xx:` prefix is the
  per-conversation override.

## Setup

### 1. Create the bot in BotFather

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. `/setinline` → select your bot → set a placeholder (e.g. `Text to translate…`).
   **Inline mode must be enabled or inline queries never reach the bot.**

### 2. Configure

```sh
cp .env.example .env
# edit .env: set BOT_TOKEN and ANTHROPIC_API_KEY
```

### 3. Install and run

This project uses [uv](https://docs.astral.sh/uv/).

```sh
uv sync                  # install dependencies
uv run python -m app.main
```

## Usage

| Action | Example |
| --- | --- |
| Translate into your default language | `@yourbot привет, как дела?` |
| Translate into a specific language | `@yourbot fr: good morning` |
| Set your default language | `/setlang Spanish` (or `/setlang es`) |
| Show your default | `/lang` |
| Help | `/start` or `/help` |

## Configuration

All settings are environment variables (see `.env.example`):

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `BOT_TOKEN` | yes | — | Telegram bot token |
| `ANTHROPIC_API_KEY` | yes | — | Anthropic API key |
| `ANTHROPIC_MODEL` | no | `claude-haiku-4-5` | Translation model (Haiku for low latency) |
| `DEFAULT_TARGET_LANG` | no | `English` | Fallback when a user has no `/setlang` |
| `DB_PATH` | no | `data/bot.db` | SQLite file for per-user settings |

## Tests

```sh
uv run pytest
```

Covers inline-prefix parsing and the SQLite settings store. End-to-end inline
translation requires a real `BOT_TOKEN`, `ANTHROPIC_API_KEY`, and a Telegram
client.

## Project layout

```
app/
  main.py        entry point: Bot, Dispatcher, polling
  config.py      environment configuration
  handlers.py    /start /help /setlang /lang + inline query handler
  translator.py  Claude translation call
  storage.py     aiosqlite per-user target language
  languages.py   inline prefix parsing + language normalization
tests/           offline unit tests
```
