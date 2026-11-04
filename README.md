# Turismo Musical — demo de compra de boletos

Busca conciertos, ve precios en USD/EUR/COP/GBP/JPY, paga **en COP** con QR Bre-B de
**Factus Pay** y recibe **factura electrónica DIAN** emitida con **Factus API v2**.

> El boleto digital generado es de demostración y **NO es un boleto oficial de Ticketmaster**.

```
backend/   FastAPI + SQLAlchemy async + httpx (adaptadores reales y fakes)
frontend/  React + TypeScript + Vite + Tailwind + TanStack Query
docs/      ARCHITECTURE.md · DECISIONS.md · reference/ (colecciones oficiales Factus)
```

## Arrancar en local (modo demo, sin claves)

```powershell
# Backend
cd backend
py -3.12 -m venv .venv           # 3.12+ (el proyecto fija 3.13 para producción)
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# Frontend (otra terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

Con todos los proveedores en `fake`, en la pantalla de pago aparece **"Simular pago exitoso"**.

## Conectar Factus Sandbox real

Las URLs del Sandbox ya vienen configuradas por defecto. En `backend/.env` solo van los
secretos, con estas equivalencias desde el entorno Postman `API Wars - Sandbox`:

| Postman | `backend/.env` |
|---|---|
| `pay_token` | `FACTUS_PAY_TOKEN` (reutiliza el token actual: `/auth` revoca el anterior) |
| `factus_client_id` / `factus_client_secret` | `FACTUS_CLIENT_ID` / `FACTUS_CLIENT_SECRET` |
| `factus_username` / `factus_password` | `FACTUS_USERNAME` / `FACTUS_PASSWORD` |
| `numbering_range_id` | `FACTUS_NUMBERING_RANGE_ID` (opcional si hay un solo rango válido) |
| `webhook_key` | `FACTUS_PAY_WEBHOOK_KEY` |
| `tm_api_key` | `TICKETMASTER_API_KEY` |
| `fx_api_key` | `FX_API_KEY` |

1. Copia `.env.example` a `backend/.env` y llena los valores de la tabla.
2. Comprueba la conexión (lista los rangos y dice cuál usará el backend):
   ```powershell
   cd backend; $env:RUN_LIVE_TESTS="1"; .\.venv\Scripts\python -m pytest tests/test_live_factus.py -v -s
   ```
3. Cambia `PAY_PROVIDER=factus` y `INVOICE_PROVIDER=factus`. Para eventos y tasas reales usa
   también `EVENTS_PROVIDER=ticketmaster` y `RATES_PROVIDER=exchangerate_api`.
4. Reinicia el backend. Paga el QR con el simulador oficial del Sandbox de Factus Pay. La página
   detecta el pago por sondeo y emite la factura.

## Calidad

```powershell
cd backend;  .\.venv\Scripts\ruff check . ; .\.venv\Scripts\python -m pytest -q
cd frontend; npx tsc -b ; npm test ; npm run build
npm run gen:api   # regenera tipos TS desde frontend/openapi.json (exportado del backend)
```

## API (prefijo `/api/v1`)

| Método | Ruta | Uso |
|---|---|---|
| GET | `/events?artist&city&country` | Buscar eventos (precios en 5 monedas) |
| GET | `/events/{id}` | Detalle |
| POST | `/quotes` | Valida rango 10.000–12.100.000 COP y desglosa |
| POST | `/orders` (header `Idempotency-Key`) | Crea orden + recaudo QR |
| GET | `/orders/{id}` | Estado (sondeo; verifica pago en Factus Pay) |
| POST | `/orders/{id}/retry-invoice` | Reintenta factura |
| GET | `/orders/{id}/invoice?format=pdf\|xml` | Proxy de descarga Factus |
| GET | `/orders/{id}/ticket` | PDF del boleto demo |
| POST | `/webhooks/factus-pay` (header `X-Webhook-Key`) | Webhook (siempre re-verifica) |

Documentación interactiva: http://localhost:8000/docs
