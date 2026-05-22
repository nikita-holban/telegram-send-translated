from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

import aiosqlite


class Storage:
    """Per-user settings persisted in SQLite (target language and provider)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS user_settings ("
            "user_id INTEGER PRIMARY KEY, "
            "target_lang TEXT, "
            "provider TEXT)"
        )
        # Migrate databases created before the provider column existed.
        try:
            await self._db.execute(
                "ALTER TABLE user_settings ADD COLUMN provider TEXT"
            )
        except sqlite3.OperationalError:
            pass  # column already present
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS usage_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "timestamp TEXT NOT NULL, "
            "provider TEXT NOT NULL, "
            "model TEXT, "
            "chars INTEGER, "
            "input_tokens INTEGER, "
            "output_tokens INTEGER)"
        )
        await self._db.commit()

    async def log_google_usage(self, chars: int) -> None:
        db = self._require_db()
        await db.execute(
            "INSERT INTO usage_log (timestamp, provider, chars) VALUES (?, 'google', ?)",
            (datetime.now(timezone.utc).isoformat(), chars),
        )
        await db.commit()

    async def google_chars_used(self) -> int:
        db = self._require_db()
        async with db.execute(
            "SELECT COALESCE(SUM(chars), 0) FROM usage_log WHERE provider = 'google'"
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def log_anthropic_usage(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> None:
        db = self._require_db()
        await db.execute(
            "INSERT INTO usage_log (timestamp, provider, model, input_tokens, output_tokens) "
            "VALUES (?, 'anthropic', ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), model, input_tokens, output_tokens),
        )
        await db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def get_target_lang(self, user_id: int) -> str | None:
        return await self._get(user_id, "target_lang")

    async def set_target_lang(self, user_id: int, target_lang: str) -> None:
        await self._set(user_id, "target_lang", target_lang)

    async def get_provider(self, user_id: int) -> str | None:
        return await self._get(user_id, "provider")

    async def set_provider(self, user_id: int, provider: str) -> None:
        await self._set(user_id, "provider", provider)

    async def _get(self, user_id: int, column: str) -> str | None:
        db = self._require_db()
        async with db.execute(
            f"SELECT {column} FROM user_settings WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

    async def _set(self, user_id: int, column: str, value: str) -> None:
        db = self._require_db()
        await db.execute(
            f"INSERT INTO user_settings (user_id, {column}) VALUES (?, ?) "
            f"ON CONFLICT(user_id) DO UPDATE SET {column} = excluded.{column}",
            (user_id, value),
        )
        await db.commit()

    def _require_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage.connect() must be called first")
        return self._db
