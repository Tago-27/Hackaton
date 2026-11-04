"""Tasas de cambio con base COP: rates[X] = unidades de X por 1 COP."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

import httpx


@dataclass(frozen=True)
class RatesSnapshot:
    rates: dict[str, Decimal]
    updated_at: datetime
    next_update_at: datetime


class RatesProvider(Protocol):
    async def latest(self) -> RatesSnapshot: ...


class RatesProviderError(RuntimeError):
    pass


class OpenErApiRates:
    """ExchangeRate-API, base COP. Se cachea hasta time_next_update_unix (1 consulta/día).

    - Con clave (colección del equipo): {fx_base}/{api_key}/latest/COP -> `conversion_rates`
    - Endpoint abierto sin clave: https://open.er-api.com/v6/latest/COP -> `rates`
    Siempre se revisa `result` aunque el HTTP sea 200.
    """

    def __init__(self, client: httpx.AsyncClient, url: str) -> None:
        self._client = client
        self._url = url
        self._snap: RatesSnapshot | None = None
        self._lock = asyncio.Lock()

    async def latest(self) -> RatesSnapshot:
        now = datetime.now(UTC)
        if self._snap and self._snap.next_update_at > now:
            return self._snap
        async with self._lock:
            if self._snap and self._snap.next_update_at > now:
                return self._snap
            try:
                r = await self._client.get(self._url, timeout=10)
                body = r.json()
            except (httpx.HTTPError, ValueError) as e:
                if self._snap:  # mejor una tasa vieja que ninguna
                    return self._snap
                raise RatesProviderError("No se pudieron obtener las tasas") from e
            if r.status_code != 200 or body.get("result") != "success":
                if self._snap:
                    return self._snap
                raise RatesProviderError(
                    f"El proveedor de tasas respondió con error: {body.get('error-type', '')}"
                )
            if body.get("base_code") != "COP":
                raise RatesProviderError("Las tasas deben tener base COP")
            raw = body.get("conversion_rates") or body.get("rates") or {}
            rates = {k: Decimal(str(v)) for k, v in raw.items()}
            updated = datetime.fromtimestamp(body["time_last_update_unix"], UTC)
            nxt = datetime.fromtimestamp(body["time_next_update_unix"], UTC)
            if nxt <= now:
                nxt = now + timedelta(minutes=30)
            self._snap = RatesSnapshot(rates, updated, nxt)
            return self._snap


class FakeRates:
    RATES = {
        "COP": Decimal("1"),
        "USD": Decimal("0.00025"),  # 1 USD = 4.000 COP
        "EUR": Decimal("0.00023"),
        "GBP": Decimal("0.0002"),  # 1 GBP = 5.000 COP
        "JPY": Decimal("0.0375"),
    }

    async def latest(self) -> RatesSnapshot:
        t = datetime(2026, 11, 4, 0, 0, tzinfo=UTC)
        return RatesSnapshot(dict(self.RATES), t, t + timedelta(days=1))
