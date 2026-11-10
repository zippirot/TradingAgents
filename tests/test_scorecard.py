"""A scorecard of settled outcomes for the manager, and old memory without allocation figures."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tradingagents.memory import publication, publication_outcomes as outcomes


@pytest.fixture
def store(tmp_path, monkeypatch):
    config = {"results_dir": str(tmp_path)}
    monkeypatch.setattr(publication, "_utcnow", lambda: datetime(2026, 10, 19, 22, tzinfo=UTC))
    monkeypatch.setattr(publication, "get_current_date", lambda: "2026-10-19")
    monkeypatch.setattr(outcomes, "get_current_date", lambda: "2026-11-04")

    def add(rating="Underweight", asof="2026-10-19", ticker="DOCN"):
        state = {"run_id": str(uuid4()), "final_rating": rating, "evaluation_mode": "prospective",
                 "final_trade_decision": rating, "evidence_quality": {"status": "limited"}}
        return publication.publish(config, state, ticker, asof)
    return config, add


def settle(config, monkeypatch, alphas):
    """Settle the 5-session window of each ticker with the given excess return; longer windows stay pending."""
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 4, 18, tzinfo=UTC).astimezone(tz)
    monkeypatch.setattr(outcomes, "datetime", Clock)

    def prices(ticker, cutoff, days, benchmark, **kwargs):
        if days != 5 or ticker not in alphas:
            return None
        alpha = alphas[ticker]
        last = 100. * (1 + alpha) + 2.
        raw, bench = last / 100. - 1, 408. / 400. - 1
        return {"raw_return": raw, "alpha_return": raw - bench, "benchmark_return": bench,
                "holding_days": 5, "resolution_date": "2026-10-27", "ticker": ticker, "benchmark": benchmark,
                "entry": {"date": "2026-10-20", "price": 100.}, "exit": {"date": "2026-10-27", "price": last},
                "benchmark_entry": {"date": "2026-10-20", "price": 400.},
                "benchmark_exit": {"date": "2026-10-27", "price": 408.},
                "price_source": "frozen fixture", "price_adjustment": "adjusted"}
    monkeypatch.setattr(outcomes, "fetch_outcome", prices)
    outcomes.settle_publications(config)


def test_no_settled_outcome_says_so_and_counts_what_is_pending(store):
    config, add = store
    add()
    card = outcomes.scorecard(config, "DOCN")
    assert card["rows"] == [] and card["settled"] == 0 and card["pending"] == 5
    text = outcomes.render_scorecard(card)
    assert "No settled outcome yet" in text and "5 outcome window(s) pending" in text
    assert "| pending |" not in text


def test_no_recommendation_on_record_adds_nothing(store):
    config, _add = store
    assert outcomes.render_scorecard(outcomes.scorecard(config, "DOCN")) == ""


def test_a_right_and_a_wrong_underweight_are_counted_against_the_benchmark(store, monkeypatch):
    config, add = store
    add(), add(asof="2026-10-16")
    add("Buy", ticker="NVDA")
    settle(config, monkeypatch, {"DOCN": .03, "NVDA": .04})
    card = outcomes.scorecard(config, "DOCN")
    # An Underweight is right when the stock lagged its benchmark; +3 percent excess is a miss.
    assert card["rows"] == [
        {"scope": "DOCN", "rating": "Underweight", "horizon": "5 sessions", "calls": 2, "right": 0,
         "average_excess": pytest.approx(.03)},
        {"scope": "All tickers", "rating": "Buy", "horizon": "5 sessions", "calls": 1, "right": 1,
         "average_excess": pytest.approx(.04)},
        {"scope": "All tickers", "rating": "Underweight", "horizon": "5 sessions", "calls": 2, "right": 0,
         "average_excess": pytest.approx(.03)},
    ]
    text = outcomes.render_scorecard(card)
    assert "DOCN | Underweight | 5 sessions | 2 | 0 of 2 | +3.00%" in text
    assert "All tickers | Buy | 5 sessions | 1 | 1 of 1 | +4.00%" in text
    assert "too few to conclude" in text and "12 outcome window(s) pending" in text


def test_an_underweight_that_lagged_is_right_and_hold_is_not_scored_for_direction(store, monkeypatch):
    config, add = store
    add(), add("Hold", ticker="NVDA")
    settle(config, monkeypatch, {"DOCN": -.05, "NVDA": .01})
    rows = {(row["scope"], row["rating"]): row for row in outcomes.scorecard(config, "DOCN")["rows"]}
    assert rows[("DOCN", "Underweight")]["right"] == 1
    assert rows[("All tickers", "Hold")]["right"] is None
    assert "All tickers | Hold | 5 sessions | 1 | not scored | +1.00%" in outcomes.render_scorecard(
        outcomes.scorecard(config, "DOCN"))


def test_ten_settled_calls_drop_the_too_few_label(store, monkeypatch):
    config, add = store
    for day in range(1, 11):
        add(asof=f"2026-10-{day:02d}")
    settle(config, monkeypatch, {"DOCN": -.01})
    card = outcomes.scorecard(config, "DOCN")
    assert card["rows"][0]["calls"] == 10 and card["rows"][0]["right"] == 10
    assert "too few to conclude" not in outcomes.render_scorecard(card)


def test_same_day_reruns_and_review_records_are_not_samples(store, monkeypatch):
    config, add = store
    add(), add("Hold"), add("REVIEW")
    settle(config, monkeypatch, {"DOCN": .03})
    card = outcomes.scorecard(config, "DOCN")
    assert [(row["scope"], row["rating"], row["calls"]) for row in card["rows"]] == [
        ("DOCN", "Underweight", 1), ("All tickers", "Underweight", 1)]


def test_outcomes_recorded_after_the_cutoff_stay_pending(store, monkeypatch):
    config, add = store
    add()
    settle(config, monkeypatch, {"DOCN": .03})
    assert outcomes.scorecard(config, "DOCN", "2026-11-04T17:59:59+00:00")["settled"] == 0
    assert outcomes.scorecard(config, "DOCN", "2026-11-04T18:00:00+00:00")["settled"] == 1


def test_a_damaged_outcome_file_is_counted_not_hidden(store):
    config, add = store
    record = add()
    path = publication.record_root(config) / "outcomes" / f"{record['decision_id']}.json"
    path.parent.mkdir()
    path.write_text("{}")
    card = outcomes.scorecard(config, "DOCN")
    assert card["unreadable"] == 1
    assert "1 outcome record(s) could not be read" in outcomes.render_scorecard(card)


# Wiring -----------------------------------------------------------------------

def test_the_manager_gets_the_scorecard_and_not_the_pending_table(store, monkeypatch):
    from types import SimpleNamespace

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config, add = store
    add()
    settle(config, monkeypatch, {"DOCN": .03})
    graph = object.__new__(TradingAgentsGraph)
    graph.config = config
    graph.memory_log = SimpleNamespace(get_past_context=lambda *a, **k: "Past analyses of DOCN", load_entries=lambda: [])
    graph.settle_all_pending = lambda wait=False: SimpleNamespace(
        failed=[], endpoint_immature=[], endpoint_terminal=[], endpoint_deferred=[], skipped_publications=[])
    state = {"company_of_interest": "DOCN", "trade_date": "2026-11-04",
             "analysis_clock": {"cutoff_utc": "2026-11-05T06:59:59+00:00", "analysis_timezone": "America/Denver"}}
    result = graph._memory_step(state)
    assert "### Track record" in result["past_context"] and "Past analyses of DOCN" in result["past_context"]
    assert "| pending |" not in result["past_context"] and "Decision | Horizon | Status" not in result["past_context"]
    # The report keeps the full table, with the scorecard above it.
    report = result["outcome_summary"]
    assert report.index("### Track record") < report.index("### Recommendation outcome horizons")
    assert "| 21 sessions | pending |" in report


# Old memory -------------------------------------------------------------------

OLD = ("**Rating**: Underweight\n\n**Executive Summary**: Reduce DOCN to roughly 30-35% of a normal/benchmark weight "
       "(40% only if the residual is hedged) and commit no new capital at $100.37. Revenue grew 39.87% year over year. "
       "Gate the rebuild on gross margin: below 53% exit the remainder of the position.")


def test_memory_shown_to_the_manager_drops_allocation_figures_and_keeps_evidence_figures():
    from tradingagents.agents.evidence_presentation import memory_without_sizing
    from tradingagents.agents.schemas import SIZING_WITHHELD

    text = memory_without_sizing(OLD)
    assert "30-35%" not in text and "40%" not in text and "$100.37" not in text and "53%" not in text
    assert "Revenue grew 39.87% year over year." in text and "**Rating**: Underweight" in text
    assert text.count(SIZING_WITHHELD) == 1
    plain = "**Rating**: Hold\n\nRevenue grew 39.87% and margin was 50.15%."
    assert memory_without_sizing(plain) == plain


def test_the_memory_log_applies_the_filter_to_past_decisions(tmp_path):
    from tradingagents.memory.log import TradingMemoryLog

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
    log.store_decision("DOCN", "2026-10-19", OLD)
    log.update_with_outcome("DOCN", "2026-10-19", 0.069, 0.069, 5, "Reflection: trimmed too early.")
    context = log.get_past_context("DOCN")
    assert "30-35%" not in context and "Revenue grew 39.87%" in context and "trimmed too early" in context
    # The stored record is untouched; only the prompt view is filtered.
    assert "30-35%" in (tmp_path / "memory.md").read_text()
