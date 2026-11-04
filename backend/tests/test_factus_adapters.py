from decimal import Decimal

import httpx
import pytest
import respx

from app.adapters.factus_invoice import FactusInvoices, FactusTokenManager, InvoiceError
from app.adapters.factus_pay import FactusPay, PayError
from app.adapters.rates import OpenErApiRates

PAY = "https://pay.test"
API = "https://api.test"


@respx.mock
async def test_pay_create_sends_two_decimal_amount_and_bearer():
    route = respx.post(f"{PAY}/v1/collections").mock(return_value=httpx.Response(201, json={
        "data": {"reference_code": "R1", "amount": "20000.00", "status": "ready",
                 "breb_key": "@k", "qr": "data:image/png;base64,AA",
                 "qr_expires_at": "2026-11-04T17:00:00Z", "collected_at": None}}))
    async with httpx.AsyncClient() as c:
        col = await FactusPay(c, PAY, "tok").create_collection("R1", Decimal("20000"))
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer tok"
    body = req.content.replace(b" ", b"")
    assert b'"amount":"20000.00"' in body
    assert b'"expiration":"900"' in body
    assert col.status == "ready"
    assert not col.already_existed


@respx.mock
async def test_pay_create_200_is_idempotent_and_422_is_error():
    respx.post(f"{PAY}/v1/collections").mock(side_effect=[
        httpx.Response(200, json={"reference_code": "R1", "amount": 20000, "status": "ready"}),
        httpx.Response(422, json={"message": "The amount field must be at least 10000."}),
    ])
    async with httpx.AsyncClient() as c:
        pay = FactusPay(c, PAY, "tok")
        assert (await pay.create_collection("R1", Decimal("20000"))).already_existed
        with pytest.raises(PayError, match="at least 10000"):
            await pay.create_collection("R2", Decimal("1000"))


@respx.mock
async def test_token_manager_password_then_refresh_and_retry_once_on_401():
    token = respx.post(f"{API}/oauth/token").mock(side_effect=[
        httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1",
                                  "expires_in": 3600}),
        httpx.Response(200, json={"access_token": "a2", "refresh_token": "r2",
                                  "expires_in": 3600}),
    ])
    bills = respx.get(f"{API}/v2/bills").mock(side_effect=[
        httpx.Response(401), httpx.Response(200, json={"data": {"data": []}})])
    async with httpx.AsyncClient() as c:
        inv = FactusInvoices(c, API, FactusTokenManager(c, API, "id", "sec", "u", "p"))
        assert await inv.find_by_reference("R1") is None
    assert token.call_count == 2
    assert b"grant_type=password" in token.calls[0].request.content
    assert b"grant_type=refresh_token" in token.calls[1].request.content
    assert bills.calls[1].request.headers["Authorization"] == "Bearer a2"


@respx.mock
async def test_invoice_validation_error_is_not_retryable():
    respx.post(f"{API}/oauth/token").mock(return_value=httpx.Response(
        200, json={"access_token": "a", "expires_in": 3600}))
    respx.post(f"{API}/v2/bills/validate").mock(return_value=httpx.Response(
        422, json={"message": "Error de validación", "data": {"errors": {"customer": "x"}}}))
    async with httpx.AsyncClient() as c:
        inv = FactusInvoices(c, API, FactusTokenManager(c, API, "id", "sec", "u", "p"))
        with pytest.raises(InvoiceError) as e:
            await inv.create({"reference_code": "R1"})
    assert e.value.retryable is False


@respx.mock
async def test_download_pdf_decodes_base64_json():
    respx.post(f"{API}/oauth/token").mock(return_value=httpx.Response(
        200, json={"access_token": "a", "expires_in": 3600}))
    respx.get(f"{API}/v2/bills/SETP1/download-pdf").mock(return_value=httpx.Response(
        200, json={"data": {"file_name": "SETP1", "pdf_base_64_encoded": "JVBERi0="}}))
    async with httpx.AsyncClient() as c:
        inv = FactusInvoices(c, API, FactusTokenManager(c, API, "id", "sec", "u", "p"))
        f = await inv.download("SETP1", "pdf")
    assert f.content == b"%PDF-"
    assert f.filename == "SETP1.pdf"


