import re

from app import main
from tests.conftest import CUSTOMER, USER

ORDER = {"event_id": "fake-001", "quantity": 3, "customer": CUSTOMER, "data_consent": True}


async def _paid_order(client, key="key-tickets-01", qty=3):
    o = (await client.post("/api/v1/orders", headers={"Idempotency-Key": key},
                           json={**ORDER, "quantity": qty})).json()
    main.state.container.pay.simulate(o["reference_code"])
    await client.get(f"/api/v1/orders/{o['id']}")
    return (await client.get(f"/api/v1/orders/{o['id']}")).json()


async def test_api_requires_login(client, anon):
    for method, path in [("GET", "/api/v1/events"), ("GET", "/api/v1/config"),
                         ("POST", "/api/v1/quotes"), ("GET", "/api/v1/orders"),
                         ("GET", "/api/v1/auth/me")]:
        r = await anon.request(method, path, json={})
        assert r.status_code == 401, path
    assert (await anon.get("/health")).status_code == 200


async def test_login_logout_and_bad_password(client, anon):
    r = await anon.post("/api/v1/auth/login", json={**USER, "password": "incorrecta"})
    assert r.status_code == 401
    r = await anon.post("/api/v1/auth/login", json={"email": "otro@x.co", "password": "x" * 8})
    assert r.status_code == 401  # mismo mensaje exista o no el correo
    r = await anon.post("/api/v1/auth/login",
                        json={"email": USER["email"].upper(), "password": USER["password"]})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert (await anon.get("/api/v1/auth/me")).json()["email"] == USER["email"]
    await anon.post("/api/v1/auth/logout")
    assert (await anon.get("/api/v1/auth/me")).status_code == 401


async def test_duplicate_email_rejected(client, anon):
    r = await anon.post("/api/v1/auth/register", json={**USER, "email": "ANA@example.com"})
    assert r.status_code == 409


async def test_orders_are_private_per_user(client, anon):
    o = (await client.post("/api/v1/orders", headers={"Idempotency-Key": "key-private-01"},
                           json=ORDER)).json()
    await anon.post("/api/v1/auth/register",
                    json={"name": "Otro Usuario", "email": "otro@example.com",
                          "password": "otra-clave-1"})
    for path in [f"/api/v1/orders/{o['id']}", f"/api/v1/orders/{o['id']}/ticket"]:
        assert (await anon.get(path)).status_code == 404
    assert (await anon.get("/api/v1/orders")).json() == []
    mine = (await client.get("/api/v1/orders")).json()
    assert [x["id"] for x in mine] == [o["id"]]
    assert mine[0]["payment"]["qr"] is None  # la lista no carga QR pesados


async def test_one_ticket_page_and_code_per_ticket(client):
    o = await _paid_order(client, qty=3)
    assert [t["code"] for t in o["tickets"]] == [
        f"{o['reference_code']}-01", f"{o['reference_code']}-02", f"{o['reference_code']}-03"]
    pdf = (await client.get(f"/api/v1/orders/{o['id']}/ticket")).content
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 3


async def test_manual_retry_ignores_exhausted_automatic_attempts(client):
    inv = main.state.container.invoices
    s = main.state.orders._s
    old = s.invoice_max_attempts
    s.invoice_max_attempts = 1
    try:
        inv.fail_next = 1
        o = await _paid_order(client, key="key-retry-01", qty=1)
        order = await main.state.orders.get(o["id"])
        assert order.status == "invoice_failed"
        await main.state.orders.reconcile()  # automático agotado: no reintenta
        assert (await main.state.orders.get(o["id"])).status == "invoice_failed"
        r = await client.post(f"/api/v1/orders/{o['id']}/retry-invoice")
        assert r.json()["status"] == "completed"
    finally:
        s.invoice_max_attempts = old


