import asyncio
import contextlib
import hmac
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import auth
from app.adapters.events import EventsProviderError
from app.adapters.factus_invoice import InvoiceError
from app.adapters.factus_pay import FakeFactusPay
from app.adapters.rates import RatesProviderError
from app.catalogs import DISCLAIMER, DOCUMENT_TYPES, MUNICIPALITIES
from app.config import get_settings
from app.container import Container, build_container
from app.db import SessionLocal, init_db
from app.models import Order, OrderStatus, User
from app.money import MoneyError
from app.schemas import (
    ConfigOut,
    DocumentTypeOut,
    ErrorOut,
    EventOut,
    EventSearchOut,
    InvoiceOut,
    LoginIn,
    MunicipalityOut,
    OrderIn,
    OrderOut,
    PaymentOut,
    QuoteIn,
    QuoteOut,
    RegisterIn,
    TicketOut,
    UserOut,
)
from app.services.catalog import CatalogService, NotFound
from app.services.orders import (
    IdempotencyConflict,
    OrderService,
    as_utc,
    pay_ref,
    tier_label,
)
from app.tickets import ticket_codes, ticket_pdf

log = logging.getLogger("app")


class State:
    container: Container
    catalog: CatalogService
    orders: OrderService


state = State()


async def _reconciler_loop(interval: int) -> None:
    while True:
        try:
            await state.orders.reconcile()
        except Exception:  # noqa: BLE001 - el conciliador nunca debe morir
            log.exception("reconciler error")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    logging.basicConfig(level=s.log_level)
    auth.make_token("startup-check")  # falla al arrancar si falta SESSION_SECRET en producción
    await init_db()
    state.container = build_container(s)
    state.catalog = CatalogService(state.container.events, state.container.rates, s)
    state.orders = OrderService(SessionLocal, state.container.pay, state.container.invoices,
                                state.catalog, s)
    task = asyncio.create_task(_reconciler_loop(s.reconciler_interval_seconds))
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await state.container.http.aclose()


app = FastAPI(title="Turismo Musical API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=True,  # cookie de sesión en desarrollo (5173 -> 8000)
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key"],
    expose_headers=["Content-Disposition"],
)

# ---------------------------------------------------------------- límite de tasa básico
_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(limit: int, window: float = 60.0):
    def dep(request: Request) -> None:
        key = f"{request.url.path}:{request.client.host if request.client else '-'}"
        now = time.monotonic()
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Demasiadas solicitudes; intenta en un momento")
        q.append(now)

    return Depends(dep)


# ---------------------------------------------------------------- sesión
async def current_user(request: Request) -> User:
    uid = auth.session_user_id(request)
    async with SessionLocal() as session:
        user = await session.get(User, uid)
    if user is None:
        raise HTTPException(401, "Inicia sesión para continuar")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def owned_order(order_id: str, user: User) -> Order:
    """La orden debe ser del usuario. Las órdenes previas al login (sin dueño) siguen
    accesibles por su id, que es un UUID aleatorio."""
    order = await state.orders.get(order_id)
    if order is None or (order.user_id is not None and order.user_id != user.id):
        raise HTTPException(404, "Orden no encontrada")
    return order


# ---------------------------------------------------------------- utilidades
def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, name=u.name, email=u.email)


def _order_out(o: Order, *, include_qr: bool = True) -> OrderOut:
    return OrderOut(
        id=o.id, reference_code=o.reference_code, status=o.status, event_id=o.event_id,
        event_name=o.event_name, event_date=o.event_date, event_venue=o.event_venue,
        event_city=o.event_city, quantity=o.quantity, ticket_tier=tier_label(o),
        total_cop=o.total_cop,
        customer_names=o.customer_names,
        payment=PaymentOut(status=o.pay_status, qr=o.pay_qr if include_qr else None,
                           breb_key=o.pay_breb_key, expires_at=as_utc(o.pay_expires_at)),
        invoice=InvoiceOut(number=o.invoice_number, cufe=o.invoice_cufe,
                           public_url=o.invoice_public_url,
                           available=o.status == OrderStatus.completed),
        tickets=[TicketOut(code=c, number=i, of=o.quantity)
                 for i, c in enumerate(ticket_codes(o), start=1)],
        error=o.invoice_error, disclaimer=DISCLAIMER, created_at=as_utc(o.created_at),
    )


def _upstream(e: Exception) -> HTTPException:
    return HTTPException(502, str(e))


ERR = {401: {"model": ErrorOut}, 404: {"model": ErrorOut}, 422: {"model": ErrorOut},
       502: {"model": ErrorOut}}
api = "/api/v1"


# ---------------------------------------------------------------- públicos
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(f"{api}/auth/register", response_model=UserOut, status_code=201, responses=ERR)
async def register(body: RegisterIn, response: Response,
                   _: None = rate_limit(5)) -> UserOut:
    email = body.email.lower()
    user = User(email=email, name=body.name, password_hash=auth.hash_password(body.password))
    async with SessionLocal() as session:
        session.add(user)
        try:
            await session.commit()
        except IntegrityError as e:
            raise HTTPException(409, "Ya existe una cuenta con ese correo") from e
    auth.set_session(response, user.id)
    return _user_out(user)


