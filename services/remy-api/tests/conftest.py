"""Test fixtures: provide valid required secrets before app import.

The app validates config fail-closed at import time, so valid secrets must be
present in the environment before ``remy_api.main`` is imported. These are
throwaway test values, never real credentials.
"""

import os

from cryptography.fernet import Fernet

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production-use-only")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
