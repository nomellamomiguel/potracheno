"""Middleware: на каждый апдейт — сессия БД и гарантированная строка пользователя."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from bot.db import repo
from bot.db.base import SessionMaker


class DBSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with SessionMaker() as session:
            data["session"] = session
            tg_user: TgUser | None = data.get("event_from_user")
            if tg_user is not None and not tg_user.is_bot:
                chat = data.get("event_chat")
                chat_id = chat.id if chat is not None else tg_user.id
                data["user"] = await repo.get_or_create_user(
                    session,
                    user_id=tg_user.id,
                    chat_id=chat_id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                )
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
