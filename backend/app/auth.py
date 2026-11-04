"""Login con correo y contraseña.

- Contraseñas con scrypt (biblioteca estándar) y sal aleatoria por usuario.
- Sesión en cookie httpOnly firmada con HMAC-SHA256 (SESSION_SECRET). SameSite=Lax
  evita que otros sitios envíen la cookie en POSTs (CSRF); Secure en producción.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, Request, Response

from app.config import get_settings

COOKIE = "tm_session"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
_dev_secret = secrets.token_bytes(32)


def _secret() -> bytes:
    s = get_settings()
    if s.session_secret is not None:
        return s.session_secret.get_secret_value().encode()
    if s.app_env == "production":
        # Respaldo si SESSION_SECRET aún no existe en el panel: se deriva de DATABASE_URL, que
        # incluye la contraseña de la base (secreta y estable entre reinicios).
        if "@" not in s.database_url:
            raise RuntimeError("Falta SESSION_SECRET en producción")
        return hashlib.sha256(b"tm-session|" + s.database_url.encode()).digest()
    return _dev_secret  # desarrollo: las sesiones se invalidan al reiniciar


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(dk.hex(), dk_hex)


# Hash fijo para gastar el mismo tiempo cuando el correo no existe (no revela si existe).
DUMMY_HASH = hash_password(secrets.token_hex(8))


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: str) -> str:
    exp = int(time.time()) + get_settings().session_days * 86400
    body = _b64(json.dumps({"uid": user_id, "exp": exp}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(body))
    except ValueError:
        return None
    if int(data.get("exp", 0)) < time.time():
        return None
    return str(data.get("uid")) or None


def set_session(response: Response, user_id: str) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE, make_token(user_id), max_age=s.session_days * 86400, httponly=True,
        secure=s.app_env == "production", samesite="lax", path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def session_user_id(request: Request) -> str:
    uid = read_token(request.cookies.get(COOKIE))
    if uid is None:
        raise HTTPException(401, "Inicia sesión para continuar")
    return uid
