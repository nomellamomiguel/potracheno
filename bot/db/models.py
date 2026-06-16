"""ORM-модели: User, Payment, ReminderLog, Feedback."""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base


class Freq(str, enum.Enum):
    week = "week"
    month = "month"
    quarter = "quarter"
    year = "year"
    once = "once"


class PaymentStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"


class ReminderStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    skipped = "skipped"


class FeedbackKind(str, enum.Enum):
    bug = "bug"
    idea = "idea"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tz: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    notify_time: Mapped[dt.time] = mapped_column(Time, default=dt.time(10, 0))
    locale: Mapped[str] = mapped_column(String(8), default="ru")
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payment_methods: Mapped[list["PaymentMethod"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)  # сумма в минорных единицах

    # Периодичность
    freq: Mapped[Freq] = mapped_column(SAEnum(Freq))
    interval: Mapped[int] = mapped_column(Integer, default=1)
    by_weekdays: Mapped[list | None] = mapped_column(JSON, nullable=True)   # [0..6], Пн=0
    by_monthdays: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [1..31] или -1 (последний)
    by_months: Mapped[list | None] = mapped_column(JSON, nullable=True)     # [1..12]
    anchor_date: Mapped[dt.date] = mapped_column(Date)

    next_due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    reminder_offsets: Mapped[list] = mapped_column(JSON, default=list)  # [{"days": 3}, ...] до 3 шт.
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus), default=PaymentStatus.active, index=True
    )

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="payments")
    reminders: Mapped[list["ReminderLog"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class ReminderLog(Base):
    """Материализованная очередь напоминаний (для надёжности и идемпотентности)."""

    __tablename__ = "reminder_log"
    __table_args__ = (
        UniqueConstraint("payment_id", "due_date", "offset_index", name="uq_reminder"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    due_date: Mapped[dt.date] = mapped_column(Date)        # дата самого платежа
    offset_index: Mapped[int] = mapped_column(Integer)     # индекс напоминания (0..2)
    scheduled_for: Mapped[dt.datetime] = mapped_column(DateTime, index=True)  # когда слать (UTC, naive)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)  # NULL = ждёт отправки
    status: Mapped[ReminderStatus] = mapped_column(
        SAEnum(ReminderStatus), default=ReminderStatus.pending
    )

    payment: Mapped["Payment"] = relationship(back_populates="reminders")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    kind: Mapped[FeedbackKind] = mapped_column(SAEnum(FeedbackKind))
    text: Mapped[str] = mapped_column(String(4000))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="payment_methods")
