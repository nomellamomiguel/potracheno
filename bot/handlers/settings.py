"""Настройки: часовой пояс и время напоминаний."""
from __future__ import annotations

import datetime as dt

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import CityCB, Nav, SettingsCB, TimeCB
from bot.db import repo
from bot.db.models import PaymentStatus, User
from bot.keyboards import (
    back_to_menu_kb,
    notify_time_kb,
    reset_confirm_kb,
    settings_kb,
    tz_kb,
)
from bot.services import reminders as rsvc
from bot.services.dates import parse_time
from bot.services.timezones import CITY_TZ, resolve_tz
from bot.states import SettingsFSM

router = Router(name="settings")


async def _refresh_reminders(session, user: User) -> None:
    """После смены tz/времени — пересчитать запланированные напоминания пользователя."""
    for p in await repo.list_payments(session, user.id):
        await rsvc.rematerialize(session, p, user)


async def _show_menu(event: Message | CallbackQuery) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(texts.SETTINGS_MENU, reply_markup=settings_kb())
        except TelegramBadRequest:
            await event.message.answer(texts.SETTINGS_MENU, reply_markup=settings_kb())
        await event.answer()
    else:
        await event.answer(texts.SETTINGS_MENU, reply_markup=settings_kb())


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_menu(message)


@router.callback_query(Nav.filter(F.action == "settings"))
async def nav_settings(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_menu(cb)


@router.callback_query(SettingsCB.filter(F.field == "reset"))
async def reset_prompt(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    await state.clear()
    payments = await repo.list_payments(
        session,
        user.id,
        statuses=(PaymentStatus.active, PaymentStatus.paused, PaymentStatus.archived),
    )
    text = texts.RESET_CONFIRM.format(count=len(payments))
    try:
        await cb.message.edit_text(text, reply_markup=reset_confirm_kb())
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=reset_confirm_kb())
    await cb.answer()


@router.callback_query(SettingsCB.filter(F.field == "reset_confirm"))
async def reset_confirm(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    await state.clear()
    await repo.reset_user_data(session, user)
    try:
        await cb.message.edit_text(texts.RESET_DONE)
    except TelegramBadRequest:
        await cb.message.answer(texts.RESET_DONE)
    await cb.answer()


@router.callback_query(SettingsCB.filter(F.field == "tz"))
async def set_tz_prompt(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFSM.tz)
    await cb.message.answer(texts.ASK_TZ, reply_markup=tz_kb())
    await cb.answer()


@router.callback_query(SettingsCB.filter(F.field == "time"))
async def set_time_prompt(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFSM.notify_time)
    await cb.message.answer(texts.ASK_NOTIFY_TIME, reply_markup=notify_time_kb())
    await cb.answer()


@router.callback_query(SettingsFSM.tz, CityCB.filter())
async def set_tz_city(cb: CallbackQuery, callback_data: CityCB, state: FSMContext, session, user: User) -> None:
    user.tz = CITY_TZ.get(callback_data.name, user.tz)
    await _refresh_reminders(session, user)
    await state.clear()
    await cb.message.answer(texts.SETTINGS_SAVED, reply_markup=back_to_menu_kb())
    await cb.answer()


@router.message(SettingsFSM.tz)
async def set_tz_text(message: Message, state: FSMContext, session, user: User) -> None:
    tz = resolve_tz(message.text or "")
    if not tz:
        await message.answer(texts.TZ_INVALID, reply_markup=tz_kb())
        return
    user.tz = tz
    await _refresh_reminders(session, user)
    await state.clear()
    await message.answer(texts.SETTINGS_SAVED, reply_markup=back_to_menu_kb())


@router.callback_query(SettingsFSM.notify_time, TimeCB.filter())
async def set_time_cb(cb: CallbackQuery, callback_data: TimeCB, state: FSMContext, session, user: User) -> None:
    # value хранится как "HHMM" без двоеточия (двоеточие — разделитель callback_data)
    user.notify_time = dt.time(int(callback_data.value[:2]), int(callback_data.value[2:]))
    await _refresh_reminders(session, user)
    await state.clear()
    await cb.message.answer(texts.SETTINGS_SAVED, reply_markup=back_to_menu_kb())
    await cb.answer()


@router.message(SettingsFSM.notify_time)
async def set_time_text(message: Message, state: FSMContext, session, user: User) -> None:
    t = parse_time(message.text or "")
    if t is None:
        await message.answer(texts.NOTIFY_TIME_INVALID, reply_markup=notify_time_kb())
        return
    user.notify_time = t
    await _refresh_reminders(session, user)
    await state.clear()
    await message.answer(texts.SETTINGS_SAVED, reply_markup=back_to_menu_kb())
