"""Small, failure-isolated Langfuse v4 adapter around physical LLM calls."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

from langfuse import Langfuse, propagate_attributes

from remy_api.config import get_settings
from remy_api.observability.context import current_observation_context

logger = logging.getLogger(__name__)
_NOT_CALLED = object()


@lru_cache
def _client() -> Langfuse | None:
    settings = get_settings()
    if not settings.langfuse_enabled:
        return None
    try:
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
            environment=settings.langfuse_environment,
        )
    except Exception:  # noqa: BLE001 - observability must never stop Remy
        logger.warning("Langfuse initialization failed; tracing is disabled", exc_info=True)
        return None


def _value(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _usage_details(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    prompt = _value(usage, "prompt_tokens") or _value(usage, "input_tokens")
    completion = _value(usage, "completion_tokens") or _value(usage, "output_tokens")
    total = _value(usage, "total_tokens")
    details: dict[str, int] = {}
    if prompt is not None:
        details["input"] = int(prompt)
    if completion is not None:
        details["output"] = int(completion)
    if total is not None:
        details["total"] = int(total)
    elif prompt is not None and completion is not None:
        details["total"] = int(prompt) + int(completion)
    return details


def _cost_details(response: Any) -> dict[str, float] | None:
    hidden = getattr(response, "_hidden_params", None)
    cost = hidden.get("response_cost") if isinstance(hidden, dict) else None
    if cost is None:
        cost = getattr(response, "response_cost", None)
    try:
        return {"total": float(cost)} if cost is not None else None
    except (TypeError, ValueError):
        return None


def _output(response: Any) -> Any:
    try:
        return response.choices[0].message.content
    except (AttributeError, IndexError):
        return None


def _langfuse_model(model: str) -> str:
    """Use the provider model id so Langfuse's price matcher recognizes it."""
    return model.split("/", 1)[1] if "/" in model else model


async def observe_generation(
    provider_call: Callable[[], Awaitable[Any]],
    *,
    name: str,
    version: int,
    model: str,
    model_parameters: dict[str, Any],
    input: Any,
    tags: list[str] | None = None,
) -> Any:
    """Run one LLM call and emit a generation with user/session attribution."""
    client = _client()
    if client is None:
        return await provider_call()

    settings = get_settings()
    context = current_observation_context()
    metadata = {
        "prompt_id": name,
        "prompt_version": version,
        "content_capture": settings.langfuse_capture_content,
    }

    response: Any = _NOT_CALLED
    provider_started = False
    try:
        with propagate_attributes(
            user_id=context.user_id,
            session_id=context.session_id,
            tags=["remy", *(tags or [])],
            metadata=metadata,
        ):
            with client.start_as_current_observation(
                as_type="generation",
                name=name,
                model=_langfuse_model(model),
                model_parameters=model_parameters,
                input=input if settings.langfuse_capture_content else None,
                version=str(version),
            ) as generation:
                provider_started = True
                response = await provider_call()
                update: dict[str, Any] = {
                    "usage_details": _usage_details(response),
                    "output": _output(response) if settings.langfuse_capture_content else None,
                }
                cost = _cost_details(response)
                if cost is not None:
                    update["cost_details"] = cost
                generation.update(**update)
                return response
    except Exception:
        if provider_started:
            # Never duplicate a billable provider call. If tracing failed while
            # recording an otherwise successful response, return that response;
            # if the provider itself failed, preserve its original exception.
            if response is not _NOT_CALLED:
                logger.warning("Langfuse failed after %s completed", name, exc_info=True)
                return response
            raise
        logger.warning("Langfuse tracing failed for %s; continuing without tracing", name, exc_info=True)
        return await provider_call()


def shutdown_langfuse() -> None:
    """Flush queued observations during FastAPI shutdown."""
    client = _client()
    if client is not None:
        try:
            client.shutdown()
        except Exception:  # noqa: BLE001
            logger.warning("Langfuse shutdown failed", exc_info=True)
