from decimal import Decimal

import pytest

from app.adapters.rates import FakeRates
from app.money import (
    MoneyError,
    check_pay_range,
    from_cop,
    reference_amounts,
    split_tax_included,
    to_cop,
    to_factus_str,
)

R = FakeRates.RATES  # 1 COP = 0.00025 USD  => 1 USD = 4.000 COP


def test_conversion_direction_rates_are_units_per_cop():
    # Si la dirección estuviera invertida, 75 USD darían 0,01875 COP.
    assert to_cop(Decimal("75"), "USD", R) == Decimal("300000")
    assert from_cop(Decimal("300000"), "USD", R) == Decimal("75.00")


def test_cop_and_jpy_have_no_decimals():
    refs = reference_amounts(Decimal("123457"), R)
    assert refs["COP"] == Decimal("123457")
    assert refs["JPY"].as_tuple().exponent == 0
    assert refs["USD"].as_tuple().exponent == -2


def test_factus_amount_string_has_two_decimals():
    assert to_factus_str(Decimal("20000")) == "20000.00"


@pytest.mark.parametrize(
    ("amount", "ok"),
    [("9999", False), ("10000", True), ("12100000", True), ("12100001", False)],
)
def test_pay_range(amount, ok):
    def check():
        check_pay_range(Decimal(amount), Decimal("10000"), Decimal("12100000"))

    if ok:
        check()
    else:
        with pytest.raises(MoneyError):
            check()


def test_empty_env_values_mean_not_configured():
    from app.config import Settings

    s = Settings(_env_file=None, factus_pay_webhook_key="", factus_numbering_range_id="  ")
    assert s.factus_pay_webhook_key is None  # un webhook nunca acepta llave vacía
    assert s.factus_numbering_range_id is None


def test_pasted_secrets_are_cleaned():
    from app.config import Settings

    s = Settings(_env_file=None, factus_password=" 'clave%ficticia' ",  # noqa: S106
                 factus_client_id='"abc-123"\n', factus_username="user@x.co")
    assert s.factus_password.get_secret_value() == "clave%ficticia"
    assert s.factus_client_id.get_secret_value() == "abc-123"
    assert s.factus_username.get_secret_value() == "user@x.co"


def test_database_url_from_render_and_neon():
    from app.config import Settings

    def url(v: str) -> str:
        return Settings(_env_file=None, database_url=v).database_url

    assert url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert url(
        "postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require"
    ) == "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require"


def test_split_tax_included_matches_total():
    price, rounding = split_tax_included(Decimal("150000"), Decimal("19"))
    assert price == Decimal("126050.42")
    assert (price * Decimal("1.19")).quantize(Decimal("0.01")) + rounding == Decimal("150000")
