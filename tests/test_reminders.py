import datetime as dt

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.db.base import Base
from bot.db.models import Freq, Payment, PaymentStatus, ReminderLog, User
from bot.services import reminders as rsvc


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _user(session) -> User:
    u = User(id=1, chat_id=1, tz="Europe/Moscow", notify_time=dt.time(10, 0))
    session.add(u)
    await session.flush()
    return u


async def _pending(session, pid: int) -> int:
    res = await session.execute(
        select(func.count())
        .select_from(ReminderLog)
        .where(ReminderLog.payment_id == pid, ReminderLog.sent_at.is_(None))
    )
    return res.scalar_one()


async def test_once_materialize_and_advance(session):
    user = await _user(session)
    anchor = dt.date.today() + dt.timedelta(days=30)
    p = Payment(
        user_id=user.id, title="Налог", currency="USD", amount_minor=100000,
        freq=Freq.once, anchor_date=anchor,
        reminder_offsets=[{"days": 3}, {"days": 1}, {"days": 0}],
        status=PaymentStatus.active,
    )
    session.add(p)
    await session.flush()

    due = await rsvc.set_initial_due_and_reminders(session, p, user)
    assert due == anchor
    assert await _pending(session, p.id) == 3

    # повторная материализация ничего не дублирует
    await rsvc.materialize_occurrence(session, p, user, p.next_due_date)
    assert await _pending(session, p.id) == 3

    # «оплатил» разовый -> следующего нет -> архив, очередь пуста
    nxt = await rsvc.advance_payment(session, p, user)
    assert nxt is None
    assert p.status == PaymentStatus.archived
    assert await _pending(session, p.id) == 0


async def test_monthly_advance(session):
    user = await _user(session)
    p = Payment(
        user_id=user.id, title="Аренда", currency="RUB", amount_minor=2500000,
        freq=Freq.month, by_monthdays=[15], anchor_date=dt.date.today(),
        reminder_offsets=[{"days": 1}], status=PaymentStatus.active,
    )
    session.add(p)
    await session.flush()

    due = await rsvc.set_initial_due_and_reminders(session, p, user)
    assert due is not None and due.day == 15 and due >= dt.date.today()

    nxt = await rsvc.advance_payment(session, p, user)
    assert nxt is not None and nxt.day == 15 and nxt > due
    assert p.status == PaymentStatus.active  # ежемесячный остаётся активным


async def test_ignored_reminder_keeps_active_on_roll(session):
    """Нет ответа на напоминание = платёж в силе: roll переносит дату, не архивирует."""
    user = await _user(session)
    today = dt.date(2026, 7, 3)
    p = Payment(
        user_id=user.id, title="Подписка", currency="EUR", amount_minor=999,
        freq=Freq.month, by_monthdays=[1], anchor_date=dt.date(2025, 1, 1),
        next_due_date=today - dt.timedelta(days=5),  # просрочено, не оплачено
        reminder_offsets=[{"days": 1}], status=PaymentStatus.active,
    )
    session.add(p)
    await session.flush()

    await rsvc.roll_payment(session, p, user, today=today)
    assert p.status == PaymentStatus.active
    assert p.next_due_date == dt.date(2026, 8, 1)


async def test_roll_catches_up_after_long_downtime(session):
    """Долгий простой бота: roll за один прогон догоняет дату до ближайшей на/после today."""
    user = await _user(session)
    today = dt.date(2026, 7, 3)
    p = Payment(
        user_id=user.id, title="Подписка", currency="EUR", amount_minor=999,
        freq=Freq.month, by_monthdays=[1], anchor_date=dt.date(2025, 1, 1),
        next_due_date=dt.date(2026, 4, 1),  # просрочка ~3 месяца
        reminder_offsets=[{"days": 1}], status=PaymentStatus.active,
    )
    session.add(p)
    await session.flush()

    await rsvc.roll_payment(session, p, user, today=today)
    assert p.status == PaymentStatus.active
    assert p.next_due_date == dt.date(2026, 8, 1)
