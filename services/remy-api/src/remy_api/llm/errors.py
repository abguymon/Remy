"""Typed exception hierarchy for the LLM client.

Per PRD §9: LLM calls never swallow failures or return ``None``. Every failure
path raises one of these so the API layer can surface it (scoped retry, degraded
marker), rather than presenting an empty result as success.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base class for all LLM client failures."""


class LLMConfigError(LLMError):
    """Misconfiguration (missing model, bad provider settings)."""


class LLMAPIError(LLMError):
    """The provider call itself failed (transport, auth, rate limit, 5xx)."""


class LLMEmptyResponseError(LLMError):
    """The provider returned no usable content."""


class LLMValidationError(LLMError):
    """Model output failed Pydantic validation even after the single retry."""

    def __init__(self, message: str, *, raw_output: str | None = None) -> None:
        super().__init__(message)
        self.raw_output = raw_output