@app.post(f"{api}/auth/login", response_model=UserOut, responses=ERR)
async def login(body: LoginIn, response: Response, _: None = rate_limit(10)) -> UserOut:
    async with SessionLocal() as session:
        user = await session.scalar(
            select(User).where(func.lower(User.email) == body.email.lower())
        )
    # Mismo trabajo y mismo mensaje exista o no el correo.
    ok = auth.verify_password(body.password, user.password_hash if user else auth.DUMMY_HASH)
    if user is None or not ok:
        raise HTTPException(401, "Correo o contraseña incorrectos")
    auth.set_session(response, user.id)
    return _user_out(user)


@app.post(f"{api}/auth/logout", status_code=204)
async def logout(response: Response) -> Response:
    auth.clear_session(response)
    response.status_code = 204
    return response


@app.get(f"{api}/auth/me", response_model=UserOut, responses=ERR)
async def me(user: CurrentUser) -> UserOut:
    return _user_out(user)


# ---------------------------------------------------------------- requieren sesión
@app.get(f"{api}/config", response_model=ConfigOut, responses=ERR)
async def config(_: CurrentUser) -> ConfigOut:
    s = get_settings()
    return ConfigOut(
        document_types=[DocumentTypeOut(**d.__dict__) for d in DOCUMENT_TYPES.values()],
        municipalities=[MunicipalityOut(code=k, name=v) for k, v in
                        sorted(MUNICIPALITIES.items(), key=lambda kv: kv[1])],
        min_cop=s.factus_pay_min_cop, max_cop=s.factus_pay_max_cop, disclaimer=DISCLAIMER,
        fake_payments=isinstance(state.container.pay, FakeFactusPay),
    )


@app.get(f"{api}/events", response_model=EventSearchOut, responses=ERR)
async def search_events(
    _: CurrentUser,
    artist: Annotated[str | None, Query(max_length=100)] = None,
    city: Annotated[str | None, Query(max_length=100)] = None,
    country: Annotated[str | None, Query(pattern=r"^[A-Za-z]{2}$")] = None,
    __: None = rate_limit(60),
) -> EventSearchOut:
    try:
        return EventSearchOut(items=await state.catalog.search(artist, city, country))
    except (EventsProviderError, RatesProviderError) as e:
        raise _upstream(e) from e


@app.get(f"{api}/events/{{event_id}}", response_model=EventOut, responses=ERR)
async def get_event(event_id: str, _: CurrentUser) -> EventOut:
    try:
        _, out = await state.catalog.event(event_id)
        return out
    except NotFound as e:
        raise HTTPException(404, str(e)) from e
    except (EventsProviderError, RatesProviderError) as e:
        raise _upstream(e) from e


@app.post(f"{api}/quotes", response_model=QuoteOut, responses=ERR)
async def quote(body: QuoteIn, _: CurrentUser) -> QuoteOut:
    try:
        return await state.catalog.quote(body.event_id, body.quantity, body.tier)
    except NotFound as e:
        raise HTTPException(404, str(e)) from e
    except MoneyError as e:
        raise HTTPException(422, str(e)) from e
    except (EventsProviderError, RatesProviderError) as e:
        raise _upstream(e) from e


@app.get(f"{api}/orders", response_model=list[OrderOut], responses=ERR)
async def my_orders(user: CurrentUser) -> list[OrderOut]:
    return [_order_out(o, include_qr=False) for o in await state.orders.list_for_user(user.id)]


@app.post(f"{api}/orders", response_model=OrderOut, status_code=201, responses=ERR)
async def create_order(
    body: OrderIn,
    user: CurrentUser,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)],
    _: None = rate_limit(10),
) -> OrderOut:
    try:
        order = await state.orders.create(body, idempotency_key, user.id)
    except IdempotencyConflict as e:
        raise HTTPException(409, str(e)) from e
    except NotFound as e:
        raise HTTPException(404, str(e)) from e
    except MoneyError as e:
        raise HTTPException(422, str(e)) from e
    except (EventsProviderError, RatesProviderError) as e:
        raise _upstream(e) from e
    return _order_out(order)


@app.get(f"{api}/orders/{{order_id}}", response_model=OrderOut, responses=ERR)
async def get_order(order_id: str, user: CurrentUser, background: BackgroundTasks) -> OrderOut:
    await owned_order(order_id, user)
    order = await state.orders.sync_payment(order_id)
    assert order is not None
    if order.status == OrderStatus.paid:
        background.add_task(state.orders.issue_invoice, order.id)
    return _order_out(order)


@app.post(f"{api}/orders/{{order_id}}/retry-payment", response_model=OrderOut,
          responses={**ERR, 409: {"model": ErrorOut}})
