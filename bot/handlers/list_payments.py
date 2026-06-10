"""Список платежей и действия: открыть, пауза, возобновить, архив, удалить."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import Nav, PaymentCB
from bot.db import repo
from bot.db.models import Payment, PaymentStatus, User
from bot.handlers.commands import show_main_menu
from bot.keyboards import (
    back_to_menu_kb,
    delete_confirm_kb,
    payment_card_kb,
    payment_list_kb,
)
from bot.services import reminders as rsvc
from bot.services.humanize import payment_card

router = Router(name="list_payments")

VISIBLE = (PaymentStatus.active, PaymentStatus.paused)


async def _render_list(event: Message | CallbackQuery, session, user: User) -> None:
    payments = await repo.list_payments(session, user.id, statuses=VISIBLE)
    if not payments:
        await _reply(event, texts.NO_PAYMENTS, back_to_menu_kb())
        return
    await _reply(event, texts.LIST_TITLE, payment_list_kb(payments))


async def _reply(event: Message | CallbackQuery, text: str, kb) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


async def _show_card(cb: CallbackQuery, payment: Payment) -> None:
    try:
        await cb.message.edit_text(payment_card(payment), reply_markup=payment_card_kb(payment))
    except TelegramBadRequest:
        await cb.message.answer(payment_card(payment), reply_markup=payment_card_kb(payment))
    await cb.answer()


@router.message(Command("list"))
async def cmd_list(message: Message, state: FSMContext, session, user: User) -> None:
    await state.clear()
    await _render_list(message, session, user)


@router.callback_query(Nav.filter(F.action == "list"))
async def nav_list(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    await state.clear()
    await _render_list(cb, session, user)


@router.callback_query(PaymentCB.filter(F.action == "list"))
async def back_to_list(cb: CallbackQuery, state: FSMContext, session, user: User) -> None:
    await state.clear()
    await _render_list(cb, session, user)


@router.callback_query(PaymentCB.filter(F.action == "open"))
async def open_card(cb: CallbackQuery, callback_data: PaymentCB, state: FSMContext, session, user: User) -> None:
    await state.clear()
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    await _show_card(cb, payment)


@router.callback_query(PaymentCB.filter(F.action == "pause"))
async def pause(cb: CallbackQuery, callback_data: PaymentCB, session, user: User) -> None:
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    payment.status = PaymentStatus.paused
    await repo.clear_pending_reminders(session, payment.id)
    await session.flush()
    await _show_card(cb, payment)


@router.callback_query(PaymentCB.filter(F.action == "resume"))
async def resume(cb: CallbackQuery, callback_data: PaymentCB, session, user: User) -> None:
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    payment.status = PaymentStatus.active
    await rsvc.roll_payment(session, payment, user)  # пересчёт даты + напоминаний
    await _show_card(cb, payment)


@router.callback_query(PaymentCB.filter(F.action == "archive"))
async def archive(cb: CallbackQuery, callback_data: PaymentCB, session, user: User) -> None:
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    payment.status = PaymentStatus.archived
    await repo.clear_pending_reminders(session, payment.id)
    await session.flush()
    try:
        await cb.message.edit_text(
            texts.ARCHIVED.format(title=payment.title), reply_markup=back_to_menu_kb()
        )
    except TelegramBadRequest:
        await cb.message.answer(
            texts.ARCHIVED.format(title=payment.title), reply_markup=back_to_menu_kb()
        )
    await cb.answer()


@router.callback_query(PaymentCB.filter(F.action == "delete"))
async def delete_prompt(cb: CallbackQuery, callback_data: PaymentCB, session, user: User) -> None:
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    await _reply(cb, f"Удалить «{payment.title}» полностью?", delete_confirm_kb(payment.id))


@router.callback_query(PaymentCB.filter(F.action == "confirm_delete"))
async def confirm_delete(cb: CallbackQuery, callback_data: PaymentCB, session, user: User) -> None:
    payment = await repo.get_user_payment(session, callback_data.id, user.id)
    if not payment:
        await cb.answer(texts.PAYMENT_GONE, show_alert=True)
        return
    title = payment.title
    await repo.delete_payment(session, payment)
    await session.flush()
    try:
        await cb.message.edit_text(texts.DELETED.format(title=title), reply_markup=back_to_menu_kb())
    except TelegramBadRequest:
        await cb.message.answer(texts.DELETED.format(title=title), reply_markup=back_to_menu_kb())
    await cb.answer()
