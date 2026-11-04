"""Rotación MANUAL del token de Factus Pay.

ADVERTENCIA: un login nuevo revoca el token anterior. Cualquier servidor que use el token
viejo dejará de cobrar hasta que actualices FACTUS_PAY_TOKEN y lo reinicies.

Uso (desde backend/):
    .venv/Scripts/python scripts/rotate_pay_token.py

Lee FACTUS_PAY_BASE_URL, FACTUS_PAY_EMAIL, FACTUS_PAY_PASSWORD (y FACTUS_PAY_ACCESS_KEY,
opcional)
del entorno o de .env. El token nuevo se escribe en .env; nunca se imprime completo.
"""

import os
import re
import sys
from pathlib import Path

import httpx

ENV = Path(".env")


def load_env() -> dict[str, str]:
    vals = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$", line)
            if m:
                v = m.group(2)
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]  # valores entre comillas son literales (como en dotenv)
                vals[m.group(1)] = v
    return {**vals, **{k: v for k, v in os.environ.items() if k.startswith("FACTUS_PAY_")}}


def main() -> int:
    env = load_env()
    missing = [k for k in ("FACTUS_PAY_BASE_URL", "FACTUS_PAY_EMAIL", "FACTUS_PAY_PASSWORD")
               if not env.get(k)]
    if missing:
        print("Faltan variables:", ", ".join(missing))
        return 1
    print("Esto REVOCA el token actual de Factus Pay.")
    if input('Escribe "ROTAR" para continuar: ').strip() != "ROTAR":
        print("Cancelado.")
        return 1
    headers = {"Accept": "application/json"}
    if env.get("FACTUS_PAY_ACCESS_KEY"):
        headers["X-Factus-Access-Key"] = env["FACTUS_PAY_ACCESS_KEY"]
    r = httpx.post(
        env["FACTUS_PAY_BASE_URL"].rstrip("/") + "/auth",
        json={"email": env["FACTUS_PAY_EMAIL"], "password": env["FACTUS_PAY_PASSWORD"]},
        headers=headers,
        timeout=20,
    )
    if r.status_code != 200:
        print(f"Error HTTP {r.status_code}")
        return 1
    token = r.json().get("token") or r.json().get("data", {}).get("token")
    if not token:
        print("La respuesta no trae 'token'.")
        return 1
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    if re.search(r"^FACTUS_PAY_TOKEN=.*$", text, flags=re.M):
        text = re.sub(r"^FACTUS_PAY_TOKEN=.*$", f"FACTUS_PAY_TOKEN={token}", text, flags=re.M)
    else:
        text += f"\nFACTUS_PAY_TOKEN={token}\n"
    ENV.write_text(text, encoding="utf-8")
    print(f"Token actualizado en .env (termina en …{token[-4:]}). Reinicia el backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