def test_pay_dates_in_sandbox_format_are_bogota_time():
    from datetime import UTC, datetime

    from app.adapters.factus_pay import _dt

    # Formato observado en el Sandbox real el 2026-11-04.
    assert _dt("04-11-2026 12:34:35 PM") == datetime(2026, 11, 4, 17, 34, 35, tzinfo=UTC)
    assert _dt("04-11-2026 12:05:00 AM") == datetime(2026, 11, 4, 5, 5, 0, tzinfo=UTC)
    assert _dt("2026-11-04T17:00:00Z") == datetime(2026, 11, 4, 17, 0, 0, tzinfo=UTC)
    assert _dt(None) is None


def _inv(c, range_id=None):
    return FactusInvoices(c, API, FactusTokenManager(c, API, "id", "sec", "u", "p"), range_id)


def _ranges(*items):
    return httpx.Response(200, json={"data": list(items)})


R_OK = {"id": 7, "is_active": 1, "is_expired": False, "deleted_at": None,
        "current": 10, "to": 1000}
R_EXPIRED = {**R_OK, "id": 3, "is_expired": True}
R_FULL = {**R_OK, "id": 4, "current": 1000}


@respx.mock
async def test_numbering_range_autoselects_single_valid():
    respx.post(f"{API}/oauth/token").mock(return_value=httpx.Response(
        200, json={"access_token": "a", "expires_in": 3600}))
    route = respx.get(f"{API}/v2/numbering-ranges").mock(
        return_value=_ranges(R_OK, R_EXPIRED, R_FULL))
    async with httpx.AsyncClient() as c:
        assert await _inv(c).numbering_range_id() == 7
    q = route.calls.last.request.url.params
    assert q["filter[document]"] == "21"
    assert q["filter[is_active]"] == "1"


@respx.mock
async def test_numbering_range_rejects_ambiguous_or_invalid_config():
    respx.post(f"{API}/oauth/token").mock(return_value=httpx.Response(
        200, json={"access_token": "a", "expires_in": 3600}))
    respx.get(f"{API}/v2/numbering-ranges").mock(
        return_value=_ranges(R_OK, {**R_OK, "id": 9}))
    async with httpx.AsyncClient() as c:
        with pytest.raises(InvoiceError, match="varios rangos"):
            await _inv(c).numbering_range_id()
        with pytest.raises(InvoiceError, match="no es un rango"):
            await _inv(c, 3).numbering_range_id()
        assert await _inv(c, 9).numbering_range_id() == 9


@respx.mock
async def test_bill_response_flat_data_with_is_validated_false():
    respx.post(f"{API}/oauth/token").mock(return_value=httpx.Response(
        200, json={"access_token": "a", "expires_in": 3600}))
    respx.post(f"{API}/v2/bills/validate").mock(return_value=httpx.Response(201, json={
        "data": {"reference_code": "R1", "number": "SETP1", "cufe": "", "is_validated": False}}))
    async with httpx.AsyncClient() as c:
        issued = await _inv(c).create({"reference_code": "R1"})
    assert issued.number == "SETP1"
    assert issued.validated is False


@respx.mock
async def test_exchangerate_api_conversion_rates_and_error_type():
    url = "https://v6.exchangerate-api.com/v6/KEY/latest/COP"
    respx.get(url).mock(side_effect=[
        httpx.Response(200, json={"result": "error", "error-type": "invalid-key"}),
        httpx.Response(200, json={"result": "success", "base_code": "COP",
                                  "time_last_update_unix": 1762214401,
                                  "time_next_update_unix": 4102444800,
                                  "conversion_rates": {"COP": 1, "USD": 0.000256}}),
    ])
    async with httpx.AsyncClient() as c:
        rates = OpenErApiRates(c, url)
        with pytest.raises(Exception, match="invalid-key"):
            await rates.latest()
        snap = await rates.latest()
    assert str(snap.rates["USD"]) == "0.000256"
