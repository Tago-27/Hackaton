from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base

_engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)

# Columnas añadidas después del primer despliegue: create_all no altera tablas existentes.
# (tabla, columna, DDL). PENDIENTE: reemplazar por Alembic antes de producción real.
_ADDED_COLUMNS = [
    ("orders", "user_id", "ALTER TABLE orders ADD COLUMN user_id VARCHAR(36) REFERENCES users(id)"),
    ("orders", "customer_municipality",
     "ALTER TABLE orders ADD COLUMN customer_municipality VARCHAR(5)"),
    ("orders", "pay_reference", "ALTER TABLE orders ADD COLUMN pay_reference VARCHAR(60)"),
    ("orders", "pay_attempt", "ALTER TABLE orders ADD COLUMN pay_attempt INTEGER DEFAULT 0"),
    ("orders", "ticket_tier", "ALTER TABLE orders ADD COLUMN ticket_tier VARCHAR(20)"),
]


def _missing_columns(sync_conn) -> list[str]:
    insp = inspect(sync_conn)
    tables = set(insp.get_table_names())
    pending = []
    for table, column, ddl in _ADDED_COLUMNS:
        if table in tables and column not in {c["name"] for c in insp.get_columns(table)}:
            pending.append(ddl)
    return pending


async def init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in await conn.run_sync(_missing_columns):
            await conn.execute(text(ddl))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
