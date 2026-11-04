# --- 1) Build del frontend (React + Vite) -----------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Sin VITE_API_BASE_URL el build de producción usa rutas relativas (/api/v1/...).
ARG VITE_PAYMENT_MODE=qr
ENV VITE_PAYMENT_MODE=${VITE_PAYMENT_MODE}
RUN npx vite build

# --- 2) Backend (FastAPI) que también sirve el build ------------------------------
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    STATIC_DIR=/app/static
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /web/dist ./static
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 10000
# Render define $PORT. --proxy-headers: Render termina TLS delante del contenedor.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
