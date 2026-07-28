"""Symmetric encryption for secrets stored at rest (Google refresh tokens)."""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class EncryptionNotConfiguredError(RuntimeError):
    pass


@lru_cache
def _fernet() -> Fernet:
    key = settings.token_encryption_key.strip()
    if not key:
        raise EncryptionNotConfiguredError(
            "TOKEN_ENCRYPTION_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise EncryptionNotConfiguredError(
            "TOKEN_ENCRYPTION_KEY is not a valid Fernet key (32 url-safe base64 bytes)."
        ) from exc


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionNotConfiguredError(
            "Stored token could not be decrypted — TOKEN_ENCRYPTION_KEY has likely "
            "changed since it was written. Reconnect the Google Calendar integration."
        ) from exc
