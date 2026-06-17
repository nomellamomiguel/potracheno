"""Точка входа: бот, диспетчер, middleware, роутеры, планировщик, long-polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import get_settings
from bot.db.base import init_db
from bot.handlers import (
    add_payment,
    commands,
    edit_payment,
    faq,
    feedback,
    list_payments,
    onboarding,
    payment_methods,
    reminders_cb,
    settings as settings_handler,
    status,
)
from bot.middlewares import DBSessionMiddleware
from bot.services.scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("potracheno")

BOT_COMMANDS = [
    BotCommand(command="add", description="Добавить платёж"),
    BotCommand(command="list", description="Мои платежи"),
    BotCommand(command="status", description="Статус и суммы"),
    BotCommand(command="settings", description="Настройки"),
    BotCommand(command="feedback", description="Обратная связь"),
    BotCommand(command="help", description="Помощь"),
]


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(DBSessionMiddleware())
    dp.callback_query.middleware(DBSessionMiddleware())
    # порядок важен: команды → онбординг → фичи → fallback
    dp.include_router(commands.router)
    dp.include_router(onboarding.router)
    dp.include_router(add_payment.router)
    dp.include_router(list_payments.router)
    dp.include_router(edit_payment.router)
    dp.include_router(status.router)
    dp.include_router(reminders_cb.router)
    dp.include_router(feedback.router)
    dp.include_router(settings_handler.router)
    dp.include_router(payment_methods.router)
    dp.include_router(faq.router)
    dp.include_router(commands.fallback_router)
    return dp


async def main() -> None:
    settings = get_settings()
    await init_db()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    scheduler = setup_scheduler(bot)

    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except Exception:  # noqa: BLE001 — не критично при старте
        log.warning("Не удалось установить меню команд", exc_info=True)

    scheduler.start()
    log.info("Бот «Потрачено» запущен, планировщик активен.")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
