from datetime import date

import pytest

from tests.test_shared_valuation import state
from tests.test_valuation import ev_request, evidence, pe_request
from tradingagents.agents.schemas import render_target_result
from tradingagents.agents.shared_valuation import prepare_shared_valuation, render_shared_valuation
from tradingagents.agents.valuation import TargetResult, validate_target
from tradingagents.dataflows.financial_evidence import FinancialFact


def with_event(**changes):
    package = evidence()
    values = {"fact_id": "issuance", "metric": "Equity Common Stock Issuance Value", "value": "887900000", "unit": "USD", "cik": package.cik, "period_start": "2026-01-01", "period_end": "2026-06-30", "as_of": package.as_of, "source_ids": ("s",), "locator": "reported equity table"}
    values.update(changes)
    return package.model_copy(update={"facts": (*package.facts, FinancialFact(**values))})


def test_positive_capital_change_excludes_decision_use_but_keeps_arithmetic():
    result = validate_target(pe_request(), with_event())
    assert result.status == "supported" and result.target == 40
    assert result.decision_use.classification == "historical_diagnostic"
    assert result.decision_use.suitability == "excluded"
    assert result.decision_use.events[0].fact_id == "issuance"
    assert not result.decision_use.final_target_eligible


def test_no_event_is_not_evidence_of_no_change():
    result = validate_target(pe_request(), evidence())
    assert result.decision_use.suitability == "comparability_unestablished"


def test_ev_prior_behavior_survives():
    result = validate_target(ev_request(), evidence())
    assert result.status == "supported" and result.target == 35
    assert result.decision_use.suitability == "conditional"



@pytest.mark.parametrize("changes", [
    {"value": 0}, {"value": None, "missing_reason": "not disclosed"},
    {"unit": "shares"}, {"unit": "EUR"},
    {"metric": "Financing Cash Flow"}, {"metric": "Total Equity"},
    {"period_start": "2025-01-01"},
    {"period_start": "2025-01-01", "period_end": "2025-06-30"},
    {"period_start": None},
])
def test_unqualified_events_do_not_establish_exclusion_or_comparability(changes):
    result = validate_target(pe_request(), with_event(**changes))
    assert result.status == "supported" and result.target == 40
    assert result.decision_use.suitability == "comparability_unestablished"
    assert not result.decision_use.events


@pytest.mark.parametrize("changes", [{"cik": "wrong"}])
def test_wrong_issuer_invalidates_source_package(changes):
    assert validate_target(pe_request(), with_event(**changes)).status == "unsupported"


def test_filing_after_cutoff_cannot_establish_event():
    package = with_event()
    package = package.model_copy(update={"sources": (package.sources[0].model_copy(update={"filed_date": date(2027, 1, 1)}),)})
    assert validate_target(pe_request(), package).status == "unsupported"


@pytest.mark.parametrize("metric", ["Common Stock Issuance Proceeds", "Equity Conversion of Debt", "Employee Stock Purchase Plan Issuance Value"])
def test_positive_verified_event_has_no_materiality_threshold(metric):
    result = validate_target(pe_request(), with_event(metric=metric, value="0.01"))
    assert result.decision_use.suitability == "excluded"


def test_overlapping_interval_retains_timing_reason():
    result = validate_target(pe_request(), with_event(period_start="2025-01-01"))
    assert any("overlaps" in r for r in result.decision_use.reasons)


def test_comparable_historical_cutoff_is_not_excluded_solely_for_age():
    package = evidence(eps={"period_start": "2025-10-20", "period_end": "2026-10-19"})
    result = validate_target(pe_request(), package)
    assert result.status == "supported" and result.target == 40
    assert result.decision_use.classification == "historical_diagnostic"
    assert result.decision_use.suitability == "conditional"
    assert not result.decision_use.final_target_eligible


def test_explicit_forward_eps_retains_existing_validation():
    request = pe_request()
    request["forecast"] = {"value": 3, "unit": "USD/shares", "period_start": "2027-01-01", "period_end": "2027-12-31", "basis": "US-GAAP", "kind": "analyst_forecast", "rationale": "Explicit forecast assumption"}
    result = validate_target(request, with_event())
    assert result.target == 60 and result.decision_use.suitability == "conditional"
    assert result.decision_use.classification == "forward_scenario"


def test_legacy_supported_does_not_imply_assessed_suitability():
    original = validate_target(pe_request(), with_event()).model_dump()
    del original["decision_use"]
    legacy = TargetResult.model_validate(original)
    assert legacy.status == "supported" and legacy.target == 40
    assert legacy.decision_use.suitability == "unassessed"
    assert "Price Target**: not provided" in render_target_result(legacy)


def test_shared_diagnostic_survives_without_decision_comparison():
    inputs = state([{"name": "Historical", "request": pe_request()}])
    inputs["financial_evidence"] = with_event().model_dump(mode="json")
    result = prepare_shared_valuation(inputs)
    row = result["rows"][0]
    assert row["result"]["target"] == "40" and row["result"]["status"] == "supported"
    assert row["diagnostic_only"] and row["comparison"] is None
    text = render_shared_valuation(result)
    assert "Historical diagnostic" in text and "historical_earnings_precedes_verified_capital_change" in text
    assert "issuance" in text


def test_final_target_renderer_keeps_diagnostic_and_omits_target():
    request = pe_request()
    request.update(decision_date="2027-01-01", rerating_assumption="Model assumption", multiple_assumption_date="2026-10-19")
    text = render_target_result(validate_target(request, with_event()))
    assert "Historical diagnostic" in text and "Price Target**: not provided" in text
    assert "Conditional decision-date valuation" not in text


@pytest.mark.parametrize("raw_request", [pe_request(), None])
def test_publication_and_free_text_cannot_bypass_suitability(raw_request):
    from tradingagents.agents.output_validation import enforce_publication
    inputs = state([])
    inputs.update(financial_evidence=with_event().model_dump(mode="json"),
                  final_rating="Buy", final_trade_decision="Fair value is $999.",
                  target_validation={"status": "supported", "target": "999", "request": raw_request})
    public = enforce_publication(inputs)
    text = public["final_trade_decision"]
    assert "Fundamental price target: unavailable" in text and "$999" not in text
    assert public["decision_context"]["basis"] == "risk assessment"
    if raw_request:
        assert public["target_validation"]["target"] == "40"
        assert public["target_validation"]["decision_use"]["suitability"] == "excluded"
        assert "Historical diagnostic" in text
    else:
        assert public["target_validation"]["target"] is None
