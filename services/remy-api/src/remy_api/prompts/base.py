"""Shared helpers for the prompt library.

Every prompt module exposes: versioned template text, typed Pydantic input/output
models, and a ``render(input) -> RenderedPrompt`` function. All output is
structured (validated by the LLM client), so prompts never ask for prose,
numbers-only, or fenced blobs (PRD §7.1, §9.3).
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from remy_api.llm.prompt import RenderedPrompt

__all__ = ["RenderedPrompt", "json_block", "indexed"]


def json_block(data: object) -> str:
    """Compact, stable JSON for embedding inputs in a user message."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def indexed(items: list[BaseModel] | list[dict] | list[str], key: str = "index") -> list[dict]:
    """Attach a 0-based ``index`` to each item for identity-safe round-tripping.

    Fixes the legacy "match output back by string equality" bug (Appendix A.2/A.3/A.4):
    inputs go in indexed, outputs reference the index, never the (drift-prone) text.
    """
    out: list[dict] = []
    for i, item in enumerate(items):
        if isinstance(item, BaseModel):
            row = item.model_dump()
        elif isinstance(item, dict):
            row = dict(item)
        else:
            row = {"value": item}
        out.append({key: i, **row})
    return out
