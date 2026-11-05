"""Evidence REVIEW is authoritative at public and persistence boundaries."""

from types import SimpleNamespace

from tradingagents.agents.rating import run_rating
from tradingagents.graph.trading_graph import TradingAgentsGraph


def state():
    return {
        "evidence_quality": {
            "status": "insufficient",
            "checks": [
                {
                    "code": "equity_movement",
                    "status": "unavailable",
                    "message": "Equity evidence missing",
                }
            ],
        },
        "final_rating": "Buy",
        "final_trade_decision": "**Rating**: Buy\nTarget $96",
        "investment_plan": "Buy at $96",
        "trader_investment_plan": "Buy",
    }


def test_quality_overrides_both_typed_rating_and_fallback():
    assert run_rating(state()) == "REVIEW"
    fallback = state()
    fallback.pop("final_rating")
    assert run_rating(fallback) == "REVIEW"


def test_record_boundary_saves_review_but_never_inserts_trading_memory(tmp_path):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path)}
    graph.selected_analysts = ()
    saved, memory = [], []
    graph._log_state = lambda date, final: saved.append(dict(final))
    graph.memory_log = SimpleNamespace(store_decision=lambda **kwargs: memory.append(kwargs))
    final = state()
    graph.record_decision("DOCN", "2026-10-19", final)
    assert not memory
    assert saved[0]["final_rating"] == "REVIEW"
    assert "$96" not in saved[0]["final_trade_decision"]
    assert saved[0]["investment_plan"] == ""
    assert saved[0]["unvalidated_outputs"]["final_trade_decision"].endswith("Target $96")


def test_unparseable_legacy_style_review_is_not_a_trading_memory_entry(tmp_path):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path)}
    graph.selected_analysts = ()
    graph._log_state = lambda *args: None
    memory = []
    graph.memory_log = SimpleNamespace(store_decision=lambda **kwargs: memory.append(kwargs))
    graph.record_decision("DOCN", "2026-10-19", {"final_trade_decision": "Unable to decide"})
    assert not memory


def test_cli_review_reason_distinguishes_evidence_failure_from_unparseable_rating():
    from cli.run import _review_explanation

    message = _review_explanation(state())
    assert "research incomplete" in message.lower()
    assert "Equity evidence missing" in message
    assert "No rating could be read" not in message
    assert "No rating could be read" in _review_explanation({"final_rating": "REVIEW"})


def test_malformed_saved_quality_cannot_crash_or_authorize_a_decision():
    from cli.run import _review_explanation
    from tradingagents.agents.output_validation import enforce_evidence_review

    for malformed in (["insufficient"], {"status": "unknown"}, {"status": "insufficient"}):
        final = {"final_rating": "Buy", "evidence_quality": malformed}
        assert run_rating(final) == "REVIEW"
        final.update(enforce_evidence_review(final))
        assert final["final_rating"] == "REVIEW"
        assert "Evidence metadata" in final["final_trade_decision"]
        assert "Research incomplete" in _review_explanation(final)
