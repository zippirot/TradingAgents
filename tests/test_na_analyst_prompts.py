"""Retained Na analyst instructions as rendered to models; N2.2 was not adopted."""

from types import SimpleNamespace

from langchain_core.messages import AIMessage

from tradingagents.agents.analysts import fundamentals_analyst, market_analyst


def _tool_prompt(monkeypatch, module):
    captured = []

    def capture(prompt, llm, tools, messages):
        captured.append(prompt.format_messages(messages=messages)[0].content)
        return AIMessage(content="Done"), "Done"

    monkeypatch.setattr(module, "take_turn", capture)
    getattr(module, f"create_{module.__name__.split('.')[-1]}")(object())({
        "trade_date": "2026-10-19", "company_of_interest": "DOCN",
        "messages": [],
    })
    return captured[0]


def test_fundamentals_multiple_rationale_requires_same_basis_reference(monkeypatch):
    prompt = _tool_prompt(monkeypatch, fundamentals_analyst)
    assert "multiple_rationale" in prompt
    assert "same multiple basis and period convention" in prompt
    assert "no same-basis reference available" in prompt


def test_sentiment_prompt_distinguishes_uncheckable(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment
    from tradingagents.agents.schemas import SentimentBand, SentimentReport

    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: "posts")
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: "posts")
    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: "headlines", raising=False)
    captured = []
    decision = SentimentReport(overall_band=SentimentBand.NEUTRAL, overall_score=5,
                               confidence="low", narrative="n")
    structured = SimpleNamespace(invoke=lambda prompt: captured.append(prompt) or decision)
    llm = SimpleNamespace(with_structured_output=lambda *a, **k: structured)
    sentiment.create_sentiment_analyst(llm)({
        "company_of_interest": "DOCN", "trade_date": "2026-10-19",
        "asset_type": "stock", "messages": [],
    })
    prompt = "\n".join(m.content for m in captured[0])
    assert "not checkable with my inputs" in prompt
    assert "contradicted" in prompt
    assert "past price level" in prompt


def test_market_prior_trading_claims_cite_price_band_table(monkeypatch):
    prompt = _tool_prompt(monkeypatch, market_analyst)
    assert "Prior closes by price band" in prompt
    assert "prior trading did or did not occur" in prompt
