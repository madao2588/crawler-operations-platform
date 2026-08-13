from __future__ import annotations

import hashlib
import hmac
import secrets

_LEGACY_PBKDF2_ITERATIONS = 100_000
_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16
_ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    if salt_hex:
        iterations, salt = _decode_salt(salt_hex)
        encoded_salt = salt_hex
    else:
        iterations = _PBKDF2_ITERATIONS
        salt = secrets.token_bytes(_SALT_BYTES)
        encoded_salt = f"{_ALGORITHM}${iterations}${salt.hex()}"
    password_hash = _derive_password_hash(password, salt, iterations=iterations)
    return password_hash.hex(), encoded_salt


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    try:
        iterations, salt = _decode_salt(salt_hex)
    except ValueError:
        return False
    computed_hash = _derive_password_hash(password, salt, iterations=iterations)
    return hmac.compare_digest(computed_hash.hex(), expected_hash)


def password_hash_needs_upgrade(salt_value: str) -> bool:
    try:
        iterations, _ = _decode_salt(salt_value)
    except ValueError:
        return True
    return not salt_value.startswith(f"{_ALGORITHM}$") or iterations < _PBKDF2_ITERATIONS


def _derive_password_hash(password: str, salt: bytes, *, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )


def _decode_salt(value: str) -> tuple[int, bytes]:
    if value.startswith(f"{_ALGORITHM}$"):
        algorithm, raw_iterations, raw_salt = value.split("$", 2)
        if algorithm != _ALGORITHM:
            raise ValueError("Unsupported password hash algorithm")
        iterations = int(raw_iterations)
        if iterations <= 0:
            raise ValueError("Invalid password hash cost")
        return iterations, bytes.fromhex(raw_salt)
    return _LEGACY_PBKDF2_ITERATIONS, bytes.fromhex(value)


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
