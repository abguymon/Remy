"""Provider-agnostic LLM client (LiteLLM).

One entrypoint — :meth:`LLMClient.structured` — sends a rendered prompt, asks
the provider for JSON-schema / tool-call structured output, validates it against
a Pydantic model, and retries exactly once (feeding the validation error back)
before raising. It never returns ``None`` and never strips markdown fences as a
parsing strategy (PRD §7.1, §9).

Provider is a config swap: LiteLLM routes off the model string
(``anthropic/...``, ``openai/...``, ``ollama/...``) and reads the matching
provider API key from its standard env name natively.
"""

from __future__ import annotations

import json
import logging
from typing import TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from remy_api.llm.errors import (
    LLMAPIError,
    LLMEmptyResponseError,
    LLMValidationError,
)
from remy_api.llm.prompt import RenderedPrompt
from remy_api.providers.settings import ProviderSettings, get_provider_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Don't let LiteLLM mutate/drop our messages or add extra provider params.
litellm.drop_params = True


class LLMClient:
    """Thin wrapper around ``litellm.acompletion`` for structured output."""

    def __init__(self, settings: ProviderSettings | None = None) -> None:
        self._settings = settings or get_provider_settings()

    @property
    def model(self) -> str:
        return self._settings.llm_model

    async def structured(self, prompt: RenderedPrompt, schema: type[T]) -> T:
        """Run ``prompt`` and return an instance of ``schema``.

        Raises:
            LLMAPIError: the provider call failed.
            LLMEmptyResponseError: the provider returned no content.
            LLMValidationError: output failed validation twice (initial + retry).
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]

        raw = await self._complete(messages, prompt.temperature, schema)
        try:
            return self._parse(raw, schema)
        except (json.JSONDecodeError, ValidationError) as first_err:
            # Bind to an outer name: Python clears the `except` variable after the block.
            error = first_err
            logger.warning(
                "LLM output for prompt %s v%d failed validation; retrying once: %s",
                prompt.prompt_id,
                prompt.version,
                error,
            )

        # Single retry: show the model its own bad output and the error.
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your previous response could not be parsed into the required "
                    f"schema. Error:\n{self._format_error(error)}\n\n"
                    "Return ONLY corrected JSON that satisfies the schema. "
                    "No prose, no markdown fences."
                ),
            }
        )
        raw_retry = await self._complete(messages, prompt.temperature, schema)
        try:
            return self._parse(raw_retry, schema)
        except (json.JSONDecodeError, ValidationError) as second_err:
            raise LLMValidationError(
                f"LLM output for prompt {prompt.prompt_id} v{prompt.version} "
                f"failed validation after retry: {self._format_error(second_err)}",
                raw_output=raw_retry,
            ) from second_err

    # -- internals ---------------------------------------------------------

    async def _complete(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        schema: type[BaseModel],
    ) -> str:
        kwargs: dict = {
            "model": self._settings.llm_model,
            "messages": messages,
            "temperature": temperature,
            "timeout": self._settings.llm_timeout,
            "num_retries": self._settings.llm_max_retries,
        }
        # Ask for native structured output where the provider/model supports it.
        # Where it doesn't, the prompt's own JSON contract carries the load and
        # validation + the retry loop catch drift.
        try:
            if litellm.supports_response_schema(model=self._settings.llm_model):
                kwargs["response_format"] = schema
        except Exception:  # noqa: BLE001 - capability probe must never break the call
            pass

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:  # noqa: BLE001 - normalize any provider/transport error
            raise LLMAPIError(f"LLM provider call failed ({self._settings.llm_model}): {exc}") from exc

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise LLMEmptyResponseError("LLM response had no choices/content") from exc

        if not content or not content.strip():
            raise LLMEmptyResponseError("LLM returned empty content")
        return content

    @staticmethod
    def _parse(raw: str, schema: type[T]) -> T:
        data = json.loads(raw)
        return schema.model_validate(data)

    @staticmethod
    def _format_error(err: Exception) -> str:
        if isinstance(err, ValidationError):
            return json.dumps(err.errors(include_url=False, include_input=False))
        return str(err)


_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Process-wide default client (lazily constructed)."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
