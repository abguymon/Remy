"""Encryption-at-rest tests (PRD §6, §9.5).

Kroger tokens must be unreadable in the raw DB file, but transparently
decrypted through the ORM.
"""

from datetime import UTC, datetime, timedelta

import pytest

from remy_api.crypto import DecryptionError, EncryptedString, decrypt, encrypt
from remy_api.db import get_session_factory
from remy_api.models import KrogerToken
from remy_api.user_service import create_user

SECRET_ACCESS = "kroger-access-token-PLAINTEXT-SENTINEL-abc123"
SECRET_REFRESH = "kroger-refresh-token-PLAINTEXT-SENTINEL-xyz789"


def test_encrypt_decrypt_round_trip():
    ciphertext = encrypt(SECRET_ACCESS)
    assert ciphertext != SECRET_ACCESS
    assert decrypt(ciphertext) == SECRET_ACCESS


def test_decrypt_rejects_garbage():
    with pytest.raises(DecryptionError):
        decrypt("not-a-valid-fernet-token")


def test_type_decorator_is_cacheable():
    # cache_ok must be True or SQLAlchemy warns and disables statement caching.
    assert EncryptedString.cache_ok is True


async def test_kroger_token_encrypted_at_rest(client, db_path):
    """Write a token row, then read the raw DB file and assert plaintext absent."""
    factory = get_session_factory()
    async with factory() as session:
        user = await create_user(session, "cryptouser", "pw12345678")
        session.add(
            KrogerToken(
                user_id=user.id,
                access_token=SECRET_ACCESS,
                refresh_token=SECRET_REFRESH,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await session.commit()

    # Raw bytes on disk must not contain the plaintext secrets.
    raw = open(db_path, "rb").read()
    assert SECRET_ACCESS.encode() not in raw
    assert SECRET_REFRESH.encode() not in raw

    # ORM read transparently decrypts.
    async with factory() as session:
        from sqlalchemy import select

        row = await session.execute(select(KrogerToken))
        token = row.scalar_one()
        assert token.access_token == SECRET_ACCESS
        assert token.refresh_token == SECRET_REFRESH
