"""Configuración del servidor. Todos los secretos llegan por variables de entorno."""

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./turismo_musical.db"
    frontend_origin: str = "http://localhost:5173"
    # Carpeta con el build de Vite. Si existe, FastAPI sirve la página en la misma URL que la API
    # (despliegue de un solo servicio en Render; sin CORS).
    static_dir: str = "static"
    log_level: str = "INFO"

    # --- Selección de adaptadores (fake = sin red ni claves) ---
    events_provider: Literal["ticketmaster", "fake"] = "fake"
    rates_provider: Literal["exchangerate_api", "open_er_api", "fake"] = "fake"
    pay_provider: Literal["factus", "fake"] = "fake"
    invoice_provider: Literal["factus", "fake"] = "fake"

    # --- Ticketmaster Discovery API ---
    ticketmaster_api_key: SecretStr | None = None
    ticketmaster_base_url: str = "https://app.ticketmaster.com/discovery/v2"
    events_cache_ttl_seconds: int = 120
    # Ticketmaster Discovery NO vende boletos: su priceRanges es solo orientativo. El precio
    # cobrable sale del catálogo propio de la demo (fixture del equipo: 119.000 COP con IVA).
    demo_ticket_price_cop: Decimal = Decimal("119000")  # ya no se usa; ver DEMO_BASE_PRICES_COP
    # Un precio del proveedor se usa solo si, convertido a COP, cae en este rango (descarta
    # valores sin sentido como 1,50 USD).
    provider_price_min_cop: Decimal = Decimal("20000")
    provider_price_max_cop: Decimal = Decimal("4000000")

    # --- Tasas de cambio (unidades de cada moneda por 1 COP) ---
    # exchangerate_api: {fx_base_url}/{fx_api_key}/latest/COP (plan Free, 1 actualización/día)
    fx_base_url: str = "https://v6.exchangerate-api.com/v6"
    fx_api_key: SecretStr | None = None
    # open_er_api: endpoint abierto sin clave del mismo proveedor
    rates_base_url: str = "https://open.er-api.com/v6/latest/COP"

    # --- Factus Pay (token fijo; NO se hace login automático) ---
    factus_pay_base_url: str = "https://pay-api-sandbox.factus.com.co"
    factus_pay_qr_expiration_seconds: int = 900
    factus_pay_token: SecretStr | None = None
    factus_pay_min_cop: Decimal = Decimal("10000")
    factus_pay_max_cop: Decimal = Decimal("12100000")
    factus_pay_poll_min_interval_seconds: float = 3.0
    factus_pay_webhook_key: SecretStr | None = None

    # --- Factus API v2 (OAuth2 password grant) ---
    factus_api_base_url: str = "https://api-sandbox.factus.com.co"
    factus_client_id: SecretStr | None = None
    factus_client_secret: SecretStr | None = None
    factus_username: SecretStr | None = None
    factus_password: SecretStr | None = None
    # Si no se define, se elige automáticamente cuando hay exactamente un rango válido.
    factus_numbering_range_id: int | None = None

    # --- Facturación (configurable; debe validarlo el equipo contable) ---
    invoice_tax_code: str = "01"  # 01 = IVA
    invoice_tax_rate: Decimal = Decimal("19.00")
    invoice_unit_measure_code: str = "94"  # 94 = unidad
    invoice_standard_code: str = "999"
    invoice_payment_form: str = "1"  # 1 = contado
    invoice_payment_method_code: str = "47"  # 47 = transferencia débito bancaria (Bre-B)
    invoice_send_email: bool = False
    invoice_customer_legal_organization_code: str = "2"  # 2 = persona natural
    invoice_customer_tribute_code: str = "ZZ"
    invoice_customer_responsibilities: list[str] = Field(default_factory=lambda: ["R-99-PN"])
    reconciler_interval_seconds: int = 60
    # Reintentos automáticos de factura (con espera creciente). El botón "Reintentar" del
    # comprador no tiene este límite.
    invoice_max_attempts: int = 8
    invoice_retry_base_seconds: int = 60

    # --- Sesiones (login) ---
    # Obligatoria en producción. En desarrollo se genera una al arrancar.
    session_secret: SecretStr | None = None
    session_days: int = 7

    @field_validator(
        "ticketmaster_api_key", "fx_api_key", "factus_pay_token", "factus_pay_webhook_key",
        "factus_client_id", "factus_client_secret", "factus_username", "factus_password",
        "factus_numbering_range_id", "session_secret", mode="before",
    )
    @classmethod
    def _clean_secret(cls, v):
        """Tolera errores típicos al pegar valores en un panel (Render, Railway…):
        espacios alrededor y comillas que venían del .env local. Vacío = no configurado."""
        if not isinstance(v, str):
            return v
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1].strip()
        return v or None

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, v: str) -> str:
        # Railway entrega postgres:// o postgresql://; SQLAlchemy async necesita asyncpg.
        if v.startswith("postgres://"):
            v = "postgresql://" + v.removeprefix("postgres://")
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v.removeprefix("postgresql://")
        if v.startswith("postgresql+asyncpg://") and "?" in v:
            # Neon/Supabase usan parámetros de libpq que asyncpg no entiende:
            # sslmode=require -> ssl=require; channel_binding se descarta.
            base, _, query = v.partition("?")
            params = []
            for p in query.split("&"):
                k, _, val = p.partition("=")
                if k == "sslmode":
                    params.append(f"ssl={val}")
                elif k and k != "channel_binding":
                    params.append(p)
            v = base + ("?" + "&".join(params) if params else "")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
