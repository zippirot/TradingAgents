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


def test_openrouter_anthropic_uses_a_json_schema_response_format(monkeypatch):
    # The pinned Anthropic host rejects a forced tool choice and an unforced tool
    # lets the model answer in prose; a JSON-schema response format is enforced.
    seen = {}
    monkeypatch.setattr(ChatOpenAI, "with_structured_output",
                        lambda self, schema, *, method=None, **kwargs: seen.update(method=method, **kwargs))
    _llm(monkeypatch, "anthropic/claude-opus-5.5").with_structured_output(Answer)
    assert seen == {"method": "json_schema"}


def test_openrouter_anthropic_request_carries_the_schema_and_no_tool(monkeypatch):
    import json

    import httpx2 as httpx

    sent = {}

    def send(client, request, *args, **kwargs):
        sent.update(json.loads(request.content))
        body = {"id": "x", "object": "chat.completion", "created": 0, "model": "anthropic/claude-opus-5.5",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": '{"text": "ok"}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        return httpx.Response(200, json=body, request=request)

    monkeypatch.setattr(httpx.Client, "send", send)
    result = _llm(monkeypatch, "anthropic/claude-opus-5.5").with_structured_output(
        Answer, include_raw=True).invoke("hi")
    assert result["parsed"] == Answer(text="ok")
    assert sent["response_format"]["type"] == "json_schema"
    assert "tools" not in sent and "tool_choice" not in sent
    assert sent["provider"] == {"order": ["Anthropic"], "allow_fallbacks": False}


def test_other_openrouter_models_keep_forced_tool_choice():
    assert get_capabilities("openai/gpt-6.1-terra-pro").supports_tool_choice
