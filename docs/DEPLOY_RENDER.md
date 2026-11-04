# Despliegue en Render

Un solo **Web Service (Docker)** sirve la API y la página en la misma URL, más una base
**PostgreSQL** de Render. Todo está declarado en `render.yaml` (Blueprint).

```
https://turismo-musical.onrender.com/          → página (React)
https://turismo-musical.onrender.com/api/v1/…  → API (FastAPI)
https://turismo-musical.onrender.com/docs      → documentación interactiva
```

## 1. Subir el código a GitHub

1. Crea un repositorio **privado** vacío en https://github.com/new (sin README ni .gitignore).
2. Desde `turismo-musical/`:
   ```powershell
   git remote add origin https://github.com/<usuario>/<repo>.git
   git push -u origin main
   ```
   `backend/.env` está en `.gitignore`: los secretos no se suben.

## 2. Crear el Blueprint en Render

1. https://dashboard.render.com → **New** → **Blueprint** → conecta el repositorio.
2. Render lee `render.yaml` y pide los valores marcados `sync: false`. Cópialos de
   `backend/.env`, **sin comillas**:

   | Variable | Valor |
   |---|---|
   | `TICKETMASTER_API_KEY` | consumer key de Ticketmaster |
   | `FX_API_KEY` | clave de ExchangeRate-API (no se usa mientras `RATES_PROVIDER=open_er_api`) |
   | `FACTUS_PAY_TOKEN` | token de Factus Pay vigente |
   | `FACTUS_CLIENT_ID` / `FACTUS_CLIENT_SECRET` | credenciales OAuth de Factus v2 |
   | `FACTUS_USERNAME` / `FACTUS_PASSWORD` | usuario y contraseña de Factus v2 |

   `FACTUS_PAY_WEBHOOK_KEY` la genera Render; `DATABASE_URL` sale de la base creada.
3. **Apply**. El primer build tarda ~5 min. Comprueba `https://<servicio>.onrender.com/health`.

## 3. Registrar el webhook en Factus Pay (opcional)

En el panel de Factus Pay registra la URL **sin** `?key`:
`https://<servicio>.onrender.com/api/v1/webhooks/factus-pay` y configura como llave el valor de
`FACTUS_PAY_WEBHOOK_KEY` (Render → servicio → Environment). Sin webhook también funciona: la
página consulta el estado del pago y el conciliador revisa cada 60 s.

## Limitaciones del plan gratis

- El servicio **se duerme tras 15 min sin tráfico**; la primera visita tarda ~1 min en despertar.
  Mientras duerme no corre el conciliador ni recibe webhooks (los pagos se concilian al despertar).
  Para la presentación abre la página unos minutos antes.
- La base PostgreSQL gratis **vence a los 30 días**.
- Rotar el token de Factus Pay invalida el que está en Render: actualiza `FACTUS_PAY_TOKEN` y
  Render redeploya solo.

## Antes de producción real (fuera de Sandbox)

- Cambiar URLs y credenciales de Factus a producción y regenerar todas las claves compartidas.
- Migraciones con Alembic (hoy las tablas se crean con `create_all`).
- Revisar el tratamiento tributario con el equipo contable (`docs/DECISIONS.md`).
