"""Password hashing and compact HS256 JWT primitives."""

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass

_PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt, expected = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(iterations))
        return hmac.compare_digest(actual, _unb64(expected))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True, slots=True)
class TokenPayload:
    subject: uuid.UUID
    expires_at: int


def create_access_token(*, subject: uuid.UUID, secret: str, lifetime_seconds: int) -> str:
    now = int(time.time())
    header = _json_b64({"alg": "HS256", "typ": "JWT"})
    payload = _json_b64({"sub": str(subject), "iat": now, "exp": now + lifetime_seconds, "jti": str(uuid.uuid4())})
    signature = _b64(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_access_token(token: str, *, secret: str) -> TokenPayload | None:
    try:
        header, payload, signature = token.split(".")
        expected = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        claims = json.loads(_unb64(payload))
        if claims.get("exp", 0) <= int(time.time()):
            return None
        return TokenPayload(subject=uuid.UUID(claims["sub"]), expires_at=int(claims["exp"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _json_b64(value: dict) -> str:
    return _b64(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
