"""Provider configuration for the LLM client and search providers (T4).

This module owns the small slice of settings that the LLM and web-search
layers need. It reads directly from the environment so it stays decoupled
from ``remy_api.config`` (which T1 owns and rewrites). When that module
grows first-class fields (``llm_provider``, ``llm_model``, ``search_provider``,
``search_api_key``), callers may pass a compatible settings object into the
factories instead of relying on this default.
"""

from remy_api.providers.settings import ProviderSettings, get_provider_settings

__all__ = ["ProviderSettings", "get_provider_settings"]
