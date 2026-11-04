import hashlib
from decimal import ROUND_HALF_UP, Decimal

from app.adapters.events import EventsProvider, ProviderEvent
from app.adapters.rates import RatesProvider, RatesSnapshot
from app.catalogs import DEMO_BASE_PRICES_COP, TICKET_TIERS
from app.config import Settings
from app.money import MoneyError, check_pay_range, reference_amounts, to_cop
from app.schemas import EventOut, QuoteOut, RatesInfo, TierOut


class NotFound(LookupError):
    pass


def _round_cop(value: Decimal, step: int = 1000) -> Decimal:
    """Precios "redondos" en pesos: múltiplos de 1.000 COP."""
    return (value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step


def demo_base_price(event_id: str) -> Decimal:
    """Precio de demo estable por concierto: siempre el mismo para el mismo evento."""
    h = int(hashlib.sha256(event_id.encode()).hexdigest(), 16)
    return DEMO_BASE_PRICES_COP[h % len(DEMO_BASE_PRICES_COP)]


class CatalogService:
    def __init__(self, events: EventsProvider, rates: RatesProvider, settings: Settings) -> None:
        self._events = events
        self._rates = rates
        self._s = settings

    def _base_cop(self, ev: ProviderEvent, snap: RatesSnapshot) -> tuple[Decimal, bool]:
        """Precio base (localidad General) en COP y si es precio de demostración.

        1. Si el proveedor publica un precio razonable, se usa convertido a COP (decisión del
           usuario 2026-11-04). Ticketmaster solo lo publica en pocos eventos y a veces con
           valores sin sentido (p. ej. 1,50 USD), por eso se exige un mínimo.
        2. Si no, precio de demo estable por concierto.
        """
        if ev.price is not None and ev.currency:
            try:
                cop = _round_cop(to_cop(ev.price, ev.currency, snap.rates))
            except MoneyError:
                cop = None
            if cop is not None and self._s.provider_price_min_cop <= cop <= \
                    self._s.provider_price_max_cop:
                return cop, False
        return demo_base_price(ev.id), True

    def _tiers(self, base: Decimal, snap: RatesSnapshot) -> list[TierOut]:
        out = []
        for code, (label, factor) in TICKET_TIERS.items():
            price = base if factor == 1 else _round_cop(base * factor)
            out.append(TierOut(code=code, label=label, unit_price_cop=price,
                               display_prices=reference_amounts(price, snap.rates)))
        return out

    def _out(self, ev: ProviderEvent, snap: RatesSnapshot) -> EventOut:
        base, is_demo = self._base_cop(ev, snap)
        return EventOut(
            id=ev.id, name=ev.name, artist=ev.artist, city=ev.city, country=ev.country,
            venue=ev.venue, date=ev.date, image_url=ev.image_url,
            original_price=ev.price, original_currency=ev.currency,
            is_demo_price=is_demo, unit_price_cop=base,
            display_prices=reference_amounts(base, snap.rates),
            tiers=self._tiers(base, snap),
            rates=RatesInfo(updated_at=snap.updated_at, next_update_at=snap.next_update_at),
        )

    async def search(self, artist: str | None, city: str | None, country: str | None):
        snap = await self._rates.latest()
        found = await self._events.search(artist=artist, city=city, country=country)
        return [self._out(e, snap) for e in found]

    async def event(self, event_id: str) -> tuple[ProviderEvent, EventOut]:
        ev = await self._events.get(event_id)
        if ev is None:
            raise NotFound("Evento no encontrado")
        return ev, self._out(ev, await self._rates.latest())

    async def quote(self, event_id: str, quantity: int, tier: str = "general") -> QuoteOut:
        """Lanza MoneyError si el total queda fuera del rango de Factus Pay."""
        _, ev = await self.event(event_id)
        chosen = next((t for t in ev.tiers if t.code == tier), None)
        if chosen is None:
            raise NotFound("Localidad no disponible")
        snap = await self._rates.latest()
        total = chosen.unit_price_cop * quantity
        check_pay_range(total, self._s.factus_pay_min_cop, self._s.factus_pay_max_cop)
        return QuoteOut(
            event_id=event_id, quantity=quantity, tier=chosen.code, tier_label=chosen.label,
            unit_price_cop=chosen.unit_price_cop, total_cop=total,
            references=reference_amounts(total, snap.rates), rates=ev.rates,
        )
