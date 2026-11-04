from decimal import Decimal

from app import main
from app.models import OrderStatus
from tests.conftest import CUSTOMER

WEBHOOK_URL = "/api/v1/webhooks/factus-pay?key=test-webhook-key"


async def _order(client, key="idem-key-0001", event="fake-001", qty=1, customer=None):
    return await client.post(
        "/api/v1/orders", headers={"Idempotency-Key": key},
        json={"event_id": event, "quantity": qty, "customer": customer or CUSTOMER,
              "data_consent": True},
    )


async def test_search_shows_five_reference_currencies(client):
    r = await client.get("/api/v1/events", params={"city": "Bogotá"})
    ev = r.json()["items"][0]
    assert ev["unit_price_cop"] == "300000"  # 75 USD * 4.000
    assert set(ev["display_prices"]) == {"USD", "EUR", "COP", "GBP", "JPY"}


async def test_quote_rejects_below_minimum(client):
    s = main.state.catalog._s
    old = s.factus_pay_min_cop
    s.factus_pay_min_cop = Decimal("5000000")
    try:
        r = await client.post("/api/v1/quotes", json={"event_id": "fake-003", "quantity": 1})
        assert r.status_code == 422
        assert "mínimo" in r.json()["detail"]
    finally:
        s.factus_pay_min_cop = old


async def test_full_flow_payment_then_invoice(client):
    r = await _order(client)
    assert r.status_code == 201
    o = r.json()
    assert o["status"] == "awaiting_payment"
    assert o["payment"]["qr"]
    # SQLite pierde la zona horaria; la API siempre debe responder en UTC explícito.
    assert o["payment"]["expires_at"].endswith(("Z", "+00:00"))

    await client.post(f"/api/v1/dev/orders/{o['id']}/simulate-payment")
    r = await client.get(f"/api/v1/orders/{o['id']}")  # verifica pago y agenda factura
    assert r.json()["status"] in ("paid", "invoicing", "completed")
    r = await client.get(f"/api/v1/orders/{o['id']}")
    assert r.json()["status"] == "completed"
    assert r.json()["invoice"]["number"].startswith("SETP")

    pdf = await client.get(f"/api/v1/orders/{o['id']}/invoice", params={"format": "pdf"})
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    ticket = await client.get(f"/api/v1/orders/{o['id']}/ticket")
    assert ticket.content.startswith(b"%PDF")

    payload = main.state.container.invoices.payloads[0]
    assert payload["reference_code"] == o["reference_code"]
    assert payload["payment_details"][0]["amount"] == "180000.00"
    assert "NO es un boleto oficial" in payload["observation"]


async def test_idempotency_key_returns_same_order(client):
    a = (await _order(client, key="same-key-123")).json()
    b = (await _order(client, key="same-key-123")).json()
    assert a["id"] == b["id"]
    assert len(main.state.container.pay.collections) == 1


async def test_double_webhook_invoices_once(client):
    o = (await _order(client)).json()
    main.state.container.pay.simulate(o["reference_code"])
    for _ in range(2):
        r = await client.post(WEBHOOK_URL, json={"data": {
            "reference_code": o["reference_code"], "amount": 180000, "status": "paid"}})
        assert r.status_code == 202
    assert len(main.state.container.invoices.payloads) == 1
    assert (await client.get(f"/api/v1/orders/{o['id']}")).json()["status"] == "completed"


async def test_webhook_rejects_bad_key_and_never_trusts_payload(client):
    o = (await _order(client)).json()
    r = await client.post("/api/v1/webhooks/factus-pay?key=nope",
                          json={"data": {"reference_code": o["reference_code"], "status": "paid"}})
    assert r.status_code == 401
    # Webhook válido pero el recaudo NO está pagado en Factus Pay => no se factura.
    await client.post(WEBHOOK_URL,
                      json={"data": {"reference_code": o["reference_code"], "status": "paid"}})
    assert (await client.get(f"/api/v1/orders/{o['id']}")).json()["status"] == "awaiting_payment"


async def test_paid_without_invoice_is_kept_and_reconciled(client):
    main.state.container.invoices.fail_next = 1
    o = (await _order(client)).json()
    main.state.container.pay.simulate(o["reference_code"])
    await main.state.orders.sync_payment(o["id"], force=True)
    order = await main.state.orders.issue_invoice(o["id"])
    assert order.status == OrderStatus.invoice_failed
    assert (await client.get(f"/api/v1/orders/{o['id']}/invoice")).status_code == 409

    await main.state.orders.reconcile()
    order = await main.state.orders.get(o["id"])
    assert order.status == OrderStatus.completed
    assert [t.to_status for t in order.transitions] == [
        "created", "awaiting_payment", "paid", "invoicing", "invoice_failed", "invoicing",
        "completed",
    ]


