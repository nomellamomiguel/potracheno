"""Сборка inline-клавиатур."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import (
    CategoryCB,
    CityCB,
    ConfirmCB,
    CurrencyCB,
    EditFieldCB,
    FeedbackKindCB,
    FreqCB,
    Nav,
    PaymentCB,
    ReminderToggleCB,
    SettingsCB,
    SnoozeCB,
    StatusCB,
    TimeCB,
    ToggleCB,
    WizardCB,
)
from bot.services.dates import RU_MONTHS, RU_WEEKDAYS
from bot.services.money import CURRENCY_ORDER, get_currency
from bot.services.timezones import CITY_TZ, TZ_BUTTONS
from bot.texts import CATEGORIES

REMINDER_PRESETS: list[tuple[int, str]] = [
    (3, "За 3 дня"),
    (1, "За 1 день"),
    (0, "В день платежа"),
]
NOTIFY_TIME_PRESETS = ["09:00", "10:00", "12:00", "18:00", "20:00", "21:00"]


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить платёж", callback_data=Nav(action="add"))
    b.button(text="📋 Мои платежи", callback_data=Nav(action="list"))
    b.button(text="📊 Статус", callback_data=Nav(action="status"))
    b.button(text="⚙️ Настройки", callback_data=Nav(action="settings"))
    b.button(text="✉️ Обратная связь", callback_data=Nav(action="feedback"))
    b.button(text="❓ Помощь", callback_data=Nav(action="help"))
    b.adjust(1, 2, 2, 1)
    return b.as_markup()


def add_first_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить платёж", callback_data=Nav(action="add"))
    b.button(text="Позже", callback_data=Nav(action="menu"))
    b.adjust(1)
    return b.as_markup()


def tz_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for city in TZ_BUTTONS:
        if city in CITY_TZ:
            b.button(text=city, callback_data=CityCB(name=city))
    b.adjust(4)
    return b.as_markup()


def notify_time_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in NOTIFY_TIME_PRESETS:
        b.button(text=t, callback_data=TimeCB(value=t.replace(":", "")))
    b.adjust(3)
    return b.as_markup()


def category_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, name in enumerate(CATEGORIES):
        b.button(text=name, callback_data=CategoryCB(idx=i))
    b.button(text="✍️ Своя категория", callback_data=CategoryCB(idx=-1))
    b.adjust(2)
    return b.as_markup()


def currency_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code in CURRENCY_ORDER:
        cur = get_currency(code)
        b.button(text=f"{code} {cur.symbol}", callback_data=CurrencyCB(code=code))
    b.button(text="Другая (ISO)", callback_data=CurrencyCB(code="custom"))
    b.adjust(3)
    return b.as_markup()


def freq_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Неделя", callback_data=FreqCB(value="week"))
    b.button(text="Месяц", callback_data=FreqCB(value="month"))
    b.button(text="Квартал", callback_data=FreqCB(value="quarter"))
    b.button(text="Год", callback_data=FreqCB(value="year"))
    b.button(text="Разово", callback_data=FreqCB(value="once"))
    b.adjust(2, 2, 1)
    return b.as_markup()


def weekdays_kb(selected: set[int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, name in enumerate(RU_WEEKDAYS):
        mark = "✅ " if i in selected else ""
        b.button(text=f"{mark}{name}", callback_data=ToggleCB(group="wd", value=i))
    b.button(text="Готово ✓", callback_data=WizardCB(action="done_week"))
    b.adjust(4, 3, 1)
    return b.as_markup()


def months_kb(selected: set[int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for m in range(1, 13):
        mark = "✅ " if m in selected else ""
        label = RU_MONTHS[m - 1][:3].capitalize()
        b.button(text=f"{mark}{label}", callback_data=ToggleCB(group="mo", value=m))
    b.button(text="Готово ✓", callback_data=WizardCB(action="done_year"))
    b.adjust(3, 3, 3, 3, 1)
    return b.as_markup()


def reminders_kb(selected: list[int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for days, label in REMINDER_PRESETS:
        mark = "✅ " if days in selected else ""
        b.button(text=f"{mark}{label}", callback_data=ReminderToggleCB(days=days))
    b.button(text="Другое (N дней)", callback_data=WizardCB(action="rem_custom"))
    b.button(text="Готово ✓", callback_data=WizardCB(action="done_reminders"))
    b.adjust(1, 1, 1, 1, 1)
    return b.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Сохранить", callback_data=ConfirmCB(action="save"))
    b.button(text="✖️ Отмена", callback_data=ConfirmCB(action="cancel"))
    b.adjust(2)
    return b.as_markup()


def payment_list_kb(payments) -> InlineKeyboardMarkup:
    from bot.services.money import format_money

    b = InlineKeyboardBuilder()
    for p in payments:
        label = f"{p.title} — {format_money(p.amount_minor, p.currency)}"
        b.button(text=label[:60], callback_data=PaymentCB(action="open", id=p.id))
    b.button(text="➕ Добавить", callback_data=Nav(action="add"))
    b.button(text="⬅️ Меню", callback_data=Nav(action="menu"))
    b.adjust(1)
    return b.as_markup()


def payment_card_kb(payment) -> InlineKeyboardMarkup:
    status = payment.status.value if hasattr(payment.status, "value") else str(payment.status)
    b = InlineKeyboardBuilder()
    pid = payment.id
    if status == "active":
        b.button(text="✏️ Изменить", callback_data=PaymentCB(action="edit", id=pid))
        b.button(text="⏸ Пауза", callback_data=PaymentCB(action="pause", id=pid))
        b.button(text="🗄 Архив", callback_data=PaymentCB(action="archive", id=pid))
        b.button(text="🗑 Удалить", callback_data=PaymentCB(action="delete", id=pid))
    else:
        b.button(text="▶️ Вернуть в активные", callback_data=PaymentCB(action="resume", id=pid))
        b.button(text="🗑 Удалить", callback_data=PaymentCB(action="delete", id=pid))
    b.button(text="⬅️ К списку", callback_data=PaymentCB(action="list", id=pid))
    b.adjust(2, 2, 1)
    return b.as_markup()


def edit_fields_kb(pid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Название", callback_data=EditFieldCB(field="title", id=pid))
    b.button(text="Категория", callback_data=EditFieldCB(field="category", id=pid))
    b.button(text="Валюта", callback_data=EditFieldCB(field="currency", id=pid))
    b.button(text="Сумма", callback_data=EditFieldCB(field="amount", id=pid))
    b.button(text="Периодичность", callback_data=EditFieldCB(field="freq", id=pid))
    b.button(text="Напоминания", callback_data=EditFieldCB(field="reminders", id=pid))
    b.button(text="⬅️ Назад", callback_data=PaymentCB(action="open", id=pid))
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def delete_confirm_kb(pid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить", callback_data=PaymentCB(action="confirm_delete", id=pid))
    b.button(text="Отмена", callback_data=PaymentCB(action="open", id=pid))
    b.adjust(2)
    return b.as_markup()


def reminder_actions_kb(pid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Оплатил", callback_data=PaymentCB(action="pay", id=pid))
    b.button(text="⏰ Отложить", callback_data=PaymentCB(action="snooze", id=pid))
    b.button(text="✏️ Изменить", callback_data=PaymentCB(action="edit", id=pid))
    b.button(text="🗑 Больше не плачу", callback_data=PaymentCB(action="archive", id=pid))
    b.adjust(2, 2)
    return b.as_markup()


def snooze_kb(pid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="+1 день", callback_data=SnoozeCB(id=pid, days=1))
    b.button(text="+3 дня", callback_data=SnoozeCB(id=pid, days=3))
    b.button(text="+1 неделя", callback_data=SnoozeCB(id=pid, days=7))
    b.adjust(3)
    return b.as_markup()


def status_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="На неделе", callback_data=StatusCB(period="week"))
    b.button(text="В этом месяце", callback_data=StatusCB(period="month"))
    b.button(text="За 12 мес", callback_data=StatusCB(period="year"))
    b.button(text="⏭ Ближайший", callback_data=StatusCB(period="nearest"))
    b.button(text="⬅️ Меню", callback_data=Nav(action="menu"))
    b.adjust(2, 2, 1)
    return b.as_markup()


def feedback_kind_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🐞 Нашёл ошибку", callback_data=FeedbackKindCB(kind="bug"))
    b.button(text="💡 Есть идея", callback_data=FeedbackKindCB(kind="idea"))
    b.adjust(1)
    return b.as_markup()


def settings_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🕒 Часовой пояс", callback_data=SettingsCB(field="tz"))
    b.button(text="⏰ Время напоминаний", callback_data=SettingsCB(field="time"))
    b.button(text="⬅️ Меню", callback_data=Nav(action="menu"))
    b.adjust(1)
    return b.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Меню", callback_data=Nav(action="menu"))
    return b.as_markup()
