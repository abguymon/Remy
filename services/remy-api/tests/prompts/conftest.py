"""Fixtures + gating for prompt evals.

Prompt evals (``@pytest.mark.prompts``) hit a real LLM and are skipped cleanly
when no provider API key is present, so the keyless unit suite always runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from remy_api.llm import LLMClient
from remy_api.providers.settings import get_provider_settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# The key each provider needs. Evals run only when the key for the *configured*
# model's provider is present, so a mismatched key (e.g. only OPENAI set while the
# default model is Anthropic) skips cleanly instead of failing with an auth error.
# Run against an available provider with: LLM_MODEL=openai/gpt-4o pytest -m prompts
_PROVIDER_KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    "openai": ("OPENAI_API_KEY",),
    "azure": ("AZURE_API_KEY",),
    "gemini": ("GEMINI_API_KEY",),
    "google": ("GEMINI_API_KEY",),
    "ollama": (),  # local endpoint; no key required
}


def _model_provider() -> str:
    model = get_provider_settings().llm_model
    return (model.split("/", 1)[0] if "/" in model else model).lower()


def llm_key_present() -> bool:
    provider = _model_provider()
    keys = _PROVIDER_KEYS.get(provider)
    if keys is None:
        # Unknown provider: run only if *some* key is set (best effort).
        return any(os.environ.get(k) for group in _PROVIDER_KEYS.values() for k in group)
    if not keys:  # e.g. ollama
        return True
    return any(os.environ.get(k) for k in keys)


def load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def pytest_collection_modifyitems(config, items):
    """Auto-skip every ``prompts``-marked test when no LLM key is configured."""
    if llm_key_present():
        return
    skip = pytest.mark.skip(reason="no LLM API key present; set e.g. ANTHROPIC_API_KEY to run prompt evals")
    for item in items:
        if "prompts" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def llm_client() -> LLMClient:
    return LLMClient()