async def retry_payment(order_id: str, user: CurrentUser,
                        _: None = rate_limit(5)) -> OrderOut:
    """Reintenta el pago de una orden fallida o vencida, sin crear otra orden."""
    await owned_order(order_id, user)
    order, error = await state.orders.retry_payment(order_id)
    assert order is not None
    if error:
        raise HTTPException(502, error)
    if order.status not in (OrderStatus.awaiting_payment, OrderStatus.paid):
        raise HTTPException(409, "Esta orden no tiene un pago pendiente de reintentar")
    return _order_out(order)


@app.post(f"{api}/orders/{{order_id}}/retry-invoice", response_model=OrderOut, responses=ERR)
async def retry_invoice(order_id: str, user: CurrentUser,
                        _: None = rate_limit(5)) -> OrderOut:
    await owned_order(order_id, user)
    order = await state.orders.issue_invoice(order_id, manual=True)
    assert order is not None
    return _order_out(order)


@app.get(f"{api}/orders/{{order_id}}/invoice", responses={**ERR, 409: {"model": ErrorOut}})
async def download_invoice(
    order_id: str, user: CurrentUser,
    format: Annotated[Literal["pdf", "xml"], Query()] = "pdf",
) -> Response:
    order = await owned_order(order_id, user)
    if order.status != OrderStatus.completed or not order.invoice_number:
        raise HTTPException(409, "La factura aún no está disponible; reintenta en unos segundos")
    try:
        f = await state.container.invoices.download(order.invoice_number, format)
    except InvoiceError as e:
        raise _upstream(e) from e
    if f is None:
        raise HTTPException(409, "Factus aún no tiene el archivo; intenta de nuevo")
    return Response(f.content, media_type=f.media_type,
                    headers={"Content-Disposition": f'attachment; filename="{f.filename}"'})


@app.get(f"{api}/orders/{{order_id}}/ticket", responses=ERR)
async def download_ticket(order_id: str, user: CurrentUser) -> Response:
    order = await owned_order(order_id, user)
    if order.status not in (OrderStatus.completed, OrderStatus.invoicing,
                            OrderStatus.invoice_failed, OrderStatus.paid):
        raise HTTPException(409, "Los boletos se generan cuando el pago está confirmado")
    return Response(ticket_pdf(order), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="boletos-{order.reference_code}.pdf"'})


# ---------------------------------------------------------------- webhook (llave propia)
@app.post(f"{api}/webhooks/factus-pay", status_code=202)
async def factus_pay_webhook(
    request: Request,
    background: BackgroundTasks,
    key: Annotated[str | None, Query(max_length=200)] = None,
    x_webhook_key: Annotated[str | None, Header(alias="X-Webhook-Key")] = None,
) -> dict[str, str]:
    # Factus Pay agrega la llave como ?key=… a la URL registrada (sin ?key) en su panel.
    expected = get_settings().factus_pay_webhook_key
    received = key or x_webhook_key or ""
    if expected is None or not hmac.compare_digest(
        received.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(401, "No autorizado")
    try:
        body = await request.json()
    except ValueError as e:
        raise HTTPException(400, "JSON inválido") from e
    data = body.get("data", body) if isinstance(body, dict) else {}
    ref = str(data.get("reference_code", ""))[:40]
    if ref:
        background.add_task(_sync_by_reference, ref)
    return {"status": "accepted"}


async def _sync_by_reference(reference_code: str) -> None:
    async with SessionLocal() as session:
        oid = await session.scalar(select(Order.id).where(
            (Order.reference_code == reference_code) | (Order.pay_reference == reference_code)))
    if oid:
        # El webhook no es prueba: se vuelve a consultar Factus Pay antes de facturar.
        await state.orders.sync_payment(oid, force=True)
        await state.orders.issue_invoice(oid)


@app.post(f"{api}/dev/orders/{{order_id}}/simulate-payment", include_in_schema=False)
async def simulate_payment(order_id: str, user: CurrentUser, ok: bool = True) -> dict[str, str]:
    pay = state.container.pay
    if not isinstance(pay, FakeFactusPay) or get_settings().app_env == "production":
        raise HTTPException(404, "No disponible")
    order = await owned_order(order_id, user)
    if pay_ref(order) not in pay.collections:
        raise HTTPException(404, "Orden no encontrada")
    pay.simulate(pay_ref(order), ok=ok)
    return {"status": "simulated"}


# ---------------------------------------------------------------- frontend (build de Vite)
# Va al final: las rutas de la API, /docs y /health se registran antes y tienen prioridad.
_static = Path(get_settings().static_dir).resolve()
if (_static / "index.html").is_file():

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "No encontrado")
        candidate = (_static / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_static):
            # Los assets de Vite llevan hash en el nombre: se pueden cachear para siempre.
            cache = "public, max-age=31536000, immutable" if full_path.startswith("assets/") \
                else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        # Rutas de React Router (/eventos/..., /ordenes/...) devuelven la app.
        return FileResponse(_static / "index.html", headers={"Cache-Control": "no-cache"})
