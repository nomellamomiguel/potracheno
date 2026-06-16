import pytest

from bot.services.money import format_money, get_currency, is_supported, parse_amount


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1000", 100000),
        ("1 000", 100000),
        ("1234,50", 123450),
        ("1 234,50", 123450),
        ("1,234.56", 123456),
        ("1.234,56", 123456),
        ("1.234", 123400),          # одиночная точка + 3 цифры -> разделитель тысяч
        ("9.99", 999),
        ("9,99", 999),
        ("0,99", 99),
        ("100", 10000),
        ("100.00", 10000),
        ("1 000 000", 100000000),
        ("1,000,000", 100000000),
        ("120 $", 12000),
        ("9000 RUB", 900000),
        ("12,5", 1250),
        ("12.5", 1250),
        ("9.999", 999900),          # 3 цифры -> тысячи => 9999.00
    ],
)
def test_parse_amount_valid(text, expected):
    assert parse_amount(text, "USD") == expected


@pytest.mark.parametrize(
    "text", ["", "  ", "abc", "-5", "0", "0,00", "-1,5", ".", ",", "$$$"]
)
def test_parse_amount_invalid(text):
    assert parse_amount(text, "USD") is None


def test_parse_amount_three_decimal_currency():
    # у валюты с exponent=3 три цифры после запятой — это дробная часть
    from bot.services import money

    money.CURRENCIES["BHD"] = money.Currency("BHD", "BD", 3)
    try:
        assert parse_amount("1,234", "BHD") == 1234  # 1.234 -> 1234 минорных
    finally:
        del money.CURRENCIES["BHD"]


@pytest.mark.parametrize(
    "minor,currency,expected",
    [
        (12000, "USD", "120,00 USD"),
        (123450, "RUB", "1 234,50 RUB"),
        (900000, "RUB", "9 000,00 RUB"),
        (99, "USD", "0,99 USD"),
        (50, "EUR", "0,50 EUR"),
        (12000, "AED", "120,00 AED"),
        (100000000, "USD", "1 000 000,00 USD"),
    ],
)
def test_format_money(minor, currency, expected):
    assert format_money(minor, currency) == expected


def test_format_money_zero_exponent():
    # KRW/VND без дробной части — тоже код вместо символа
    assert format_money(1500, "KRW") == "1 500 KRW"


def test_round_trip():
    for text in ("1 234,50", "9,99", "1000000"):
        minor = parse_amount(text, "RUB")
        # после parse->format->parse значение не меняется (код валюты при парсинге отбрасывается)
        assert parse_amount(format_money(minor, "RUB"), "RUB") == minor


def test_unknown_currency_defaults():
    cur = get_currency("XYZ")
    assert cur.code == "XYZ" and cur.exponent == 2
    assert not is_supported("XYZ")
    assert is_supported("usd")