async def test_colombian_customer_requires_municipality(client):
    co = {**CUSTOMER, "country": "CO"}
    r = await client.post("/api/v1/orders", headers={"Idempotency-Key": "key-muni-01"},
                          json={**ORDER, "customer": co})
    assert r.status_code == 422
    assert "municipio" in r.text
    r = await client.post("/api/v1/orders", headers={"Idempotency-Key": "key-muni-02"},
                          json={**ORDER, "customer": {**co, "municipality": "11001"}})
    assert r.status_code == 201
    order = await main.state.orders.get(r.json()["id"])
    customer = main.state.orders.build_invoice_payload(order, 389)["customer"]
    assert customer["country_code"] == "CO"
    assert customer["municipality_code"] == "11001"


async def test_legacy_colombian_order_without_municipality_omits_country(client):
    r = await client.post("/api/v1/orders", headers={"Idempotency-Key": "key-muni-03"},
                          json={**ORDER, "customer": {**CUSTOMER, "country": "US",
                                                      "municipality": "11001"}})
    order = await main.state.orders.get(r.json()["id"])
    assert order.customer_municipality is None  # se ignora fuera de Colombia
    customer = main.state.orders.build_invoice_payload(order, 389)["customer"]
    assert customer["country_code"] == "US"
    assert "municipality_code" not in customer
    order.customer_country = "CO"  # como una orden creada antes de pedir municipio
    customer = main.state.orders.build_invoice_payload(order, 389)["customer"]
    assert "country_code" not in customer
    assert "municipality_code" not in customer


async def test_config_lists_municipalities(client):
    munis = (await client.get("/api/v1/config")).json()["municipalities"]
    assert {"code": "11001", "name": "Bogotá D.C."} in munis


async def _failed_order(client, key):
    o = (await client.post("/api/v1/orders", headers={"Idempotency-Key": key},
                           json={**ORDER, "quantity": 1})).json()
    main.state.container.pay.simulate(o["reference_code"], ok=False)
    o = (await client.get(f"/api/v1/orders/{o['id']}")).json()
    assert o["status"] == "payment_failed"
    return o


async def test_retry_payment_updates_same_order(client):
    pay = main.state.container.pay
    o = await _failed_order(client, "key-retrypay-01")
    r = await client.post(f"/api/v1/orders/{o['id']}/retry-payment")
    assert r.status_code == 200
    again = r.json()
    assert again["id"] == o["id"]  # misma orden, no una nueva
    assert again["status"] == "awaiting_payment"
    assert again["error"] is None and again["payment"]["qr"]
    new_ref = f"{o['reference_code']}-R1"
    assert new_ref in pay.collections

    pay.simulate(new_ref)
    await client.get(f"/api/v1/orders/{o['id']}")
    done = (await client.get(f"/api/v1/orders/{o['id']}")).json()
    assert done["status"] == "completed"
    mine = (await client.get("/api/v1/orders")).json()
    assert [x["status"] for x in mine if x["id"] == o["id"]] == ["completed"]
    payload = main.state.container.invoices.payloads[-1]
    assert payload["reference_code"] == o["reference_code"]  # la factura conserva la orden
    assert payload["payment_details"][0]["reference_code"] == new_ref


async def test_retry_payment_detects_late_payment_without_new_qr(client):
    pay = main.state.container.pay
    o = await _failed_order(client, "key-retrypay-02")
    pay.simulate(o["reference_code"], ok=True)  # el cobro original terminó pagado
    r = await client.post(f"/api/v1/orders/{o['id']}/retry-payment")
    assert r.json()["status"] == "paid"
    assert f"{o['reference_code']}-R1" not in pay.collections


async def test_retry_payment_is_noop_while_still_awaiting(client):
    o = (await client.post("/api/v1/orders", headers={"Idempotency-Key": "key-retrypay-03"},
                           json={**ORDER, "quantity": 1})).json()
    await client.post(f"/api/v1/orders/{o['id']}/retry-payment")
    r = await client.post(f"/api/v1/orders/{o['id']}/retry-payment")
    assert r.status_code == 200  # sigue esperando pago: devuelve la orden tal cual
    assert r.json()["payment"]["status"] == "ready"
