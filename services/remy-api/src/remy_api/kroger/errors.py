"""Typed error hierarchy for the Kroger integration (PRD §9.1).

Every Kroger call either succeeds or raises one of these — nothing returns
``None`` on failure, so a broken integration can never masquerade as "no
results". The FastAPI layer maps these to the uniform error envelope via
:func:`register_kroger_error_handler`; the planner (T5) catches them to produce
scoped, visible degraded-result markers.
"""

from __future__ import annotations


class KrogerError(Exception):
    """Base class for all Kroger integration failures."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class KrogerNotConnectedError(KrogerError):
    """The user has no valid Kroger OAuth token (never connected or refresh failed).

    Surfaced to the UI/agent as "Kroger not connected — visit Settings" (§7.4).
    """


class KrogerAuthError(KrogerError):
    """An OAuth/token exchange or refresh against Kroger failed (upstream auth)."""


class KrogerRateLimitError(KrogerError):
    """Kroger returned HTTP 429. Carries the ``Retry-After`` seconds if provided."""

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class KrogerAPIError(KrogerError):
    """A non-2xx response from a Kroger data endpoint (products/locations/cart)."""
