import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class OrderStatus(enum.StrEnum):
    created = "created"
    awaiting_payment = "awaiting_payment"
    paid = "paid"
    invoicing = "invoicing"
    completed = "completed"
    payment_expired = "payment_expired"
    payment_failed = "payment_failed"
    invoice_failed = "invoice_failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Null solo en órdenes creadas antes de existir el login.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    reference_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.created, index=True)

    # Evento (copia mínima para el boleto)
    event_id: Mapped[str] = mapped_column(String(100))
    event_name: Mapped[str] = mapped_column(String(300))
    event_date: Mapped[str | None] = mapped_column(String(40))
    event_venue: Mapped[str | None] = mapped_column(String(300))
    event_city: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    # Código de localidad (general/preferencial/vip). Null en órdenes anteriores = General.
    ticket_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_price_cop: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_cop: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    # Datos personales mínimos para facturar
    customer_doc_type: Mapped[str] = mapped_column(String(10))
    customer_doc_number: Mapped[str] = mapped_column(String(30))
    customer_names: Mapped[str] = mapped_column(String(200))
    customer_email: Mapped[str] = mapped_column(String(200))
    customer_address: Mapped[str | None] = mapped_column(String(300))
    customer_country: Mapped[str | None] = mapped_column(String(2))
    customer_municipality: Mapped[str | None] = mapped_column(String(5), nullable=True)
    data_consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Pago (Factus Pay). Cada reintento de pago usa una referencia nueva de recaudo
    # (REF-R1, REF-R2…) porque Factus Pay no permite reutilizarla; la factura siempre usa
    # reference_code. pay_reference=None significa que el recaudo usa reference_code.
    pay_reference: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    pay_attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pay_qr: Mapped[str | None] = mapped_column(Text)
    pay_breb_key: Mapped[str | None] = mapped_column(String(200))
    pay_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pay_status: Mapped[str | None] = mapped_column(String(20))
    pay_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pay_last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Factura (Factus v2)
    invoice_number: Mapped[str | None] = mapped_column(String(50))
    invoice_cufe: Mapped[str | None] = mapped_column(String(200))
    invoice_public_url: Mapped[str | None] = mapped_column(String(500))
    invoice_attempts: Mapped[int] = mapped_column(Integer, default=0)
    invoice_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    transitions: Mapped[list["OrderTransition"]] = relationship(
        back_populates="order", order_by="OrderTransition.id", lazy="selectin"
    )


class OrderTransition(Base):
    __tablename__ = "order_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped[Order] = relationship(back_populates="transitions")
