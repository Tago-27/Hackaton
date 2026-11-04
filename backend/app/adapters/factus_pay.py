"""Factus Pay: recaudos QR (Bre-B).

Rutas según la colección oficial `factus-pay`:
    POST {base}/v1/collections                    body {reference_code, amount}
    GET  {base}/v1/collections/{reference_code}
Autenticación: Bearer con token FIJO cargado del entorno. Nunca hacemos login
automático porque un login nuevo revoca el token anterior (ver scripts/rotate_pay_token.py).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

import httpx

from app.money import to_factus_str


@dataclass
class PayCollection:
    reference_code: str
    amount: Decimal
    status: str  # ready | paid | failed (y otros que el proveedor añada)
    qr: str | None = None
    breb_key: str | None = None
    qr_expires_at: datetime | None = None
    collected_at: datetime | None = None
    already_existed: bool = False


class PayProvider(Protocol):
    async def create_collection(
        self, reference_code: str, amount_cop: Decimal
    ) -> PayCollection: ...

    async def get_collection(self, reference_code: str) -> PayCollection | None: ...


class PayError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


BOGOTA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano


def _dt(v: str | None) -> datetime | None:
    """Factus Pay Sandbox responde fechas como '04-11-2026 12:34:35 PM' en hora de Colombia
    (observado 2026-11-04). También se acepta ISO 8601 por si cambia el formato."""
    if not v:
        return None
    try:
        d = datetime.strptime(v.strip(), "%d-%m-%Y %I:%M:%S %p").replace(tzinfo=BOGOTA)
    except ValueError:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=BOGOTA)
    return d.astimezone(UTC)


def _parse(body: dict) -> PayCollection:
    data = body.get("data", body)
    if isinstance(data, dict) and "collection" in data:
        data = data["collection"]
    return PayCollection(
        reference_code=str(data["reference_code"]),
        amount=Decimal(str(data["amount"])),
        status=str(data.get("status", "")).lower(),
        qr=data.get("qr"),
        breb_key=data.get("breb_key"),
        qr_expires_at=_dt(data.get("qr_expires_at")),
        collected_at=_dt(data.get("collected_at")),
    )


def _error_message(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        return f"HTTP {r.status_code}"
    return str(body.get("message") or body.get("errors") or f"HTTP {r.status_code}")


class FactusPay:
    def __init__(
        self, client: httpx.AsyncClient, base_url: str, token: str, expiration_seconds: int = 900
    ) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._expiration = expiration_seconds

    async def create_collection(self, reference_code: str, amount_cop: Decimal) -> PayCollection:
        # La misma referencia recupera el recaudo (200) en lugar de duplicarlo: nunca se
        # regenera reference_code en un reintento ni se cambia el monto bajo la misma referencia.
        payload = {
            "reference_code": reference_code,
            "amount": to_factus_str(amount_cop),
            "expiration": str(self._expiration),
        }
        try:
            r = await self._client.post(
                f"{self._base}/v1/collections", json=payload, headers=self._headers, timeout=15
            )
        except httpx.HTTPError as e:
            raise PayError("No se pudo contactar a Factus Pay") from e
        if r.status_code in (200, 201):
            col = _parse(r.json())
            col.already_existed = r.status_code == 200  # 200 = ya existía (idempotente)
            return col
        if r.status_code == 401:
            raise PayError("Token de Factus Pay inválido o revocado", 401)
        raise PayError(f"Factus Pay rechazó el recaudo: {_error_message(r)}", r.status_code)

    async def get_collection(self, reference_code: str) -> PayCollection | None:
        try:
            r = await self._client.get(
                f"{self._base}/v1/collections/{reference_code}", headers=self._headers, timeout=10
            )
        except httpx.HTTPError as e:
            raise PayError("No se pudo contactar a Factus Pay") from e
        if r.status_code == 404:
            return None
        if r.status_code == 401:
            raise PayError("Token de Factus Pay inválido o revocado", 401)
        if r.status_code != 200:
            raise PayError(f"Factus Pay respondió {_error_message(r)}", r.status_code)
        return _parse(r.json())


# 1x1 PNG transparente: suficiente para que el frontend pinte "un QR" en modo fake.
_FAKE_QR = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@dataclass
class FakeFactusPay:
    """Determinista. El pago se simula con `simulate(reference, ok=True|False)`."""

    collections: dict[str, PayCollection] = field(default_factory=dict)

    async def create_collection(self, reference_code: str, amount_cop: Decimal) -> PayCollection:
        if reference_code in self.collections:
            existing = self.collections[reference_code]
            return PayCollection(**{**existing.__dict__, "already_existed": True})
        col = PayCollection(
            reference_code=reference_code,
            amount=amount_cop.quantize(Decimal("0.01")),
            status="ready",
            qr=_FAKE_QR,
            breb_key="@demo-turismo-musical",
            qr_expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        self.collections[reference_code] = col
        return col

    async def get_collection(self, reference_code: str) -> PayCollection | None:
        col = self.collections.get(reference_code)
        return PayCollection(**col.__dict__) if col else None

    def simulate(self, reference_code: str, ok: bool = True) -> None:
        col = self.collections[reference_code]
        col.status = "paid" if ok else "failed"
        col.collected_at = datetime.now(UTC) if ok else None
