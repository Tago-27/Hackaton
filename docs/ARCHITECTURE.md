# Arquitectura

```
Navegador ──► Frontend (React) ──► Backend FastAPI /api/v1 ──┬─► EventsProvider   (Ticketmaster | Fake)
                                                             ├─► RatesProvider    (open.er-api | Fake)
                                                             ├─► PayProvider      (Factus Pay | Fake)
                                                             ├─► InvoiceProvider  (Factus v2 | Fake)
                                                             └─► BD (SQLite local / PostgreSQL)
```

- El frontend **solo** llama al backend. Ningún token de Factus ni clave de proveedor llega al navegador.
- Cada adaptador está en `backend/app/adapters/` con una implementación real y otra fake determinista.
  Se eligen con `*_PROVIDER` en el entorno (`backend/app/container.py`).
- Las pruebas y el modo de desarrollo funcionan sin red usando los fakes.

## Dinero (`backend/app/money.py`)

- Siempre `Decimal`. COP y JPY sin decimales; USD, EUR y GBP con 2, redondeando `ROUND_HALF_UP`.
- Las tasas vienen como **unidades de cada moneda por 1 COP**:
  `X = COP × rate[X]` y `COP = X ÷ rate[X]`. Una prueba unitaria verifica esa dirección.
- A Factus se envían montos como texto con 2 decimales (`"20000.00"`).
- Factus Pay acepta de 10.000 a 12.100.000 COP. `/quotes` y `/orders` validan ese rango.

## Factus Pay (`adapters/factus_pay.py`)

Las rutas vienen de la colección oficial `factus-pay`:
`POST /v1/collections {reference_code, amount}` y `GET /v1/collections/{reference_code}`.
Se usa un token Bearer **fijo** del entorno; no hay login automático (`scripts/rotate_pay_token.py`
rota el token a mano). Una respuesta 200 al crear se trata como idempotente: el recaudo ya existía.

## Factus API v2 (`adapters/factus_invoice.py`)

- La autenticación usa `POST /oauth/token` con form-data y password grant. El token se renueva
  con `refresh_token` antes de que venza, según el `expires_in` real. Un candado evita
  renovaciones concurrentes, y ante un 401 se reintenta una sola vez.
- `POST /v2/bills/validate` crea la factura.
- `GET /v2/bills?filter[reference_code]=` consulta antes de crear o reintentar, para no duplicar.
- `GET /v2/bills/{number}/download-pdf|xml` descarga los archivos. Si llegan en JSON base64,
  se decodifican.

## Máquina de estados (`services/orders.py`)

```
created → awaiting_payment ─┬─► paid → invoicing ─┬─► completed
                            ├─► payment_failed    └─► invoice_failed ─(conciliador)─► invoicing
                            └─► payment_expired
```

- **Pago:** `GET /orders/{id}` consulta Factus Pay, con un intervalo mínimo de 3 s, y pasa a `paid`
  solo si coinciden el estado, la referencia y el monto. Un webhook dispara la misma verificación;
  nunca se confía en lo que trae el payload.
- **Factura:** se crea únicamente desde `paid` o `invoice_failed`, con compare-and-set en la BD.
  El `reference_code` de la factura es el mismo de la orden.
- **Conciliador:** corre al arrancar y cada 60 s. Reintenta `invoice_failed` (hasta 5 intentos),
  rescata las órdenes atascadas en `invoicing` y sincroniza pagos pendientes.
- Cada cambio de estado queda registrado en `order_transitions`.
