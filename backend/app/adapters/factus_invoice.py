"""Factus API v2: facturación electrónica DIAN.

Rutas según la colección oficial `API Factus V2`:
    POST {base}/oauth/token                         (form-data, grant_type=password|refresh_token)
    POST {base}/v2/bills/validate                   crear y validar factura
    GET  {base}/v2/bills?filter[reference_code]=X   consultar por referencia (antes de reintentar)
    GET  {base}/v2/bills/{number}
    GET  {base}/v2/bills/{number}/download-pdf | download-xml
    GET  {base}/v2/numbering-ranges?filter[document]=21&filter[is_active]=1

Contrato confirmado con la colección del equipo (API_Wars_Fase1): la respuesta de
/v2/bills/validate trae `data.number`, `data.cufe`, `data.reference_code` y `data.is_validated`.
Una factura con is_validated=false NO se da por emitida: queda pendiente y se concilia.
"""

import asyncio
import base64
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass
class IssuedInvoice:
    number: str
    cufe: str | None = None
    public_url: str | None = None
    validated: bool = True


@dataclass
class InvoiceFile:
    content: bytes
    media_type: str
    filename: str


class InvoiceProvider(Protocol):
    async def numbering_range_id(self) -> int: ...

    async def create(self, payload: dict) -> IssuedInvoice: ...

    async def find_by_reference(self, reference_code: str) -> IssuedInvoice | None: ...

    async def download(self, number: str, fmt: str) -> InvoiceFile | None: ...


class InvoiceError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class FactusTokenManager:
    """OAuth2 solo en servidor. Renueva antes de vencer usando expires_in real, con candado."""

    MARGIN_SECONDS = 60

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
    ) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/oauth/token"
        self._creds = (client_id, client_secret, username, password)
        self._access: str | None = None
        self._refresh: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        if self._access and time.monotonic() < self._expires_at - self.MARGIN_SECONDS:
            return self._access
        async with self._lock:
            if self._access and time.monotonic() < self._expires_at - self.MARGIN_SECONDS:
                return self._access
            if self._refresh and await self._request("refresh_token"):
                return self._access  # type: ignore[return-value]
            if await self._request("password"):
                return self._access  # type: ignore[return-value]
            raise InvoiceError("No se pudo autenticar con Factus API", retryable=True)

    def invalidate(self) -> None:
        self._expires_at = 0.0

    async def _request(self, grant: str) -> bool:
        cid, secret, user, pwd = self._creds
        data = {"grant_type": grant, "client_id": cid, "client_secret": secret}
        if grant == "password":
            data |= {"username": user, "password": pwd}
        else:
            data["refresh_token"] = self._refresh or ""
        try:
            r = await self._client.post(
                self._url, data=data, headers={"Accept": "application/json"}, timeout=15
            )
        except httpx.HTTPError:
            return False
        if r.status_code != 200:
            if grant == "refresh_token":
                self._refresh = None
            return False
        body = r.json()
        self._access = body["access_token"]
        self._refresh = body.get("refresh_token")
        self._expires_at = time.monotonic() + float(body.get("expires_in", 0))
        return True


def _bill(b: dict) -> IssuedInvoice:
    validated = b.get("is_validated", True)
    return IssuedInvoice(
        number=str(b["number"]),
        cufe=b.get("cufe") or None,
        public_url=b.get("public_url") or b.get("qr"),
        validated=validated is True or validated in (1, "1", "true"),
    )


def _parse_bill(body: dict) -> IssuedInvoice:
    data = body.get("data", body)
    bill = data.get("bill", data) if isinstance(data, dict) else {}
    return _bill(bill)


