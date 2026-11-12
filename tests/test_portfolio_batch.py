"""The batch and review commands: what runs, what is skipped, and where the review is written."""
import json
from datetime import date

import pytest

from cli import batch as batch_module, review as review_module
from tradingagents.portfolio import PortfolioContext

DAY = "2026-11-11"
BOOK = {"currency": "USD", "cash": 20000, "portfolio_value": 100000, "default_standard_weight": 0.05,
        "rating_weights": {"Buy": 1.5, "Overweight": 1.25, "Hold": 1.0, "Underweight": 0.5, "Sell": 0},
        "positions": [{"ticker": "AAA", "quantity": 50}], "watchlist": ["BBB", "CCC"]}


def record(ticker, as_of, rating, sequence):
    return {"ticker": ticker, "requested_as_of": as_of, "sequence": sequence, "canonical_rating": rating}


@pytest.fixture
def harness(monkeypatch):
    calls, records = [], []
    monkeypatch.setattr("tradingagents.memory.publication.scan_records", lambda config, ticker=None: {"records": records, "skipped": []})
    monkeypatch.setattr("cli.selections.get_user_selections",
                        lambda flags: {"ticker": flags["ticker"], "analysis_date": flags["date"], "asset_type": "stock",
                                       "research_depth": 1, "deep_think_llm": "deep"})

    def run_analysis(checkpoint=None, portfolio=None, flags=None, selections=None):
        calls.append({"flags": flags, "selections": selections, "portfolio": portfolio})
        if selections["ticker"] == "BBB" and getattr(run_analysis, "fail", False):
            raise RuntimeError("boom")
    monkeypatch.setattr("cli.run.run_analysis", run_analysis)
    return calls, records, run_analysis


def test_three_tickers_run_with_one_set_of_answers(harness):
    calls, _, _ = harness
    book = PortfolioContext.model_validate(BOOK)
    outcome = batch_module.run_batch(book, None, DAY, False)
    assert outcome == {"ran": ["AAA", "BBB", "CCC"], "skipped": [], "failed": []}
    assert [call["selections"]["ticker"] for call in calls] == ["AAA", "BBB", "CCC"]
    shared = [{k: v for k, v in call["selections"].items() if k != "ticker"} for call in calls]
    assert shared[0] == shared[1] == shared[2] and shared[0]["analysis_date"] == DAY
    assert all(call["flags"]["save"] is True and call["flags"]["show"] is False and call["portfolio"] is book for call in calls)


def test_a_fresh_rating_is_skipped_a_stale_or_review_one_runs_and_refresh_runs_all(harness):
    calls, records, _ = harness
    records += [record("AAA", "2026-11-10", "Buy", 1), record("BBB", "2026-09-01", "Buy", 2), record("CCC", "2026-11-10", "REVIEW", 3)]
    book = PortfolioContext.model_validate(BOOK)
    outcome = batch_module.run_batch(book, None, DAY, False)
    assert outcome["ran"] == ["BBB", "CCC"] and outcome["skipped"][0][0] == "AAA" and "rated Buy on 2026-11-10" in outcome["skipped"][0][1]
    calls.clear()
    assert batch_module.run_batch(book, None, DAY, True)["ran"] == ["AAA", "BBB", "CCC"]


def test_one_failure_is_recorded_and_the_next_ticker_still_runs(harness):
    calls, _, run_analysis = harness
    run_analysis.fail = True
    outcome = batch_module.run_batch(PortfolioContext.model_validate(BOOK), ["AAA", "BBB", "CCC"], DAY, False)
    assert outcome["ran"] == ["AAA", "CCC"] and outcome["failed"] == [("BBB", "RuntimeError: boom")]


def test_an_invalid_ticker_is_refused_before_any_run_and_nothing_to_run_asks_nothing(harness, monkeypatch):
    calls, records, _ = harness
    with pytest.raises(ValueError, match="not a ticker"):
        batch_module.run_batch(PortfolioContext.model_validate(BOOK), ["AAA", "not a ticker!"], DAY, False)
    assert calls == []
    records += [record(t, "2026-11-10", "Hold", i) for i, t in enumerate(("AAA", "BBB", "CCC"), 1)]
    monkeypatch.setattr("cli.selections.get_user_selections", lambda flags: pytest.fail("asked with nothing to run"))
    assert batch_module.run_batch(PortfolioContext.model_validate(BOOK), None, DAY, False)["ran"] == []


def test_the_review_is_saved_under_portfolio_reviews_and_one_price_failure_does_not_stop_it(tmp_path, monkeypatch):
    path = tmp_path / "book.json"
    path.write_text(json.dumps(BOOK))
    results = tmp_path / "results"
    records = [record("AAA", "2026-11-10", "Buy", 1), record("BBB", "2026-11-10", "Overweight", 2), record("CCC", "2026-11-10", "REVIEW", 3)]
    monkeypatch.setattr("tradingagents.memory.publication.scan_records",
                        lambda config, ticker=None: {"records": records, "skipped": [{"path": "x.json", "reason": "ValueError"}]})

    def quote(ticker, as_of):
        if ticker == "BBB":
            raise RuntimeError("network down")
        return {"status": "available", "close": "100", "currency": "USD", "session_date": as_of}
    monkeypatch.setattr("tradingagents.dataflows.vendors.yahoo.price_observation.get_price_observation", quote)
    monkeypatch.setattr("tradingagents.dataflows.vendors.yahoo.fundamentals.get_company_profile",
                        lambda ticker: {"sector": "Technology"} if ticker == "AAA" else {})
    saved = review_module.run_review(str(path), DAY, config={"results_dir": str(results)})
    assert saved.parent == results / "portfolio_reviews" and saved.is_file()
    assert not (results / "publications").exists()
    text = saved.read_text()
    assert "AAA | yes | Buy | 2026-11-10 | Add" in text
    assert "BBB | no | Overweight | 2026-11-10 | Not reviewed | no usable price: price fetch failed (RuntimeError)" in text
    assert "No rating (analysis stopped at REVIEW)" in text and "1 saved record file(s) could not be read" in text
    assert date.fromisoformat(saved.name[:10])
