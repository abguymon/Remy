"""Keyless tests for Langfuse attribution, privacy, usage, and failure isolation."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import remy_api.observability.langfuse as langfuse_mod
from remy_api.observability import bind_observation_context, current_observation_context


class _Generation:
    def __init__(self) -> None:
        self.update_kwargs: dict = {}

    def update(self, **kwargs):
        self.update_kwargs = kwargs


class _Client:
    def __init__(self) -> None:
        self.start_kwargs: dict = {}
        self.generation = _Generation()

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.start_kwargs = kwargs
        yield self.generation


def _settings(*, capture: bool = False):
    return SimpleNamespace(
        langfuse_enabled=True,
        langfuse_capture_content=capture,
    )


def _response():
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="private output"))],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        _hidden_params={"response_cost": 0.0012},
    )


async def test_disabled_observability_is_a_noop(monkeypatch):
    calls = 0

    async def provider():
        nonlocal calls
        calls += 1
        return _response()

    monkeypatch.setattr(langfuse_mod, "_client", lambda: None)
    result = await langfuse_mod.observe_generation(
        provider,
        name="meal_extraction",
        version=2,
        model="openai/gpt-4o-mini",
        model_parameters={},
        input=[{"role": "user", "content": "secret"}],
    )
    assert result is not None
    assert calls == 1


async def test_generation_tracks_user_session_usage_and_cost_without_content(monkeypatch):
    client = _Client()
    propagated: dict = {}

    @contextmanager
    def propagate(**kwargs):
        propagated.update(kwargs)
        yield

    monkeypatch.setattr(langfuse_mod, "_client", lambda: client)
    monkeypatch.setattr(langfuse_mod, "get_settings", lambda: _settings())
    monkeypatch.setattr(langfuse_mod, "propagate_attributes", propagate)

    with bind_observation_context(user_id="user-1", session_id="plan-1"):
        await langfuse_mod.observe_generation(
            _response_async,
            name="product_ranking",
            version=3,
            model="openai/gpt-4o-mini",
            model_parameters={"temperature": 0},
            input=[{"role": "user", "content": "secret"}],
            tags=["structured-generation"],
        )

    assert propagated["user_id"] == "user-1"
    assert propagated["session_id"] == "plan-1"
    assert propagated["tags"] == ["remy", "structured-generation"]
    assert propagated["metadata"]["prompt_version"] == 3
    assert client.start_kwargs["model"] == "gpt-4o-mini"
    assert client.start_kwargs["input"] is None
    assert client.generation.update_kwargs == {
        "usage_details": {"input": 20, "output": 10, "total": 30},
        "output": None,
        "cost_details": {"total": pytest.approx(0.0012)},
    }


async def test_content_capture_requires_explicit_opt_in(monkeypatch):
    client = _Client()
    monkeypatch.setattr(langfuse_mod, "_client", lambda: client)
    monkeypatch.setattr(langfuse_mod, "get_settings", lambda: _settings(capture=True))
    monkeypatch.setattr(langfuse_mod, "propagate_attributes", _passthrough)
    raw_input = [{"role": "user", "content": "show me"}]

    await langfuse_mod.observe_generation(
        _response_async,
        name="meal_extraction",
        version=1,
        model="openai/gpt-4o-mini",
        model_parameters={},
        input=raw_input,
    )

    assert client.start_kwargs["input"] == raw_input
    assert client.generation.update_kwargs["output"] == "private output"


async def test_post_call_telemetry_failure_does_not_repeat_provider(monkeypatch):
    class BrokenGeneration(_Generation):
        def update(self, **kwargs):
            raise RuntimeError("telemetry broke")

    client = _Client()
    client.generation = BrokenGeneration()
    calls = 0

    async def provider():
        nonlocal calls
        calls += 1
        return _response()

    monkeypatch.setattr(langfuse_mod, "_client", lambda: client)
    monkeypatch.setattr(langfuse_mod, "get_settings", lambda: _settings())
    monkeypatch.setattr(langfuse_mod, "propagate_attributes", _passthrough)

    result = await langfuse_mod.observe_generation(
        provider,
        name="meal_extraction",
        version=1,
        model="openai/gpt-4o-mini",
        model_parameters={},
        input=[],
    )
    assert result.choices[0].message.content == "private output"
    assert calls == 1


def test_nested_context_preserves_user_and_overrides_session():
    with bind_observation_context(user_id="user-1"):
        with bind_observation_context(session_id="plan-1"):
            context = current_observation_context()
            assert context.user_id == "user-1"
            assert context.session_id == "plan-1"
        assert current_observation_context().session_id is None


async def _response_async():
    return _response()


@contextmanager
def _passthrough(**_kwargs):
    yield
