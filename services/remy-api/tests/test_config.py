"""Fail-closed configuration tests (PRD §6, §9.5)."""

import pytest
from cryptography.fernet import Fernet

from remy_api.config import ConfigError, Settings, get_settings

VALID_FERNET = Fernet.generate_key().decode()


def _clear_secret_env(monkeypatch):
    # Ensure a stray .env / process env does not leak real values in.
    for key in ("JWT_SECRET", "ENCRYPTION_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_missing_jwt_secret_aborts(monkeypatch):
    _clear_secret_env(monkeypatch)
    monkeypatch.setenv("ENCRYPTION_KEY", VALID_FERNET)
    get_settings.cache_clear()
    with pytest.raises(ConfigError, match="JWT_SECRET"):
        Settings(_env_file=None)


def test_placeholder_jwt_secret_aborts(monkeypatch):
    _clear_secret_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "your_jwt_secret_here")
    monkeypatch.setenv("ENCRYPTION_KEY", VALID_FERNET)
    with pytest.raises(ConfigError, match="placeholder"):
        Settings(_env_file=None)


def test_missing_encryption_key_aborts(monkeypatch):
    _clear_secret_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "a-perfectly-real-looking-secret-value-1234")
    with pytest.raises(ConfigError, match="ENCRYPTION_KEY"):
        Settings(_env_file=None)


def test_invalid_fernet_key_aborts(monkeypatch):
    _clear_secret_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "a-perfectly-real-looking-secret-value-1234")
    monkeypatch.setenv("ENCRYPTION_KEY", "not-a-valid-fernet-key")
    with pytest.raises(ConfigError, match="Fernet"):
        Settings(_env_file=None)


def test_valid_secrets_load(monkeypatch):
    _clear_secret_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "a-perfectly-real-looking-secret-value-1234")
    monkeypatch.setenv("ENCRYPTION_KEY", VALID_FERNET)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.jwt_secret
    assert settings.encryption_key == VALID_FERNET
    get_settings.cache_clear()
