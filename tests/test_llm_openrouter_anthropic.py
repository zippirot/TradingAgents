"""OpenRouter must keep Anthropic structured output on a host that accepts it."""
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from tradingagents.llm_clients.capabilities import get_capabilities
from tradingagents.llm_clients.openai_client import OpenAIClient


class Answer(BaseModel):
    text: str


def _llm(monkeypatch, model):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    return OpenAIClient(model, provider="openrouter").get_llm()


def test_openrouter_anthropic_requests_pin_provider_order(monkeypatch):
    llm = _llm(monkeypatch, "anthropic/claude-opus-5.5")
    assert llm.extra_body == {"provider": {"order": ["Anthropic"], "allow_fallbacks": False}}


def test_openrouter_other_models_are_not_pinned(monkeypatch):
    assert _llm(monkeypatch, "openai/gpt-6.1-terra-pro").extra_body is None


def test_openrouter_anthropic_omits_forced_tool_choice_when_flagged(monkeypatch):
    seen = {}
    monkeypatch.setattr(ChatOpenAI, "with_structured_output",
                        lambda self, schema, *, method=None, **kwargs: seen.update(method=method, **kwargs))
    _llm(monkeypatch, "anthropic/claude-opus-5.5").with_structured_output(Answer)
    assert seen == {"method": "function_calling", "tool_choice": None}


def test_other_openrouter_models_keep_forced_tool_choice():
    assert get_capabilities("openai/gpt-6.1-terra-pro").supports_tool_choice
