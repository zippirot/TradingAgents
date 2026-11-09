"""OpenRouter model selection: prompts are labeled by mode (#1000); required
prompts exit cleanly on cancel; the output-language prompt defaults to English
on cancel; and the OpenRouter list is newest-first."""

from unittest import mock

import pytest

from cli import prompts, selections
from tradingagents.llm_clients.factory import build_llm_kwargs
from tradingagents.llm_clients.openai_client import OpenAIClient


def _asks(value):
    return mock.Mock(ask=mock.Mock(return_value=value))


@pytest.mark.unit
class TestOpenRouterPromptLabel:
    @pytest.mark.parametrize("mode,label", [("quick", "Quick-Thinking"), ("deep", "Deep-Thinking")])
    def test_prompt_states_the_mode(self, mode, label):
        captured = {}

        def fake_select(message, **kwargs):
            captured["message"] = message
            return _asks("openrouter/some-model")

        with mock.patch.object(prompts, "_fetch_openrouter_models",
                               return_value=[("Some Model", "openrouter/some-model")]), \
             mock.patch.object(prompts.questionary, "select", side_effect=fake_select):
            out = prompts.select_openrouter_model(mode)

        assert label in captured["message"]
        assert out == "openrouter/some-model"


@pytest.mark.unit
class TestOpenRouterLatestFirst:
    def test_models_sorted_newest_first(self):
        payload = {"data": [
            {"id": "old/model", "name": "Old", "created": 1000},
            {"id": "new/model", "name": "New", "created": 3000},
            {"id": "mid/model", "name": "Mid", "created": 2000},
        ]}
        resp = mock.Mock()
        resp.json.return_value = payload
        resp.raise_for_status = mock.Mock()
        with mock.patch("requests.get", return_value=resp):
            out = prompts._fetch_openrouter_models()
        assert [mid for _, mid in out] == ["new/model", "mid/model", "old/model"]


@pytest.mark.unit
class TestMainstreamFilter:
    def test_dropdown_prefers_mainstream_over_niche(self):
        # _fetch returns newest-first; the shortlist should drop niche namespaces.
        models = [
            ("Fusion", "openrouter/fusion"),
            ("Niche", "nex-agi/nex-n2-pro:free"),
            ("Claude", "anthropic/claude-x"),
            ("GPT", "openai/gpt-x"),
        ]
        captured = {}

        def fake_select(message, **kwargs):
            captured["values"] = [c.value for c in kwargs["choices"]]
            return _asks("anthropic/claude-x")

        with mock.patch.object(prompts, "_fetch_openrouter_models", return_value=models), \
             mock.patch.object(prompts.questionary, "select", side_effect=fake_select):
            prompts.select_openrouter_model("quick")

        assert "anthropic/claude-x" in captured["values"]
        assert "openai/gpt-x" in captured["values"]
        assert "openrouter/fusion" not in captured["values"]
        assert "nex-agi/nex-n2-pro:free" not in captured["values"]
        assert "custom" in captured["values"]  # escape hatch preserved

    def test_falls_back_to_all_when_no_mainstream(self):
        models = [("Niche", "nex-agi/x"), ("Other", "thedrummer/y")]
        captured = {}

        def fake_select(message, **kwargs):
            captured["values"] = [c.value for c in kwargs["choices"]]
            return _asks("nex-agi/x")

        with mock.patch.object(prompts, "_fetch_openrouter_models", return_value=models), \
             mock.patch.object(prompts.questionary, "select", side_effect=fake_select):
            prompts.select_openrouter_model("deep")

        assert "nex-agi/x" in captured["values"]  # fallback keeps the list usable


@pytest.mark.unit
class TestCancelExitsCleanly:
    def test_dropdown_cancel_exits(self):
        with mock.patch.object(prompts, "_fetch_openrouter_models", return_value=[]), \
             mock.patch.object(prompts.questionary, "select", return_value=_asks(None)), \
             pytest.raises(SystemExit):
            prompts.select_openrouter_model("quick")

    def test_custom_id_cancel_exits(self):
        with mock.patch.object(prompts, "_fetch_openrouter_models", return_value=[]), \
             mock.patch.object(prompts.questionary, "select", return_value=_asks("custom")), \
             mock.patch.object(prompts.questionary, "text", return_value=_asks(None)), \
             pytest.raises(SystemExit):
            prompts.select_openrouter_model("deep")

    def test_prompt_custom_model_id_cancel_exits(self):
        with mock.patch.object(prompts.questionary, "text", return_value=_asks(None)), \
             pytest.raises(SystemExit):
            prompts._prompt_custom_model_id()


