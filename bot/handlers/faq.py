"""Раздел «Помощь и советы» (FAQ о регулярных платежах) — статичные экраны."""
from __future__ import annotations

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot import texts
from bot.callbacks import FaqCB
from bot.keyboards import faq_menu_kb, faq_section_kb

router = Router(name="faq")

_SECTION_TEXT = {
    "types": texts.FAQ_TYPES,
    "find": texts.FAQ_FIND,
    "dark": texts.FAQ_DARK,
    "date": texts.FAQ_DATE,
    "cancel": texts.FAQ_CANCEL,
    "currency": texts.FAQ_CURRENCY,
}


@router.callback_query(FaqCB.filter())
async def faq_open(cb: CallbackQuery, callback_data: FaqCB, state: FSMContext) -> None:
    # FAQ доступен в т.ч. из первого шага мастера /add — тогда прерываем мастер
    interrupted = await state.get_state() is not None
    if interrupted:
        await state.clear()

    if callback_data.section == "intro":
        text, kb = texts.FAQ_INTRO, faq_menu_kb()
    else:
        text = _SECTION_TEXT.get(callback_data.section, texts.FAQ_INTRO)
        kb = faq_section_kb()

    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer(texts.INTERRUPTED if interrupted else None)
