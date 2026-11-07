"""Shared scenarios use the existing calculator without choosing a final target."""

import json
from copy import deepcopy

from tests.test_valuation import ev_request, evidence, pe_request
from tradingagents.agents.shared_valuation import prepare_shared_valuation, render_shared_valuation


def state(rows):
    report = "Research\n```valuation_scenarios\n" + json.dumps(rows) + "\n```"
    return {
        "company_of_interest": "DOCN", "asset_type": "stock", "trade_date": "2026-10-19",
        "financial_evidence": evidence().model_dump(mode="json"),
        "financial_claim_validation": {"raw_report": report},
        "evidence_quality": {"status": "sufficient", "scope": "Selected US SEC-filer fundamentals"},
    }


def test_shared_rows_calculate_independently_and_do_not_choose_target():
    from tests.test_case_valuation import revenue_case
    low, high = revenue_case()["request"], revenue_case()["request"]
    for raw in (low, high):
        raw["capital"]["cash"]["value"] = "100"
        raw["capital"]["closing_shares"]["value"] = "100"
        raw["capital"]["obligations"]["borrowings"]["value"] = "200"
    high["multiple"] = "4"
    inputs = state([{"name": "Lower", "request": low}, {"name": "Higher", "request": high}])
    original = deepcopy(inputs)
    result = prepare_shared_valuation(inputs)
    assert result["status"] == "available"
    assert [r["result"]["target"] for r in result["rows"]] == ["35", "47"]
    assert "target" not in result
    assert inputs == original
    text = render_shared_valuation(result)
    assert "35" in text and "47" in text
    assert "conditional" in text.lower() and "assumption" in text.lower()
    assert "**Price Target**" not in text


def test_invalid_row_does_not_discard_supported_row():
    bad = pe_request()
    bad["eps_fact_id"] = "invented"
    result = prepare_shared_valuation(state([
        {"name": "Supported", "request": pe_request()}, {"name": "Missing", "request": bad},
    ]))
    assert result["status"] == "partial"
    assert len(result["rows"]) == 1
    assert result["rows"][0]["result"]["target"] == "40"
    assert result["reasons"]


def test_missing_scenarios_does_not_change_quality_or_decision():
    inputs = state([])
    inputs["final_rating"] = "Hold"
    original = deepcopy(inputs)
    result = prepare_shared_valuation(inputs)
    assert result["status"] == "unavailable" and result["reasons"]
    assert inputs == original


def test_insufficient_evidence_skips_even_valid_requests():
    inputs = state([{"name": "Base", "request": pe_request()}])
    inputs["evidence_quality"]["status"] = "insufficient"
    result = prepare_shared_valuation(inputs)
    assert result["status"] == "not_applicable"
    assert not result["rows"]


def test_mixed_methods_are_not_presented_as_a_price_range():
    result = prepare_shared_valuation(state([
        {"name": "Revenue", "request": ev_request()},
        {"name": "Earnings", "request": pe_request()},
    ]))
    assert result["status"] == "partial" and len(result["rows"]) == 1
    assert result["rows"][0]["diagnostic_only"]
    assert "Legacy revenue case lacks" in " ".join(result["reasons"])


def test_multiple_ev_scenarios_cannot_create_an_early_weighted_target():
    request = ev_request()
    second = deepcopy(request["scenarios"][0])
    second["name"] = "Second"
    request["scenarios"][0]["weight"] = "0.5"
    second["weight"] = "0.5"
    request["scenarios"].append(second)
    result = prepare_shared_valuation(state([{"name": "Weighted", "request": request}]))
    assert result["status"] == "unavailable" and not result["rows"]


def test_duplicate_names_reject_collection():
    result = prepare_shared_valuation(state([
        {"name": "Same", "request": pe_request()},
        {"name": " Same ", "request": pe_request()},
    ]))
    assert result["status"] == "unavailable" and not result["rows"]


def test_duplicate_or_invalid_fences_are_unavailable():
    inputs = state([{"name": "Base", "request": pe_request()}])
    original = inputs["financial_claim_validation"]["raw_report"]
    for report in (original + original, "no block", "```valuation_scenarios\n{\n```",
                   "```valuation_scenarios\n" + " " * 48001 + "\n```"):
        inputs["financial_claim_validation"]["raw_report"] = report
        assert prepare_shared_valuation(inputs)["status"] == "unavailable"


