from __future__ import annotations

import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 100_000
_SALT_BYTES = 16


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(_SALT_BYTES)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return password_hash.hex(), salt.hex()


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    computed_hash, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(computed_hash, expected_hash)


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)
