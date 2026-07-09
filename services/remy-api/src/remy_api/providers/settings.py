"""Provider settings shim.

LLM/search configuration lives on :class:`remy_api.config.Settings` (the
single source of truth). This module survives as the import point the
``llm``/``search`` factories use; ``ProviderSettings`` is a structural alias —
any object exposing the provider attributes works at call sites.
"""

from __future__ import annotations

from remy_api.config import Settings, get_settings

ProviderSettings = Settings


def get_provider_settings() -> Settings:
    """Return the app settings (providers read their config from it)."""
    return get_settings()
