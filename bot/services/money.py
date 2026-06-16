"""Валюты, парсинг и форматирование сумм.

Суммы хранятся в минорных единицах (целое число, напр. копейки/центы). Это даёт
единый формат для дробных, целых и нулевых значений и исключает ошибки float.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Разделители для красивого вывода (неразрывные — чтобы число не переносилось в Telegram)
_THIN_SPACE = " "  # узкий неразрывный пробел — разделитель тысяч
_NBSP = " "        # неразрывный пробел — перед символом валюты


@dataclass(frozen=True)
class Currency:
    code: str
    symbol: str
    exponent: int = 2  # число знаков после запятой


# Поддерживаемые валюты (легко расширяется). Порядок — как показывать в клавиатуре.
CURRENCIES: dict[str, Currency] = {
    "USD": Currency("USD", "$"),
    "EUR": Currency("EUR", "€"),
    "RUB": Currency("RUB", "₽"),
    "GBP": Currency("GBP", "£"),
    "CHF": Currency("CHF", "CHF"),
    "MXN": Currency("MXN", "Mex$"),
    "KZT": Currency("KZT", "₸"),
    "GEL": Currency("GEL", "₾"),
    "AMD": Currency("AMD", "֏"),
    "PLN": Currency("PLN", "zł"),
    "CZK": Currency("CZK", "Kč"),
    "NOK": Currency("NOK", "kr"),
    "SEK": Currency("SEK", "kr"),
    "THB": Currency("THB", "฿"),
    "KRW": Currency("KRW", "₩", 0),  # у воны нет дробной части
    "IDR": Currency("IDR", "Rp", 0),  # рупия без дробной части
    "AUD": Currency("AUD", "A$"),
    "CAD": Currency("CAD", "C$"),
    "BRL": Currency("BRL", "R$"),
    "ARS": Currency("ARS", "AR$"),
    "COP": Currency("COP", "COL$"),
    "CNY": Currency("CNY", "¥"),
    "INR": Currency("INR", "₹"),
}

CURRENCY_ORDER: list[str] = list(CURRENCIES.keys())

# Частые валюты — первый экран выбора; остальные показываются под «🌍 Больше валют».
COMMON_CURRENCIES: list[str] = ["RUB", "USD", "EUR", "MXN"]


def get_currency(code: str) -> Currency:
    """Возвращает валюту по коду; для неизвестного ISO-кода — дефолт с 2 знаками."""
    code = (code or "").upper()
    return CURRENCIES.get(code, Currency(code, code, 2))


def is_supported(code: str) -> bool:
    return (code or "").upper() in CURRENCIES


def is_valid_iso(code: str) -> bool:
    """Грубая проверка: ровно 3 латинские буквы."""
    return bool(re.fullmatch(r"[A-Za-z]{3}", (code or "").strip()))


def parse_amount(text: str, currency: str) -> int | None:
    """Парсит пользовательский ввод суммы в минорные единицы.

    Правила (локаль-агностичные):
      * пробелы (в т.ч. NBSP/узкий) — разделители тысяч, удаляются;
      * лишние символы/символ валюты отбрасываются;
      * последняя группа из 1..exponent цифр после '.'/',' трактуется как дробная часть,
        иначе все '.'/',' считаются разделителями тысяч;
      * отрицательные и нулевые суммы отклоняются (возвращается None).

    Примеры (exponent=2): '1 234,50' -> 123450, '1,234.56' -> 123456,
    '1.234' -> 123400, '9.99' -> 999, '1000' -> 100000.
    """
    cur = get_currency(currency)
    s = re.sub(r"\s", "", text or "")  # убираем все пробелы, включая NBSP/узкий
    s = re.sub(r"[^0-9.,-]", "", s)
    if not s or s in {"-", ".", ","}:
        return None
    if s.startswith("-"):
        return None  # суммы только положительные

    last_sep = max(s.rfind("."), s.rfind(","))
    if last_sep == -1:
        digits, frac = s, ""
    else:
        trailing = s[last_sep + 1:]
        if trailing.isdigit() and 1 <= len(trailing) <= max(cur.exponent, 0):
            digits = re.sub(r"[.,]", "", s[:last_sep]) or "0"
            frac = trailing
        else:
            digits = re.sub(r"[.,]", "", s)
            frac = ""

    if not digits.isdigit() or (frac and not frac.isdigit()):
        return None

    try:
        value = Decimal(f"{digits}.{frac}") if frac else Decimal(digits)
    except InvalidOperation:
        return None
    if value <= 0:
        return None

    minor = int(value.scaleb(cur.exponent).to_integral_value(rounding=ROUND_HALF_UP))
    return minor or None


def _group_thousands(digits: str) -> str:
    """'1234567' -> '1 234 567' (узкий неразрывный пробел как разделитель тысяч)."""
    n = len(digits)
    parts = [digits[max(i - 3, 0):i] for i in range(n, 0, -3)]
    return _THIN_SPACE.join(reversed(parts))


def format_money(amount_minor: int, currency: str) -> str:
    """Форматирует минорные единицы в строку с фикс. числом знаков и символом валюты.

    Единый формат: '120,00 $', '9 000,00 ₽', '1 234,50 €' (пробелы — неразрывные).
    """
    cur = get_currency(currency)
    sign = "-" if amount_minor < 0 else ""
    a = abs(amount_minor)
    if cur.exponent <= 0:
        body = _group_thousands(str(a))
    else:
        divisor = 10 ** cur.exponent
        int_part = _group_thousands(str(a // divisor))
        frac_part = str(a % divisor).rjust(cur.exponent, "0")
        body = f"{int_part},{frac_part}"
    return f"{sign}{body}{_NBSP}{cur.symbol}"
