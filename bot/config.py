"""Настройки приложения, читаются из переменных окружения / .env."""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    admin_chat_id: int | None = None

    @field_validator("admin_chat_id", mode="before")
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        # пустой ADMIN_CHAT_ID= в .env трактуем как «не задан»
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        return v
    db_url: str = "sqlite+aiosqlite:///data/potracheno.db"
    default_tz: str = "Europe/Moscow"
    default_notify_time: str = "10:00"  # HH:MM, локальное время напоминаний по умолчанию
    scheduler_tick_seconds: int = 60
    roll_hour_utc: int = 1  # час (UTC) ежедневного roll-job'а

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def notify_time(self) -> dt.time:
        hh, mm = self.default_notify_time.split(":")
        return dt.time(int(hh), int(mm))


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
