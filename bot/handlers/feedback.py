"""Обратная связь: баг/идея → сохранить в БД и переслать админу."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import FeedbackKindCB, Nav
from bot.config import get_settings
from bot.db import repo
from bot.db.models import FeedbackKind, User
from bot.keyboards import back_to_menu_kb, feedback_kind_kb
from bot.services.humanize import esc
from bot.states import FeedbackFSM

router = Router(name="feedback")


@router.callback_query(Nav.filter(F.action == "feedback"))
async def fb_start_cb(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FeedbackFSM.kind)
    await cb.message.answer(texts.FEEDBACK_KIND, reply_markup=feedback_kind_kb())
    await cb.answer()


@router.message(Command("feedback"))
async def fb_start_cmd(message: Message, state: FSMContext) -> None:
    await state.set_state(FeedbackFSM.kind)
    await message.answer(texts.FEEDBACK_KIND, reply_markup=feedback_kind_kb())


@router.callback_query(FeedbackFSM.kind, FeedbackKindCB.filter())
async def fb_kind(cb: CallbackQuery, callback_data: FeedbackKindCB, state: FSMContext) -> None:
    await state.update_data(kind=callback_data.kind)
    await state.set_state(FeedbackFSM.text)
    await cb.message.answer(texts.FEEDBACK_TEXT)
    await cb.answer()


@router.message(FeedbackFSM.text)
async def fb_text(message: Message, state: FSMContext, session, user: User, bot: Bot) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer(texts.FEEDBACK_TEXT)
        return
    data = await state.get_data()
    kind = FeedbackKind(data.get("kind", "idea"))
    await repo.add_feedback(session, user_id=user.id, kind=kind, text=text[:4000])
    await state.clear()

    settings = get_settings()
    if settings.admin_chat_id:
        label = "🐞 Баг" if kind == FeedbackKind.bug else "💡 Идея"
        who = f"@{user.username}" if user.username else f"id {user.id}"
        try:
            await bot.send_message(settings.admin_chat_id, f"{label} от {who}:\n\n{esc(text)}")
        except Exception:  # noqa: BLE001 — недоступность админ-чата не критична
            pass

    await message.answer(texts.FEEDBACK_SAVED, reply_markup=back_to_menu_kb())
