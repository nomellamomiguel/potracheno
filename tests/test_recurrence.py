import datetime as dt
from types import SimpleNamespace

import pytest

from bot.services.recurrence import (
    next_due_for_payment,
    next_occurrence,
    next_occurrences,
)

D = dt.date


def test_weekly_every_week():
    occ = next_occurrences(freq="week", anchor_date=D(2026, 6, 1), count=3)
    assert occ == [D(2026, 6, 1), D(2026, 6, 8), D(2026, 6, 15)]


def test_weekly_interval_two():
    occ = next_occurrences(freq="week", anchor_date=D(2026, 6, 1), interval=2, count=3)
    assert occ == [D(2026, 6, 1), D(2026, 6, 15), D(2026, 6, 29)]


def test_weekly_multiple_weekdays():
    occ = next_occurrences(
        freq="week",
        anchor_date=D(2026, 6, 1),
        by_weekdays=[0, 2, 4],  # Пн/Ср/Пт
        count=6,
        after=D(2026, 5, 31),
    )
    assert len(occ) == 6
    assert all(o.weekday() in {0, 2, 4} for o in occ)
    assert occ == sorted(occ)
    assert all(o >= D(2026, 6, 1) for o in occ)


def test_monthly_day_clamp_to_end():
    occ = next_occurrences(
        freq="month", anchor_date=D(2026, 1, 31), by_monthdays=[31], count=3
    )
    assert occ == [D(2026, 1, 31), D(2026, 2, 28), D(2026, 3, 31)]


def test_monthly_last_day_sentinel():
    occ = next_occurrences(
        freq="month", anchor_date=D(2026, 1, 15), by_monthdays=[-1], count=3
    )
    assert occ == [D(2026, 1, 31), D(2026, 2, 28), D(2026, 3, 31)]


def test_monthly_multiple_days():
    occ = next_occurrences(
        freq="month", anchor_date=D(2026, 6, 1), by_monthdays=[1, 15], count=4
    )
    assert occ == [D(2026, 6, 1), D(2026, 6, 15), D(2026, 7, 1), D(2026, 7, 15)]


def test_monthly_leap_year():
    occ = next_occurrences(
        freq="month", anchor_date=D(2024, 1, 31), by_monthdays=[31], count=2
    )
    assert occ == [D(2024, 1, 31), D(2024, 2, 29)]  # 2024 — високосный


def test_quarterly():
    occ = next_occurrences(
        freq="quarter", anchor_date=D(2026, 1, 10), by_monthdays=[10], count=3
    )
    assert occ == [D(2026, 1, 10), D(2026, 4, 10), D(2026, 7, 10)]


def test_yearly():
    occ = next_occurrences(freq="year", anchor_date=D(2026, 3, 15), count=2)
    assert occ == [D(2026, 3, 15), D(2027, 3, 15)]


def test_yearly_several_months():
    occ = next_occurrences(
        freq="year",
        anchor_date=D(2026, 3, 1),
        by_months=[3, 9],
        by_monthdays=[1],
        count=3,
    )
    assert occ == [D(2026, 3, 1), D(2026, 9, 1), D(2027, 3, 1)]


def test_once():
    assert next_occurrences(freq="once", anchor_date=D(2026, 5, 1)) == [D(2026, 5, 1)]
    # если дата уже наступила (after >= anchor) — пусто
    assert next_occurrences(freq="once", anchor_date=D(2026, 5, 1), after=D(2026, 5, 1)) == []


def test_after_filters_past():
    nxt = next_occurrence(
        freq="month", anchor_date=D(2026, 1, 15), by_monthdays=[15], after=D(2026, 6, 20)
    )
    assert nxt == D(2026, 7, 15)


def test_next_due_for_payment_obj():
    payment = SimpleNamespace(
        freq="month",
        anchor_date=D(2026, 1, 15),
        interval=1,
        by_weekdays=None,
        by_monthdays=[15],
        by_months=None,
    )
    assert next_due_for_payment(payment, after=D(2026, 2, 1)) == D(2026, 2, 15)


def test_unknown_freq_raises():
    with pytest.raises(ValueError):
        next_occurrences(freq="daily", anchor_date=D(2026, 1, 1))
