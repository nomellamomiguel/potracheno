"""Движок периодичности: вычисление ближайших дат платежей.

Поддерживаемые частоты (`freq`):
  * week    — еженедельно/несколько раз в неделю (by_weekdays), каждые N недель (interval);
  * month   — ежемесячно/несколько чисел (by_monthdays), каждые N месяцев (interval);
  * quarter — раз в квартал (= каждые 3*interval месяцев) по числу(ам) by_monthdays;
  * year    — раз в год/несколько раз в год (by_months) по числу by_monthdays;
  * once    — разовый платёж (только anchor_date).

Дни месяца клэмпятся к последнему дню (31 в феврале -> 28/29); значение -1 = последний день.
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections.abc import Sequence

from dateutil.rrule import WEEKLY, rrule

_SAFE_ITER_LIMIT = 2000


def _clamp_day(year: int, month: int, day: int) -> int:
    last = calendar.monthrange(year, month)[1]
    if day == -1 or day > last:
        return last
    return max(1, day)


def _add_months(year: int, month0: int, delta: int) -> tuple[int, int]:
    """month0 — индекс месяца 0..11. Возвращает (year, month 1..12)."""
    total = month0 + delta
    return year + total // 12, total % 12 + 1


def _week_occurrences(anchor, after, interval, weekdays, count):
    weekdays = sorted(weekdays) if weekdays else [anchor.weekday()]
    rule = rrule(
        WEEKLY,
        interval=interval,
        byweekday=weekdays,
        dtstart=dt.datetime.combine(anchor, dt.time()),
    )
    horizon = after + dt.timedelta(days=366 * 10)
    res: list[dt.date] = []
    for d in rule:
        occ = d.date()
        if occ < anchor:
            continue
        if occ > after:
            res.append(occ)
            if len(res) >= count:
                break
        if occ > horizon:  # safety: rrule бесконечен
            break
    return res


def _month_step_occurrences(anchor, after, months_step, monthdays, count):
    days = monthdays or [anchor.day]
    res: list[dt.date] = []
    k = 0
    while len(res) < count and k < _SAFE_ITER_LIMIT:
        y, m = _add_months(anchor.year, anchor.month - 1, months_step * k)
        k += 1
        for d in days:
            occ = dt.date(y, m, _clamp_day(y, m, d))
            if occ >= anchor and occ > after:
                res.append(occ)
    return sorted(set(res))[:count]


def _year_occurrences(anchor, after, interval, months, monthday, count):
    months = sorted(months) if months else [anchor.month]
    day = monthday if monthday is not None else anchor.day
    res: list[dt.date] = []
    k = 0
    while len(res) < count and k < _SAFE_ITER_LIMIT:
        y = anchor.year + interval * k
        k += 1
        for mo in months:
            occ = dt.date(y, mo, _clamp_day(y, mo, day))
            if occ >= anchor and occ > after:
                res.append(occ)
    return sorted(set(res))[:count]


def next_occurrences(
    *,
    freq: str,
    anchor_date: dt.date,
    interval: int = 1,
    by_weekdays: Sequence[int] | None = None,
    by_monthdays: Sequence[int] | None = None,
    by_months: Sequence[int] | None = None,
    after: dt.date | None = None,
    count: int = 1,
) -> list[dt.date]:
    """До `count` ближайших дат платежа строго после `after` и не раньше `anchor_date`.

    `after` по умолчанию — день перед anchor_date (вернётся и сама дата старта).
    """
    if after is None:
        after = anchor_date - dt.timedelta(days=1)
    interval = max(interval or 1, 1)

    if freq == "once":
        return [anchor_date] if anchor_date > after else []
    if freq == "week":
        return _week_occurrences(anchor_date, after, interval, list(by_weekdays or []), count)
    if freq == "month":
        return _month_step_occurrences(anchor_date, after, interval, list(by_monthdays or []), count)
    if freq == "quarter":
        return _month_step_occurrences(anchor_date, after, 3 * interval, list(by_monthdays or []), count)
    if freq == "year":
        md = (list(by_monthdays or []) or [None])[0]
        return _year_occurrences(anchor_date, after, interval, list(by_months or []), md, count)
    raise ValueError(f"Unknown freq: {freq!r}")


def next_occurrence(*, after: dt.date | None = None, **kwargs) -> dt.date | None:
    occ = next_occurrences(after=after, count=1, **kwargs)
    return occ[0] if occ else None


def _freq_value(freq) -> str:
    return freq.value if hasattr(freq, "value") else str(freq)


def next_due_for_payment(payment, after: dt.date | None = None) -> dt.date | None:
    """Удобная обёртка: считает следующую дату для ORM-объекта Payment."""
    return next_occurrence(
        freq=_freq_value(payment.freq),
        anchor_date=payment.anchor_date,
        interval=payment.interval or 1,
        by_weekdays=payment.by_weekdays,
        by_monthdays=payment.by_monthdays,
        by_months=payment.by_months,
        after=after,
    )
