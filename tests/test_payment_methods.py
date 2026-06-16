import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.db import repo
from bot.db.base import Base
from bot.db.models import User
from bot.db.repo import MAX_PAYMENT_METHODS


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