def _errors(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        return f"HTTP {r.status_code}"
    msg = body.get("message") or ""
    errs = body.get("data", {}).get("errors") if isinstance(body.get("data"), dict) else None
    errs = errs or body.get("errors")
    return f"{msg} {errs}" if errs else (msg or f"HTTP {r.status_code}")


class FactusInvoices:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        tokens: FactusTokenManager,
        numbering_range_id: int | None = None,
    ):
        self._client = client
        self._base = base_url.rstrip("/")
        self._tokens = tokens
        self._configured_range = numbering_range_id
        self._range: int | None = None

    async def numbering_range_id(self) -> int:
        """Rango de factura de venta (document=21) activo, vigente y con consecutivos.

        Usa FACTUS_NUMBERING_RANGE_ID si es válido; si no, el único rango válido. Nunca adivina
        entre varios ni usa IDs copiados de ejemplos.
        """
        if self._range is not None:
            return self._range
        r = await self._send("GET", "/v2/numbering-ranges",
                             params={"filter[document]": "21", "filter[is_active]": "1"},
                             timeout=20)
        if r.status_code != 200:
            raise InvoiceError(f"No se pudieron consultar rangos: {_errors(r)}", retryable=True)
        data = r.json().get("data", [])
        items = data.get("data", []) if isinstance(data, dict) else data
        valid = [
            x for x in items or []
            if x.get("is_active") and not x.get("is_expired") and not x.get("deleted_at")
            and int(x.get("current") or 0) < int(x.get("to") or 0)
        ]
        ids = [int(x["id"]) for x in valid]
        if self._configured_range is not None:
            if self._configured_range not in ids:
                raise InvoiceError(
                    f"FACTUS_NUMBERING_RANGE_ID={self._configured_range} no es un rango válido. "
                    f"Válidos: {ids}", retryable=False)
            self._range = self._configured_range
        elif len(ids) == 1:
            self._range = ids[0]
        else:
            raise InvoiceError(
                "Hay varios rangos válidos; define FACTUS_NUMBERING_RANGE_ID" if ids
                else "No hay un rango de facturación activo y utilizable", retryable=False)
        return self._range

    async def _send(self, method: str, path: str, **kw) -> httpx.Response:
        """Reintenta exactamente una vez ante 401 con un token nuevo."""
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {await self._tokens.token()}",
                       "Accept": "application/json"}
            r = await self._client.request(method, f"{self._base}{path}", headers=headers, **kw)
            if r.status_code != 401 or attempt == 1:
                return r
            self._tokens.invalidate()
        raise AssertionError("unreachable")

    async def create(self, payload: dict) -> IssuedInvoice:
        try:
            r = await self._send("POST", "/v2/bills/validate", json=payload, timeout=60)
        except httpx.TimeoutException as e:
            raise InvoiceError("Timeout al emitir factura", retryable=True) from e
        except httpx.HTTPError as e:
            raise InvoiceError("No se pudo contactar a Factus API", retryable=True) from e
        if r.status_code in (200, 201):
            return _parse_bill(r.json())
        retryable = r.status_code >= 500 or r.status_code in (401, 409, 429)
        raise InvoiceError(f"Factus rechazó la factura: {_errors(r)}", retryable=retryable,
                           status_code=r.status_code)

    async def find_by_reference(self, reference_code: str) -> IssuedInvoice | None:
        try:
            r = await self._send("GET", "/v2/bills",
                                 params={"filter[reference_code]": reference_code}, timeout=20)
        except httpx.HTTPError as e:
            raise InvoiceError("No se pudo consultar Factus API", retryable=True) from e
        if r.status_code != 200:
            raise InvoiceError(f"Consulta de factura falló: {_errors(r)}", retryable=True)
        data = r.json().get("data", {})
        items = data.get("data", data) if isinstance(data, dict) else data
        for bill in items or []:
            if str(bill.get("reference_code")) == reference_code and bill.get("number"):
                return _bill(bill)
        return None

    async def download(self, number: str, fmt: str) -> InvoiceFile | None:
        r = await self._send("GET", f"/v2/bills/{number}/download-{fmt}", timeout=30)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise InvoiceError(f"Descarga falló: {_errors(r)}", retryable=True)
        media = "application/pdf" if fmt == "pdf" else "application/xml"
        ctype = r.headers.get("content-type", "")
        if "json" not in ctype:
            return InvoiceFile(r.content, media, f"factura-{number}.{fmt}")
        # Factus suele devolver el archivo en base64 dentro de JSON.
        data = r.json().get("data", {})
        b64 = data.get(f"{fmt}_base_64_encoded") or data.get("file") or data.get("content")
        if not b64:
            return None
        name = data.get("file_name") or f"factura-{number}"
        if not name.endswith(f".{fmt}"):
            name += f".{fmt}"
        return InvoiceFile(base64.b64decode(b64), media, name)


@dataclass
class FakeInvoices:
    issued: dict[str, IssuedInvoice] = field(default_factory=dict)
    payloads: list[dict] = field(default_factory=list)
    fail_next: int = 0
    unvalidated_next: int = 0

    async def numbering_range_id(self) -> int:
        return 8

    async def create(self, payload: dict) -> IssuedInvoice:
        self.payloads.append(payload)
        if self.fail_next:
            self.fail_next -= 1
            raise InvoiceError("Fallo simulado", retryable=True)
        ref = payload["reference_code"]
        if ref in self.issued:
            raise InvoiceError("reference_code duplicado", retryable=False, status_code=409)
        validated = not self.unvalidated_next
        if self.unvalidated_next:
            self.unvalidated_next -= 1
        inv = IssuedInvoice(number=f"SETP{990000000 + len(self.issued) + 1}",
                            cufe=f"cufe-demo-{ref}" if validated else None, validated=validated)
        self.issued[ref] = inv
        return inv

    def validate_all(self) -> None:
        for ref, inv in self.issued.items():
            self.issued[ref] = IssuedInvoice(inv.number, f"cufe-demo-{ref}", inv.public_url, True)

    async def find_by_reference(self, reference_code: str) -> IssuedInvoice | None:
        return self.issued.get(reference_code)

    async def download(self, number: str, fmt: str) -> InvoiceFile | None:
        if not any(i.number == number for i in self.issued.values()):
            return None
        if fmt == "pdf":
            from app.tickets import simple_pdf

            body = simple_pdf([f"Factura de demostracion {number}", "Documento fake sin validez."])
            return InvoiceFile(body, "application/pdf", f"factura-{number}.pdf")
        xml = f'<?xml version="1.0"?><Invoice><ID>{number}</ID><Demo>true</Demo></Invoice>'
        return InvoiceFile(xml.encode(), "application/xml", f"factura-{number}.xml")
