"""TypeSafe Jev client: typed decisions with calibrated probabilities.

Jev answers questions with a fixed answer space instead of generating text:
https://docs.typesafe.ai. Remy uses its ``choice`` primitive to pick among a
store's search results (``PRODUCT_RANKER=jev``). Failures raise
:class:`JevError`; callers decide how to degrade (PRD §9.1 — never silent).
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
    input_tokens: int = 0


async def choice(
    state: str,
    instructions: str,
    criteria: dict[str, str | None],
    *,
    client: httpx.AsyncClient | None = None,
) -> ChoiceAnswer:
    """Ask Jev to pick one of ``criteria`` (option key → description) for ``state``."""
    settings = get_settings()
    if not settings.typesafe_api_key:
        raise JevError("TYPESAFE_API_KEY is not set.")
    body = {
        "model": settings.jev_model,
        "state": state,
        "questions": {"pick": {"type": "choice", "instructions": instructions, "criteria": criteria}},
    }
    headers = {"Authorization": f"Bearer {settings.typesafe_api_key}"}
    owns = client is None
    client = client or httpx.AsyncClient(base_url=settings.typesafe_base_url, timeout=settings.jev_timeout)
    try:
        resp = await client.post(_ENDPOINT, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        answer = data["answers"]["pick"]
        return ChoiceAnswer(
            choice=answer["choice"],
            confidence=answer["confidence"],
            probabilities=answer["probabilities"],
            input_tokens=(data.get("usage") or {}).get("input_tokens", 0),
        )
    except httpx.HTTPStatusError as exc:
        raise JevError(f"Jev returned HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise JevError(f"Could not reach Jev: {exc}") from exc
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise JevError(f"Unexpected Jev response: {exc}") from exc
    finally:
        if owns:
            await client.aclose()
