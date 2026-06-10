"""Материализация напоминаний и продвижение платежей по датам."""
from __future__ import annotations

import datetime as dt
from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db import repo
from bot.db.models import Payment, PaymentStatus, ReminderLog, User
from bot.services.recurrence import next_due_for_payment


def utcnow() -> dt.datetime:
    """Текущее время в UTC, naive (для сравнения с scheduled_for в БД)."""
    return dt.datetime.now(timezone.utc).replace(tzinfo=None)


def zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo(get_settings().default_tz)


def _scheduled_for(due_date: dt.date, offset_days: int, user: User) -> dt.datetime:
    """Локальная дата платежа − offset_days в notify_time -> UTC (naive)."""
    tz = zone(user.tz)
    local = dt.datetime.combine(
        due_date - dt.timedelta(days=offset_days), user.notify_time, tzinfo=tz
    )
    return local.astimezone(timezone.utc).replace(tzinfo=None)


async def materialize_occurrence(
    session: AsyncSession,
    payment: Payment,
    user: User,
    due_date: dt.date | None,
    *,
    now: dt.datetime | None = None,
) -> None:
    """Создаёт строки ReminderLog для каждого оффсета (идемпотентно)."""
    if due_date is None:
        return
    now = now or utcnow()
    existing = await repo.existing_offsets(session, payment.id, due_date)
    for idx, off in enumerate(payment.reminder_offsets or []):
        if idx in existing:
            continue
        days = int(off.get("days", 0))
        sched = _scheduled_for(due_date, days, user)
        if sched < now:
            continue  # время напоминания уже прошло — не планируем
        session.add(
            ReminderLog(
                payment_id=payment.id,
                due_date=due_date,
                offset_index=idx,
                scheduled_for=sched,
            )
        )
    await session.flush()


async def rematerialize(
    session: AsyncSession, payment: Payment, user: User, *, now: dt.datetime | None = None
) -> None:
    await repo.clear_pending_reminders(session, payment.id)
    await materialize_occurrence(session, payment, user, payment.next_due_date, now=now)


async def set_initial_due_and_reminders(
    session: AsyncSession, payment: Payment, user: User
) -> dt.date | None:
    """После создания платежа: вычислить next_due_date и материализовать напоминания."""
    today = dt.date.today()
    due = next_due_for_payment(payment, after=today - dt.timedelta(days=1))
    payment.next_due_date = due
    await session.flush()
    if due is not None:
        await materialize_occurrence(session, payment, user, due)
    return due


async def advance_payment(
    session: AsyncSession, payment: Payment, user: User
) -> dt.date | None:
    """Платёж оплачен/прошёл: перейти к следующей дате (None -> архив)."""
    base = payment.next_due_date or dt.date.today()
    nxt = next_due_for_payment(payment, after=base)
    payment.next_due_date = nxt
    if nxt is None:
        payment.status = PaymentStatus.archived
    await session.flush()
    await rematerialize(session, payment, user)
    return nxt


async def snooze_payment(
    session: AsyncSession, payment: Payment, user: User, days: int
) -> dt.datetime:
    """Отложить: добавить разовое напоминание через `days` дней."""
    sched = utcnow() + dt.timedelta(days=days)
    due = payment.next_due_date or dt.date.today()
    idx = await repo.next_free_offset_index(session, payment.id, due)
    session.add(
        ReminderLog(
            payment_id=payment.id, due_date=due, offset_index=idx, scheduled_for=sched
        )
    )
    await session.flush()
    return sched


async def roll_payment(session: AsyncSession, payment: Payment, user: User) -> None:
    """Ежедневный roll: подтянуть просроченные/пустые next_due и напоминания."""
    today = dt.date.today()
    due = payment.next_due_date
    if due is None:
        nd = next_due_for_payment(payment, after=today - dt.timedelta(days=1))
        payment.next_due_date = nd
        if nd is None:
            payment.status = PaymentStatus.archived
        else:
            await materialize_occurrence(session, payment, user, nd)
    elif due < today:
        nd = next_due_for_payment(payment, after=due)
        payment.next_due_date = nd
        if nd is None:
            payment.status = PaymentStatus.archived
        else:
            await rematerialize(session, payment, user)
    else:
        await materialize_occurrence(session, payment, user, due)
    await session.flush()
