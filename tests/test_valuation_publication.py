from tests.test_valuation import evidence
from tests.test_valuation_comparison import state
from tests.test_valuation_funding import request
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.schemas import render_target_result
from tradingagents.agents.valuation import validate_target


def test_forward_render_uses_own_capital_and_no_undated_target():
    result = validate_target(request(), evidence())
    rendered = render_target_result(result)
    assert '**Conditional valuation sensitivity**' in rendered
    assert 'net obligations None' not in rendered
    assert '2027-12-31' in rendered and '70' in rendered
    assert 'Closing cash' in rendered and 'Funding gap' in rendered


def test_publication_replays_price_comparison(monkeypatch):
    current = state(monkeypatch)
    raw = request()
    raw['scenarios'][0]['multiple_assumption_date'] = '2026-10-19'
    current.update(evidence_quality={'status': 'limited'}, portfolio_rating='Buy',
                   target_validation={'request': raw, 'target': '99999'},
                   valuation_price_comparison={'status': 'available', 'rows': [{'price': 99999}]})
    result = enforce_publication(current)
    assert result['valuation_price_comparison']['status'] == 'available'
    assert '99999' not in result['final_trade_decision']
    assert 'What the price implies' in result['final_trade_decision']


def test_review_clears_stale_price_comparison():
    public = enforce_publication({'evidence_quality': {'status': 'insufficient', 'checks': []},
                                  'valuation_price_comparison': {'status': 'available', 'rows': [{'price': 99999}]}})
    assert public['valuation_price_comparison']['status'] == 'unavailable'


def test_funding_gap_final_render_keeps_bridge_without_price():
    result = validate_target(request(cash_capex=500), evidence())
    assert result.status == 'unsupported'
    rendered = render_target_result(result)
    assert 'Funding gap' in rendered and '350' in rendered
    assert 'Closing cash' in rendered and '-350' in rendered
    assert '**Conditional valuation sensitivity**' not in rendered


def test_explicit_horizon_with_undated_multiple_remains_sensitivity():
    raw = request()
    raw.update(decision_date='2028-01-31', rerating_assumption='Illustrative delayed rerating')
    rendered = render_target_result(validate_target(raw, evidence()))
    assert '**Conditional valuation sensitivity**' in rendered


def test_decision_card_survives_reexport_and_keeps_trader_provisional(monkeypatch):
    current = state(monkeypatch)
    current.update(evidence_quality={'status': 'limited'}, final_rating='Underweight',
                   trader_investment_plan='**Action**: Sell\nFINAL TRANSACTION PROPOSAL: **SELL**')
    public = {**current, **enforce_publication(current)}
    assert public['decision_context']['rating'] == 'Underweight'
    assert public['decision_context']['trader_provisional'] == 'Sell'
    assert 'Research decision card' in public['final_trade_decision']
    assert {**public, **enforce_publication(public)} == public


def test_b_report_artifacts_keep_replayed_card_and_comparison(monkeypatch, tmp_path):
    import json

    from tradingagents.reporting import write_report_tree
    current = state(monkeypatch)
    raw = request()
    raw['scenarios'][0]['multiple_assumption_date'] = '2026-10-19'
    current.update(evidence_quality={'status': 'limited'}, final_rating='Underweight',
                   target_validation={'request': raw})
    write_report_tree(current, 'DOCN', tmp_path)
    evidence_json = json.loads((tmp_path / 'evidence.json').read_text())
    assert evidence_json['decision_context']['rating'] == 'Underweight'
    assert evidence_json['valuation_price_comparison']['status'] == 'available'
    for name in ('complete_report.md', 'complete_report.html'):
        text = (tmp_path / name).read_text()
        assert 'Research decision card' in text and 'What the price implies' in text
        assert 'Conditional valuation sensitivity' in text and 'Closing cash' in text
