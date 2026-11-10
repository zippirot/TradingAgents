"""Repairs after DOCN run 86aa515f (Build Z): lost valuation cases, a stale price, and a 5/5 score."""

from copy import deepcopy

import pytest

from tests.test_case_valuation import revenue_case
from tests.test_operational_audit import observed
from tests.test_shared_valuation import state
from tradingagents.agents.shared_valuation import prepare_shared_valuation, render_shared_valuation
from tradingagents.operational_audit import assess_audit, render_assessment
from tradingagents.reporting import prepare_report_state, stale_price_note

_FALLBACK = {"reason": "Latest completed session has no close; using last valid completed session",
             "latest_completed_session_date": "2026-11-09", "selected_session_date": "2026-11-06",
             "missing_completed_session_dates": ["2026-11-09"]}
_STALE = ("**Stale price:** the latest completed session 2026-11-09 has no close from the data source; "
          "all price and indicator figures use 2026-11-06.")


# Z1 ------------------------------------------------------------------------

def _without_label(field):
    row = revenue_case()
    capital = row["request"]["capital"]
    del (capital["obligations"]["borrowings"] if field == "obligations.borrowings" else capital[field])["assumption"]
    return row


@pytest.mark.parametrize("field", ["obligations.borrowings", "cash", "closing_shares"])
def test_case_with_a_missing_assumption_label_is_priced_as_an_estimate(field):
    complete = prepare_shared_valuation(state([revenue_case()]))
    row = _without_label(field)
    submitted = deepcopy(row)
    record = prepare_shared_valuation(state([row]))
    note = f"Row 1: assumption label missing on {field}; treated as estimated."
    assert record["status"] == "available" and len(record["rows"]) == 1
    assert record["reasons"] == [note]
    assert record["rows"][0]["result"]["target"] == complete["rows"][0]["result"]["target"]
    assert note in render_shared_valuation(record)
    # The analyst's submission is kept as written.
    assert row == submitted and record["requests"] == [submitted]


def test_complete_case_carries_no_label_note():
    record = prepare_shared_valuation(state([revenue_case()]))
    assert record["status"] == "available" and record["reasons"] == []


def test_invalid_assumption_label_is_still_rejected():
    row = revenue_case()
    row["request"]["capital"]["obligations"]["borrowings"]["assumption"] = "guess"
    record = prepare_shared_valuation(state([row]))
    assert not record["rows"]
    assert record["reasons"] == ["Row 1 omitted: malformed valuation request at capital.obligations.borrowings.assumption"]


def test_other_missing_capital_fields_are_still_rejected():
    row = revenue_case()
    del row["request"]["capital"]["cash"]["value"]
    record = prepare_shared_valuation(state([row]))
    assert not record["rows"] and "malformed valuation request at capital.cash.value" in record["reasons"][0]


# Z2 ------------------------------------------------------------------------

def _priced(fallback=None, session="2026-11-06"):
    price = {"status": "available", "session_date": session}
    if fallback is not None:
        price["price_fallback"] = fallback
    return {"price_observation": price}


def test_stale_price_note_names_both_sessions():
    assert stale_price_note(_priced(_FALLBACK)) == _STALE


@pytest.mark.parametrize("inputs", [
    {}, {"price_observation": None}, {"price_observation": {"status": "unavailable"}}, _priced(),
    _priced({**_FALLBACK, "latest_completed_session_date": "2026-11-06"}),
    _priced({"reason": "x"}), _priced("text"),
])
def test_no_stale_price_note_without_an_earlier_session(inputs):
    assert stale_price_note(inputs) == ""


def _report_state(**extra):
    return {"company_of_interest": "DOCN", "trade_date": "2026-11-09",
            "evidence_quality": {"status": "limited", "scope": "Selected US SEC-filer fundamentals"},
            "final_trade_decision": "**Rating**: Underweight", "market_report": "Canonical market",
            "unvalidated_outputs": {"market_report": "RSI is 27."}, **extra}


def test_stale_price_leads_the_decision_and_the_market_section():
    prepared = prepare_report_state(_report_state(**_priced(_FALLBACK)))
    assert prepared["final_trade_decision"].startswith(_STALE + "\n\n")
    assert prepared["market_report"].startswith(_STALE + "\n\n")
    assert prepared["final_trade_decision"].count("Stale price") == 1


def test_current_price_adds_no_stale_line():
    prepared = prepare_report_state(_report_state(**_priced()))
    assert "Stale price" not in prepared["final_trade_decision"] + prepared["market_report"]


@pytest.mark.parametrize("quality", [{"evidence_quality": {"status": "insufficient"}}, {}])
def test_stale_price_also_leads_review_and_legacy_presentations(quality, tmp_path):
    from tradingagents.reporting import write_report_tree

    base = {"company_of_interest": "DOCN", "trade_date": "2026-11-09",
            "final_trade_decision": "**Rating**: Hold", "market_report": "Market text", **quality}
    prepared = prepare_report_state({**base, **_priced(_FALLBACK)})
    assert prepared["final_trade_decision"].startswith(_STALE + "\n\n")
    assert prepared["market_report"].startswith(_STALE + "\n\n")
    current = prepare_report_state({**base, **_priced()})
    assert "Stale price" not in current["final_trade_decision"] + current["market_report"]
    write_report_tree({**base, **_priced(_FALLBACK)}, "DOCN", tmp_path, settings={}, html=True)
    assert (tmp_path / "1_analysts" / "market.md").read_text().startswith(_STALE)
    assert (tmp_path / "5_portfolio" / "decision.md").read_text().startswith(_STALE)
    for name in ("complete_report.md", "complete_report.html"):
        assert (tmp_path / name).read_text().count("Stale price:") == 3


