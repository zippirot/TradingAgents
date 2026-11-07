"""Focused integration proofs for retained document evidence and final debate questions."""
import json
from datetime import date
from types import SimpleNamespace

from tests.test_document_search_state import package as fixture_package, state as corpus_state
from tradingagents.agents.document_access import run_document_search
from tradingagents.agents.evidence_validation import assess_financial_package
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.dataflows.financial_evidence import EvidencePackage


def test_search_only_quote_enters_canonical_sources_but_paraphrase_does_not():
    fixture = fixture_package()
    document = fixture.documents[0].model_copy(update={"content_hash": "a" * 64})
    fixture = fixture.model_copy(update={"documents": (document,)})
    run = corpus_state(fixture)
    run["document_search_trace"] = run_document_search(
        run, "revenue", role="fundamentals", call_id="search-1"
    )["document_search_trace"]
    passage = run["document_search_trace"]["fundamentals:search-1"]["passages"][0]
    claim = {
        "source_id": passage["source_id"], "locator": passage["locator"],
        "metric": "revenue", "value": "50", "unit": "million",
        "period": "Third Quarter 2026", "kind": "historical",
        "quote": passage["text"],
    }
    run["fundamentals_report"] = "```disclosures\n" + json.dumps([claim]) + "\n```"
    evidence = EvidencePackage(cik=run["issuer_identity"]["cik"], as_of=date(2026, 9, 1))
    accepted = assess_financial_package(run, evidence, disclosures=None)
    assert any(
        source["source_id"] == passage["source_id"]
        for source in accepted["financial_evidence"]["sources"]
    )
    assert accepted["disclosure_evidence"]["extraction"]["claims"]
    assert passage["text"] in accepted["canonical_financial_context"]
    assert accepted["final_rating"] == "REVIEW"  # no core statements, unrelated to quote validity

    claim["quote"] = "The company earned fifty million dollars during the quarter."
    run["fundamentals_report"] = "```disclosures\n" + json.dumps([claim]) + "\n```"
    rejected = assess_financial_package(run, evidence, disclosures=None)
    assert not rejected["disclosure_evidence"]["extraction"]["claims"]
    assert any("exact retrieved source span" in reason for reason in
               rejected["disclosure_evidence"]["extraction"]["rejected"])


class QuestionLLM:
    def __init__(self, role):
        self.role = role
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=(
            f"{self.role} view\n```document_questions\n"
            f'["lease commitments"]\n```'
        ))


def test_final_bull_bear_turns_capture_questions_and_research_manager_keeps_them(monkeypatch):
    from tradingagents.agents.managers import research_manager as module

    debate = {
        "history": "", "bull_history": "", "bear_history": "",
        "current_response": "", "count": 0,
    }
    run = {
        **corpus_state(), "market_report": "", "sentiment_report": "",
        "news_report": "", "fundamentals_report": "",
        "investment_debate_state": debate,
        "_document_question_final_turn": True,
    }
    bull_llm = QuestionLLM("Bull")
    bull = create_bull_researcher(bull_llm)(run)
    assert "document_questions" in bull_llm.prompts[0]
    assert bull["investment_debate_state"]["document_questions"]["bull"]["questions"][0]["query"] == "lease commitments"
    bear_llm = QuestionLLM("Bear")
    bear = create_bear_researcher(bear_llm)({
        **run, "investment_debate_state": bull["investment_debate_state"],
    })
    questions = bear["investment_debate_state"]["document_questions"]
    assert set(questions) == {"bull", "bear"}
    assert questions["bear"]["questions"][0]["query"] == "lease commitments"

    monkeypatch.setattr(module, "bind_structured", lambda *args: object())
    monkeypatch.setattr(module, "invoke_structured_or_freetext", lambda *args: "Recommendation: Hold")
    manager = module.create_research_manager(object())({
        **run, "investment_debate_state": bear["investment_debate_state"],
    })
    assert manager["investment_debate_state"]["document_questions"] == questions



def test_compiled_graph_wraps_last_debate_turn_with_question_flag(monkeypatch):
    import tradingagents.graph.setup as setup_module
    from tradingagents.graph.conditional_logic import ConditionalLogic

    def noop(*args, **kwargs):
        return lambda state: {}
    for name in (
        "create_aggressive_debator", "create_conservative_debator",
        "create_neutral_debator", "create_portfolio_manager",
        "create_trader", "create_market_analyst", "create_research_manager",
    ):
        monkeypatch.setattr(setup_module, name, noop)
    monkeypatch.setattr(setup_module, "create_advisory_audit", noop)
    monkeypatch.setattr(setup_module, "create_source_acquisition", noop)
    monkeypatch.setattr(setup_module, "create_evidence_gate", noop)
    bull_llm = QuestionLLM("Bull")
    bear_llm = QuestionLLM("Bear")
    monkeypatch.setattr(setup_module, "create_bull_researcher", lambda llm: create_bull_researcher(bull_llm))
    monkeypatch.setattr(setup_module, "create_bear_researcher", lambda llm: create_bear_researcher(bear_llm))
    graph = setup_module.GraphSetup(
        object(), object(), ConditionalLogic(max_debate_rounds=2), max_tool_rounds=1,
    ).setup_graph(selected_analysts=("market",))
    run = {
        **corpus_state(), "market_report": "", "sentiment_report": "",
        "news_report": "", "fundamentals_report": "",
        "investment_debate_state": {
            "history": "", "bull_history": "", "bear_history": "",
            "current_response": "", "count": 2,
        },
    }
    bull = graph.nodes["Bull Researcher"].runnable.invoke(run)
    assert bull["investment_debate_state"]["document_questions"]["bull"]["questions"]
    run["investment_debate_state"] = bull["investment_debate_state"]
    bear = graph.nodes["Bear Researcher"].runnable.invoke(run)
    assert set(bear["investment_debate_state"]["document_questions"]) == {"bull", "bear"}
