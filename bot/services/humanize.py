"""Человекочитаемые описания периодичности, напоминаний и карточек платежей (RU, HTML)."""
from __future__ import annotations

import datetime as dt
import html

from bot.services.dates import (
    RU_MONTHS,
    RU_WEEKDAYS,
    days_left,
    format_date,
)
from bot.services.money import format_money


def esc(text: str | None) -> str:
    return html.escape(text or "")


def _freq_value(freq) -> str:
    return freq.value if hasattr(freq, "value") else str(freq)


def _monthdays_phrase(days: list[int] | None) -> str:
    if not days:
        return ""
    if days == [-1]:
        return "в последний день месяца"
    return "числа " + ", ".join(str(d) for d in days)


def describe_recurrence(
    freq,
    interval: int = 1,
    by_weekdays: list[int] | None = None,
    by_monthdays: list[int] | None = None,
    by_months: list[int] | None = None,
) -> str:
    freq = _freq_value(freq)
    interval = interval or 1

    if freq == "once":
        return "разово"

    if freq == "week":
        days = ""
        if by_weekdays:
            days = " (" + ", ".join(RU_WEEKDAYS[d] for d in sorted(by_weekdays)) + ")"
        base = "каждую неделю" if interval == 1 else f"каждые {interval} нед."
        return base + days

    if freq == "month":
        base = "ежемесячно" if interval == 1 else f"каждые {interval} мес."
        phrase = _monthdays_phrase(by_monthdays)
        return f"{base}, {phrase}" if phrase else base

    if freq == "quarter":
        phrase = _monthdays_phrase(by_monthdays)
        return f"раз в квартал, {phrase}" if phrase else "раз в квартал"

    if freq == "year":
        months = ""
        if by_months:
            months = " (" + ", ".join(RU_MONTHS[m - 1] for m in sorted(by_months)) + ")"
        phrase = _monthdays_phrase(by_monthdays)
        base = "раз в год" if (not by_months or len(by_months) == 1) else "несколько раз в год"
        tail = f", {phrase}" if phrase else ""
        return base + months + tail

    return freq


def describe_reminders(offsets: list[dict] | None) -> str:
    if not offsets:
        return "без напоминаний"
    parts = []
    for o in offsets:
        n = int(o.get("days", 0))
        if n <= 0:
            parts.append("в день платежа")
        elif n == 1:
            parts.append("за 1 день")
        else:
            parts.append(f"за {n} дн.")
    return ", ".join(parts)


def due_phrase(due: dt.date | None, today: dt.date | None = None) -> str:
    if due is None:
        return "—"
    left = days_left(due, today)
    if left < 0:
        return f"{format_date(due)} (просрочен)"
    if left == 0:
        return f"{format_date(due)} (сегодня)"
    if left == 1:
        return f"{format_date(due)} (завтра)"
    return f"{format_date(due)} (через {left} дн.)"


def payment_card(payment) -> str:
    """Многострочная карточка платежа (HTML)."""
    title = esc(payment.title)
    cat = f" · {esc(payment.category)}" if payment.category else ""
    amount = format_money(payment.amount_minor, payment.currency)
    rec = describe_recurrence(
        payment.freq,
        payment.interval,
        payment.by_weekdays,
        payment.by_monthdays,
        payment.by_months,
    )
    rem = describe_reminders(payment.reminder_offsets)
    status_val = payment.status.value if hasattr(payment.status, "value") else str(payment.status)
    marks = {"paused": " ⏸ на паузе", "archived": " 🗄 в архиве"}
    mark = marks.get(status_val, "")
    method = getattr(payment, "payment_method", None)
    method_line = f"\nСпособ оплаты: {esc(method)}" if method else ""
    return (
        f"💳 <b>{title}</b>{cat}{mark}\n"
        f"Сумма: <b>{amount}</b>\n"
        f"Периодичность: {rec}\n"
        f"Ближайший платёж: {due_phrase(payment.next_due_date)}\n"
        f"Напоминания: {rem}"
        f"{method_line}"
    )