def test_stale_price_sits_above_the_executive_summary_in_both_exports(tmp_path):
    from tradingagents.reporting import write_report_tree

    for name, inputs in (("stale", _priced(_FALLBACK)), ("current", _priced())):
        folder = tmp_path / name
        write_report_tree(_report_state(**inputs), "DOCN", folder, settings={}, html=True)
        markdown = (folder / "complete_report.md").read_text()
        page = (folder / "complete_report.html").read_text()
        if name == "stale":
            assert 0 < markdown.index("**Stale price:**") < markdown.index("## Executive summary")
            assert 0 < page.index("Stale price:") < page.index('id="executive-summary"')
        else:
            assert "Stale price" not in markdown + page


# Z3 ------------------------------------------------------------------------

def _scenarios(submitted, priced):
    return {"shared_valuation_scenarios": {
        "status": "available" if priced else "unavailable",
        "requests": [{"name": f"Case {n}", "request": {}} for n in range(submitted)],
        "rows": [{"name": f"Case {n}"} for n in range(priced)], "reasons": []}}


@pytest.mark.parametrize("extra,score,code", [
    (_scenarios(2, 0), 3, "valuation_cases_rejected"),
    (_scenarios(3, 2), 4, "valuation_case_rejected"),
    (_priced(_FALLBACK), 3, "price_session_fallback"),
])
def test_lost_capability_lowers_the_operational_score(extra, score, code):
    assessment = assess_audit({**observed(), **extra})
    assert assessment["score"] == score
    assert [finding["code"] for finding in assessment["findings"]] == [code]
    assert assessment["findings"][0]["text"] in render_assessment(assessment)


def test_run_86aa515f_shape_is_degraded_and_names_both_losses():
    assessment = assess_audit({**observed(), **_scenarios(2, 0), **_priced(_FALLBACK)})
    assert (assessment["score"], assessment["name"]) == (3, "Degraded")
    assert {finding["code"] for finding in assessment["findings"]} == {"valuation_cases_rejected", "price_session_fallback"}
    text = assessment["consequence"]
    assert "2 of 2 submitted valuation cases" in text and "2026-11-06" in text and "2026-11-09" in text


@pytest.mark.parametrize("extra", [
    {}, _scenarios(2, 2), _scenarios(0, 0), _priced(),
    {"shared_valuation_scenarios": {"status": "not_applicable", "requests": [], "rows": [], "reasons": []}},
    {"shared_valuation_scenarios": "text", "price_observation": "text"},
])
def test_intact_capability_keeps_a_clean_run_strong(extra):
    assert assess_audit({**observed(), **extra})["score"] == 5


def test_cases_rejected_as_a_collection_still_lower_the_score():
    """Duplicate names reject the whole submission before any row is priced."""
    record = prepare_shared_valuation(state([revenue_case(), revenue_case()]))
    assert record["rows"] == [] and record["requests"] == [] and record["rejected_submissions"] == 2
    assessment = assess_audit({**observed(), "shared_valuation_scenarios": record})
    assert assessment["score"] == 3
    assert "Rejected: 2 of 2 submitted valuation cases." in assessment["findings"][0]["text"]


def test_no_proposal_and_unreadable_counts_do_not_lower_the_score():
    empty = prepare_shared_valuation(state([]))
    assert "rejected_submissions" not in empty
    assert assess_audit({**observed(), "shared_valuation_scenarios": empty})["score"] == 5
    for count in (True, -1, "2", 2.0, None):
        record = {"status": "unavailable", "requests": [], "rows": [], "reasons": [], "rejected_submissions": count}
        assert assess_audit({**observed(), "shared_valuation_scenarios": record})["score"] == 5, count


# Z4, Z5 --------------------------------------------------------------------

def test_risk_analysts_are_told_carried_conditions_are_kept():
    from pathlib import Path

    import tradingagents.agents.risk_mgmt as risk
    from tradingagents.agents.schemas import CARRIED_PLAN_HEADING

    heading = CARRIED_PLAN_HEADING.strip("*")
    for name in ("aggressive_debator", "conservative_debator", "neutral_debator"):
        source = (Path(risk.__file__).parent / f"{name}.py").read_text()
        assert f'under "{heading}" are part of the Trader\'s plan and count as kept' in source, name


def test_trader_is_asked_to_keep_the_exposure_condition():
    from tests.test_structured_agents import _make_trader_state, _structured_trader_llm
    from tradingagents.agents.trader.trader import create_trader

    captured = {}
    create_trader(_structured_trader_llm(captured))(_make_trader_state())
    prompt = " ".join(str(getattr(m, "content", m.get("content") if isinstance(m, dict) else m)) for m in captured["prompt"])
    assert "conditional on current exposure" in prompt and "state that condition" in prompt
