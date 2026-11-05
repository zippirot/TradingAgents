from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage

from tests.test_price_implied_valuation import synthetic_state
from tradingagents.agents import context


def source_state(monkeypatch):
    state = synthetic_state(monkeypatch)
    state["evidence_acquisition"] = {
        "schema_version": 1, "status": "ready", "ticker": "DOCN", "as_of": state["trade_date"],
        "asset_type": "stock", "selected_analysts": ["market", "social", "news", "fundamentals"],
        "source_checks": [{"code": "source_integrity", "status": "pass", "message": "Source lineage checked"}],
    }
    state["canonical_financial_context"] = "UNBOUNDED_CONTEXT" * 10000
    state["messages"] = []
    return state


def test_shared_brief_retains_price_fact_definitions_and_bound(monkeypatch):
    state = source_state(monkeypatch)
    text = context.build_shared_source_brief(state)
    assert "20 USD" in text and "2026-10-19" in text
    assert state["price_observation"]["source_id"] in text
    assert "Common Shares Outstanding" in text and "2026-06-30" in text
    assert "source_ids" in text and "period_start" in text and "basis" in text
    assert len(text) <= context.SHARED_SOURCE_BRIEF_MAX_CHARS
    state["shared_source_brief"] = text
    prompt_context = context.get_instrument_context_from_state(state)
    assert text in prompt_context and "UNBOUNDED_CONTEXT" not in prompt_context
    assert "not final evidence-gate approval" in text


def test_integrity_failure_keeps_price_but_no_financial_endorsement(monkeypatch):
    state = source_state(monkeypatch)
    state["evidence_acquisition"]["source_checks"][0]["status"] = "fail"
    state["evidence_acquisition"]["source_checks"][0]["message"] = "Conflicting source lineage"
    text = context.build_shared_source_brief(state)
    assert "Conflicting source lineage" in text
    assert "20 USD" in text and "Common Shares Outstanding" not in text
    state["price_observation"] = {"status": "unavailable", "reason": "No completed source bar"}
    assert "No completed source bar" in context.build_shared_source_brief(state)


@pytest.mark.parametrize("role", ["market", "news", "fundamentals", "social"])
def test_all_actual_analyst_factories_consume_identical_brief(monkeypatch, role):
    from tradingagents.agents.analysts import (
        fundamentals_analyst,
        market_analyst,
        news_analyst,
        sentiment_analyst,
    )
    state = source_state(monkeypatch)
    brief = context.build_shared_source_brief(state)
    state["shared_source_brief"] = brief
    captured = []
    def turn(prompt, llm, tools, messages):
        captured.extend(prompt.format_messages(messages=messages))
        return AIMessage(content="Research"), "Research"
    modules = {"market": market_analyst, "news": news_analyst, "fundamentals": fundamentals_analyst}
    if role != "social":
        mod = modules[role]
        monkeypatch.setattr(mod, "take_turn", turn)
        getattr(mod, "create_" + role + "_analyst")(object())(deepcopy(state))
    else:
        monkeypatch.setattr(sentiment_analyst, "bind_structured", lambda *args: None)
        monkeypatch.setattr(sentiment_analyst.get_news, "func", lambda *args: "News unavailable")
        monkeypatch.setattr(sentiment_analyst, "jev_screen", lambda *args: None)
        monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages", lambda *a, **k: "Social claim: 250 users; unauthenticated account")
        monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts", lambda *a, **k: "Unavailable")
        monkeypatch.setattr(sentiment_analyst, "subreddits_for", lambda *args: ())
        def invoke(structured, llm, messages, *args):
            captured.extend(messages)
            return "Research"
        monkeypatch.setattr(sentiment_analyst, "invoke_structured_or_freetext", invoke)
        sentiment_analyst.create_sentiment_analyst(object())(deepcopy(state))
    system = str(captured[0].content)
    assert brief in system and "UNBOUNDED_CONTEXT" not in system
    if role == "news":
        assert "issuer disclosure" in system and "independent news coverage" in system
    if role == "social":
        assert "metric, period, unit and definition" in system
        assert "does not authenticate" in system

