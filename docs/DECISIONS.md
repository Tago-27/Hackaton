# Decisiones

| # | Decisión | Motivo / estado |
|---|---|---|
| 1 | `.python-version` = 3.13; el código es compatible con 3.12+ | El usuario eligió 3.13. En este equipo no está instalado, así que el desarrollo local usa 3.12. |
| 2 | Proveedor de eventos: **Ticketmaster Discovery API v2** | Lo eligió el usuario el 2026-11-04. Requiere `TICKETMASTER_API_KEY`. |
| 3 | Tasas de cambio: **ExchangeRate-API** `v6.exchangerate-api.com/v6/{key}/latest/COP` (`RATES_PROVIDER=exchangerate_api`) | Es el proveedor de la colección del equipo (`API_Wars_Fase1`). Usa el plan Free, con una actualización diaria; se cachea hasta `time_next_update_unix` y se revisa `result`/`error-type` aunque el HTTP sea 200. El endpoint abierto `open.er-api.com` queda como alternativa sin clave. **2026-11-04:** la clave del equipo responde `inactive-account` (correo sin confirmar), así que por ahora se usa `open_er_api`. |
| 4 | Mínimo de Factus Pay: 10.000 COP | Lo confirma el 422 observado en Postman. |
| 5 | Máximo de Factus Pay: 12.100.000 COP | **PENDIENTE** contrastarlo con una muestra real. |
| 6 | Rutas y hosts de Factus contrastados con `API_Wars_Fase1` (2026-11-04): `pay-api-sandbox.factus.com.co` y `api-sandbox.factus.com.co` | Las colecciones están en `docs/reference/`, sin secretos. |
| 7 | Respuestas de Factus: Pay y v2 traen el objeto bajo `data`. En v2 se exige `data.is_validated=true`; si no, la orden queda `invoice_failed` con el número guardado y se concilia por la misma referencia, **sin crear otra factura** | Lo indica la colección del equipo. **PENDIENTE** guardar JSON reales sanitizados en `docs/samples/`. |
| 8 | **Precio (actualizado 2026-11-04 por decisión del usuario):** si Ticketmaster publica `priceRanges` y convertido a COP queda entre 20.000 y 4.000.000, se usa (redondeado a 1.000) como precio General; si no, precio de demo estable por concierto (89.000–450.000 COP, `DEMO_BASE_PRICES_COP`). Localidades: General ×1, Preferencial ×1,6, VIP ×2,5 | Antes todos costaban 119.000 COP. Medido en producción: Ticketmaster publica precio en ~5 % de los eventos (y a veces valores sin sentido como 1,50 USD). Esto se aparta de la colección del equipo, que pedía no cobrar `priceRanges`. Factura VIP validada en Sandbox (SETP990033506). |
| 9 | Impuestos configurables: IVA 19 % incluido en el total, con `cash_rounding_amount` para el redondeo | **PENDIENTE**: el tratamiento tributario del boleto lo debe validar el equipo contable. |
| 10 | Códigos de documento DIAN: 13 CC, 31 NIT, 22 CE, 41 Pasaporte (`app/catalogs.py`) | La colección oficial usa 13 y 31. **PENDIENTE** verificar 22 y 41 con una factura validada. NIT sin DV por ahora. |
| 11 | Medio de pago en la factura: `47` (transferencia débito bancaria, Bre-B) | Configurable. **PENDIENTE** confirmarlo. |
| 12 | Token de Factus Pay fijo, sin login automático; rotación manual con confirmación | Un login nuevo revoca el anterior. |
| 13 | Webhook: la llave llega como `?key=` (Factus Pay la agrega a la URL registrada) y se compara en tiempo constante. El payload `{data:{reference_code,amount,status}}` nunca se usa como prueba de pago | Lo indica la colección del equipo. El header `X-Webhook-Key` se acepta como alternativa. Si el proceso cae antes de procesarlo, el conciliador (cada 60 s) recupera el pago igualmente. |
| 14 | Las tablas se crean con `create_all` al arrancar | **PENDIENTE**: migrar a Alembic antes de producción. |
| 15 | Renovar un QR vencido crea una orden nueva (nuevo `reference_code`) | Factus Pay usa el `reference_code` como clave única del recaudo. |
| 16 | El boleto de la demo no es oficial | El aviso aparece en pantalla, en el PDF del boleto y en la observación de la factura. |
| 17 | No se ejecutan pruebas contra servicios reales sin `RUN_LIVE_TESTS=1` y no se despliega sin aprobación | Lo exige el brief. |
| 18 | Rango de numeración: `filter[document]=21`. Se usa `FACTUS_NUMBERING_RANGE_ID` si es válido; si no, el único rango activo, vigente y con consecutivos disponibles. Si hay varios, se exige elegirlo | Lo indica la colección del equipo. Nunca se usan IDs copiados de ejemplos. |
| 19 | Factus Pay: el cuerpo incluye `"expiration": "900"`. La misma referencia nunca cambia de monto ni se regenera en un reintento | Lo indica la colección del equipo. |
| 19b | Fechas de Factus Pay: llegan como `dd-mm-YYYY hh:mm:ss AM/PM` en hora de Colombia (UTC-5), y la API las devuelve en UTC | Observado en el Sandbox real el 2026-11-04 (`docs/samples/factus_pay_get_collection.sanitized.json`). |
| 19c | Verificación en vivo (2026-11-04) | Factus v2: login OAuth, rango 389 (SETP) elegido automáticamente y factura SETP990033377 validada con CUFE (100.000 + IVA 19 % = 119.000), con descargas PDF/XML funcionando. Factus Pay: token generado con `/auth`, recaudo creado (201) y consultado (200). **PENDIENTE:** pagar un QR con el simulador para verificar `paid` de punta a punta. |
| 20 | **CONFLICTO sin resolver:** las monedas de referencia | El brief pide USD/EUR/COP/GBP/JPY y la colección usa USD/EUR/GBP/MXN/CAD. Por ahora se mantiene el brief. |
| 21 | **CONFLICTO sin resolver:** el formato del contrato | La sección "Gateway" de la colección usa camelCase (`eventId`, `payable{currency,amount}`), mientras la API usa snake_case como en el brief. La colección lo marca como "contrato aún no implementado". |
| 22 | `GET /orders/{id}` consulta Factus Pay como máximo cada 3 s por orden | La colección propone que ese GET solo lea la BD. El brief pide sondeo de respaldo. **PENDIENTE** decidir si se mueve a un worker. |
