"""Encryption-at-rest helpers (PRD §6, §9.5).

Sensitive columns (Kroger OAuth tokens, and any future secret) are encrypted
with Fernet using the validated ``ENCRYPTION_KEY`` from config. Two surfaces are
exposed:

* :func:`encrypt` / :func:`decrypt` — explicit functions for ad-hoc use and for
  testing that plaintext never hits disk.
* :class:`EncryptedString` — a SQLAlchemy ``TypeDecorator`` so a model column is
  transparently encrypted on write and decrypted on read. The ciphertext (a
  URL-safe base64 Fernet token) is what actually lands in the database file.

The Fernet instance is built lazily from :func:`get_settings` so importing this
module never forces config validation before the app is ready.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from remy_api.config import get_settings


class DecryptionError(RuntimeError):
    """Raised when stored ciphertext cannot be decrypted (wrong/rotated key)."""


@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string, returning a Fernet token (URL-safe base64 str)."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token produced by :func:`encrypt`.

    Raises :class:`DecryptionError` rather than returning ``None`` so a bad key
    or corrupt value surfaces loudly (PRD §9.1 — no silent failures).
    """
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError, TypeError) as exc:
        raise DecryptionError("Failed to decrypt stored value (key mismatch or corruption).") from exc


def reset_cache() -> None:
    """Drop the cached Fernet instance. Used by tests that swap the key."""
    _fernet.cache_clear()


class EncryptedString(TypeDecorator):
    """A ``String`` column whose value is Fernet-encrypted at rest.

    Encryption happens in the ORM layer, so the raw DB file contains only
    ciphertext. Portable across SQLite/Postgres (underlying type is ``String``).
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:  # noqa: ANN001
        if value is None:
            return None
        return encrypt(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:  # noqa: ANN001
        if value is None:
            return None
        return decrypt(value)
