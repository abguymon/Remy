"""Encryption utilities for sensitive data at rest"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from remy_api.config import get_settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet | None:
    """Get Fernet instance from configured encryption key, or None if not configured."""
    settings = get_settings()
    if not settings.encryption_key:
        return None
    return Fernet(settings.encryption_key.encode())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value. Returns plaintext unchanged if no encryption key is configured."""
    fernet = _get_fernet()
    if fernet is None:
        return plaintext
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_value(stored: str) -> str:
    """
    Decrypt a stored value. If decryption fails (e.g. value was stored as plaintext
    before encryption was enabled), returns the original value.
    """
    fernet = _get_fernet()
    if fernet is None:
        return stored
    try:
        return fernet.decrypt(stored.encode()).decode()
    except (InvalidToken, Exception):
        # Value was likely stored as plaintext before encryption was enabled
        logger.warning("Failed to decrypt value, treating as plaintext (will be re-encrypted on next write)")
        return stored
