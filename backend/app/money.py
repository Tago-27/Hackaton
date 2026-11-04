"""Reglas de dinero. Siempre Decimal, nunca float.

Convención de tasas: `rates[X]` = unidades de la moneda X por 1 COP
(así responde open.er-api.com/v6/latest/COP). Por tanto:
    monto_en_X   = monto_cop * rates[X]
    monto_en_cop = monto_en_X / rates[X]
"""

from decimal import ROUND_HALF_UP, Decimal

DISPLAY_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "COP", "GBP", "JPY")
ZERO_DECIMAL_CURRENCIES = frozenset({"COP", "JPY"})


class MoneyError(ValueError):
    pass


def quantum(currency: str) -> Decimal:
    return Decimal("1") if currency in ZERO_DECIMAL_CURRENCIES else Decimal("0.01")


def round_currency(amount: Decimal, currency: str) -> Decimal:
    return amount.quantize(quantum(currency), rounding=ROUND_HALF_UP)


def to_cop(amount: Decimal, currency: str, rates: dict[str, Decimal]) -> Decimal:
    """Convierte un monto en `currency` a COP entero (el cobro es en pesos sin centavos)."""
    if currency == "COP":
        return round_currency(amount, "COP")
    rate = rates.get(currency)
    if rate is None or rate <= 0:
        raise MoneyError(f"No hay tasa para {currency}")
    return round_currency(amount / rate, "COP")


def from_cop(amount_cop: Decimal, currency: str, rates: dict[str, Decimal]) -> Decimal:
    if currency == "COP":
        return round_currency(amount_cop, "COP")
    rate = rates.get(currency)
    if rate is None or rate <= 0:
        raise MoneyError(f"No hay tasa para {currency}")
    return round_currency(amount_cop * rate, currency)


def reference_amounts(amount_cop: Decimal, rates: dict[str, Decimal]) -> dict[str, Decimal]:
    return {c: from_cop(amount_cop, c, rates) for c in DISPLAY_CURRENCIES}


def to_factus_str(amount: Decimal) -> str:
    """Factus espera montos como texto con dos decimales."""
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def check_pay_range(amount_cop: Decimal, min_cop: Decimal, max_cop: Decimal) -> None:
    if amount_cop < min_cop:
        raise MoneyError(f"El monto mínimo para pagar con Factus Pay es {min_cop:,.0f} COP")
    if amount_cop > max_cop:
        raise MoneyError(f"El monto máximo para pagar con Factus Pay es {max_cop:,.0f} COP")


def split_tax_included(total: Decimal, tax_rate: Decimal) -> tuple[Decimal, Decimal]:
    """Dado un total con impuesto incluido, devuelve (precio_sin_impuesto, ajuste_redondeo).

    Factus calcula total = precio * (1 + tasa/100). El ajuste compensa la diferencia
    de redondeo para que el total facturado coincida con lo cobrado.
    """
    factor = Decimal(1) + tax_rate / Decimal(100)
    price = (total / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    computed = (price * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return price, total - computed
