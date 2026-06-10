"""Парсинг и форматирование дат, ввод дней/времени."""
from __future__ import annotations

import datetime as dt
import re

RU_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
RU_WEEKDAYS_FULL = [
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
]
RU_MONTHS = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]
RU_MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def parse_date(text: str, today: dt.date | None = None) -> dt.date | None:
    """Принимает 'сегодня'/'завтра'/'ДД.ММ'/'ДД.ММ.ГГГГ' (разделители . - /).

    Если год не указан и дата уже прошла — переносит на следующий год.
    """
    today = today or dt.date.today()
    s = (text or "").strip().lower()
    if s in {"сегодня", "today"}:
        return today
    if s in {"завтра", "tomorrow"}:
        return today + dt.timedelta(days=1)
    m = re.fullmatch(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?", s)
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    year_raw = m.group(3)
    year = today.year if year_raw is None else int(year_raw)
    if year < 100:
        year += 2000
    try:
        result = dt.date(year, month, day)
    except ValueError:
        return None
    if year_raw is None and result < today:
        try:
            result = dt.date(year + 1, month, day)
        except ValueError:
            return None
    return result


def format_date(d: dt.date) -> str:
    return d.strftime("%d.%m.%Y")


def format_date_human(d: dt.date) -> str:
    """'12 июня 2026'."""
    return f"{d.day} {RU_MONTHS_GEN[d.month - 1]} {d.year}"


def parse_time(text: str) -> dt.time | None:
    """Принимает 'ЧЧ:ММ' или 'ЧЧ'."""
    s = (text or "").strip()
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", s)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2)) if m.group(2) else 0
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return dt.time(hh, mm)
    return None


def parse_monthdays(text: str) -> list[int] | None:
    """'15' -> [15]; '1, 15' -> [1, 15]; 'последний'/'last' -> [-1]."""
    s = (text or "").strip().lower()
    if s in {"последний", "последнее", "last", "конец месяца", "конец"}:
        return [-1]
    parts = re.split(r"[,\s;]+", s)
    days: list[int] = []
    for p in parts:
        if not p:
            continue
        if not p.isdigit():
            return None
        d = int(p)
        if not 1 <= d <= 31:
            return None
        if d not in days:
            days.append(d)
    return sorted(days) if days else None


def days_left(d: dt.date, today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return (d - today).days
