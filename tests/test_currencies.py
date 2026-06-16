from bot.keyboards import MORE_CURRENCIES_ORDER
from bot.services.money import COMMON_CURRENCIES, CURRENCIES


def test_more_currencies_all_in_currencies():
    for code in MORE_CURRENCIES_ORDER:
        assert code in CURRENCIES, f"{code} отсутствует в CURRENCIES"


def test_more_currencies_no_common():
    for code in COMMON_CURRENCIES:
        assert code not in MORE_CURRENCIES_ORDER


def test_more_currencies_no_duplicates():
    assert len(MORE_CURRENCIES_ORDER) == len(set(MORE_CURRENCIES_ORDER))


def test_more_currencies_full_coverage():
    # выбран вариант «все некоммон-валюты» (включая KRW/IDR)
    assert set(MORE_CURRENCIES_ORDER) == set(CURRENCIES) - set(COMMON_CURRENCIES)
