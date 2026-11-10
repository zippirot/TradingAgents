"""Native SQLite continuation from a completed Trader node, with offline models."""
import json
from copy import deepcopy
from pathlib import Path

from langchain_core.messages import AIMessage
from langgraph.config import get_config

from tests.test_case_valuation import revenue_case
from tests.test_shared_valuation import state as case_state
from tradingagents.agents.audit_pass import AuditOutput
from tradingagents.agents.schemas import RequiredHorizonPortfolioDecision
from tradingagents.agents.shared_valuation import prepare_shared_valuation
from tradingagents.graph import trading_graph
from tradingagents.memory.publication import list_records, runtime_versions
from tradingagents.reporting import verified_publication, write_report_tree

RISK = ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"] * 3


class FixtureModel:
    def __init__(self, calls, tier, schema=None):
        self.calls = calls
        self.tier = tier
        self.schema = schema

    def get_llm(self):
        return self

    def bind_tools(self, tools):
        return self

    def with_structured_output(self, schema, **kwargs):
        return FixtureModel(self.calls, self.tier, schema)

    def invoke(self, prompt):
        node = get_config()["metadata"]["langgraph_node"]
        self.calls.append((node, self.tier))
        if node in RISK:
            assert self.tier == "quick" and self.schema is None
            return AIMessage(content="Offline fixture risk comment.")
        assert self.tier == "deep"
        if node == "Advisory Audit":
            assert self.schema is AuditOutput
            # Exercise exactly one bounded retry as well as the successful audit.
            if self.calls.count((node, self.tier)) == 1:
                return {"unexpected": "Offline fixture malformed first audit"}
            return AuditOutput(findings=[])
        assert node == "Portfolio Manager" and self.schema is RequiredHorizonPortfolioDecision
        return self.schema(rating="Hold", executive_summary="Offline fixture decision.",
                           investment_thesis="Offline fixture reasoning.", time_horizon="3 months",
                           no_case_reason="Offline fixture retains advisory cases without adoption.")


def finish_fixture_checkpoint(graph, ticker, day, expected_thread=None, expected_id=None):
    """Exercise the native graph, without initializing a run or clearing its checkpoint."""
    with graph.checkpoint_scope(ticker, day) as tid:
        if expected_thread:
            assert tid == expected_thread
        args = graph.propagator.get_graph_args()
        args["config"]["configurable"] = {"thread_id": tid}
        checkpoint = graph.graph.get_state(args["config"])
        before = checkpoint.values
        assert checkpoint.next == ("Aggressive Analyst",)
        if expected_id:
            assert checkpoint.config["configurable"]["checkpoint_id"] == expected_id
        assert before["risk_debate_state"]["count"] == 0 and graph.checkpoint_input({}) is None
        for _ in graph.stream_run(None, **args):
            pass
        end = graph.graph.get_state(args["config"])
        assert not end.next
        after = end.values
        assert after["run_id"] == before["run_id"] and after["risk_debate_state"]["count"] == 9
        for key in ("market_report", "sentiment_report", "news_report", "fundamentals_report",
                    "investment_debate_state", "investment_plan", "trader_investment_plan"):
            assert after["unvalidated_outputs"][key] == before[key]
        for key in ("shared_source_brief", "price_observation", "financial_evidence", "issuer_identity",
                    "filing_evidence", "document_sources", "transcript_sources", "analysis_clock",
                    "market_observation_cutoff", "shared_valuation_scenarios"):
            assert after.get(key) == before.get(key), key
        assert len(after["advisory_audit"]["attempts"]) == 2
        assert after["advisory_audit"]["status"] == "completed with zero findings"
        assert after["decision_context"]["case_groups"]
        return before, after


def publish_fixture_twice(graph, ticker, day, final, report_path):
    """Recover after graph finish and publication without repeating model calls."""
    graph.record_decision(ticker, day, final)
    first = final["publication_record"].copy()
    with graph.checkpoint_scope(ticker, day) as tid:
        saved = graph.graph.get_state({"configurable": {"thread_id": tid}})
        assert not saved.next and saved.values["run_id"] == final["run_id"]
        assert saved.values["decision_context"]["assumption_changes"] == final["decision_context"]["assumption_changes"]
        assert saved.values["decision_context"]["assumption_changes"]["status"] == "no_prior"
        # A crash after the immutable record commit can precede the state log.
        record, _ = verified_publication(graph.config, saved.values, ticker, day)
        assert record["record_sha256"] == first["record_sha256"]
        log = Path(graph.config["results_dir"]) / ticker / "TradingAgentsStrategy_logs" / f"full_states_log_{day}.json"
        recovered = json.loads(log.read_text())
        assert recovered["run_id"] == saved.values["run_id"]
        graph.record_decision(ticker, day, recovered)
        assert first == recovered["publication_record"]
        write_report_tree(recovered, ticker, Path(report_path), graph.run_settings(),
                          publication_config=graph.config)
    records = list_records(graph.config, ticker)
    assert len(records) == 1 and records[0]["decision_id"] == final["run_id"]
    assert len(graph.memory_log.load_entries()) == 1
    return first


def test_native_resume_after_trader_does_not_repeat_completed_roles(tmp_path, monkeypatch):
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.propagation import Propagator

    calls = []
    monkeypatch.setattr(trading_graph, "create_tier_client",
                        lambda cfg, tier, **kw: FixtureModel(calls, tier))
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg.update(checkpoint_enabled=True, max_debate_rounds=3, max_risk_discuss_rounds=3,
               data_cache_dir=str(tmp_path / "cache"), results_dir=str(tmp_path / "results"),
               memory_log_path=str(tmp_path / "memory.md"))
    graph = trading_graph.TradingAgentsGraph(config=cfg)
    evidence = case_state([revenue_case()])
    ticker, day = evidence["company_of_interest"], evidence["trade_date"]
    seed = {**Propagator().create_initial_state(ticker, day, instrument_context="Offline fixture."),
            **evidence, "run_settings": graph.run_settings(), "publication_versions": runtime_versions(),
            "investment_plan": "Offline plan", "trader_investment_plan": "Offline proposal",
            "shared_valuation_scenarios": prepare_shared_valuation(evidence)}
    for role in ("market", "sentiment", "news", "fundamentals"):
        seed[f"{role}_report"] = f"Retained offline {role} report."
    with graph.checkpoint_scope(ticker, day) as tid:
        graph.graph.update_state({"configurable": {"thread_id": tid}}, seed, as_node="Trader")
    _, final = finish_fixture_checkpoint(graph, ticker, day)
    publish_fixture_twice(graph, ticker, day, final, tmp_path / "report")
    # The fixture manager does not address the priced case, so it is asked once more.
    assert calls == [(role, "quick") for role in RISK] + [
        ("Advisory Audit", "deep"), ("Advisory Audit", "deep"), ("Portfolio Manager", "deep"),
        ("Portfolio Manager", "deep")]
