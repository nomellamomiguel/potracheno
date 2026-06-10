"""Действия из напоминания: Оплатил, Отложить (снуз).

«Изменить» обрабатывает edit_payment, «Больше не плачу» (archive) — list_payments.
Если на напоминание не ответили — платёж остаётся активным и roll перенесёт его на
следующую дату (продолжаем напоминать).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from bot import texts
from bot.callbacks import PaymentCB, SnoozeCB
from bot.db import repo
from bot.db.models import User
from bot.keyboards import snooze_kb
from bot.services import reminders as rsvc
from bot.services.dates import format_date

router = Router(name="reminders_cb")

_SNOOZE_WHEN = {1: "завтра", 3: "через 3 дня", 7: "через неделю"}


async def _drop_markup(cb: CallbackQuery) -> None:
    try:
        await cb.message.edit_reply_markup()
    except TelegramBadRequest:
        pass


@router.callback_query(PaymentCB.filter(F.action == "pay"))
async def mark_paid(cb: CallbackQuery, callback_data: PaymentCB, session, user: User) -> None:
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    nxt = await rsvc.advance_payment(session, payment, user)
    await _drop_markup(cb)
    if nxt is None:
        await cb.message.answer(texts.PAID_DONE_LAST)
    else:
        await cb.message.answer(texts.PAID_DONE.format(date=format_date(nxt)))
    await cb.answer("Готово ✅")


@router.callback_query(PaymentCB.filter(F.action == "snooze"))
async def snooze_menu(cb: CallbackQuery, callback_data: PaymentCB, session, user: User) -> None:
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    try:
        await cb.message.edit_reply_markup(reply_markup=snooze_kb(payment.id))
    except TelegramBadRequest:
        pass
    await cb.answer()


@router.callback_query(SnoozeCB.filter())
async def snooze_do(cb: CallbackQuery, callback_data: SnoozeCB, session, user: User) -> None:
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    await rsvc.snooze_payment(session, payment, user, callback_data.days)
    when = _SNOOZE_WHEN.get(callback_data.days, f"через {callback_data.days} дн.")
    await _drop_markup(cb)
    await cb.message.answer(texts.SNOOZE_DONE.format(when=when))
    await cb.answer()
