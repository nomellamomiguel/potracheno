"""Правки платежа: меню полей, простые поля текстом, периодичность/напоминания — через мастер."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import EditFieldCB, PaymentCB
from bot.db import repo
from bot.db.models import Payment, User
from bot.keyboards import edit_fields_kb, freq_kb, payment_card_kb, reminders_kb, with_nav
from bot.services.humanize import payment_card
from bot.services.money import is_valid_iso, parse_amount
from bot.states import AddPayment, EditPayment

router = Router(name="edit_payment")

# Поля, которые правим простым вводом текста -> подсказка
SCALAR_PROMPTS = {
    "title": texts.ADD_TITLE,
    "category": texts.ADD_CATEGORY_CUSTOM,
    "currency": texts.ADD_CURRENCY_CUSTOM,
    "amount": texts.ADD_AMOUNT,
}


async def _seed_wizard(state: FSMContext, payment: Payment) -> None:
    """Заполняет FSM текущими значениями платежа для повторного прохода мастера."""
    await state.update_data(
        edit_id=payment.id,
        title=payment.title,
        category=payment.category,
        currency=payment.currency,
        amount_minor=payment.amount_minor,
        freq=payment.freq.value,
        interval=payment.interval,
        by_weekdays=payment.by_weekdays,
        by_monthdays=payment.by_monthdays,
        by_months=payment.by_months,
        anchor_iso=payment.anchor_date.isoformat(),
        reminders=[int(o.get("days", 0)) for o in (payment.reminder_offsets or [])],
        reminder_offsets=payment.reminder_offsets or [],
        sel=[],
        quarter=(payment.freq.value == "quarter"),
        history=[],
    )


@router.callback_query(PaymentCB.filter(F.action == "edit"))
async def edit_menu(cb: CallbackQuery, callback_data: PaymentCB, state: FSMContext, session, user: User) -> None:
    await state.clear()
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    text = "Что изменить?\n\n" + payment_card(payment)
    try:
        await cb.message.edit_text(text, reply_markup=edit_fields_kb(payment.id))
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=edit_fields_kb(payment.id))
    await cb.answer()


@router.callback_query(EditFieldCB.filter())
async def edit_field(cb: CallbackQuery, callback_data: EditFieldCB, state: FSMContext, session, user: User) -> None:
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    field = callback_data.field
    if field in SCALAR_PROMPTS:
        await state.set_state(EditPayment.waiting_value)
        await state.update_data(edit_field=field, edit_id=payment.id)
        await cb.message.answer(SCALAR_PROMPTS[field])
        await cb.answer()
        return
    # периодичность / напоминания — переиспользуем мастер добавления
    await _seed_wizard(state, payment)
    if field == "freq":
        await state.set_state(AddPayment.freq)
        await cb.message.answer(texts.ADD_FREQ, reply_markup=with_nav(freq_kb(), back=False))
    else:  # reminders
        await state.set_state(AddPayment.reminders)
        data = await state.get_data()
        await cb.message.answer(
            texts.ADD_REMINDERS,
            reply_markup=with_nav(reminders_kb(data.get("reminders", [])), back=False),
        )
    await cb.answer()


@router.message(EditPayment.waiting_value)
async def edit_value(message: Message, state: FSMContext, session, user: User) -> None:
    data = await state.get_data()
    field = data.get("edit_field")
    payment = await repo.get_user_payment(session, data.get("edit_id"), user.id)
    if not payment:
        await state.clear()
        await message.answer(texts.PAYMENT_GONE)
        return
    text = (message.text or "").strip()
    if field == "title":
        if not text:
            await message.answer(texts.ADD_TITLE)
            return
        payment.title = text[:255]
    elif field == "category":
        payment.category = text[:64] or None
    elif field == "currency":
        code = text.upper()
        if not is_valid_iso(code):
            await message.answer(texts.ADD_CURRENCY_INVALID)
            return
        payment.currency = code
    elif field == "amount":
        minor = parse_amount(text, payment.currency)
        if minor is None:
            await message.answer(texts.ADD_AMOUNT_INVALID)
            return
        payment.amount_minor = minor
    await session.flush()
    await state.clear()
    await message.answer(
        "Готово ✅\n\n" + payment_card(payment), reply_markup=payment_card_kb(payment)
    )
