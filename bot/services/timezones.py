"""Помощник для выбора часового пояса в онбординге."""
from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

# Популярные города -> IANA tz (для кнопок и быстрого ввода)
CITY_TZ: dict[str, str] = {
    "Москва": "Europe/Moscow",
    "Санкт-Петербург": "Europe/Moscow",
    "Калининград": "Europe/Kaliningrad",
    "Екатеринбург": "Asia/Yekaterinburg",
    "Новосибирск": "Asia/Novosibirsk",
    "Владивосток": "Asia/Vladivostok",
    "Алматы": "Asia/Almaty",
    "Астана": "Asia/Almaty",
    "Тбилиси": "Asia/Tbilisi",
    "Ереван": "Asia/Yerevan",
    "Баку": "Asia/Baku",
    "Варшава": "Europe/Warsaw",
    "Мехико": "America/Mexico_City",
    "Киев": "Europe/Kyiv",
    "Минск": "Europe/Minsk",
    "Стамбул": "Europe/Istanbul",
    "Берлин": "Europe/Berlin",
    "Лондон": "Europe/London",
    "Дубай": "Asia/Dubai",
    "Белград": "Europe/Belgrade",
}

# Кнопки для онбординга (подмножество)
TZ_BUTTONS: list[str] = [
    "Москва", "Калининград", "Екатеринбург", "Новосибирск",
    "Алматы", "Тбилиси", "Ереван", "Баку",
    "Варшава", "Мехико", "Киев", "Минск",
    "Стамбул", "Белград", "Берлин", "Дубай",
]


@lru_cache(maxsize=1)
def _all_tz() -> frozenset[str]:
    return frozenset(available_timezones())


def resolve_tz(text: str) -> str | None:
    """Город из списка или прямой IANA-идентификатор -> tz; иначе None."""
    s = (text or "").strip()
    if not s:
        return None
    for city, tz in CITY_TZ.items():
        if city.lower() == s.lower():
            return tz
    if s in _all_tz():
        return s
    # допускаем ввод без учёта регистра для IANA
    low = s.lower()
    for tz in _all_tz():
        if tz.lower() == low:
            return tz
    return None


def is_valid_tz(key: str) -> bool:
    try:
        ZoneInfo(key)
        return True
    except Exception:
        return False
