"""The rendered-prompt contract shared by the prompt library and the LLM client.

Lives in ``llm`` (not ``prompts``) so the client can consume it without
importing the prompt library, keeping the dependency direction one-way:
``prompts`` -> ``llm``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedPrompt:
    """A fully-rendered prompt ready to send to the LLM.

    Attributes:
        prompt_id: Stable identifier (e.g. ``"meal_extraction"``).
        version: Template version; bump when wording/schema changes so evals
            can track which version they were tuned against.
        system: System-role instructions (rules, role, output contract).
        user: User-role content (the actual task inputs).
        temperature: Sampling temperature; extraction/ranking prompts use 0.
    """

    prompt_id: str
    version: int
    system: str
    user: str
    temperature: float = 0.0
