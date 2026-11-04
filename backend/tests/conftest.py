import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": f"sqlite+aiosqlite:///{_tmp}/test.db",
    "EVENTS_PROVIDER": "fake", "RATES_PROVIDER": "fake",
    "PAY_PROVIDER": "fake", "INVOICE_PROVIDER": "fake",
    "FACTUS_PAY_WEBHOOK_KEY": "test-webhook-key",
    "FACTUS_PAY_POLL_MIN_INTERVAL_SECONDS": "0",
    "RECONCILER_INTERVAL_SECONDS": "3600",
    "INVOICE_RETRY_BASE_SECONDS": "0",
    "FACTUS_NUMBERING_RANGE_ID": "8",
})

import httpx  # noqa: E402
import pytest  # noqa: E402

from app import main  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
async def client():
    main._hits.clear()
    async with main.lifespan(main.app):
        async with SessionLocal() as s:
            for t in reversed(Base.metadata.sorted_tables):
                await s.execute(t.delete())
            await s.commit()
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/auth/register", json=USER)
            assert r.status_code == 201, r.text
            yield c


@pytest.fixture
async def anon():
    """Cliente sin sesión (usa la misma app ya iniciada por `client`)."""
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


USER = {"name": "Ana Pérez", "email": "ana@example.com", "password": "clave-segura-1"}
CUSTOMER = {"doc_type": "13", "doc_number": "1020304050", "names": "Ana Pérez",
            "email": "ana@example.com"}
