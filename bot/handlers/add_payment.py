"""Мастер добавления платежа (FSM «вопрос-ответ») с навигацией Назад/Отменить.

Навигация — через стек истории шагов в FSM data["history"]:
  * переход вперёд (_goto) кладёт текущий шаг в стек и показывает следующий;
  * «⬅️ Назад» (WizardNavCB back) снимает шаг со стека и заново показывает его;
  * «✖️ Отменить» (WizardNavCB cancel) — state.clear() + главное меню.
Показ каждого шага — отдельная функция show_* (см. STEP_SHOW).
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import (
    AddMethodCB,
    CategoryCB,
    ConfirmCB,
    CurrencyCB,
    FreqCB,
    Nav,
    ReminderToggleCB,
    ToggleCB,
    WizardCB,
    WizardNavCB,
)
from bot.db import repo
from bot.db.models import Freq, Payment, PaymentStatus, User
from bot.handlers.commands import show_main_menu
from bot.keyboards import (
    add_method_kb,
    after_save_kb,
    category_kb,
    confirm_kb,
    currency_kb,
    currency_more_kb,
    freq_kb,
    months_kb,
    payment_card_kb,
    reminders_kb,
    title_nav_kb,
    weekdays_kb,
    with_nav,
    wizard_nav_kb,
)
from bot.services.dates import parse_date, parse_monthdays
from bot.services.humanize import payment_card
from bot.services.money import is_valid_iso, parse_amount
from bot.services.recurrence import next_due_for_payment
from bot.services.reminders import set_initial_due_and_reminders
from bot.states import AddPayment
from bot.texts import CATEGORIES

router = Router(name="add_payment")


# --- низкоуровневые помощники ---
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


async def _nav_back(state: FSMContext) -> bool:
    """Есть ли куда возвращаться (непустой стек истории)."""
    data = await state.get_data()
    return bool(data.get("history"))


async def _push_current(state: FSMContext) -> None:
    current = await state.get_state()
    data = await state.get_data()
    hist = list(data.get("history", []))
    if current:
        hist.append(current)
    await state.update_data(history=hist)


async def _goto(event, state: FSMContext, show, session=None, user: User | None = None) -> None:
    """Переход вперёд: текущий шаг в стек, затем показать следующий."""
    await _push_current(state)
    await show(event, state, session, user)


# --- предпросмотр платежа для шага подтверждения ---
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
        payment_method=data.get("payment_method"),
        status="active",
        anchor_date=anchor,
        next_due_date=None,
    )
    ns.next_due_date = next_due_for_payment(ns, after=dt.date.today() - dt.timedelta(days=1))
    return ns


# --- функции показа шагов (set state + prompt + клавиатура с навигацией) ---
async def show_title(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.title)
    await _send(event, texts.ADD_TITLE, title_nav_kb())


async def show_category(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.category)
    await _send(event, texts.ADD_CATEGORY, with_nav(category_kb(), back=await _nav_back(state)))


async def show_category_custom(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.category_custom)
    await _send(event, texts.ADD_CATEGORY_CUSTOM, wizard_nav_kb(await _nav_back(state)))


async def show_currency(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.currency)
    await _send(event, texts.ADD_CURRENCY, with_nav(currency_kb(), back=await _nav_back(state)))


async def show_currency_custom(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.currency_custom)
    await _send(event, texts.ADD_CURRENCY_CUSTOM, wizard_nav_kb(await _nav_back(state)))


async def show_amount(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.amount)
    await _send(event, texts.ADD_AMOUNT, wizard_nav_kb(await _nav_back(state)))


async def show_freq(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.freq)
    await _send(event, texts.ADD_FREQ, with_nav(freq_kb(), back=await _nav_back(state)))


async def show_week_days(event, state, session=None, user=None) -> None:
    await state.update_data(sel=[])  # сброс галочек при (повторном) входе
    await state.set_state(AddPayment.week_days)
    await _send(event, texts.ADD_WEEK_DAYS, with_nav(weekdays_kb(set()), back=await _nav_back(state)))


async def show_month_days(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.month_days)
    data = await state.get_data()
    prompt = texts.ADD_QUARTER_DAYS if data.get("quarter") else texts.ADD_MONTH_DAYS
    await _send(event, prompt, wizard_nav_kb(await _nav_back(state)))


async def show_year_months(event, state, session=None, user=None) -> None:
    await state.update_data(sel=[])
    await state.set_state(AddPayment.year_months)
    await _send(event, texts.ADD_YEAR_MONTHS, with_nav(months_kb(set()), back=await _nav_back(state)))


async def show_year_day(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.year_day)
    await _send(event, texts.ADD_YEAR_DAY, wizard_nav_kb(await _nav_back(state)))


async def show_once_date(event, state, session=None, user=None) -> None:
    await state.set_state(AddPayment.once_date)
    await _send(event, texts.ADD_ONCE_DATE, wizard_nav_kb(await _nav_back(state)))


async def show_reminders(event, state, session=None, user=None) -> None:
    await state.update_data(reminders=[])  # сброс выбранных напоминаний при (повторном) входе
    await state.set_state(AddPayment.reminders)
    await _send(event, texts.ADD_REMINDERS, with_nav(reminders_kb([]), back=await _nav_back(state)))


async def show_payment_method(event, state, session=None, user=None) -> None:
    methods = await repo.list_payment_methods(session, user.id)
    await state.set_state(AddPayment.payment_method)
    await _send(event, texts.ADD_METHOD, with_nav(add_method_kb(methods), back=await _nav_back(state)))


async def show_confirm(event, state, session=None, user=None) -> None:
    data = await state.get_data()
    card = payment_card(_preview(data))
    await state.set_state(AddPayment.confirm)
    # на confirm «Отменить» уже есть в confirm_kb -> добавляем только «Назад»
    await _send(event, texts.ADD_CONFIRM.format(card=card), with_nav(confirm_kb(), back=True, cancel=False))


STEP_SHOW = {
    AddPayment.title.state: show_title,
    AddPayment.category.state: show_category,
    AddPayment.category_custom.state: show_category_custom,
    AddPayment.currency.state: show_currency,
    AddPayment.currency_custom.state: show_currency_custom,
    AddPayment.amount.state: show_amount,
    AddPayment.freq.state: show_freq,
    AddPayment.week_days.state: show_week_days,
    AddPayment.month_days.state: show_month_days,
    AddPayment.year_months.state: show_year_months,
    AddPayment.year_day.state: show_year_day,
    AddPayment.once_date.state: show_once_date,
    AddPayment.reminders.state: show_reminders,
    AddPayment.payment_method.state: show_payment_method,
}


async def _begin(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddPayment.title)
    await state.set_data({"history": []})
    await _send(event, texts.ADD_TITLE, title_nav_kb())


# --- навигация: Отмена и Назад (в любом состоянии AddPayment) ---
@router.callback_query(StateFilter(AddPayment), WizardNavCB.filter(F.action == "cancel"))
async def wizard_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await cb.message.edit_reply_markup()
    except TelegramBadRequest:
        pass
    await show_main_menu(cb, text=texts.CANCELLED)


@router.callback_query(StateFilter(AddPayment), WizardNavCB.filter(F.action == "back"))
async def wizard_back(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    data = await state.get_data()
    hist = list(data.get("history", []))
    if not hist:  # некуда назад — выходим в меню
        await state.clear()
        await show_main_menu(cb, text=texts.CANCELLED)
        return
    prev = hist.pop()
    await state.update_data(history=hist)
    show = STEP_SHOW.get(prev)
    if show is None:
        await state.clear()
        await show_main_menu(cb)
        return
    await show(cb, state, session, user)


# --- старт мастера ---
@router.callback_query(Nav.filter(F.action == "add"))
async def add_from_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await _begin(cb, state)


# --- шаги ---
@router.message(AddPayment.title)
async def step_title(message: Message, state: FSMContext, session, user: User) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(texts.ADD_TITLE, reply_markup=title_nav_kb())
        return
    await state.update_data(title=title[:255])
    await _goto(message, state, show_category, session, user)


@router.callback_query(AddPayment.category, CategoryCB.filter())
async def step_category(cb: CallbackQuery, callback_data: CategoryCB, state: FSMContext, session, user: User) -> None:
    if callback_data.idx == -1:
        await _goto(cb, state, show_category_custom, session, user)
        return
    await state.update_data(category=CATEGORIES[callback_data.idx])
    await _goto(cb, state, show_currency, session, user)


@router.message(AddPayment.category_custom)
async def step_category_custom(message: Message, state: FSMContext, session, user: User) -> None:
    await state.update_data(category=((message.text or "").strip()[:64] or None))
    await _goto(message, state, show_currency, session, user)


@router.callback_query(AddPayment.currency, CurrencyCB.filter())
async def step_currency(cb: CallbackQuery, callback_data: CurrencyCB, state: FSMContext, session, user: User) -> None:
    code = callback_data.code
    if code == "more":  # внутришаговая навигация: показать остальные валюты
        await _edit_markup(cb, with_nav(currency_more_kb(), back=False))
        return
    if code == "back":  # вернуться к частым валютам (внутри шага)
        await _edit_markup(cb, with_nav(currency_kb(), back=await _nav_back(state)))
        return
    if code == "custom":
        await _goto(cb, state, show_currency_custom, session, user)
        return
    await state.update_data(currency=code)
    await _goto(cb, state, show_amount, session, user)


@router.message(AddPayment.currency_custom)
async def step_currency_custom(message: Message, state: FSMContext, session, user: User) -> None:
    code = (message.text or "").strip().upper()
    if not is_valid_iso(code):
        await message.answer(texts.ADD_CURRENCY_INVALID, reply_markup=wizard_nav_kb(await _nav_back(state)))
        return
    await state.update_data(currency=code)
    await _goto(message, state, show_amount, session, user)


@router.message(AddPayment.amount)
async def step_amount(message: Message, state: FSMContext, session, user: User) -> None:
    data = await state.get_data()
    minor = parse_amount(message.text or "", data.get("currency", "USD"))
    if minor is None:
        await message.answer(texts.ADD_AMOUNT_INVALID, reply_markup=wizard_nav_kb(await _nav_back(state)))
        return
    await state.update_data(amount_minor=minor)
    await _goto(message, state, show_freq, session, user)


@router.callback_query(AddPayment.freq, FreqCB.filter())
async def step_freq(cb: CallbackQuery, callback_data: FreqCB, state: FSMContext, session, user: User) -> None:
    freq = callback_data.value
    await state.update_data(
        freq=freq, interval=1, by_weekdays=None, by_monthdays=None,
        by_months=None, quarter=False, sel=[],
    )
    if freq == "week":
        await _goto(cb, state, show_week_days, session, user)
    elif freq == "month":
        await _goto(cb, state, show_month_days, session, user)
    elif freq == "quarter":
        await state.update_data(quarter=True)
        await _goto(cb, state, show_month_days, session, user)
    elif freq == "year":
        await _goto(cb, state, show_year_months, session, user)
    else:  # once
        await _goto(cb, state, show_once_date, session, user)


@router.callback_query(AddPayment.week_days, ToggleCB.filter(F.group == "wd"))
async def step_week_toggle(cb: CallbackQuery, callback_data: ToggleCB, state: FSMContext) -> None:
    data = await state.get_data()
    sel = set(data.get("sel", []))
    sel.symmetric_difference_update({callback_data.value})
    await state.update_data(sel=sorted(sel))
    await _edit_markup(cb, with_nav(weekdays_kb(sel), back=await _nav_back(state)))


@router.callback_query(AddPayment.week_days, WizardCB.filter(F.action == "done_week"))
async def step_week_done(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    data = await state.get_data()
    sel = sorted(set(data.get("sel", [])))
    await state.update_data(by_weekdays=sel or None)
    await _goto(cb, state, show_reminders, session, user)


@router.message(AddPayment.month_days)
async def step_month_days(message: Message, state: FSMContext, session, user: User) -> None:
    days = parse_monthdays(message.text or "")
    if not days:
        await message.answer(texts.ADD_MONTH_DAYS_INVALID, reply_markup=wizard_nav_kb(await _nav_back(state)))
        return
    data = await state.get_data()
    if data.get("quarter"):
        days = days[:1]
    await state.update_data(by_monthdays=days)
    await _goto(message, state, show_reminders, session, user)


@router.callback_query(AddPayment.year_months, ToggleCB.filter(F.group == "mo"))
async def step_year_toggle(cb: CallbackQuery, callback_data: ToggleCB, state: FSMContext) -> None:
    data = await state.get_data()
    sel = set(data.get("sel", []))
    sel.symmetric_difference_update({callback_data.value})
    await state.update_data(sel=sorted(sel))
    await _edit_markup(cb, with_nav(months_kb(sel), back=await _nav_back(state)))


@router.callback_query(AddPayment.year_months, WizardCB.filter(F.action == "done_year"))
async def step_year_done(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    data = await state.get_data()
    sel = sorted(set(data.get("sel", [])))
    if not sel:
        await cb.answer("Отметь хотя бы один месяц", show_alert=True)
        return
    await state.update_data(by_months=sel)
    await _goto(cb, state, show_year_day, session, user)


@router.message(AddPayment.year_day)
async def step_year_day(message: Message, state: FSMContext, session, user: User) -> None:
    days = parse_monthdays(message.text or "")
    if not days:
        await message.answer(texts.ADD_MONTH_DAYS_INVALID, reply_markup=wizard_nav_kb(await _nav_back(state)))
        return
    await state.update_data(by_monthdays=days[:1])
    await _goto(message, state, show_reminders, session, user)


@router.message(AddPayment.once_date)
async def step_once_date(message: Message, state: FSMContext, session, user: User) -> None:
    d = parse_date(message.text or "")
    if not d:
        await message.answer(texts.ADD_DATE_INVALID, reply_markup=wizard_nav_kb(await _nav_back(state)))
        return
    await state.update_data(anchor_iso=d.isoformat())
    await _goto(message, state, show_reminders, session, user)


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
    await _edit_markup(cb, with_nav(reminders_kb(rem), back=await _nav_back(state)))


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
    await message.answer(texts.ADD_REMINDERS, reply_markup=with_nav(reminders_kb(rem), back=await _nav_back(state)))


@router.callback_query(AddPayment.reminders, WizardCB.filter(F.action == "done_reminders"))
async def step_rem_done(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    data = await state.get_data()
    rem = sorted(set(data.get("reminders", [])), reverse=True)
    if not rem:
        rem = [1]  # дефолт — «за 1 день»
    await state.update_data(reminder_offsets=[{"days": d} for d in rem])
    await _goto(cb, state, show_payment_method, session, user)


@router.callback_query(AddPayment.payment_method, AddMethodCB.filter())
async def step_method(cb: CallbackQuery, callback_data: AddMethodCB, state: FSMContext, session, user: User) -> None:
    v = callback_data.value
    if v == "add":  # добавить способ inline, не выходя из мастера
        await _push_current(state)  # чтобы «Назад» из ввода вернул к выбору способа
        await state.set_state(AddPayment.method_new)
        await cb.message.answer(texts.METHOD_ADD_PROMPT, reply_markup=wizard_nav_kb(True))
        await cb.answer()
        return
    if v == "skip":
        await state.update_data(payment_method=None)
        await _goto(cb, state, show_confirm, session, user)
        return
    if v == "cash":
        name = "Наличные"
    elif v == "card":
        name = "Карта/трансфер"
    elif v.isdigit():
        method = await repo.get_user_payment_method(session, int(v), user.id)
        if not method:
            await cb.answer(texts.METHOD_GONE, show_alert=True)
            return
        name = method.name
    else:
        await cb.answer()
        return
    await state.update_data(payment_method=name)
    await _goto(cb, state, show_confirm, session, user)


@router.message(AddPayment.method_new)
async def step_method_new(message: Message, state: FSMContext, session, user: User) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(texts.METHOD_NAME_EMPTY, reply_markup=wizard_nav_kb(True))
        return
    method = await repo.add_payment_method(session, user.id, name)
    if method is None:  # лимит — вернуться к выбору способа
        await message.answer(texts.METHOD_LIMIT.format(limit=repo.MAX_PAYMENT_METHODS))
        # снимаем со стека шаг payment_method, который положили при входе в method_new
        data = await state.get_data()
        hist = list(data.get("history", []))
        if hist:
            hist.pop()
        await state.update_data(history=hist)
        await show_payment_method(message, state, session, user)
        return
    # создан — выбираем его и идём к подтверждению (payment_method уже в стеке -> Назад вернёт к нему)
    await state.update_data(payment_method=method.name)
    await show_confirm(message, state, session, user)


# --- подтверждение ---
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
        payment.payment_method = data.get("payment_method")
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
        payment_method=data.get("payment_method"),
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
