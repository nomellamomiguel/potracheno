"""Мастер добавления платежа (FSM «вопрос-ответ»)."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import (
    CategoryCB,
    ConfirmCB,
    CurrencyCB,
    FreqCB,
    Nav,
    ReminderToggleCB,
    ToggleCB,
    WizardCB,
)
from bot.db import repo
from bot.db.models import Freq, Payment, PaymentStatus, User
from bot.handlers.commands import show_main_menu
from bot.keyboards import (
    after_save_kb,
    category_kb,
    confirm_kb,
    currency_kb,
    currency_more_kb,
    freq_kb,
    months_kb,
    payment_card_kb,
    reminders_kb,
    weekdays_kb,
)
from bot.services.dates import parse_date, parse_monthdays
from bot.services.humanize import payment_card
from bot.services.money import is_valid_iso, parse_amount
from bot.services.recurrence import next_due_for_payment
from bot.services.reminders import set_initial_due_and_reminders
from bot.states import AddPayment
from bot.texts import CATEGORIES

router = Router(name="add_payment")


async def _send(event: Message | CallbackQuery, text: str, kb=None) -> None:
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer(text, reply_markup=kb)
    if isinstance(event, CallbackQuery):
        await event.answer()


async def _edit_markup(cb: CallbackQuery, kb) -> None:
    try:
        await cb.message.edit_reply_markup(reply_markup=kb)
    except TelegramBadRequest:
        pass
    await cb.answer()


async def _begin(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddPayment.title)
    await _send(event, texts.ADD_TITLE)


@router.callback_query(Nav.filter(F.action == "add"))
async def add_from_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await _begin(cb, state)


@router.message(Command("add"))
async def add_from_cmd(message: Message, state: FSMContext) -> None:
    await _begin(message, state)


@router.message(AddPayment.title)
async def step_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(texts.ADD_TITLE)
        return
    await state.update_data(title=title[:255])
    await state.set_state(AddPayment.category)
    await message.answer(texts.ADD_CATEGORY, reply_markup=category_kb())


@router.callback_query(AddPayment.category, CategoryCB.filter())
async def step_category(cb: CallbackQuery, callback_data: CategoryCB, state: FSMContext) -> None:
    if callback_data.idx == -1:
        await state.set_state(AddPayment.category_custom)
        await _send(cb, texts.ADD_CATEGORY_CUSTOM)
        return
    await state.update_data(category=CATEGORIES[callback_data.idx])
    await _ask_currency(cb, state)


@router.message(AddPayment.category_custom)
async def step_category_custom(message: Message, state: FSMContext) -> None:
    await state.update_data(category=((message.text or "").strip()[:64] or None))
    await _ask_currency(message, state)


async def _ask_currency(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddPayment.currency)
    await _send(event, texts.ADD_CURRENCY, currency_kb())


@router.callback_query(AddPayment.currency, CurrencyCB.filter())
async def step_currency(cb: CallbackQuery, callback_data: CurrencyCB, state: FSMContext) -> None:
    code = callback_data.code
    if code == "more":
        await _edit_markup(cb, currency_more_kb())
        return
    if code == "back":
        await _edit_markup(cb, currency_kb())
        return
    if code == "custom":
        await state.set_state(AddPayment.currency_custom)
        await _send(cb, texts.ADD_CURRENCY_CUSTOM)
        return
    await state.update_data(currency=code)
    await _ask_amount(cb, state)


@router.message(AddPayment.currency_custom)
async def step_currency_custom(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip().upper()
    if not is_valid_iso(code):
        await message.answer(texts.ADD_CURRENCY_INVALID)
        return
    await state.update_data(currency=code)
    await _ask_amount(message, state)


async def _ask_amount(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddPayment.amount)
    await _send(event, texts.ADD_AMOUNT)


@router.message(AddPayment.amount)
async def step_amount(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    minor = parse_amount(message.text or "", data.get("currency", "USD"))
    if minor is None:
        await message.answer(texts.ADD_AMOUNT_INVALID)
        return
    await state.update_data(amount_minor=minor)
    await state.set_state(AddPayment.freq)
    await message.answer(texts.ADD_FREQ, reply_markup=freq_kb())


@router.callback_query(AddPayment.freq, FreqCB.filter())
async def step_freq(cb: CallbackQuery, callback_data: FreqCB, state: FSMContext) -> None:
    freq = callback_data.value
    await state.update_data(
        freq=freq, interval=1, by_weekdays=None, by_monthdays=None,
        by_months=None, quarter=False, sel=[],
    )
    if freq == "week":
        await state.set_state(AddPayment.week_days)
        await _send(cb, texts.ADD_WEEK_DAYS, weekdays_kb(set()))
    elif freq == "month":
        await state.set_state(AddPayment.month_days)
        await _send(cb, texts.ADD_MONTH_DAYS)
    elif freq == "quarter":
        await state.update_data(quarter=True)
        await state.set_state(AddPayment.month_days)
        await _send(cb, texts.ADD_QUARTER_DAYS)
    elif freq == "year":
        await state.set_state(AddPayment.year_months)
        await _send(cb, texts.ADD_YEAR_MONTHS, months_kb(set()))
    else:  # once
        await state.set_state(AddPayment.once_date)
        await _send(cb, texts.ADD_ONCE_DATE)


@router.callback_query(AddPayment.week_days, ToggleCB.filter(F.group == "wd"))
async def step_week_toggle(cb: CallbackQuery, callback_data: ToggleCB, state: FSMContext) -> None:
    data = await state.get_data()
    sel = set(data.get("sel", []))
    sel.symmetric_difference_update({callback_data.value})
    await state.update_data(sel=sorted(sel))
    await _edit_markup(cb, weekdays_kb(sel))


@router.callback_query(AddPayment.week_days, WizardCB.filter(F.action == "done_week"))
async def step_week_done(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    sel = sorted(set(data.get("sel", [])))
    await state.update_data(by_weekdays=sel or None)
    await _ask_reminders(cb, state)


@router.message(AddPayment.month_days)
async def step_month_days(message: Message, state: FSMContext) -> None:
    days = parse_monthdays(message.text or "")
    if not days:
        await message.answer(texts.ADD_MONTH_DAYS_INVALID)
        return
    data = await state.get_data()
    if data.get("quarter"):
        days = days[:1]
    await state.update_data(by_monthdays=days)
    await _ask_reminders(message, state)


@router.callback_query(AddPayment.year_months, ToggleCB.filter(F.group == "mo"))
async def step_year_toggle(cb: CallbackQuery, callback_data: ToggleCB, state: FSMContext) -> None:
    data = await state.get_data()
    sel = set(data.get("sel", []))
    sel.symmetric_difference_update({callback_data.value})
    await state.update_data(sel=sorted(sel))
    await _edit_markup(cb, months_kb(sel))


@router.callback_query(AddPayment.year_months, WizardCB.filter(F.action == "done_year"))
async def step_year_done(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    sel = sorted(set(data.get("sel", [])))
    if not sel:
        await cb.answer("Отметь хотя бы один месяц", show_alert=True)
        return
    await state.update_data(by_months=sel)
    await state.set_state(AddPayment.year_day)
    await _send(cb, texts.ADD_YEAR_DAY)


@router.message(AddPayment.year_day)
async def step_year_day(message: Message, state: FSMContext) -> None:
    days = parse_monthdays(message.text or "")
    if not days:
        await message.answer(texts.ADD_MONTH_DAYS_INVALID)
        return
    await state.update_data(by_monthdays=days[:1])
    await _ask_reminders(message, state)


@router.message(AddPayment.once_date)
async def step_once_date(message: Message, state: FSMContext) -> None:
    d = parse_date(message.text or "")
    if not d:
        await message.answer(texts.ADD_DATE_INVALID)
        return
    await state.update_data(anchor_iso=d.isoformat())
    await _ask_reminders(message, state)


async def _ask_reminders(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.update_data(reminders=[])
    await state.set_state(AddPayment.reminders)
    await _send(event, texts.ADD_REMINDERS, reminders_kb([]))


@router.callback_query(AddPayment.reminders, ReminderToggleCB.filter())
async def step_rem_toggle(cb: CallbackQuery, callback_data: ReminderToggleCB, state: FSMContext) -> None:
    data = await state.get_data()
    rem = list(data.get("reminders", []))
    days = callback_data.days
    if days in rem:
        rem.remove(days)
    elif len(rem) >= 3:
        await cb.answer(texts.ADD_REMINDERS_LIMIT, show_alert=True)
        return
    else:
        rem.append(days)
    rem = sorted(set(rem), reverse=True)
    await state.update_data(reminders=rem)
    await _edit_markup(cb, reminders_kb(rem))


@router.callback_query(AddPayment.reminders, WizardCB.filter(F.action == "rem_custom"))
async def step_rem_custom_prompt(cb: CallbackQuery) -> None:
    await _send(cb, texts.ADD_REMINDERS_CUSTOM)


@router.message(AddPayment.reminders)
async def step_rem_custom_value(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(texts.ADD_REMINDERS_CUSTOM)
        return
    days = int(raw)
    data = await state.get_data()
    rem = list(data.get("reminders", []))
    if days not in rem:
        if len(rem) >= 3:
            await message.answer(texts.ADD_REMINDERS_LIMIT)
            return
        rem.append(days)
    rem = sorted(set(rem), reverse=True)
    await state.update_data(reminders=rem)
    await message.answer(texts.ADD_REMINDERS, reply_markup=reminders_kb(rem))


@router.callback_query(AddPayment.reminders, WizardCB.filter(F.action == "done_reminders"))
async def step_rem_done(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rem = sorted(set(data.get("reminders", [])), reverse=True)
    if not rem:
        rem = [1]  # дефолт по договорённости — «за 1 день»
    await state.update_data(reminder_offsets=[{"days": d} for d in rem])
    await _show_confirm(cb, state)


def _preview(data: dict):
    iso = data.get("anchor_iso")
    anchor = dt.date.fromisoformat(iso) if iso else dt.date.today()
    ns = SimpleNamespace(
        title=data.get("title", ""),
        category=data.get("category"),
        currency=data.get("currency", "USD"),
        amount_minor=data.get("amount_minor", 0),
        freq=data.get("freq", "month"),
        interval=data.get("interval", 1),
        by_weekdays=data.get("by_weekdays"),
        by_monthdays=data.get("by_monthdays"),
        by_months=data.get("by_months"),
        reminder_offsets=data.get("reminder_offsets", []),
        status="active",
        anchor_date=anchor,
        next_due_date=None,
    )
    ns.next_due_date = next_due_for_payment(ns, after=dt.date.today() - dt.timedelta(days=1))
    return ns


async def _show_confirm(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    card = payment_card(_preview(data))
    await state.set_state(AddPayment.confirm)
    await _send(event, texts.ADD_CONFIRM.format(card=card), confirm_kb())


@router.callback_query(AddPayment.confirm, ConfirmCB.filter(F.action == "cancel"))
async def confirm_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await cb.message.edit_reply_markup()
    except TelegramBadRequest:
        pass
    await show_main_menu(cb, text=texts.CANCELLED)


@router.callback_query(AddPayment.confirm, ConfirmCB.filter(F.action == "save"))
async def confirm_save(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    data = await state.get_data()
    iso = data.get("anchor_iso")
    anchor = dt.date.fromisoformat(iso) if iso else dt.date.today()
    edit_id = data.get("edit_id")

    if edit_id:  # режим правки — обновляем существующий платёж
        payment = await repo.get_user_payment(session, edit_id, user.id)
        if not payment:
            await state.clear()
            await cb.message.answer(texts.PAYMENT_GONE)
            await cb.answer()
            return
        payment.title = data["title"]
        payment.category = data.get("category")
        payment.currency = data["currency"]
        payment.amount_minor = data["amount_minor"]
        payment.freq = Freq(data["freq"])
        payment.interval = data.get("interval", 1)
        payment.by_weekdays = data.get("by_weekdays")
        payment.by_monthdays = data.get("by_monthdays")
        payment.by_months = data.get("by_months")
        payment.anchor_date = anchor
        payment.reminder_offsets = data.get("reminder_offsets", [])
        await session.flush()
        await repo.clear_pending_reminders(session, payment.id)
        due = await set_initial_due_and_reminders(session, payment, user)
        await state.clear()
        try:
            await cb.message.edit_reply_markup()
        except TelegramBadRequest:
            pass
        if due is None:
            await cb.message.answer(texts.NO_NEXT_DATE)
        await cb.message.answer(
            "Изменения сохранены ✅\n\n" + payment_card(payment),
            reply_markup=payment_card_kb(payment),
        )
        await cb.answer()
        return

    payment = Payment(
        user_id=user.id,
        title=data["title"],
        category=data.get("category"),
        currency=data["currency"],
        amount_minor=data["amount_minor"],
        freq=Freq(data["freq"]),
        interval=data.get("interval", 1),
        by_weekdays=data.get("by_weekdays"),
        by_monthdays=data.get("by_monthdays"),
        by_months=data.get("by_months"),
        anchor_date=anchor,
        reminder_offsets=data.get("reminder_offsets", []),
        status=PaymentStatus.active,
    )
    session.add(payment)
    await session.flush()
    due = await set_initial_due_and_reminders(session, payment, user)
    await state.clear()
    try:
        await cb.message.edit_reply_markup()
    except TelegramBadRequest:
        pass
    if due is None:
        await cb.message.answer(texts.NO_NEXT_DATE)
    await cb.message.answer(texts.SAVED, reply_markup=after_save_kb())
    await cb.answer()
