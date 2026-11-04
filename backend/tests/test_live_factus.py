"""Pruebas contra el Sandbox REAL de Factus. Solo corren con RUN_LIVE_TESTS=1.

    RUN_LIVE_TESTS=1 pytest tests/test_live_factus.py -v -s

Leen credenciales de backend/.env. No imprimen tokens, QR ni datos personales.
"""

import json
import os
import uuid
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.adapters.factus_invoice import FactusInvoices, FactusTokenManager
from app.adapters.factus_pay import FactusPay
from app.config import Settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1", reason="Define RUN_LIVE_TESTS=1 para usar Sandbox"
)


@pytest.fixture
def live_settings() -> Settings:
    # conftest solo fija proveedores/BD; las URLs y credenciales de Factus salen de backend/.env.
    s = Settings(_env_file=".env")
    if not s.factus_pay_base_url or not s.factus_api_base_url:
        pytest.skip("Faltan FACTUS_PAY_BASE_URL / FACTUS_API_BASE_URL en .env")
    return s


async def test_factus_v2_login_and_numbering_ranges(live_settings):
    s = live_settings
    async with httpx.AsyncClient() as c:
        tokens = FactusTokenManager(
            c, s.factus_api_base_url, s.factus_client_id.get_secret_value(),
            s.factus_client_secret.get_secret_value(), s.factus_username.get_secret_value(),
            s.factus_password.get_secret_value(),
        )
        tok = await tokens.token()
        assert tok
        r = await c.get(f"{s.factus_api_base_url.rstrip('/')}/v2/numbering-ranges",
                        params={"filter[document]": "21", "filter[is_active]": "1"},
                        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})
        assert r.status_code == 200, r.text[:300]
        body = r.json().get("data", {})
        items = body.get("data", body) if isinstance(body, dict) else body
        print("\nRangos de factura activos (id, prefijo, actual/hasta, vencido):")
        for it in items or []:
            print(" ", it.get("id"), it.get("prefix"), f"{it.get('current')}/{it.get('to')}",
                  it.get("is_expired"))
        # conftest fija un rango ficticio para las pruebas fake; aquí se usa la autoselección.
        inv = FactusInvoices(c, s.factus_api_base_url, tokens, None)
        print("Rango que usará el backend:", await inv.numbering_range_id())


async def test_factus_v2_lookup_unknown_reference(live_settings):
    s = live_settings
    async with httpx.AsyncClient() as c:
        tokens = FactusTokenManager(
            c, s.factus_api_base_url, s.factus_client_id.get_secret_value(),
            s.factus_client_secret.get_secret_value(), s.factus_username.get_secret_value(),
            s.factus_password.get_secret_value(),
        )
        inv = FactusInvoices(c, s.factus_api_base_url, tokens)
        assert await inv.find_by_reference(f"NOEXISTE-{uuid.uuid4().hex[:8]}") is None


async def test_factus_pay_create_and_get_collection(live_settings):
    s = live_settings
    ref = f"TEST{uuid.uuid4().hex[:12].upper()}"
    async with httpx.AsyncClient() as c:
        pay = FactusPay(c, s.factus_pay_base_url, s.factus_pay_token.get_secret_value())
        col = await pay.create_collection(ref, Decimal("20000"))
        assert col.reference_code == ref
        assert col.amount == Decimal("20000")
        assert col.status == "ready"
        assert col.qr and col.qr.startswith("data:image")
        again = await pay.get_collection(ref)
        assert again is not None
        assert again.status in ("ready", "paid")

        # Muestra sanitizada para docs/samples (sin QR, llave Bre-B ni identificadores reales).
        r = await c.get(f"{s.factus_pay_base_url.rstrip('/')}/v1/collections/{ref}",
                        headers={"Authorization": f"Bearer {s.factus_pay_token.get_secret_value()}",
                                 "Accept": "application/json"})
        body = r.json()
        data = body.get("data", body)
        for k in ("qr", "breb_key"):
            if data.get(k):
                data[k] = "[REDACTADO]"
        data["reference_code"] = "[REFERENCIA]"
        out = Path(__file__).resolve().parents[2] / "docs" / "samples"
        out.mkdir(parents=True, exist_ok=True)
        (out / "factus_pay_get_collection.sanitized.json").write_text(
            json.dumps({"http_status": r.status_code, "body": body}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\nRecaudo {ref} creado; simula el pago en el portal Sandbox para probar 'paid'.")
