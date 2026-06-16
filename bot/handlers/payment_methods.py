"""Управление способами оплаты (этап 1): список, добавление, переименование, удаление."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import MethodCB, SettingsCB
from bot.db import repo
from bot.db.models import User
from bot.db.repo import MAX_PAYMENT_METHODS
from bot.keyboards import (
    method_delete_confirm_kb,
    payment_method_card_kb,
    payment_methods_kb,
)
from bot.services.humanize import esc
from bot.states import PaymentMethodFSM

router = Router(name="payment_methods")


async def _show_list(event: Message | CallbackQuery, session, user: User) -> None:
    methods = await repo.list_payment_methods(session, user.id)
    text = texts.METHODS_TITLE if methods else texts.METHODS_EMPTY
    kb = payment_methods_kb(methods)
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(SettingsCB.filter(F.field == "methods"))
async def open_methods(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    await state.clear()
    await _show_list(cb, session, user)


@router.callback_query(MethodCB.filter(F.action == "list"))
async def back_to_list(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    await state.clear()
    await _show_list(cb, session, user)


@router.callback_query(MethodCB.filter(F.action == "add"))
async def add_prompt(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PaymentMethodFSM.add)
    await cb.message.answer(texts.METHOD_ADD_PROMPT)
    await cb.answer()


@router.message(PaymentMethodFSM.add)
async def add_value(message: Message, state: FSMContext, session, user: User) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(texts.METHOD_NAME_EMPTY)
        return
    method = await repo.add_payment_method(session, user.id, name)
    await state.clear()
    if method is None:
        await message.answer(texts.METHOD_LIMIT.format(limit=MAX_PAYMENT_METHODS))
    else:
        await message.answer(texts.METHOD_ADDED.format(name=esc(method.name)))
    await _show_list(message, session, user)


@router.callback_query(MethodCB.filter(F.action == "open"))
async def open_card(cb: CallbackQuery, callback_data: MethodCB, state: FSMContext, session, user: User) -> None:
    await state.clear()
    method = await repo.get_user_payment_method(session, callback_data.id, user.id)
    if not method:
        await cb.answer(texts.METHOD_GONE, show_alert=True)
        return
    text = f"💳 <b>{esc(method.name)}</b>"
    try:
        await cb.message.edit_text(text, reply_markup=payment_method_card_kb(method.id))
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=payment_method_card_kb(method.id))
    await cb.answer()


@router.callback_query(MethodCB.filter(F.action == "rename"))
async def rename_prompt(cb: CallbackQuery, callback_data: MethodCB, state: FSMContext, session, user: User) -> None:
    method = await repo.get_user_payment_method(session, callback_data.id, user.id)
    if not method:
        await cb.answer(texts.METHOD_GONE, show_alert=True)
        return
    await state.set_state(PaymentMethodFSM.rename)
    await state.update_data(method_id=method.id)
    await cb.message.answer(texts.METHOD_RENAME_PROMPT)
    await cb.answer()


@router.message(PaymentMethodFSM.rename)
async def rename_value(message: Message, state: FSMContext, session, user: User) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(texts.METHOD_NAME_EMPTY)
        return
    data = await state.get_data()
    method = await repo.get_user_payment_method(session, data.get("method_id"), user.id)
    if not method:
        await state.clear()
        await message.answer(texts.METHOD_GONE)
        return
    await repo.rename_payment_method(session, method, name)
    await state.clear()
    await message.answer(texts.METHOD_RENAMED.format(name=esc(method.name)))
    await _show_list(message, session, user)


@router.callback_query(MethodCB.filter(F.action == "delete"))
async def delete_prompt(cb: CallbackQuery, callback_data: MethodCB, session, user: User) -> None:
    method = await repo.get_user_payment_method(session, callback_data.id, user.id)
    if not method:
        await cb.answer(texts.METHOD_GONE, show_alert=True)
        return
    text = texts.METHOD_DELETE_CONFIRM.format(name=esc(method.name))
    try:
        await cb.message.edit_text(text, reply_markup=method_delete_confirm_kb(method.id))
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=method_delete_confirm_kb(method.id))
    await cb.answer()


@router.callback_query(MethodCB.filter(F.action == "confirm_delete"))
async def confirm_delete(cb: CallbackQuery, callback_data: MethodCB, state: FSMContext, session, user: User) -> None:
    await state.clear()
    method = await repo.get_user_payment_method(session, callback_data.id, user.id)
    if not method:
        await cb.answer(texts.METHOD_GONE, show_alert=True)
        return
    await repo.delete_payment_method(session, method)
    await session.flush()
    await _show_list(cb, session, user)