def test_replayed_requests_recompute_prices_and_check_run_date():
    inputs = state([{"name": "Base", "request": pe_request()}])
    record = prepare_shared_valuation(inputs)
    record["rows"][0]["result"]["target"] = "999"
    replayed = prepare_shared_valuation(inputs, record["requests"])
    assert replayed["rows"][0]["result"]["target"] == "40"
    inputs["trade_date"] = "2026-10-20"
    assert prepare_shared_valuation(inputs, record["requests"])["status"] == "unavailable"


def test_optional_scope_does_not_accept_canonical_facts_accidentally():
    inputs = state([{"name": "Base", "request": pe_request()}])
    inputs["evidence_quality"]["scope"] = "not_applicable"
    assert prepare_shared_valuation(inputs)["status"] == "not_applicable"


def test_shared_context_reaches_both_researchers_before_their_calls():
    from unittest.mock import MagicMock

    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    inputs = state([{"name": "Scenario marker", "request": pe_request()}])
    inputs["shared_valuation_scenarios"] = prepare_shared_valuation(inputs)
    inputs.update({"market_report": "m", "news_report": "n", "sentiment_report": "s",
                   "fundamentals_report": "f", "investment_debate_state": {"count": 0}})
    expected = render_shared_valuation(inputs["shared_valuation_scenarios"])
    for factory in (create_bull_researcher, create_bear_researcher):
        llm = MagicMock()
        llm.invoke.return_value.content = "Challenge assumptions"
        factory(llm)(inputs)
        llm.invoke.assert_called_once()
        prompt = llm.invoke.call_args.args[0]
        assert expected in prompt
        assert "assumption" in prompt.lower()


def test_research_manager_sees_table_without_debate_repeating_it():
    from unittest.mock import MagicMock

    from tradingagents.agents.managers.research_manager import create_research_manager
    from tradingagents.agents.schemas import ResearchPlan

    inputs = state([{"name": "Scenario marker", "request": pe_request()}])
    inputs["shared_valuation_scenarios"] = prepare_shared_valuation(inputs)
    inputs["investment_debate_state"] = {"history": "No table repeated", "count": 2}
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = ResearchPlan(
        recommendation="Hold", rationale="Evidence", strategic_actions="Wait")
    create_research_manager(llm)(inputs)
    prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
    assert render_shared_valuation(inputs["shared_valuation_scenarios"]) in prompt


def report_state():
    inputs = state([{"name": "Shared case", "request": pe_request()}])
    inputs.update({"fundamentals_report": "Canonical financial inputs",
                   "canonical_financial_context": "Canonical financial inputs",
                   "final_rating": "Hold", "final_trade_decision": "**Rating**: Hold",
                   "target_validation": {"request": None}})
    inputs["shared_valuation_scenarios"] = prepare_shared_valuation(inputs)
    return inputs


def test_publication_replays_shared_prices_without_promoting_final_target(tmp_path):
    from tradingagents.reporting import prepare_report_state, write_report_tree

    inputs = report_state()
    inputs["shared_valuation_scenarios"]["rows"][0]["result"]["target"] = "987654321"
    original = deepcopy(inputs)
    prepared = prepare_report_state(inputs)
    assert prepared["shared_valuation_scenarios"]["rows"][0]["result"]["target"] == "40"
    assert prepared["target_validation"]["target"] is None
    assert "987654321" not in prepared["fundamentals_report"]
    title = "### Shared valuation scenarios — conditional research inputs"
    assert prepared["fundamentals_report"].count(title) == 1
    again = prepare_report_state(prepared)
    assert again["fundamentals_report"] == prepared["fundamentals_report"]
    write_report_tree(inputs, "DOCN", tmp_path)
    md = (tmp_path / "complete_report.md").read_text()
    html = (tmp_path / "complete_report.html").read_text()
    assert "Shared valuation scenarios" in md and "Shared valuation scenarios" in html
    assert "987654321" not in md + html
    exported = json.loads((tmp_path / "evidence.json").read_text())
    assert exported["shared_valuation_scenarios"]["rows"][0]["result"]["target"] == "40"
    assert inputs == original


def test_review_publication_suppresses_stale_shared_table():
    from tradingagents.reporting import prepare_report_state

    inputs = report_state()
    inputs["evidence_quality"] = {"status": "insufficient", "checks": [
        {"status": "unavailable", "message": "Missing evidence"}]}
    prepared = prepare_report_state(inputs)
    assert prepared["final_rating"] == "REVIEW"
    assert not prepared["shared_valuation_scenarios"]["rows"]
    assert "Shared valuation scenarios" not in prepared["fundamentals_report"]


