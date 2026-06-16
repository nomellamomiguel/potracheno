"""Типизированные callback-data для inline-кнопок."""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class Nav(CallbackData, prefix="nav"):
    action: str  # add | list | status | settings | feedback | help | menu | add_first


class CityCB(CallbackData, prefix="city"):
    name: str


class TimeCB(CallbackData, prefix="time"):
    value: str  # "HHMM" без двоеточия (":" — служебный разделитель callback_data в aiogram)


class CurrencyCB(CallbackData, prefix="cur"):
    code: str  # ISO-код, либо служебное: "more" | "back" | "custom"


class CategoryCB(CallbackData, prefix="cat"):
    idx: int  # индекс в CATEGORIES, -1 = своя


class FreqCB(CallbackData, prefix="freq"):
    value: str  # week | month | quarter | year | once


class ToggleCB(CallbackData, prefix="tg"):
    group: str  # "wd" (день недели 0..6) | "mo" (месяц 1..12)
    value: int


class WizardCB(CallbackData, prefix="wz"):
    action: str  # done_week | done_year | done_reminders | cur_custom | cat_custom | rem_custom


class ReminderToggleCB(CallbackData, prefix="rem"):
    days: int


class ConfirmCB(CallbackData, prefix="cfm"):
    action: str  # save | cancel


class PaymentCB(CallbackData, prefix="pmt"):
    action: str  # open|pay|edit|pause|resume|archive|delete|confirm_delete|snooze|list
    id: int


class EditFieldCB(CallbackData, prefix="edt"):
    field: str  # title|category|currency|amount|freq|reminders
    id: int


class SnoozeCB(CallbackData, prefix="snz"):
    id: int
    days: int


class StatusCB(CallbackData, prefix="st"):
    period: str  # week | month | year | nearest | menu


class FeedbackKindCB(CallbackData, prefix="fbk"):
    kind: str  # bug | idea


class SettingsCB(CallbackData, prefix="set"):
    field: str  # tz | time | methods | reset | reset_confirm | menu


class MethodCB(CallbackData, prefix="pm"):
    action: str  # open | add | rename | delete | confirm_delete | list
    id: int      # 0 — когда id не нужен
