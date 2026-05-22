from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    anthropic_api_key: str | None
    anthropic_model: str
    google_project_id: str | None
    google_location: str
    google_budget_usd: float | None
    default_provider: str
    default_target_lang: str
    db_path: str


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill it in."
        )
    return value


def load_config() -> Config:
    bot_token = _require("BOT_TOKEN")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or None
    google_project_id = os.getenv("GOOGLE_PROJECT_ID") or None

    if google_project_id and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError(
            "GOOGLE_PROJECT_ID is set but GOOGLE_APPLICATION_CREDENTIALS is "
            "missing. Point it at a service-account key file."
        )
    if not anthropic_api_key and not google_project_id:
        raise RuntimeError(
            "No translation provider configured. Set ANTHROPIC_API_KEY "
            "and/or GOOGLE_PROJECT_ID in your .env file."
        )

    raw_budget = os.getenv("GOOGLE_BUDGET_USD", "").strip()
    google_budget_usd = float(raw_budget) if raw_budget else None

    return Config(
        bot_token=bot_token,
        anthropic_api_key=anthropic_api_key,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
        google_project_id=google_project_id,
        google_location=os.getenv("GOOGLE_LOCATION", "us-central1"),
        google_budget_usd=google_budget_usd,
        default_provider=os.getenv("DEFAULT_PROVIDER", "anthropic").strip().lower(),
        default_target_lang=os.getenv("DEFAULT_TARGET_LANG", "English"),
        db_path=os.getenv("DB_PATH", "data/bot.db"),
    )
