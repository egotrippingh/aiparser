"""Пароли и непрозрачные сессионные токены."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1,
                            maxmem=64 * 1024 * 1024)
    return f"scrypt$32768$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        name, n, r, p, salt, expected = encoded.split("$")
        if name != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, OverflowError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()
