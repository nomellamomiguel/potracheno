import datetime as dt
from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.callbacks import AddMethodCB
from bot.db import repo
from bot.db.base import Base
from bot.db.models import Freq, Payment, PaymentStatus, User
from bot.db.repo import MAX_PAYMENT_METHODS
from bot.keyboards import add_method_kb


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _user(session, uid: int = 1) -> User:
    u = User(id=uid, chat_id=uid)
    session.add(u)
    await session.flush()
    return u


async def test_add_strip_and_list(session):
    await _user(session)
    m = await repo.add_payment_method(session, 1, "  Сбер  ")
    assert m is not None and m.name == "Сбер"  # strip
    assert [x.name for x in await repo.list_payment_methods(session, 1)] == ["Сбер"]
    assert await repo.count_payment_methods(session, 1) == 1


async def test_name_truncated_to_64(session):
    await _user(session)
    m = await repo.add_payment_method(session, 1, "x" * 100)
    assert len(m.name) == 64


async def test_limit_10(session):
    await _user(session)
    for i in range(MAX_PAYMENT_METHODS):
        assert await repo.add_payment_method(session, 1, f"m{i}") is not None
    # 11-й не создаётся
    assert await repo.add_payment_method(session, 1, "overflow") is None
    assert await repo.count_payment_methods(session, 1) == MAX_PAYMENT_METHODS


async def test_rename(session):
    await _user(session)
    m = await repo.add_payment_method(session, 1, "Old")
    await repo.rename_payment_method(session, m, "  New  ")
    assert m.name == "New"


async def test_delete(session):
    await _user(session)
    m = await repo.add_payment_method(session, 1, "Tmp")
    await repo.delete_payment_method(session, m)
    await session.flush()
    assert await repo.count_payment_methods(session, 1) == 0


async def test_user_isolation(session):
    await _user(session, 1)
    await _user(session, 2)
    m1 = await repo.add_payment_method(session, 1, "U1")
    # чужой способ недоступен
    assert await repo.get_user_payment_method(session, m1.id, 2) is None
    assert await repo.get_user_payment_method(session, m1.id, 1) is m1
    assert await repo.list_payment_methods(session, 2) == []


async def test_reset_clears_payment_methods(session):
    u = await _user(session)
    await repo.add_payment_method(session, 1, "Сбер")
    await repo.add_payment_method(session, 1, "Тинькофф")
    p = Payment(
        user_id=1, title="X", currency="USD", amount_minor=100, freq=Freq.month,
        by_monthdays=[1], anchor_date=dt.date.today(), reminder_offsets=[],
        status=PaymentStatus.active,
    )
    session.add(p)
    await session.flush()
    await repo.reset_user_data(session, u)
    assert await repo.count_payment_methods(session, 1) == 0
    assert await repo.list_payment_methods(session, 1) == []


def _method_values(methods) -> list[str]:
    kb = add_method_kb(methods)
    return [AddMethodCB.unpack(b.callback_data).value for row in kb.inline_keyboard for b in row]


def test_add_method_button_respects_limit():
    below = [SimpleNamespace(id=i, name=f"m{i}") for i in range(3)]
    assert "add" in _method_values(below)  # < лимита — кнопка есть
    full = [SimpleNamespace(id=i, name=f"m{i}") for i in range(MAX_PAYMENT_METHODS)]
    assert "add" not in _method_values(full)  # == лимит — кнопки нет
