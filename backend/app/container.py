"""Construye los adaptadores reales o fakes según variables de entorno."""

from dataclasses import dataclass

import httpx

from app.adapters.events import EventsProvider, FakeEvents, TicketmasterEvents
from app.adapters.factus_invoice import (
    FactusInvoices,
    FactusTokenManager,
    FakeInvoices,
    InvoiceProvider,
)
from app.adapters.factus_pay import FactusPay, FakeFactusPay, PayProvider
from app.adapters.rates import FakeRates, OpenErApiRates, RatesProvider
from app.config import Settings


class ConfigError(RuntimeError):
    pass


def _need(value, name: str):
    if value is None or value == "":
        raise ConfigError(f"Falta la variable de entorno {name.upper()}")
    return value.get_secret_value() if hasattr(value, "get_secret_value") else value


@dataclass
class Container:
    settings: Settings
    http: httpx.AsyncClient
    events: EventsProvider
    rates: RatesProvider
    pay: PayProvider
    invoices: InvoiceProvider


def build_container(s: Settings, http: httpx.AsyncClient | None = None) -> Container:
    http = http or httpx.AsyncClient(headers={"User-Agent": "turismo-musical-demo/0.1"})

    if s.events_provider == "ticketmaster":
        events: EventsProvider = TicketmasterEvents(
            http, s.ticketmaster_base_url, _need(s.ticketmaster_api_key, "ticketmaster_api_key"),
            s.events_cache_ttl_seconds,
        )
    else:
        events = FakeEvents()

    if s.rates_provider == "exchangerate_api":
        key = _need(s.fx_api_key, "fx_api_key")
        rates: RatesProvider = OpenErApiRates(http, f"{s.fx_base_url.rstrip('/')}/{key}/latest/COP")
    elif s.rates_provider == "open_er_api":
        rates = OpenErApiRates(http, s.rates_base_url)
    else:
        rates = FakeRates()

    if s.pay_provider == "factus":
        pay: PayProvider = FactusPay(
            http, _need(s.factus_pay_base_url, "factus_pay_base_url"),
            _need(s.factus_pay_token, "factus_pay_token"), s.factus_pay_qr_expiration_seconds,
        )
    else:
        pay = FakeFactusPay()

    if s.invoice_provider == "factus":
        base = _need(s.factus_api_base_url, "factus_api_base_url")
        tokens = FactusTokenManager(
            http, base,
            _need(s.factus_client_id, "factus_client_id"),
            _need(s.factus_client_secret, "factus_client_secret"),
            _need(s.factus_username, "factus_username"),
            _need(s.factus_password, "factus_password"),
        )
        invoices: InvoiceProvider = FactusInvoices(http, base, tokens, s.factus_numbering_range_id)
    else:
        invoices = FakeInvoices()

    return Container(s, http, events, rates, pay, invoices)
