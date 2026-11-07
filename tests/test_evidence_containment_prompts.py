"""Prompt delivery contracts; actual model compliance requires the live proof."""

from importlib import import_module
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("role", ["fundamentals", "market", "news"])
def test_tool_analysts_receive_evidence_limits(monkeypatch, role):
    module = import_module(f"tradingagents.agents.analysts.{role}_analyst")
    captured = []

    def turn(prompt, llm, tools, messages):
        captured.extend(prompt.format_messages(messages=messages))
        return SimpleNamespace(content="research"), "research"

    monkeypatch.setattr(module, "take_turn", turn)
    getattr(module, f"create_{role}_analyst")(object())(
        {
            "company_of_interest": "DOCN",
            "trade_date": "2026-10-19",
            "asset_type": "stock",
            "messages": [],
        }
    )
    text = "\n".join(m.content for m in captured)
    assert "unavailable to these tools" in text
    assert "Do not infer a financing transaction" in text
    assert "subjective scenario weights" in text
    assert "VWMA does not establish" in text
    assert "contract-specific market prices" in text


def test_sentiment_scopes_absence_and_headlines():
    from tradingagents.agents.analysts.sentiment_analyst import _build_system_message

    text = _build_system_message(
        ticker="DOCN",
        start_date="2026-10-12",
        end_date="2026-10-19",
        news_block="Question headline?",
        stocktwits_block="unavailable",
        reddit_block="No matches",
    )
    assert "queried feed and date window" in text
    assert "question headline is not an asserted event" in text


@pytest.mark.parametrize("role", ["bull", "bear", "research", "portfolio"])
def test_downstream_roles_cannot_promote_unsupported_claims(monkeypatch, role):
    kind = "researchers" if role in ("bull", "bear") else "managers"
    suffix = "researcher" if kind == "researchers" else "manager"
    module = import_module(f"tradingagents.agents.{kind}.{role}_{suffix}")
    captured = []
    llm = SimpleNamespace(
        invoke=lambda prompt: captured.append(prompt) or SimpleNamespace(content="Hold")
    )
    if kind == "managers":
        monkeypatch.setattr(module, "bind_structured", lambda *a: None)
        monkeypatch.setattr(module, "invoke_structured", lambda *a: None)
    debate = {
        "history": "Unverified conversion hypothesis",
        "count": 1,
        "bull_history": "",
        "bear_history": "",
        "current_response": "",
        "aggressive_history": "",
        "conservative_history": "",
        "neutral_history": "",
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
    }
    state = {
        "company_of_interest": "DOCN",
        "investment_debate_state": debate,
        "risk_debate_state": debate,
        "investment_plan": "Unbridged target $96",
        "trader_investment_plan": "",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "Missing statement",
    }
    getattr(module, f"create_{role}_{suffix}")(llm)(state)
    text = str(captured[0])
    assert "Debate repetition is not independent verification" in text
    assert "Do not infer a financing transaction" in text
    assert "Without actual portfolio" in text
    assert "Omit numeric price targets" in text
