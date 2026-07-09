"""LLM-native web-search provider (alternative backend).

Uses the model provider's *own* web-search tool via LiteLLM, then asks the model
to return the hits as JSON we validate. This is the alternative to Brave.

Provider support is intentionally narrow and explicit: only providers whose
models expose a first-party web-search tool through LiteLLM are supported —
currently **Anthropic** (``anthropic/*`` via the ``web_search`` tool) and
**OpenAI** (``openai/*`` via ``web_search_options``). For any other model this
provider raises :class:`SearchConfigError` at call time rather than silently
degrading. If you are not on one of those providers, use ``SEARCH_PROVIDER=brave``.
"""

from __future__ import annotations

import json
import logging

import litellm

from remy_api.search.base import (
    SearchConfigError,
    SearchProviderError,
    SearchResult,
    SearchTimeoutError,
    _ResultsEnvelope,
)

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a web-search tool. Use your web search capability to find real, "
    "currently-live pages for the user's query. Return ONLY a JSON object of the "
    'form {"results": [{"title": str, "url": str, "snippet": str}]} with the '
    "actual result URLs you found. No prose, no markdown fences. Do not invent URLs."
)


class LLMSearchProvider:
    """Web search delegated to the LLM provider's native search tool."""

    def __init__(self, model: str, timeout: float = 30.0) -> None:
        self._model = model
        self._timeout = timeout
        self._provider = self._detect_provider(model)

    @staticmethod
    def _detect_provider(model: str) -> str:
        head = model.split("/", 1)[0].lower() if "/" in model else model.lower()
        if head in ("anthropic", "claude"):
            return "anthropic"
        if head in ("openai", "azure"):
            return "openai"
        raise SearchConfigError(
            f"LLM-native search is only supported for Anthropic and OpenAI models; "
            f"got '{model}'. Set SEARCH_PROVIDER=brave instead."
        )

    def _build_kwargs(self, prompt: str) -> dict:
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "timeout": self._timeout,
        }
        if self._provider == "anthropic":
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]
        else:  # openai
            kwargs["web_search_options"] = {}
        return kwargs

    async def search(
        self,
        query: str,
        site: str | None = None,
        max_results: int = 10,
    ) -> list[SearchResult]:
        q = f"{query} site:{site.strip()}" if site else query
        prompt = f"Find up to {max_results} web pages for: {q}"

        try:
            response = await litellm.acompletion(**self._build_kwargs(prompt))
        except litellm.Timeout as exc:  # type: ignore[attr-defined]
            raise SearchTimeoutError(f"LLM search timed out after {self._timeout}s") from exc
        except Exception as exc:  # noqa: BLE001 - normalize provider/transport errors
            raise SearchProviderError(f"LLM search call failed: {exc}") from exc

        try:
            content = response.choices[0].message.content or ""
        except (AttributeError, IndexError) as exc:
            raise SearchProviderError("LLM search returned no content") from exc

        try:
            envelope = _ResultsEnvelope.model_validate(json.loads(content))
        except (ValueError, TypeError) as exc:
            raise SearchProviderError(f"LLM search returned unparseable results: {exc}") from exc

        return envelope.results[:max_results]