def test_retained_source_tools_do_not_refetch_or_change_vintage(monkeypatch):
    import json

    from tests.test_evidence_gate import complete_evidence
    from tradingagents.agents import tools
    from tradingagents.agents.evidence_validation import assess_financial_package

    facts, docs = complete_evidence()
    initial = {"company_of_interest": "DOCN", "trade_date": "2026-10-19"}
    state = {**initial, **assess_financial_package(initial, facts, docs, source_only=True)}
    state["issuer_identity"] = {"cik": facts.cik}
    state["evidence_acquisition"] = {"schema_version": 1, "status": "ready", "ticker": "DOCN",
        "as_of": "2026-10-19", "raw_financial_evidence": facts.model_dump(mode="json"),
        "source_checks": state.pop("source_checks")}
    def forbidden(*a, **k):
        pytest.fail("Acquired source must not be fetched again")
    monkeypatch.setattr(tools, "build_financial_evidence", forbidden)
    monkeypatch.setattr(tools, "build_filing_evidence", forbidden)
    financial = tools.get_financial_evidence.func("DOCN", "2026-10-19", "2026-10-19", state)
    filing = tools.get_filing_evidence.func("DOCN", "2026-10-19", "2026-10-19", state)
    assert json.loads(financial)["cik"] == facts.cik
    assert json.loads(filing) == docs.model_dump(mode="json")
    for tool in (tools.get_financial_evidence, tools.get_filing_evidence):
        result = tool.func("DOCN", "2026-10-18", "2026-10-19", state)
        assert "retained" in result.lower() and "cutoff" in result.lower()
        missing = {**state, "evidence_acquisition": {**state["evidence_acquisition"], "status": "unavailable", "reason": "SEC unavailable"}}
        assert "SEC unavailable" in tool.func("DOCN", "2026-10-19", "2026-10-19", missing)

def test_source_vintage_and_brief_survive_evidence_export(monkeypatch, tmp_path):
    import json

    from tradingagents.agents.evidence_validation import review_terminal_state
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.reporting import evidence_snapshot

    state = source_state(monkeypatch)
    state["shared_source_brief"] = context.build_shared_source_brief(state)
    state.update(review_terminal_state({"status": "insufficient", "checks": []}))
    state.update(dict.fromkeys(("market_report", "news_report", "sentiment_report", "fundamentals_report"), ""))
    app = object.__new__(TradingAgentsGraph)
    app.config = {"results_dir": str(tmp_path)}
    app.run_settings = lambda: {}
    app._log_state(state["trade_date"], state)
    saved = json.loads(next(tmp_path.rglob("full_states_log_*.json")).read_text())
    snapshot = evidence_snapshot(state)
    for key in ("shared_source_brief", "evidence_acquisition"):
        assert saved[key] == snapshot[key] == state[key]

def test_bounded_brief_keeps_guidance_base_growth_shares_and_filing_reference(monkeypatch):
    from tests.test_price_implied_guidance_ranges import source_state as source_guidance_state
    from tradingagents.dataflows.disclosure_discovery import discover_disclosures
    from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact

    state = source_guidance_state(monkeypatch)
    package = EvidencePackage.model_validate(state["financial_evidence"])
    document, source = package.sources
    extra_sources = tuple(source.model_copy(update={"source_id": f"other-{i}", "url": "https://example.test/" + "x"*180 + str(i)}) for i in range(20))
    extra_facts = tuple(FinancialFact(fact_id=f"extra-{i}", metric=f"Other metric {i}", value=i+1,
        unit="USD", cik=package.cik, period_end="2026-09-30", as_of=package.as_of,
        source_ids=(s.source_id,), locator="synthetic") for i,s in enumerate(extra_sources))
    package = package.model_copy(update={"sources": (source, *extra_sources, document), "facts": (*package.facts, *extra_facts)})
    state["financial_evidence"] = package.model_dump(mode="json")
    state["disclosure_evidence"]["extraction"] = discover_disclosures(state["disclosure_evidence"]["packages"]).model_dump(mode="json")
    state["evidence_acquisition"] = {"status": "ready", "ticker": "DOCN", "as_of": state["trade_date"],
        "source_checks": [{"code": "source_integrity", "status": "pass"}]}
    brief = context.build_shared_source_brief(state)
    assert '"locator":"block-46"' in brief  # Full-year revenue base for growth floor.
    assert '"locator":"block-4"' in brief   # Growth floor and its horizon.
    assert '"locator":"block-44"' in brief  # Conditional guided share range.
    assert document.url in brief
    assert len(brief) <= context.SHARED_SOURCE_BRIEF_MAX_CHARS
