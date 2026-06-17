"""Базовые команды: /start, /help, /menu, /cancel, главное меню, fallback."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import Nav
from bot.db import repo
from bot.db.models import PaymentStatus, User
from bot.keyboards import (
    back_to_menu_kb,
    feedback_kind_kb,
    main_menu_kb,
    payment_list_kb,
    settings_kb,
    status_menu_kb,
    tz_kb,
)
from bot.states import FeedbackFSM, Onboarding

router = Router(name="commands")
fallback_router = Router(name="fallback")


async def show_main_menu(event: Message | CallbackQuery, *, text: str = texts.MAIN_MENU) -> None:
    kb = main_menu_kb()
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


async def start_onboarding(message: Message, state: FSMContext) -> None:
    await state.set_state(Onboarding.tz)
    await message.answer(texts.WELCOME)
    await message.answer(texts.ASK_TZ, reply_markup=tz_kb())


async def _interrupt(message: Message, state: FSMContext) -> None:
    """Если пользователь в активном FSM-состоянии — прервать его с уведомлением."""
    if await state.get_state() is not None:
        await state.clear()
        await message.answer(texts.INTERRUPTED)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    if user.onboarded:
        await show_main_menu(message)
    else:
        await start_onboarding(message, state)


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await _interrupt(message, state)
    await message.answer(texts.HELP, reply_markup=back_to_menu_kb())


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await _interrupt(message, state)
    await show_main_menu(message)


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext) -> None:
    await _interrupt(message, state)
    await message.answer(texts.SETTINGS_MENU, reply_markup=settings_kb())


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext) -> None:
    await _interrupt(message, state)
    await message.answer(texts.STATUS_MENU, reply_markup=status_menu_kb())


@router.message(Command("list"))
async def cmd_list(message: Message, state: FSMContext, session, user: User) -> None:
    await _interrupt(message, state)
    payments = await repo.list_payments(
        session, user.id, statuses=(PaymentStatus.active, PaymentStatus.paused)
    )
    text = texts.LIST_TITLE if payments else texts.NO_PAYMENTS
    await message.answer(text, reply_markup=payment_list_kb(payments))


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    await _interrupt(message, state)
    from bot.handlers.add_payment import _begin  # ленивый импорт — избегаем цикла

    await _begin(message, state)


@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext) -> None:
    await _interrupt(message, state)
    await state.set_state(FeedbackFSM.kind)
    await message.answer(texts.FEEDBACK_KIND, reply_markup=feedback_kind_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    await show_main_menu(message, text=texts.CANCELLED if current else texts.NOTHING_TO_CANCEL)


@router.callback_query(Nav.filter(F.action == "menu"))
async def nav_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_main_menu(cb)


@router.callback_query(Nav.filter(F.action == "help"))
async def nav_help(cb: CallbackQuery) -> None:
    try:
        await cb.message.edit_text(texts.HELP, reply_markup=back_to_menu_kb())
    except TelegramBadRequest:
        await cb.message.answer(texts.HELP, reply_markup=back_to_menu_kb())
    await cb.answer()


@fallback_router.message(StateFilter(None))
async def fallback_message(message: Message, user: User) -> None:
    if not user.onboarded:
        await message.answer(texts.NEED_ONBOARDING)
    else:
        await show_main_menu(message, text=texts.UNKNOWN)


@fallback_router.callback_query()
async def fallback_callback(cb: CallbackQuery) -> None:
    # гасим «часики» у неизвестных/устаревших кнопок
    await cb.answer()
