"""TypeSafe Jev client: typed decisions with calibrated probabilities.

Jev answers questions with a fixed answer space instead of generating text:
https://docs.typesafe.ai. Remy uses ``choice`` to pick among a store's search
results and batches of yes/no ``noul`` questions to filter recipe-search
results and saved-recipe matches — each enabled per step via ``JEV_STEPS``.
Failures raise :class:`JevError`; callers fall back to the LLM prompt for that
step (PRD §9.1 — never silent).
"""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel, Field, ValidationError

from remy_api.config import get_settings

logger = logging.getLogger("remy.decisions.jev")

_ENDPOINT = "/v1/systemone"


class JevError(Exception):
    """Jev was unavailable, misconfigured, or returned an unusable answer."""


class ChoiceAnswer(BaseModel):
    choice: str
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[str, float]


def enabled(step: str) -> bool:
    """Whether ``step`` ("products" | "listicles" | "saved_recipes") uses Jev."""
    return step in get_settings().jev_step_set


async def _ask(state: str, questions: dict[str, dict], client: httpx.AsyncClient | None) -> dict[str, dict]:
    settings = get_settings()
    if not settings.typesafe_api_key:
        raise JevError("TYPESAFE_API_KEY is not set.")
    body = {"model": settings.jev_model, "state": state, "questions": questions}
    headers = {"Authorization": f"Bearer {settings.typesafe_api_key}"}
    owns = client is None
    client = client or httpx.AsyncClient(base_url=settings.typesafe_base_url, timeout=settings.jev_timeout)
    try:
        resp = await client.post(_ENDPOINT, json=body, headers=headers)
        resp.raise_for_status()
        answers = resp.json()["answers"]
        if not isinstance(answers, dict) or set(answers) != set(questions):
            raise ValueError("answers do not match the questions asked")
        return answers
    except httpx.HTTPStatusError as exc:
        raise JevError(f"Jev returned HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise JevError(f"Could not reach Jev: {exc}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise JevError(f"Unexpected Jev response: {exc}") from exc
    finally:
        if owns:
            await client.aclose()


async def choice(
    state: str,
    instructions: str,
    criteria: dict[str, str | None],
    *,
    client: httpx.AsyncClient | None = None,
) -> ChoiceAnswer:
    """Ask Jev to pick one of ``criteria`` (option key → description) for ``state``."""
    answers = await _ask(
        state, {"pick": {"type": "choice", "instructions": instructions, "criteria": criteria}}, client
    )
    try:
        a = answers["pick"]
        return ChoiceAnswer(choice=a["choice"], confidence=a["confidence"], probabilities=a["probabilities"])
    except (KeyError, TypeError, ValidationError) as exc:
        raise JevError(f"Unexpected Jev response: {exc}") from exc


async def yes_no(
    state: str,
    questions: dict[str, str],
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, float]:
    """Ask several yes/no questions about ``state`` in one call; key → P(yes)."""
    answers = await _ask(state, {k: {"type": "noul", "instructions": q} for k, q in questions.items()}, client)
    try:
        return {k: float(answers[k]["noul"]) for k in questions}
    except (KeyError, TypeError, ValueError) as exc:
        raise JevError(f"Unexpected Jev response: {exc}") from exc
