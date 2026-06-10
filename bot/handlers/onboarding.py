"""Онбординг: часовой пояс → время напоминаний → предложить добавить платёж."""
from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import CityCB, TimeCB
from bot.db.models import User
from bot.keyboards import add_first_kb, notify_time_kb, tz_kb
from bot.services.dates import parse_time
from bot.services.timezones import CITY_TZ, resolve_tz
from bot.states import Onboarding

router = Router(name="onboarding")


async def _ask_notify_time(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Onboarding.notify_time)
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer(texts.ASK_NOTIFY_TIME, reply_markup=notify_time_kb())
    if isinstance(event, CallbackQuery):
        await event.answer()


async def _finish(event: Message | CallbackQuery, state: FSMContext, user: User) -> None:
    user.onboarded = True
    await state.clear()
    text = texts.ONBOARD_DONE.format(tz=user.tz, time=user.notify_time.strftime("%H:%M"))
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer(text, reply_markup=add_first_kb())
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(Onboarding.tz, CityCB.filter())
async def ob_tz_city(cb: CallbackQuery, callback_data: CityCB, state: FSMContext, user: User) -> None:
    user.tz = CITY_TZ.get(callback_data.name, user.tz)
    await _ask_notify_time(cb, state)


@router.message(Onboarding.tz)
async def ob_tz_text(message: Message, state: FSMContext, user: User) -> None:
    tz = resolve_tz(message.text or "")
    if not tz:
        await message.answer(texts.TZ_INVALID, reply_markup=tz_kb())
        return
    user.tz = tz
    await _ask_notify_time(message, state)


@router.callback_query(Onboarding.notify_time, TimeCB.filter())
async def ob_time_cb(cb: CallbackQuery, callback_data: TimeCB, state: FSMContext, user: User) -> None:
    t = parse_time(callback_data.value)
    if t is not None:
        user.notify_time = t
    await _finish(cb, state, user)


@router.message(Onboarding.notify_time)
async def ob_time_text(message: Message, state: FSMContext, user: User) -> None:
    t = parse_time(message.text or "")
    if t is None:
        await message.answer(texts.NOTIFY_TIME_INVALID, reply_markup=notify_time_kb())
        return
    user.notify_time = t
    await _finish(message, state, user)