@pytest.mark.unit
class TestLanguageDefaultsToEnglish:
    def test_select_cancel_defaults_english(self):
        with mock.patch.object(prompts.questionary, "select", return_value=_asks(None)):
            assert prompts.ask_output_language() == "English"

    def test_custom_language_cancel_defaults_english(self):
        with mock.patch.object(prompts.questionary, "select", return_value=_asks("custom")), \
             mock.patch.object(prompts.questionary, "text", return_value=_asks(None)):
            assert prompts.ask_output_language() == "English"


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["quick", "deep"])
@pytest.mark.parametrize("live", [[], [("New", "openai/newer-model"),
                                      ("Opus duplicate", "anthropic/claude-opus-5.5")]])
def test_requested_models_stay_visible_once_without_changing_default(mode, live):
    captured = {}
    saved = "openai/newer-model"

    def fake_select(message, **kwargs):
        captured.update(kwargs)
        return _asks("openai/gpt-6.1-sol")

    with mock.patch.object(prompts, "_fetch_openrouter_models", return_value=live), \
         mock.patch.object(prompts.questionary, "select", side_effect=fake_select):
        assert prompts.select_openrouter_model(mode, default=saved) == "openai/gpt-6.1-sol"

    values = [c.value for c in captured["choices"]]
    pinned = ["anthropic/claude-opus-5.5", "deepseek/deepseek-v4-pro", "openai/gpt-6.1-sol"]
    assert values[:3] == pinned
    assert all(values.count(mid) == 1 for mid in pinned)
    assert "custom" in values
    if live:
        assert captured["default"] == saved


@pytest.mark.unit
def test_openrouter_forwards_reasoning_effort_in_extra_body(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    kwargs = build_llm_kwargs({"llm_provider": "openrouter", "openai_reasoning_effort": "high"})
    llm = OpenAIClient("anthropic/claude-sonnet-4.5", provider="openrouter", **kwargs).get_llm()

    payload = llm._get_request_payload("hello")
    assert payload["extra_body"] == {"reasoning": {"effort": "high"}}
    assert "reasoning_effort" not in payload


@pytest.mark.unit
def test_openrouter_without_configured_effort_uses_ordinary_payload(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    kwargs = build_llm_kwargs({"llm_provider": "openrouter", "openai_reasoning_effort": None})
    llm = OpenAIClient("openai/gpt-5.4", provider="openrouter", **kwargs).get_llm()

    payload = llm._get_request_payload("hello")
    assert "extra_body" not in payload
    assert "reasoning_effort" not in payload


@pytest.mark.unit
def test_dropped_effort_is_warned_not_silent(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with caplog.at_level("WARNING"):
        llm = OpenAIClient("gpt-4.1", provider="openai", reasoning_effort="low").get_llm()

    assert llm.reasoning_effort is None
    assert "reasoning effort 'low' not forwarded to provider 'openai'" in caplog.text


@pytest.mark.unit
def test_other_provider_dropped_effort_is_warned_not_silent(caplog):
    with caplog.at_level("WARNING"):
        kwargs = build_llm_kwargs({"llm_provider": "google", "openai_reasoning_effort": "high"})

    assert "reasoning_effort" not in kwargs
    assert "reasoning effort 'high' not forwarded to provider 'google'" in caplog.text


@pytest.mark.unit
def test_openrouter_cli_shows_step8_reasoning_effort_prompt(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_OPENAI_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(selections.updates, "enabled", lambda: False)
    monkeypatch.setattr(selections, "get_ticker", lambda: "AAPL")
    monkeypatch.setattr(selections, "get_analysis_date", lambda: "2026-11-07")
    monkeypatch.setattr(selections, "ask_output_language", lambda _default: "English")
    monkeypatch.setattr(selections, "select_ground_truth_audit", lambda flags: False)
    monkeypatch.setattr(selections, "select_analysts", lambda *_: [])
    monkeypatch.setattr(selections, "select_research_depth", lambda *_: 1)
    monkeypatch.setattr(selections, "select_llm_provider", lambda *_: ("openrouter", None))
    monkeypatch.setattr(selections, "select_shallow_thinking_agent", lambda *_: "anthropic/claude-haiku")
    monkeypatch.setattr(selections, "select_deep_thinking_agent", lambda *_: "anthropic/claude-sonnet")
    monkeypatch.setattr(selections, "ensure_api_key", lambda *_: None)
    monkeypatch.setattr(selections, "ensure_signed_in", lambda *_: None)
    effort_prompt = mock.Mock(return_value="medium")
    monkeypatch.setattr(selections, "ask_openai_reasoning_effort", effort_prompt)

    result = selections._prompt_selections({}, {})

    effort_prompt.assert_called_once_with()
    assert result["openai_reasoning_effort"] == "medium"