def test_final_request_is_independent_of_early_price():
    from tests.test_portfolio_valuation import decision, invoke, state as pm_state
    from tradingagents.reporting import prepare_report_state

    inputs = {**pm_state(), **report_state()}
    request = pe_request()
    request["multiple"] = "30"
    for final_request, expected in ((request, "60"), ({"method": "unsupported"}, None), (None, None)):
        updates, _ = invoke(decision(valuation_request=final_request), inputs)
        published = prepare_report_state({**inputs, **updates})
        assert published["shared_valuation_scenarios"]["rows"][0]["result"]["target"] == "40"
        assert published["target_validation"]["target"] == expected


def test_unclosed_model_fence_cannot_swallow_shared_scenario_section(tmp_path):
    from tradingagents.reporting import write_report_tree

    inputs = report_state()
    inputs["financial_claim_validation"]["raw_report"] = "Research\n```disclosures\n["
    write_report_tree(inputs, "DOCN", tmp_path)
    html = (tmp_path / "complete_report.html").read_text()
    import re
    assert re.search(r"<h[1-6][^>]*>Shared valuation scenarios", html)


def test_forward_shared_rows_render_own_capital_and_replay_comparison(monkeypatch):
    from tests.test_valuation_comparison import state as quoted_state
    from tests.test_valuation_funding import request as funding_request
    low, high = funding_request(), funding_request(equity_proceeds=200, equity_issue_price=20)
    for raw in (low, high):
        raw['scenarios'][0]['multiple_assumption_date'] = '2026-10-19'
    inputs = state([{'name': 'No issuance', 'request': low}, {'name': 'Equity funded', 'request': high}])
    inputs.update(quoted_state(monkeypatch))
    record = prepare_shared_valuation(inputs)
    assert record['status'] == 'available', record
    assert all(row['comparison']['status'] == 'available' for row in record['rows'])
    text = render_shared_valuation(record)
    assert 'net obligations None' not in text and 'None actual common shares' not in text
    assert '110' in text and '270' in text
    assert '2027-12-31' in text and '2026-10-19' in text and 'Conditional scenario comparison' in text
    record['rows'][0]['comparison']['rows'][0]['implied_multiple'] = '999'
    replay = prepare_shared_valuation(inputs, record['requests'])
    assert replay['rows'][0]['comparison']['rows'][0]['implied_multiple'] != '999'


def test_unfunded_shared_row_preserves_bridge_without_price_or_return():
    from tests.test_valuation_funding import request as funding_request
    raw = funding_request(cash_capex=500)
    record = prepare_shared_valuation(state([{'name': 'Unfunded', 'request': raw}]))
    assert record['status'] == 'partial' and len(record['rows']) == 1
    row = record['rows'][0]
    assert row['result']['target'] is None
    assert row['result']['scenario_results'][0]['funding_gap'] == '350'
    assert row['comparison']['status'] == 'unavailable' and not row['comparison']['rows']
    text = render_shared_valuation(record)
    assert '350' in text and '-350' in text and 'funding' in text.lower()
    assert '= 30.5' not in text  # unfinanced arithmetic is not a published price
    assert 'None USD/shares' not in text and 'net obligations None' not in text


def test_shared_rows_with_different_decision_dates_are_not_comparable():
    low, high = ev_request(), ev_request()
    low.update(decision_date='2027-01-19', rerating_assumption='Results catalyst.')
    high.update(decision_date='2027-04-19', rerating_assumption='Results catalyst.')
    record = prepare_shared_valuation(state([{'name': 'Three months', 'request': low},
                                           {'name': 'Six months', 'request': high}]))
    assert record['status'] == 'unavailable' and not record['rows']


def test_undated_shared_arithmetic_keeps_comparison_explicitly_unavailable():
    record = prepare_shared_valuation(state([{'name': 'Legacy', 'request': ev_request()}]))
    assert record['status'] == 'unavailable' and not record['rows']
    assert record['requests'][0]['request'] == ev_request()
    assert 'Legacy revenue case lacks' in render_shared_valuation(record)


def test_explicit_empty_proposal_is_distinct_from_malformed_payload():
    result = prepare_shared_valuation(state([]))
    assert result['reasons'] == ['No valuation scenarios were proposed; no numerical sensitivity published.']
    malformed = state([])
    malformed['financial_claim_validation']['raw_report'] = '```valuation_scenarios\n[broken\n```'
    assert 'malformed' in prepare_shared_valuation(malformed)['reasons'][0]
