"""FSM-состояния для диалоговых сценариев."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    tz = State()
    notify_time = State()


class AddPayment(StatesGroup):
    title = State()
    category = State()
    category_custom = State()
    currency = State()
    currency_custom = State()
    amount = State()
    freq = State()
    week_days = State()
    month_days = State()
    year_months = State()
    year_day = State()
    once_date = State()
    reminders = State()
    payment_method = State()
    confirm = State()


class EditPayment(StatesGroup):
    waiting_value = State()


class FeedbackFSM(StatesGroup):
    kind = State()
    text = State()


class SettingsFSM(StatesGroup):
    tz = State()
    notify_time = State()


class PaymentMethodFSM(StatesGroup):
    add = State()
    rename = State()
