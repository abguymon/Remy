"""Keyless unit tests for the LLM client: parsing, validation, retry, errors.

``litellm.acompletion`` is stubbed so these run with no network/key.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import remy_api.llm.client as client_mod
from remy_api.llm import (
    LLMAPIError,
    LLMClient,
    LLMEmptyResponseError,
    LLMValidationError,
    RenderedPrompt,
)


class _Schema(BaseModel):
    name: str
    count: int


def _prompt() -> RenderedPrompt:
    return RenderedPrompt(prompt_id="t", version=1, system="sys", user="usr")


def _fake_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _stub_acompletion(monkeypatch, responses: list):
    """Queue string/exception responses returned by successive acompletion calls."""
    calls = {"n": 0}

    async def fake(**kwargs):
        i = calls["n"]
        calls["n"] += 1
        item = responses[min(i, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return _fake_response(item)

    monkeypatch.setattr(client_mod.litellm, "acompletion", fake)
    monkeypatch.setattr(client_mod.litellm, "supports_response_schema", lambda **k: False)
    return calls


async def test_structured_happy_path(monkeypatch):
    _stub_acompletion(monkeypatch, ['{"name": "onion", "count": 3}'])
    out = await LLMClient().structured(_prompt(), _Schema)
    assert out.name == "onion" and out.count == 3


async def test_structured_retries_once_then_succeeds(monkeypatch):
    calls = _stub_acompletion(monkeypatch, ["not json at all", '{"name": "x", "count": 1}'])
    out = await LLMClient().structured(_prompt(), _Schema)
    assert out.count == 1
    assert calls["n"] == 2  # exactly one retry


async def test_structured_raises_after_second_failure(monkeypatch):
    calls = _stub_acompletion(monkeypatch, ["nope", '{"name": "x"}'])  # 2nd missing required field
    with pytest.raises(LLMValidationError) as exc:
        await LLMClient().structured(_prompt(), _Schema)
    assert calls["n"] == 2
    assert exc.value.raw_output == '{"name": "x"}'


async def test_provider_error_is_typed(monkeypatch):
    _stub_acompletion(monkeypatch, [RuntimeError("boom")])
    with pytest.raises(LLMAPIError):
        await LLMClient().structured(_prompt(), _Schema)


async def test_empty_content_raises(monkeypatch):
    _stub_acompletion(monkeypatch, ["   "])
    with pytest.raises(LLMEmptyResponseError):
        await LLMClient().structured(_prompt(), _Schema)


async def test_never_returns_none(monkeypatch):
    _stub_acompletion(monkeypatch, ['{"name": "y", "count": 2}'])
    out = await LLMClient().structured(_prompt(), _Schema)
    assert out is not None