async def test_failed_payment(client):
    o = (await _order(client)).json()
    await client.post(f"/api/v1/dev/orders/{o['id']}/simulate-payment", params={"ok": "false"})
    assert (await client.get(f"/api/v1/orders/{o['id']}")).json()["status"] == "payment_failed"


async def test_document_validation(client):
    r = await _order(client, key="k-doc-0001", customer={**CUSTOMER, "doc_number": "ABC123"})
    assert r.status_code == 422
    passport = {**CUSTOMER, "doc_type": "41", "doc_number": "AB123456"}
    r = await _order(client, key="k-doc-0002", customer=passport)
    assert r.status_code == 201


async def test_unvalidated_invoice_is_not_completed_nor_duplicated(client):
    inv = main.state.container.invoices
    inv.unvalidated_next = 1
    o = (await _order(client)).json()
    main.state.container.pay.simulate(o["reference_code"])
    await main.state.orders.sync_payment(o["id"], force=True)
    order = await main.state.orders.issue_invoice(o["id"])
    assert order.status == OrderStatus.invoice_failed
    assert order.invoice_number  # se conserva el número para conciliar
    assert (await client.get(f"/api/v1/orders/{o['id']}/invoice")).status_code == 409

    inv.validate_all()
    await main.state.orders.reconcile()
    order = await main.state.orders.get(o["id"])
    assert order.status == OrderStatus.completed
    assert len(inv.payloads) == 1  # nunca se creó una segunda factura


async def test_provider_price_used_when_reasonable(client):
    ev = (await client.get("/api/v1/events/fake-002")).json()  # 75 USD
    assert ev["is_demo_price"] is False
    assert ev["unit_price_cop"] == "300000"


async def test_missing_or_absurd_price_gets_stable_demo_price(client):
    from app.adapters.events import ProviderEvent
    from app.catalogs import DEMO_BASE_PRICES_COP
    from app.services.catalog import demo_base_price

    no_price = (await client.get("/api/v1/events/fake-003")).json()
    assert no_price["is_demo_price"] is True
    assert Decimal(no_price["unit_price_cop"]) in DEMO_BASE_PRICES_COP
    again = (await client.get("/api/v1/events/fake-003")).json()
    assert again["unit_price_cop"] == no_price["unit_price_cop"]  # estable

    catalog = main.state.catalog
    snap = await catalog._rates.latest()
    absurd = ProviderEvent("tm-x", "X", None, None, None, None, None, None,
                           Decimal("1.5"), "USD")  # = 6.000 COP: se descarta
    out = catalog._out(absurd, snap)
    assert out.is_demo_price is True
    assert out.unit_price_cop == demo_base_price("tm-x")
    # Los precios varían entre conciertos.
    assert len({demo_base_price(f"evento-{i}") for i in range(40)}) > 3


async def test_ticket_tiers_prices_and_order(client):
    ev = (await client.get("/api/v1/events/fake-001")).json()  # 180.000 COP
    tiers = {t["code"]: t for t in ev["tiers"]}
    assert [t["label"] for t in ev["tiers"]] == ["General", "Preferencial", "VIP"]
    assert tiers["general"]["unit_price_cop"] == "180000"
    assert tiers["preferencial"]["unit_price_cop"] == "288000"
    assert tiers["vip"]["unit_price_cop"] == "450000"
    q = (await client.post("/api/v1/quotes",
                           json={"event_id": "fake-001", "quantity": 2, "tier": "vip"})).json()
    assert q["total_cop"] == "900000" and q["tier_label"] == "VIP"

    r = await _order(client, key="key-tier-vip-01", qty=2)
    assert r.json()["ticket_tier"] == "General"
    r = await client.post("/api/v1/orders", headers={"Idempotency-Key": "key-tier-vip-02"},
                          json={"event_id": "fake-001", "quantity": 2, "tier": "vip",
                                "customer": CUSTOMER, "data_consent": True})
    o = r.json()
    assert o["ticket_tier"] == "VIP" and o["total_cop"] == "900000.00"
    order = await main.state.orders.get(o["id"])
    item = main.state.orders.build_invoice_payload(order, 389)["items"][0]
    assert "VIP" in item["name"]
    assert item["code_reference"].endswith("-VIP")
