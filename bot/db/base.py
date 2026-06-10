"""Async-движок SQLAlchemy, фабрика сессий и инициализация схемы."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from bot.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    """Создаёт каталог для файла SQLite, если его ещё нет."""
    if url.startswith("sqlite") and ":///" in url:
        path_part = url.split(":///", 1)[1]
        if path_part and path_part != ":memory:":
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)


_settings = get_settings()
_ensure_sqlite_dir(_settings.db_url)

engine = create_async_engine(_settings.db_url, echo=False, future=True)
SessionMaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Создаёт таблицы по моделям (для MVP вместо миграций)."""
    from bot.db import models  # noqa: F401  — регистрирует мапперы

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
