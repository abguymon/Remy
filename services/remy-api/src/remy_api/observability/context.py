"""Task-local user and plan attribution for LLM observations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class ObservationContext:
    user_id: str | None = None
    session_id: str | None = None


_context: ContextVar[ObservationContext | None] = ContextVar("remy_observation_context", default=None)


def current_observation_context() -> ObservationContext:
    return _context.get() or ObservationContext()


@contextmanager
def bind_observation_context(
    *, user_id: str | None = None, session_id: str | None = None
) -> Iterator[ObservationContext]:
    """Temporarily add attribution without discarding inherited values."""
    current = current_observation_context()
    value = ObservationContext(
        user_id=user_id if user_id is not None else current.user_id,
        session_id=session_id if session_id is not None else current.session_id,
    )
    token = _context.set(value)
    try:
        yield value
    finally:
        _context.reset(token)
