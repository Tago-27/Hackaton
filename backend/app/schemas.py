import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.catalogs import DOCUMENT_TYPES, MUNICIPALITIES

Currency = Literal["USD", "EUR", "COP", "GBP", "JPY"]


class RatesInfo(BaseModel):
    updated_at: datetime
    next_update_at: datetime
    note: str = "Valores en USD, EUR, GBP y JPY son referenciales. El cobro es en COP."


TierCode = Literal["general", "preferencial", "vip"]


class TierOut(BaseModel):
    code: TierCode
    label: str
    unit_price_cop: Decimal
    display_prices: dict[Currency, Decimal]


class EventOut(BaseModel):
    id: str
    name: str
    artist: str | None
    city: str | None
    country: str | None
    venue: str | None
    date: str | None
    image_url: str | None
    original_price: Decimal | None
    original_currency: str | None
    is_demo_price: bool = Field(
        description="True: el precio cobrable sale del catálogo de la demo. original_price es "
        "solo orientativo (Ticketmaster no vende boletos a través de Discovery)."
    )
    unit_price_cop: Decimal = Field(description="Precio de la localidad General (desde).")
    display_prices: dict[Currency, Decimal]
    tiers: list[TierOut]
    rates: RatesInfo


class EventSearchOut(BaseModel):
    items: list[EventOut]


class QuoteIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=10)
    tier: TierCode = "general"


class QuoteOut(BaseModel):
    event_id: str
    quantity: int
    charge_currency: Literal["COP"] = "COP"
    tier: TierCode
    tier_label: str
    unit_price_cop: Decimal
    total_cop: Decimal
    references: dict[Currency, Decimal]
    rates: RatesInfo


class CustomerIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    doc_type: str
    doc_number: str = Field(min_length=3, max_length=20)
    names: str = Field(min_length=3, max_length=200)
    email: str = Field(max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    address: str | None = Field(default=None, max_length=300)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    municipality: str | None = Field(
        default=None, pattern=r"^\d{5}$",
        description="Código DANE del municipio. Obligatorio si country es CO.",
    )

    @model_validator(mode="after")
    def _doc(self) -> "CustomerIn":
        dt = DOCUMENT_TYPES.get(self.doc_type)
        if dt is None:
            raise ValueError("Tipo de documento no soportado")
        if not re.fullmatch(dt.pattern, self.doc_number):
            raise ValueError(f"Número de documento inválido para {dt.label}")
        if self.country == "CO":
            # Factus exige municipality_code cuando el cliente es colombiano.
            if self.municipality not in MUNICIPALITIES:
                raise ValueError("Selecciona tu municipio (obligatorio para Colombia)")
        else:
            self.municipality = None
        return self


class OrderIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=10)
    tier: TierCode = "general"
    customer: CustomerIn
    data_consent: Literal[True] = Field(
        description="El comprador autoriza el tratamiento de sus datos personales."
    )


class PaymentOut(BaseModel):
    status: str | None
    qr: str | None
    breb_key: str | None
    expires_at: datetime | None


class InvoiceOut(BaseModel):
    number: str | None
    cufe: str | None
    public_url: str | None
    available: bool


class RegisterIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=3, max_length=200)
    email: str = Field(max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(max_length=200)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: str
    name: str
    email: str


class TicketOut(BaseModel):
    code: str = Field(description="Código único del boleto: <referencia>-<n>")
    number: int
    of: int


class OrderOut(BaseModel):
    id: str
    reference_code: str
    status: Literal[
        "created", "awaiting_payment", "paid", "invoicing", "completed",
        "payment_expired", "payment_failed", "invoice_failed",
    ]
    event_id: str
    event_name: str
    event_date: str | None
    event_venue: str | None
    event_city: str | None
    quantity: int
    ticket_tier: str = Field(description="Nombre de la localidad (General, Preferencial, VIP).")
    total_cop: Decimal
    customer_names: str
    payment: PaymentOut
    invoice: InvoiceOut
    tickets: list[TicketOut]
    error: str | None
    disclaimer: str
    created_at: datetime


class DocumentTypeOut(BaseModel):
    code: str
    label: str
    pattern: str


class MunicipalityOut(BaseModel):
    code: str
    name: str


class ConfigOut(BaseModel):
    document_types: list[DocumentTypeOut]
    municipalities: list[MunicipalityOut]
    min_cop: Decimal
    max_cop: Decimal
    disclaimer: str
    fake_payments: bool


class ErrorOut(BaseModel):
    detail: str
