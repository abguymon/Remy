"""Prompt-id dispatch adapter (T3 ⇄ T4 seam).

The recipes module depends on the minimal ``StructuredLLM`` protocol —
``structured(prompt_id, input, schema)`` — so it never imports the prompt
library directly. This adapter satisfies that protocol by looking up the prompt
module for ``prompt_id``, building its typed input model from the dict,
rendering, and delegating to the real :class:`LLMClient`.

Register additional prompt ids here only when a consumer needs the id-based
indirection; planner code should import prompt modules and call
``client.structured(module.render(...), schema)`` directly.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from remy_api.llm.client import get_llm_client
from remy_api.prompts import recipe_extraction

T = TypeVar("T", bound=BaseModel)

_RENDERERS = {
    recipe_extraction.PROMPT_ID: (recipe_extraction.RecipeExtractionInput, recipe_extraction.render),
}


class PromptIdLLM:
    """``StructuredLLM``-protocol adapter over the shared LLM client."""

    async def structured(self, prompt_id: str, input: dict, schema: type[T]) -> T:  # noqa: A002
        try:
            input_model, render = _RENDERERS[prompt_id]
        except KeyError:
            raise KeyError(f"No prompt registered for id {prompt_id!r}") from None
        return await get_llm_client().structured(render(input_model(**input)), schema)


_adapter: PromptIdLLM | None = None


def get_prompt_id_llm() -> PromptIdLLM:
    """Shared adapter instance for StructuredLLM consumers (recipes fallback)."""
    global _adapter
    if _adapter is None:
        _adapter = PromptIdLLM()
    return _adapter
