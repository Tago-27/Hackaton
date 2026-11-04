"""Catálogos configurables.

PENDIENTE: confirmar los códigos con una factura validada real en Postman. Son los
códigos DIAN de tipo de documento que usa Factus v2 en `identification_document_code`
(la colección oficial usa 13 para cédula y 31 para NIT).
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DocumentType:
    code: str
    label: str
    pattern: str  # regex que debe cumplir el número


DOCUMENT_TYPES: dict[str, DocumentType] = {
    "13": DocumentType("13", "Cédula de ciudadanía", r"^\d{5,10}$"),
    "31": DocumentType("31", "NIT", r"^\d{6,15}$"),
    "22": DocumentType("22", "Cédula de extranjería", r"^\d{3,10}$"),
    "41": DocumentType("41", "Pasaporte", r"^[A-Za-z0-9]{5,20}$"),
}

DISCLAIMER = (
    "Boleto digital de demostración: NO es un boleto oficial de Ticketmaster "
    "ni de ningún organizador."
)


# Municipios para clientes colombianos: código DANE de 5 dígitos, que es lo que Factus v2
# recibe en `customer.municipality_code` (verificado 2026-11-04: 11001 aceptado; con
# country_code=CO el campo es obligatorio). Factus no expone catálogo propio en v2.
# PENDIENTE: ampliar la lista si se necesitan otros municipios.
MUNICIPALITIES: dict[str, str] = {
    "11001": "Bogotá D.C.",
    "05001": "Medellín (Antioquia)",
    "76001": "Cali (Valle del Cauca)",
    "08001": "Barranquilla (Atlántico)",
    "13001": "Cartagena (Bolívar)",
    "68001": "Bucaramanga (Santander)",
    "54001": "Cúcuta (Norte de Santander)",
    "66001": "Pereira (Risaralda)",
    "17001": "Manizales (Caldas)",
    "47001": "Santa Marta (Magdalena)",
    "73001": "Ibagué (Tolima)",
    "50001": "Villavicencio (Meta)",
    "52001": "Pasto (Nariño)",
    "23001": "Montería (Córdoba)",
    "20001": "Valledupar (Cesar)",
    "41001": "Neiva (Huila)",
    "63001": "Armenia (Quindío)",
    "19001": "Popayán (Cauca)",
    "70001": "Sincelejo (Sucre)",
    "15001": "Tunja (Boyacá)",
    "44001": "Riohacha (La Guajira)",
    "18001": "Florencia (Caquetá)",
    "27001": "Quibdó (Chocó)",
    "88001": "San Andrés",
    "68679": "San Gil (Santander)",
    "68276": "Floridablanca (Santander)",
    "05088": "Bello (Antioquia)",
    "05266": "Envigado (Antioquia)",
    "05360": "Itagüí (Antioquia)",
    "05615": "Rionegro (Antioquia)",
    "08758": "Soledad (Atlántico)",
    "25754": "Soacha (Cundinamarca)",
    "25175": "Chía (Cundinamarca)",
    "25899": "Zipaquirá (Cundinamarca)",
    "76520": "Palmira (Valle del Cauca)",
}


# Localidades por concierto: código -> (nombre, multiplicador sobre el precio base/General).
TICKET_TIERS: dict[str, tuple[str, Decimal]] = {
    "general": ("General", Decimal("1")),
    "preferencial": ("Preferencial", Decimal("1.6")),
    "vip": ("VIP", Decimal("2.5")),
}

# Precios base de demostración (localidad General) cuando el proveedor no publica precio.
# A cada concierto le corresponde siempre el mismo (ver services/catalog.demo_base_price).
DEMO_BASE_PRICES_COP: tuple[Decimal, ...] = tuple(
    Decimal(v) for v in (89000, 119000, 149000, 179000, 219000, 259000, 299000, 349000, 450000)
)
