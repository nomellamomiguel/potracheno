"""Статус: суммы предстоящих платежей (по валютам) и ближайший платёж."""
from __future__ import annotations

import calendar
import datetime as dt

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import Nav, StatusCB
from bot.db import repo
from bot.db.models import Payment, User
from bot.keyboards import status_menu_kb
from bot.services.humanize import due_phrase, esc
from bot.services.money import format_money
from bot.services.recurrence import next_occurrences
from bot.services.reminders import zone

router = Router(name="status")


async def _show_menu(event: Message | CallbackQuery) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(texts.STATUS_MENU, reply_markup=status_menu_kb())
        except TelegramBadRequest:
            await event.message.answer(texts.STATUS_MENU, reply_markup=status_menu_kb())
        await event.answer()
    else:
        await event.answer(texts.STATUS_MENU, reply_markup=status_menu_kb())


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_menu(message)


@router.callback_query(Nav.filter(F.action == "status"))
async def nav_status(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_menu(cb)


def _window(period: str, today: dt.date) -> tuple[dt.date, dt.date, str]:
    if period == "week":
        return today, today + dt.timedelta(days=6 - today.weekday()), texts.STATUS_WEEK_TITLE
    if period == "month":
        last = calendar.monthrange(today.year, today.month)[1]
        return today, today.replace(day=last), texts.STATUS_MONTH_TITLE
    return today, today + dt.timedelta(days=365), texts.STATUS_YEAR_TITLE


def _occurrences_in(payment: Payment, start: dt.date, end: dt.date) -> list[dt.date]:
    occ = next_occurrences(
        freq=payment.freq.value,
        anchor_date=payment.anchor_date,
        interval=payment.interval,
        by_weekdays=payment.by_weekdays,
        by_monthdays=payment.by_monthdays,
        by_months=payment.by_months,
        after=start - dt.timedelta(days=1),
        count=400,
    )
    return [d for d in occ if d <= end]


@router.callback_query(StatusCB.filter(F.period == "nearest"))
async def status_nearest(cb: CallbackQuery, session, user: User) -> None:
    payments = [p for p in await repo.list_payments(session, user.id) if p.next_due_date]
    if not payments:
        await _edit(cb, texts.NEAREST_NONE)
        return
    p = min(payments, key=lambda x: x.next_due_date)
    text = (
        f"{texts.NEAREST_TITLE}\n"
        f"💳 <b>{esc(p.title)}</b> — <b>{format_money(p.amount_minor, p.currency)}</b>\n"
        f"{due_phrase(p.next_due_date)}"
    )
    await _edit(cb, text)


@router.callback_query(StatusCB.filter())
async def status_period(cb: CallbackQuery, callback_data: StatusCB, session, user: User) -> None:
    period = callback_data.period
    today = dt.datetime.now(zone(user.tz)).date()
    start, end, title = _window(period, today)
    payments = await repo.list_payments(session, user.id)

    items: list[tuple[dt.date, Payment]] = []
    totals: dict[str, int] = {}
    for p in payments:
        for d in _occurrences_in(p, start, end):
            items.append((d, p))
            totals[p.currency] = totals.get(p.currency, 0) + p.amount_minor

    if not items:
        await _edit(cb, f"{title}\n{texts.STATUS_EMPTY}")
        return

    items.sort(key=lambda x: x[0])
    totals_str = ", ".join(format_money(v, c) for c, v in totals.items())

    # уникальные названия платежей в порядке первого появления
    names: list[str] = []
    seen: set[str] = set()
    for _, p in items:
        if p.title not in seen:
            seen.add(p.title)
            names.append(esc(p.title))

    lines = [
        title,
        texts.STATUS_TOTALS.format(totals=totals_str),
        "",
        texts.STATUS_PAYMENTS.format(names=", ".join(names)),
    ]
    await _edit(cb, "\n".join(lines))


async def _edit(cb: CallbackQuery, text: str) -> None:
    try:
        await cb.message.edit_text(text, reply_markup=status_menu_kb())
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=status_menu_kb())
    await cb.answer()
