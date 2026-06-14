"""Помощник для выбора часового пояса в онбординге.

CITY_TZ: для каждого города два ключа — русское и английское название — на одну IANA-зону.
"""
from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

# Популярные города -> IANA tz (рус + англ ключи на одну зону)
CITY_TZ: dict[str, str] = {
    # --- СНГ / Россия ---
    "Москва": "Europe/Moscow", "Moscow": "Europe/Moscow",
    "Санкт-Петербург": "Europe/Moscow", "Saint Petersburg": "Europe/Moscow",
    "Казань": "Europe/Moscow", "Kazan": "Europe/Moscow",
    "Сочи": "Europe/Moscow", "Sochi": "Europe/Moscow",
    "Калининград": "Europe/Kaliningrad", "Kaliningrad": "Europe/Kaliningrad",
    "Екатеринбург": "Asia/Yekaterinburg", "Yekaterinburg": "Asia/Yekaterinburg",
    "Новосибирск": "Asia/Novosibirsk", "Novosibirsk": "Asia/Novosibirsk",
    "Красноярск": "Asia/Krasnoyarsk", "Krasnoyarsk": "Asia/Krasnoyarsk",
    "Владивосток": "Asia/Vladivostok", "Vladivostok": "Asia/Vladivostok",
    "Алматы": "Asia/Almaty", "Almaty": "Asia/Almaty",
    "Астана": "Asia/Almaty", "Astana": "Asia/Almaty",
    "Ташкент": "Asia/Tashkent", "Tashkent": "Asia/Tashkent",
    "Бишкек": "Asia/Bishkek", "Bishkek": "Asia/Bishkek",
    "Душанбе": "Asia/Dushanbe", "Dushanbe": "Asia/Dushanbe",
    "Тбилиси": "Asia/Tbilisi", "Tbilisi": "Asia/Tbilisi",
    "Ереван": "Asia/Yerevan", "Yerevan": "Asia/Yerevan",
    "Баку": "Asia/Baku", "Baku": "Asia/Baku",
    "Минск": "Europe/Minsk", "Minsk": "Europe/Minsk",
    "Киев": "Europe/Kyiv", "Kyiv": "Europe/Kyiv", "Kiev": "Europe/Kyiv",
    # --- Европа ---
    "Лондон": "Europe/London", "London": "Europe/London",
    "Париж": "Europe/Paris", "Paris": "Europe/Paris",
    "Берлин": "Europe/Berlin", "Berlin": "Europe/Berlin",
    "Гамбург": "Europe/Berlin", "Hamburg": "Europe/Berlin",
    "Мадрид": "Europe/Madrid", "Madrid": "Europe/Madrid",
    "Барселона": "Europe/Madrid", "Barcelona": "Europe/Madrid",
    "Лиссабон": "Europe/Lisbon", "Lisbon": "Europe/Lisbon",
    "Рим": "Europe/Rome", "Rome": "Europe/Rome",
    "Милан": "Europe/Rome", "Milan": "Europe/Rome",
    "Прага": "Europe/Prague", "Prague": "Europe/Prague",
    "Вена": "Europe/Vienna", "Vienna": "Europe/Vienna",
    "Варшава": "Europe/Warsaw", "Warsaw": "Europe/Warsaw",
    "Стамбул": "Europe/Istanbul", "Istanbul": "Europe/Istanbul",
    "Белград": "Europe/Belgrade", "Belgrade": "Europe/Belgrade",
    "Амстердам": "Europe/Amsterdam", "Amsterdam": "Europe/Amsterdam",
    "Цюрих": "Europe/Zurich", "Zurich": "Europe/Zurich",
    "Женева": "Europe/Zurich", "Geneva": "Europe/Zurich",
    "Дублин": "Europe/Dublin", "Dublin": "Europe/Dublin",
    "Осло": "Europe/Oslo", "Oslo": "Europe/Oslo",
    "Стокгольм": "Europe/Stockholm", "Stockholm": "Europe/Stockholm",
    "Хельсинки": "Europe/Helsinki", "Helsinki": "Europe/Helsinki",
    "Афины": "Europe/Athens", "Athens": "Europe/Athens",
    "Будапешт": "Europe/Budapest", "Budapest": "Europe/Budapest",
    # --- Северная Америка ---
    "Нью-Йорк": "America/New_York", "New York": "America/New_York",
    "Бостон": "America/New_York", "Boston": "America/New_York",
    "Майами": "America/New_York", "Miami": "America/New_York",
    "Чикаго": "America/Chicago", "Chicago": "America/Chicago",
    "Денвер": "America/Denver", "Denver": "America/Denver",
    "Лос-Анджелес": "America/Los_Angeles", "Los Angeles": "America/Los_Angeles",
    "Сан-Франциско": "America/Los_Angeles", "San Francisco": "America/Los_Angeles",
    "Сиэтл": "America/Los_Angeles", "Seattle": "America/Los_Angeles",
    "Торонто": "America/Toronto", "Toronto": "America/Toronto",
    "Монреаль": "America/Toronto", "Montreal": "America/Toronto",
    "Ванкувер": "America/Vancouver", "Vancouver": "America/Vancouver",
    "Мехико": "America/Mexico_City", "Mexico City": "America/Mexico_City",
    # --- Южная Америка ---
    "Буэнос-Айрес": "America/Argentina/Buenos_Aires", "Buenos Aires": "America/Argentina/Buenos_Aires",
    "Сан-Паулу": "America/Sao_Paulo", "Sao Paulo": "America/Sao_Paulo",
    "Рио-де-Жанейро": "America/Sao_Paulo", "Rio de Janeiro": "America/Sao_Paulo",
    "Богота": "America/Bogota", "Bogota": "America/Bogota",
    "Сантьяго": "America/Santiago", "Santiago": "America/Santiago",
    "Лима": "America/Lima", "Lima": "America/Lima",
    "Монтевидео": "America/Montevideo", "Montevideo": "America/Montevideo",
    # --- Азия / Ближний Восток ---
    "Бангкок": "Asia/Bangkok", "Bangkok": "Asia/Bangkok",
    "Сеул": "Asia/Seoul", "Seoul": "Asia/Seoul",
    "Токио": "Asia/Tokyo", "Tokyo": "Asia/Tokyo",
    "Сингапур": "Asia/Singapore", "Singapore": "Asia/Singapore",
    "Гонконг": "Asia/Hong_Kong", "Hong Kong": "Asia/Hong_Kong",
    "Шанхай": "Asia/Shanghai", "Shanghai": "Asia/Shanghai",
    "Пекин": "Asia/Shanghai", "Beijing": "Asia/Shanghai",
    "Дубай": "Asia/Dubai", "Dubai": "Asia/Dubai",
    "Тель-Авив": "Asia/Jerusalem", "Tel Aviv": "Asia/Jerusalem",
    "Дели": "Asia/Kolkata", "Delhi": "Asia/Kolkata",
    "Мумбаи": "Asia/Kolkata", "Mumbai": "Asia/Kolkata",
    "Денпасар": "Asia/Makassar", "Denpasar": "Asia/Makassar",
    "Бали": "Asia/Makassar", "Bali": "Asia/Makassar",
    "Куала-Лумпур": "Asia/Kuala_Lumpur", "Kuala Lumpur": "Asia/Kuala_Lumpur",
    "Джакарта": "Asia/Jakarta", "Jakarta": "Asia/Jakarta",
    # --- Австралия / Океания ---
    "Сидней": "Australia/Sydney", "Sydney": "Australia/Sydney",
    "Мельбурн": "Australia/Melbourne", "Melbourne": "Australia/Melbourne",
    "Брисбен": "Australia/Brisbane", "Brisbane": "Australia/Brisbane",
    "Перт": "Australia/Perth", "Perth": "Australia/Perth",
    "Окленд": "Pacific/Auckland", "Auckland": "Pacific/Auckland",
}

# Ровно 20 кнопок (5 рядов по 4) — популярные для русскоязычной аудитории, без дублей зон.
TZ_BUTTONS: list[str] = [
    "Москва", "Калининград", "Екатеринбург", "Новосибирск",
    "Владивосток", "Алматы", "Ташкент", "Тбилиси",
    "Ереван", "Баку", "Минск", "Киев",
    "Варшава", "Стамбул", "Берлин", "Лондон",
    "Лиссабон", "Дубай", "Бангкок", "Мехико",
]


@lru_cache(maxsize=1)
def _all_tz() -> frozenset[str]:
    return frozenset(available_timezones())


def resolve_tz(text: str) -> str | None:
    """Город (рус/англ, без учёта регистра) или прямой IANA-идентификатор -> tz; иначе None."""
    s = (text or "").strip()
    if not s:
        return None
    # 1) точное совпадение с городом без учёта регистра
    low = s.lower()
    for city, tz in CITY_TZ.items():
        if city.lower() == low:
            return tz
    # 2) прямой IANA-идентификатор
    if s in _all_tz():
        return s
    # 3) IANA без учёта регистра
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
