"""APScheduler: тик отправки напоминаний и ежедневный roll дат."""
from __future__ import annotations

import datetime as dt
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot import texts
from bot.config import get_settings
from bot.db import repo
from bot.db.base import SessionMaker
from bot.db.models import Payment, ReminderLog, ReminderStatus, User
from bot.keyboards import reminder_actions_kb
from bot.services import reminders as rsvc
from bot.services.dates import format_date
from bot.services.humanize import esc
from bot.services.money import format_money

log = logging.getLogger(__name__)


def _when_phrase(due_date: dt.date, user: User) -> str:
    today_local = dt.datetime.now(rsvc.zone(user.tz)).date()
    left = (due_date - today_local).days
    if left <= 0:
        return "Сегодня"
    if left == 1:
        return "Завтра"
    return f"Через {left} дн."


async def _send_reminder(bot: Bot, user: User, payment: Payment, r: ReminderLog) -> None:
    cat = f" · {esc(payment.category)}" if payment.category else ""
    text = texts.REMINDER.format(
        when=_when_phrase(r.due_date, user),
        title=esc(payment.title),
        cat=cat,
        amount=format_money(payment.amount_minor, payment.currency),
        date=format_date(r.due_date),
    )
    await bot.send_message(
        user.chat_id, text, reply_markup=reminder_actions_kb(payment.id)
    )


async def process_due_reminders(bot: Bot) -> None:
    async with SessionMaker() as session:
        rows = await repo.due_reminders(session, rsvc.utcnow())
        for r in rows:
            payment = r.payment
            user = payment.user
            try:
                await _send_reminder(bot, user, payment, r)
                r.sent_at = rsvc.utcnow()
                r.status = ReminderStatus.sent
            except TelegramForbiddenError:
                # пользователь заблокировал бота — не отправляем, помечаем пропущенным
                r.sent_at = rsvc.utcnow()
                r.status = ReminderStatus.skipped
            except Exception:  # noqa: BLE001 — единичный сбой не должен валить весь тик
                log.exception("Не удалось отправить напоминание id=%s", r.id)
        await session.commit()


async def roll_occurrences(bot: Bot) -> None:
    async with SessionMaker() as session:
        for payment in await repo.all_active_payments(session):
            try:
                await rsvc.roll_payment(session, payment, payment.user)
            except Exception:  # noqa: BLE001
                log.exception("roll_payment failed id=%s", payment.id)
        await session.commit()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    s = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        process_due_reminders,
        "interval",
        seconds=s.scheduler_tick_seconds,
        args=[bot],
        id="tick",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        roll_occurrences,
        "cron",
        hour=s.roll_hour_utc,
        minute=0,
        args=[bot],
        id="roll",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
