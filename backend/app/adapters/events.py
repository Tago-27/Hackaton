"""Proveedor de eventos musicales: Ticketmaster Discovery API v2 o fake determinista."""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

import httpx


@dataclass(frozen=True)
class ProviderEvent:
    id: str
    name: str
    artist: str | None
    city: str | None
    country: str | None
    venue: str | None
    date: str | None  # ISO 8601 (fecha u hora local)
    image_url: str | None
    price: Decimal | None
    currency: str | None


class EventsProvider(Protocol):
    async def search(
        self, *, artist: str | None, city: str | None, country: str | None
    ) -> list[ProviderEvent]: ...

    async def get(self, event_id: str) -> ProviderEvent | None: ...


class EventsProviderError(RuntimeError):
    pass


class TicketmasterEvents:
    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str, ttl: int) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._ttl = ttl
        self._cache: dict[str, tuple[float, object]] = {}

    def _cached(self, key: str) -> object | None:
        hit = self._cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        return None

    def _store(self, key: str, value: object) -> None:
        self._cache[key] = (time.monotonic() + self._ttl, value)

    async def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        try:
            r = await self._client.get(
                f"{self._base}{path}", params={**params, "apikey": self._key}, timeout=10
            )
        except httpx.HTTPError as e:
            raise EventsProviderError("No se pudo contactar al proveedor de eventos") from e
        if r.status_code == 429:
            raise EventsProviderError(
                "El proveedor de eventos limitó las solicitudes; intenta luego"
            )
        return r

    async def search(self, *, artist, city, country) -> list[ProviderEvent]:
        # Solo eventos futuros: sin startDateTime, Discovery también devuelve eventos pasados.
        # Se redondea a la hora para que la caché siga funcionando.
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        params = {"classificationName": "music", "size": "20", "sort": "date,asc",
                  "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if artist:
            params["keyword"] = artist
        if city:
            params["city"] = city
        if country:
            params["countryCode"] = country.upper()
        key = "s:" + repr(sorted(params.items()))
        cached = self._cached(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        r = await self._get("/events.json", params)
        if r.status_code != 200:
            raise EventsProviderError(f"Proveedor de eventos respondió {r.status_code}")
        raw = r.json().get("_embedded", {}).get("events", [])
        events = [_parse_tm(e) for e in raw]
        self._store(key, events)
        for ev in events:
            self._store("e:" + ev.id, ev)
        return events

    async def get(self, event_id: str) -> ProviderEvent | None:
        cached = self._cached("e:" + event_id)
        if cached is not None:
            return cached  # type: ignore[return-value]
        r = await self._get(f"/events/{event_id}.json", {})
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise EventsProviderError(f"Proveedor de eventos respondió {r.status_code}")
        ev = _parse_tm(r.json())
        self._store("e:" + event_id, ev)
        return ev


def _parse_tm(e: dict) -> ProviderEvent:
    emb = e.get("_embedded", {})
    venue = (emb.get("venues") or [{}])[0]
    attraction = (emb.get("attractions") or [{}])[0]
    images = sorted(e.get("images") or [], key=lambda i: i.get("width", 0), reverse=True)
    start = e.get("dates", {}).get("start", {})
    prices = e.get("priceRanges") or []
    price = currency = None
    if prices and prices[0].get("min") is not None:
        price = Decimal(str(prices[0]["min"]))
        currency = prices[0].get("currency")
    return ProviderEvent(
        id=e["id"],
        name=e.get("name", ""),
        artist=attraction.get("name"),
        city=(venue.get("city") or {}).get("name"),
        country=(venue.get("country") or {}).get("countryCode"),
        venue=venue.get("name"),
        date=start.get("dateTime") or start.get("localDate"),
        image_url=images[0]["url"] if images else None,
        price=price,
        currency=currency,
    )


_FAKE = [
    ProviderEvent("fake-001", "Noche de Vallenato", "Silvestre Ruiz", "Valledupar", "CO",
                  "Parque de la Leyenda", "2027-04-26T20:00:00", None, Decimal("180000"), "COP"),
    ProviderEvent("fake-002", "Rock al Parque Tour", "Los Andes Eléctricos", "Bogotá", "CO",
                  "Movistar Arena", "2027-02-14T19:30:00", None, Decimal("75.00"), "USD"),
    ProviderEvent("fake-003", "Salsa bajo las estrellas", "Orquesta del Pacífico", "Cali", "CO",
                  "Teatro al Aire Libre Los Cristales", "2027-03-08T21:00:00", None, None, None),
    ProviderEvent("fake-004", "Madrid Indie Fest", "Las Olas", "Madrid", "ES",
                  "WiZink Center", "2027-05-20T21:00:00", None, Decimal("55.00"), "EUR"),
    ProviderEvent("fake-005", "London Jazz Night", "The Blue Notes", "London", "GB",
                  "Royal Albert Hall", "2027-06-02T19:00:00", None, Decimal("40.00"), "GBP"),
    ProviderEvent("fake-006", "Tokyo City Pop Live", "Neon Avenue", "Tokyo", "JP",
                  "Budokan", "2027-07-11T18:00:00", None, Decimal("9800"), "JPY"),
]


class FakeEvents:
    async def search(self, *, artist, city, country) -> list[ProviderEvent]:
        def ok(e: ProviderEvent) -> bool:
            if artist and artist.lower() not in f"{e.artist} {e.name}".lower():
                return False
            if city and city.lower() not in (e.city or "").lower():
                return False
            return not (country and country.upper() != e.country)

        return [e for e in _FAKE if ok(e)]

    async def get(self, event_id: str) -> ProviderEvent | None:
        return next((e for e in _FAKE if e.id == event_id), None)
