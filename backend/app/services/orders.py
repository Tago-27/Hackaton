"""Máquina de estados de la orden: pago Factus Pay → factura Factus v2.

Reglas clave (ver docs/ARCHITECTURE.md):
- Un webhook nunca basta: siempre se consulta el recaudo y se verifican estado, referencia y monto.
- Solo se factura desde `paid` (o reintento desde `invoice_failed`) con compare-and-set en BD.
- Antes de crear la factura se consulta si ya existe por reference_code
  (evita duplicados tras un timeout).
- Un pago confirmado sin factura queda en `invoice_failed` y el conciliador lo reintenta.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.factus_invoice import InvoiceError, InvoiceProvider, IssuedInvoice
from app.adapters.factus_pay import PayError, PayProvider
from app.catalogs import DISCLAIMER, TICKET_TIERS
from app.config import Settings
from app.models import Order, OrderStatus, OrderTransition, utcnow
from app.money import split_tax_included, to_factus_str
from app.schemas import OrderIn
from app.services.catalog import CatalogService

log = logging.getLogger("orders")


class IdempotencyConflict(ValueError):
    pass
S = OrderStatus


def as_utc(dt: datetime | None) -> datetime | None:
    # SQLite devuelve datetimes sin zona; todo lo guardamos en UTC.
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def tier_label(order: Order) -> str:
    return TICKET_TIERS.get(order.ticket_tier or "general", ("General", 1))[0]


def pay_ref(order: Order) -> str:
    """Referencia del recaudo vigente en Factus Pay."""
    return order.pay_reference or order.reference_code


def new_reference() -> str:
    return f"TM{datetime.now(UTC):%y%m%d}{secrets.token_hex(4).upper()}"


class OrderService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        pay: PayProvider,
        invoices: InvoiceProvider,
        catalog: CatalogService,
        settings: Settings,
    ) -> None:
        self._sessions = sessions
        self._pay = pay
        self._invoices = invoices
        self._catalog = catalog
        self._s = settings

    # ------------------------------------------------------------------ helpers
    async def get(self, order_id: str) -> Order | None:
        async with self._sessions() as session:
            return await session.get(Order, order_id)

    async def _transition(
        self, session: AsyncSession, order: Order, to: S, note: str | None = None, **values
    ) -> bool:
        """Compare-and-set: solo cambia si la orden sigue en el estado observado."""
        res = await session.execute(
            update(Order)
            .where(Order.id == order.id, Order.status == order.status)
            .values(status=to, updated_at=utcnow(), **values)
        )
        if res.rowcount != 1:
            await session.rollback()
            return False
        session.add(OrderTransition(order_id=order.id, from_status=order.status, to_status=to,
                                    note=note))
        await session.commit()
        return True

    # ------------------------------------------------------------------ crear
    async def list_for_user(self, user_id: str) -> list[Order]:
        async with self._sessions() as session:
            return list((await session.scalars(
                select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
            )).all())

    async def create(self, data: OrderIn, idempotency_key: str, user_id: str) -> Order:
        async with self._sessions() as session:
            existing = await session.scalar(
                select(Order).where(Order.idempotency_key == idempotency_key)
            )
            if existing:
                if existing.user_id != user_id:
                    raise IdempotencyConflict("Idempotency-Key ya usada")
                return existing

        quote = await self._catalog.quote(data.event_id, data.quantity, data.tier)  # valida rango
        _, ev = await self._catalog.event(data.event_id)
        c = data.customer
        order = Order(
            id=str(uuid.uuid4()),
            user_id=user_id,
            reference_code=new_reference(),
            idempotency_key=idempotency_key,
            status=S.created,
            event_id=ev.id, event_name=ev.name, event_date=ev.date, event_venue=ev.venue,
            event_city=ev.city, quantity=data.quantity, ticket_tier=quote.tier,
            unit_price_cop=quote.unit_price_cop, total_cop=quote.total_cop,
            customer_doc_type=c.doc_type, customer_doc_number=c.doc_number,
            customer_names=c.names, customer_email=c.email, customer_address=c.address,
            customer_country=c.country, customer_municipality=c.municipality,
            data_consent_at=utcnow(),
        )
        async with self._sessions() as session:
            session.add(order)
            session.add(OrderTransition(order_id=order.id, from_status=None,
                                        to_status=S.created))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                again = await session.scalar(
                    select(Order).where(Order.idempotency_key == idempotency_key)
                )
                if again:
                    return again
                raise

        await self._create_collection(order)
        return await self.get(order.id)  # type: ignore[return-value]

    async def _create_collection(self, order: Order) -> None:
        async with self._sessions() as session:
            order = await session.get(Order, order.id)  # type: ignore[assignment]
            try:
                col = await self._pay.create_collection(pay_ref(order), order.total_cop)
            except PayError as e:
                log.warning("pay.create failed order=%s status=%s", order.id, e.status_code)
                await self._transition(session, order, S.payment_failed, str(e),
                                       invoice_error=f"No se pudo crear el cobro: {e}")
                return
            if col.reference_code != pay_ref(order) or col.amount != order.total_cop:
                await self._transition(session, order, S.payment_failed,
                                       "Recaudo con referencia o monto distintos",
                                       invoice_error="El cobro creado no coincide con la orden")
                return
            await self._transition(
                session, order, S.awaiting_payment, "Recaudo creado",
                pay_qr=col.qr, pay_breb_key=col.breb_key, pay_expires_at=col.qr_expires_at,
                pay_status=col.status,
            )

    # ------------------------------------------------------------------ pago
    async def sync_payment(self, order_id: str, *, force: bool = False) -> Order | None:
        async with self._sessions() as session:
            order = await session.get(Order, order_id)
            if order is None or order.status != S.awaiting_payment:
                return order
            now = utcnow()
            last = as_utc(order.pay_last_checked_at)
            interval = timedelta(seconds=self._s.factus_pay_poll_min_interval_seconds)
            if not force and last and now - last < interval:
                return order
            try:
                col = await self._pay.get_collection(pay_ref(order))
            except PayError as e:
                log.warning("pay.get failed order=%s status=%s", order.id, e.status_code)
                return order
            order.pay_last_checked_at = now
            if col is not None:
                order.pay_status = col.status
            await session.commit()

            if col is not None and col.status == "paid":
                if col.reference_code != pay_ref(order) or col.amount != order.total_cop:
                    await self._transition(session, order, S.payment_failed,
                                           "Pago con monto o referencia distintos",
                                           invoice_error="El pago recibido no coincide")
                else:
                    await self._transition(session, order, S.paid, "Pago verificado en Factus Pay",
                                           pay_collected_at=col.collected_at or now)
            elif col is not None and col.status == "failed":
                await self._transition(session, order, S.payment_failed, "Factus Pay: failed",
                                       invoice_error="El pago fue rechazado")
            elif (exp := as_utc(order.pay_expires_at)) and exp < now:
                await self._transition(session, order, S.payment_expired, "QR vencido")
        return await self.get(order_id)

    async def retry_payment(self, order_id: str) -> tuple[Order | None, str | None]:
        """Reintenta el pago de la MISMA orden si quedó fallida o vencida.

        1. Si el recaudo actual sí terminó pagado (pago tardío o reintento en el simulador),
           la orden pasa a `paid`.
        2. Si no, se crea un recaudo nuevo (REF-Rn) y la orden vuelve a `awaiting_payment`.
        Devuelve (orden, mensaje_de_error).
        """
        async with self._sessions() as session:
            order = await session.get(Order, order_id)
            if order is None or order.status not in (S.payment_failed, S.payment_expired):
                return order, None
            now = utcnow()
            try:
                current = await self._pay.get_collection(pay_ref(order))
            except PayError as e:
                return order, f"No se pudo consultar Factus Pay: {e}"
            if (current is not None and current.status == "paid"
                    and current.reference_code == pay_ref(order)
                    and current.amount == order.total_cop):
                await self._transition(session, order, S.paid,
                                       "Pago confirmado al reintentar (recaudo anterior)",
                                       pay_status="paid", invoice_error=None,
                                       pay_collected_at=current.collected_at or now)
                return await self.get(order_id), None

            attempt = (order.pay_attempt or 0) + 1
            new_ref = f"{order.reference_code}-R{attempt}"
            try:
                col = await self._pay.create_collection(new_ref, order.total_cop)
            except PayError as e:
                log.warning("pay.retry failed order=%s status=%s", order.id, e.status_code)
                return order, f"No se pudo crear el nuevo cobro: {e}"
            if col.reference_code != new_ref or col.amount != order.total_cop:
                return order, "El cobro creado no coincide con la orden"
            ok = await self._transition(
                session, order, S.awaiting_payment, f"Nuevo intento de pago ({new_ref})",
                pay_reference=new_ref, pay_attempt=attempt, pay_qr=col.qr,
                pay_breb_key=col.breb_key, pay_expires_at=col.qr_expires_at,
                pay_status=col.status, pay_last_checked_at=None, invoice_error=None,
            )
            if not ok:  # otro clic ganó la carrera; la misma referencia es idempotente
                return await self.get(order_id), None
        return await self.get(order_id), None

    # ------------------------------------------------------------------ factura
    def build_invoice_payload(self, order: Order, numbering_range_id: int) -> dict:
        s = self._s
        total = Decimal(order.total_cop)
        unit_total = Decimal(order.unit_price_cop)
        price, _ = split_tax_included(unit_total, s.invoice_tax_rate)
        factor = Decimal(1) + s.invoice_tax_rate / Decimal(100)
        computed = (price * order.quantity * factor).quantize(Decimal("0.01"))
        tier = tier_label(order)
        customer: dict = {
            "identification_document_code": order.customer_doc_type,
            "identification": order.customer_doc_number,
            "names": order.customer_names,
            "email": order.customer_email,
            "legal_organization_code": s.invoice_customer_legal_organization_code,
            "tribute_code": s.invoice_customer_tribute_code,
            "responsibilities": s.invoice_customer_responsibilities,
        }
        if order.customer_address:
            customer["address"] = order.customer_address
        if order.customer_country == "CO":
            # Con country_code=CO Factus exige municipality_code. Órdenes antiguas sin
            # municipio se envían sin país (Factus lo acepta; verificado en Sandbox).
            if order.customer_municipality:
                customer["country_code"] = "CO"
                customer["municipality_code"] = order.customer_municipality
        elif order.customer_country:
            customer["country_code"] = order.customer_country
        return {
            "reference_code": order.reference_code,
            "document": "01",
            "numbering_range_id": numbering_range_id,
            "operation_type": "10",
            "send_email": s.invoice_send_email,
            "observation": f"{DISCLAIMER} Orden {order.reference_code}.",
            "payment_details": [{
                "payment_form": s.invoice_payment_form,
                "payment_method_code": s.invoice_payment_method_code,
                "reference_code": pay_ref(order),
                "amount": to_factus_str(total),
            }],
            "cash_rounding_amount": to_factus_str(total - computed),
            "customer": customer,
            "items": [{
                "code_reference": f"EVT-{order.event_id}"[:33] + f"-{tier[:3].upper()}",
                "name": f"Boleto demo (no oficial) - {tier} - {order.event_name}"[:200],
                "quantity": f"{order.quantity}.00",
                "discount_rate": "0.00",
                "price": to_factus_str(price),
                "unit_measure_code": s.invoice_unit_measure_code,
                "standard_code": s.invoice_standard_code,
                "taxes": [{"code": s.invoice_tax_code,
                           "rate": to_factus_str(s.invoice_tax_rate)}],
            }],
        }

    def _retry_due(self, order: Order) -> bool:
        """Reintento automático con espera creciente: base, 2x, 4x… (máx. 30 min)."""
        if order.invoice_attempts >= self._s.invoice_max_attempts:
            return False
        if order.status != S.invoice_failed or order.invoice_attempts == 0:
            return True
        wait = min(self._s.invoice_retry_base_seconds * 2 ** (order.invoice_attempts - 1), 1800)
        last = as_utc(order.updated_at) or utcnow()
        return utcnow() - last >= timedelta(seconds=wait)

    async def issue_invoice(self, order_id: str, *, manual: bool = False) -> Order | None:
        """`manual=True` (botón del comprador) ignora el límite y la espera de reintentos."""
        async with self._sessions() as session:
            order = await session.get(Order, order_id)
            if order is None or order.status not in (S.paid, S.invoice_failed):
                return order
            if not manual and not self._retry_due(order):
                return order
            if not await self._transition(session, order, S.invoicing, "Emitiendo factura",
                                          invoice_attempts=order.invoice_attempts + 1):
                return await self.get(order_id)  # otro proceso ganó la carrera

        async with self._sessions() as session:
            order = await session.get(Order, order_id)
            assert order is not None
            try:
                issued = await self._invoices.find_by_reference(order.reference_code)
                if issued is None:
                    issued = await self._create_or_recover(order)
            except InvoiceError as e:
                # El mensaje de Factus describe campos, no credenciales; se recorta por si acaso.
                log.warning("invoice failed order=%s ref=%s status=%s retryable=%s msg=%s",
                            order.id, order.reference_code, e.status_code, e.retryable,
                            str(e)[:300])
                await self._transition(session, order, S.invoice_failed, str(e),
                                       invoice_error=str(e)[:2000])
            else:
                if not issued.validated:
                    # Creada pero sin validar ante la DIAN: no se da por emitida ni se crea
                    # otra. El conciliador vuelve a consultarla por la misma referencia.
                    await self._transition(
                        session, order, S.invoice_failed, "Factura pendiente de validación",
                        invoice_number=issued.number,
                        invoice_error="Factura creada; pendiente de validación DIAN",
                    )
                    return await self.get(order_id)
                await self._transition(
                    session, order, S.completed, "Factura emitida",
                    invoice_number=issued.number, invoice_cufe=issued.cufe,
                    invoice_public_url=issued.public_url, invoice_error=None,
                )
        return await self.get(order_id)

    async def _create_or_recover(self, order: Order) -> IssuedInvoice:
        range_id = await self._invoices.numbering_range_id()
        try:
            return await self._invoices.create(self.build_invoice_payload(order, range_id))
        except InvoiceError as e:
            if not e.retryable:
                raise
            # Timeout/5xx/409: pudo haberse creado. Consultar antes de reintentar.
            found = await self._invoices.find_by_reference(order.reference_code)
            if found:
                return found
            raise

    # ------------------------------------------------------------------ conciliador
    async def reconcile(self) -> int:
        """Reprocesa órdenes atascadas. Se ejecuta al arrancar y periódicamente."""
        now = utcnow()
        stale = now - timedelta(minutes=5)
        async with self._sessions() as session:
            stuck = (await session.scalars(
                select(Order).where(Order.status == S.invoicing)
            )).all()
            for o in stuck:
                if (as_utc(o.updated_at) or now) < stale:
                    await self._transition(session, o, S.invoice_failed,
                                           "Facturación interrumpida; se reintentará")
            ids = (await session.scalars(
                select(Order.id).where(Order.status.in_([S.awaiting_payment, S.paid,
                                                         S.invoice_failed]))
            )).all()
        for oid in ids:
            await self.sync_payment(oid, force=True)
            await self.issue_invoice(oid)
        return len(ids)
