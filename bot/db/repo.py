"""Доступ к данным: пользователи, платежи, напоминания, обратная связь."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import (
    Feedback,
    FeedbackKind,
    Payment,
    PaymentMethod,
    PaymentStatus,
    ReminderLog,
    User,
)

ACTIVE = (PaymentStatus.active,)


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_or_create_user(
    session: AsyncSession,
    *,
    user_id: int,
    chat_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        user = User(id=user_id, chat_id=chat_id, username=username, first_name=first_name)
        session.add(user)
        await session.flush()
    elif user.chat_id != chat_id:
        user.chat_id = chat_id
    return user


async def list_payments(
    session: AsyncSession,
    user_id: int,
    statuses: tuple[PaymentStatus, ...] = ACTIVE,
) -> list[Payment]:
    stmt = (
        select(Payment)
        .where(Payment.user_id == user_id, Payment.status.in_(statuses))
        .order_by(Payment.next_due_date.is_(None), Payment.next_due_date, Payment.id)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_payment(session: AsyncSession, payment_id: int) -> Payment | None:
    return await session.get(Payment, payment_id)


async def get_user_payment(
    session: AsyncSession, payment_id: int, user_id: int
) -> Payment | None:
    p = await session.get(Payment, payment_id)
    return p if (p and p.user_id == user_id) else None


async def all_active_payments(session: AsyncSession) -> list[Payment]:
    res = await session.execute(
        select(Payment)
        .where(Payment.status == PaymentStatus.active)
        .options(selectinload(Payment.user))
    )
    return list(res.scalars().all())


async def delete_payment(session: AsyncSession, payment: Payment) -> None:
    await session.delete(payment)


async def clear_pending_reminders(session: AsyncSession, payment_id: int) -> None:
    await session.execute(
        sa_delete(ReminderLog).where(
            ReminderLog.payment_id == payment_id,
            ReminderLog.sent_at.is_(None),
        )
    )


async def delete_reminders_for_payment(session: AsyncSession, payment_id: int) -> None:
    """Удаляет ВСЕ напоминания платежа (и отправленные, и ожидающие)."""
    await session.execute(
        sa_delete(ReminderLog).where(ReminderLog.payment_id == payment_id)
    )


async def reset_user_data(session: AsyncSession, user: User) -> int:
    """Полный сброс: удаляет все платежи (с напоминаниями), способы оплаты и настройки.

    Возвращает число удалённых платежей. Затрагивает только данные этого user.id.
    """
    payments = await list_payments(
        session,
        user.id,
        statuses=(PaymentStatus.active, PaymentStatus.paused, PaymentStatus.archived),
    )
    for payment in payments:
        await delete_reminders_for_payment(session, payment.id)  # сначала напоминания
        await delete_payment(session, payment)                   # затем сам платёж
    # удаляем все способы оплаты пользователя
    await session.execute(
        sa_delete(PaymentMethod).where(PaymentMethod.user_id == user.id)
    )
    user.onboarded = False
    user.tz = "Europe/Moscow"
    user.notify_time = dt.time(10, 0)
    await session.flush()
    return len(payments)


async def existing_offsets(
    session: AsyncSession, payment_id: int, due_date: dt.date
) -> set[int]:
    res = await session.execute(
        select(ReminderLog.offset_index).where(
            ReminderLog.payment_id == payment_id,
            ReminderLog.due_date == due_date,
        )
    )
    return set(res.scalars().all())


async def next_free_offset_index(
    session: AsyncSession, payment_id: int, due_date: dt.date
) -> int:
    used = await existing_offsets(session, payment_id, due_date)
    return (max(used) + 1) if used else 0


async def due_reminders(
    session: AsyncSession, now_utc: dt.datetime
) -> list[ReminderLog]:
    stmt = (
        select(ReminderLog)
        .join(Payment, ReminderLog.payment_id == Payment.id)
        .where(
            ReminderLog.sent_at.is_(None),
            ReminderLog.scheduled_for <= now_utc,
            Payment.status == PaymentStatus.active,
        )
        .options(
            selectinload(ReminderLog.payment).selectinload(Payment.user)
        )
        .order_by(ReminderLog.scheduled_for)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def add_feedback(
    session: AsyncSession, *, user_id: int, kind: FeedbackKind, text: str
) -> Feedback:
    fb = Feedback(user_id=user_id, kind=kind, text=text)
    session.add(fb)
    await session.flush()
    return fb


# --- Способы оплаты ---
MAX_PAYMENT_METHODS = 10


async def list_payment_methods(session: AsyncSession, user_id: int) -> list[PaymentMethod]:
    res = await session.execute(
        select(PaymentMethod)
        .where(PaymentMethod.user_id == user_id)
        .order_by(PaymentMethod.created_at, PaymentMethod.id)
    )
    return list(res.scalars().all())


async def count_payment_methods(session: AsyncSession, user_id: int) -> int:
    res = await session.execute(
        select(func.count())
        .select_from(PaymentMethod)
        .where(PaymentMethod.user_id == user_id)
    )
    return res.scalar_one()


async def add_payment_method(
    session: AsyncSession, user_id: int, name: str
) -> PaymentMethod | None:
    if await count_payment_methods(session, user_id) >= MAX_PAYMENT_METHODS:
        return None
    method = PaymentMethod(user_id=user_id, name=(name or "").strip()[:64])
    session.add(method)
    await session.flush()
    return method


async def get_user_payment_method(
    session: AsyncSession, method_id: int, user_id: int
) -> PaymentMethod | None:
    m = await session.get(PaymentMethod, method_id)
    return m if (m and m.user_id == user_id) else None


async def rename_payment_method(
    session: AsyncSession, method: PaymentMethod, new_name: str
) -> None:
    method.name = (new_name or "").strip()[:64]
    await session.flush()


async def delete_payment_method(session: AsyncSession, method: PaymentMethod) -> None:
    await session.delete(method)
