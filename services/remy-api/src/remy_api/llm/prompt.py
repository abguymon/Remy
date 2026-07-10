"""The rendered-prompt contract shared by the prompt library and the LLM client.

Lives in ``llm`` (not ``prompts``) so the client can consume it without
importing the prompt library, keeping the dependency direction one-way:
``prompts`` -> ``llm``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImagePart:
    """One inline image attached to a (multimodal) prompt's user turn.

    Provider-agnostic: the LLM client turns this into LiteLLM's standard
    ``image_url`` content-part with a ``data:`` URI, which routes correctly for
    ``openai/*`` and ``anthropic/*`` models. ``data`` is raw base64 (no
    ``data:`` prefix); ``media_type`` is an image MIME type (e.g. ``image/jpeg``).
    """

    media_type: str
    data: str

    def data_uri(self) -> str:
        return f"data:{self.media_type};base64,{self.data}"


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
        images: Optional inline images for a multimodal user turn. Empty for
            text-only prompts (the common case), which the client sends
            unchanged as a plain string content.
    """

    prompt_id: str
    version: int
    system: str
    user: str
    temperature: float = 0.0
    images: tuple[ImagePart, ...] = field(default_factory=tuple)
