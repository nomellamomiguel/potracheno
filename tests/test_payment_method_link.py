import datetime as dt
from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot import texts
from bot.db.base import Base, _migrate
from bot.db.models import Freq, Payment, PaymentStatus, User
from bot.handlers.status import methods_breakdown


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _mk(method, currency="USD", amount=100):
    p = Payment(
        user_id=1, title="X", currency=currency, amount_minor=amount,
        freq=Freq.month, by_monthdays=[1], anchor_date=dt.date.today(),
        reminder_offsets=[], status=PaymentStatus.active,
    )
    if method is not None:
        p.payment_method = method
    return p


async def test_migration_idempotent():
    """Колонка добавляется один раз; повторный _migrate не падает и не дублирует."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE TABLE payments (id INTEGER PRIMARY KEY)")
        await conn.run_sync(_migrate)  # добавляет payment_method
        await conn.run_sync(_migrate)  # повторно — ничего не делает, не падает
        cols = [
            row[1]
            for row in (await conn.exec_driver_sql("PRAGMA table_info(payments)")).fetchall()
        ]
    assert cols.count("payment_method") == 1
    await engine.dispose()


async def test_payment_saves_method_as_string(session):
    session.add(User(id=1, chat_id=1))
    await session.flush()
    p = _mk("Сбер")
    session.add(p)
    await session.flush()
    got = await session.get(Payment, p.id)
    assert got.payment_method == "Сбер"


async def test_payment_method_default_none(session):
    """«Пропустить» / старые платежи -> NULL."""
    session.add(User(id=1, chat_id=1))
    await session.flush()
    p = _mk(None)
    session.add(p)
    await session.flush()
    got = await session.get(Payment, p.id)
    assert got.payment_method is None


def test_methods_breakdown_groups():
    items = [
        (dt.date.today(), _mk("Наличные", "USD", 100)),
        (dt.date.today(), _mk("Сбер", "RUB", 200)),
        (dt.date.today(), _mk(None, "EUR", 50)),
        (dt.date.today(), _mk("Наличные", "USD", 25)),
    ]
    by_method, has_any = methods_breakdown(items)
    assert has_any is True
    assert by_method["Наличные"] == {"USD": 125}
    assert by_method["Сбер"] == {"RUB": 200}
    assert by_method[texts.METHOD_NONE_GROUP] == {"EUR": 50}


def test_methods_breakdown_hidden_when_no_methods():
    items = [
        (dt.date.today(), _mk(None, "USD", 100)),
        (dt.date.today(), _mk(None, "RUB", 200)),
    ]
    _, has_any = methods_breakdown(items)
    assert has_any is False  # ни у кого нет способа -> разрез скрывается
