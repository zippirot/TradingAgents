"""Earnings cases are carried to the next run like revenue cases.

Found 2026-11-12 while diagnosing why MSFT's rating differed between runs on one close: the carry-forward of
the analyst's own earlier cases selected revenue cases only, so every company valued on earnings (MSFT, WMT,
CAT) re-derived its forecasts and multiples from scratch each run.
"""
from tradingagents.agents import prior_cases as module

EARNINGS = [{"name": name, "scenario_role": role, "request": {
    "method": "earnings_case", "eps_fact_id": "f" * 64, "multiple": multiple,
    "forecast": {"value": eps, "unit": "USD/shares", "period_start": "2026-07-01", "period_end": "2027-06-30"}}}
    for name, role, eps, multiple in (("Base", "base", "20.00", "28"), ("Downside", "downside", "18.50", "23"))]


def _patched(monkeypatch, requests):
    record = {"decision_id": "d" * 32, "canonical_rating": "Hold"}
    monkeypatch.setattr("tradingagents.agents.assumption_history.prior_publication", lambda *a: (record, "2026-11-11"))
    monkeypatch.setattr("tradingagents.memory.publication.load_evidence",
                        lambda *a: {"shared_valuation_scenarios": {"requests": requests}})
    return module.prior_cases({}, "MSFT", {"trade_date": "2026-11-12"})


def test_the_last_decisions_earnings_cases_are_offered_back_with_their_eps_and_multiples(monkeypatch):
    context = _patched(monkeypatch, EARNINGS)
    assert [(c["request"]["forecast"]["value"], c["request"]["multiple"]) for c in context["cases"]] == [
        ("20.00", "28"), ("18.50", "23")]
    text = module.render_prior_cases(context)
    assert "```previous_valuation_scenarios" in text and '"multiple":"28"' in text and '"value":"20.00"' in text
    assert "earnings per share forecast" in text


def test_legacy_methods_are_still_not_carried(monkeypatch):
    legacy = [{"name": "Base", "request": {"method": "pe", "multiple": "20"}}]
    assert _patched(monkeypatch, legacy) is None
