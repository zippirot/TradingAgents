"""Forward funding arithmetic uses actual shares, without invented funding."""
from copy import deepcopy
from decimal import Decimal

import pytest

from tests.test_valuation import ev_request, evidence
from tradingagents.agents.valuation import validate_target


def change(**updates):
    return {'cash_proceeds': 0, 'fees': 0, 'noncash_additions': 0, 'principal_payments': 0,
                'converted_principal': 0, 'conversion_price': None} | updates


def request(**updates):
    raw = ev_request()
    raw['capital_structure_assumption'] = 'forward_capital_v1'
    raw['scenarios'][0]['funding'] = {
        'version': 'forward_capital_v1', 'unit': 'USD', 'period_start': '2026-07-01',
        'capital_date': '2027-12-31', 'operating_cash_flow': 50,
        'operating_cash_flow_basis': 'after_interest_and_operating_lease_payments',
        'cash_capex': 80, 'acquisitions': 0, 'equity_proceeds': 0, 'equity_fees': 0,
        'equity_issue_price': None, 'other_dilution_shares': 0,
        'obligation_changes': {'borrowings': change()},
        'operating_assumptions': 'Revenue and margins remain analyst assumptions.',
        'cash_conversion_rationale': '50 cash after interest and operating lease payments over the full bridge interval.',
        'funding_rationale': 'No other funding assumed.',
    } | updates
    return raw


def result(raw=None):
    value = validate_target(raw or request(), evidence())
    assert value.status == 'supported', value.reasons
    return value.scenario_results[0]


def test_forward_no_issuance_and_legacy_snapshot_are_distinct():
    r = result()
    assert (r.closing_cash, r.closing_obligations, r.shares_outstanding) == (70, 200, 100)
    assert r.net_obligations == 130 and r.price == Decimal('34.7')
    assert r.funding_gap == 0 and str(r.capital_date) == '2027-12-31'
    legacy = result(ev_request())
    assert legacy.net_obligations == 100 and legacy.shares_outstanding == 100
    assert str(legacy.capital_date) == '2026-06-30'


def test_equity_funding_fees_and_other_dilution_are_not_eps_denominators():
    r = result(request(equity_proceeds=200, equity_fees=10, equity_issue_price=20, other_dilution_shares=5))
    assert r.closing_cash == 260 and r.shares_outstanding == 115
    assert r.net_obligations == -60
    assert abs(r.price - Decimal(3660)/115) < Decimal('1e-25')


def test_borrowing_repayment_and_conversion_reduce_debt_once():
    r = result(request(obligation_changes={'borrowings': change(cash_proceeds=100, fees=5,
                       principal_payments=50, converted_principal=100, conversion_price=20)}))
    assert (r.closing_cash, r.closing_obligations, r.shares_outstanding) == (115, 150, 105)
    assert r.net_obligations == 35


def test_lease_additions_are_noncash_and_operating_principal_not_deducted_twice():
    raw = request(obligation_changes={
        'borrowings': change(), 'finance_leases': change(noncash_additions=40, principal_payments=5),
        'equipment': change(), 'operating_leases': change(noncash_additions=20, principal_payments=10)})
    raw.update(perimeter='all_leases', multiple_perimeter='all_leases',
               obligation_ids_by_category={'borrowings': ['debt'], 'finance_leases': ['finance'],
                                            'equipment': ['equipment'], 'operating_leases': ['operating']})
    r = result(raw)
    assert r.closing_cash == 65  # operating lease payments already in CFO
    assert r.closing_obligations == 305


def test_shortfall_is_visible_without_cash_plug():
    target = validate_target(request(cash_capex=500), evidence())
    assert target.status == 'unsupported' and target.target is None
    assert any('shortfall' in reason for reason in target.reasons)
    r = target.scenario_results[0]
    assert r.closing_cash == -350 and r.funding_gap == 350
    assert r.closing_obligations == 200 and r.shares_outstanding == 100
    assert r.net_obligations == 550
    assert any('shortfall' in a.lower() for a in r.funding_assumptions)


@pytest.mark.parametrize('update', [
    {'unit': 'EUR'}, {'period_start': '2026-10-20'}, {'capital_date': '2027-06-30'},
    {'equity_proceeds': 100}, {'equity_fees': 1}, {'equity_issue_price': 0},
    {'obligation_changes': {}}, {'cash_conversion_rationale': ' '},
    {'obligation_changes': {'borrowings': change(principal_payments=150, converted_principal=100, conversion_price=10)}},
    {'obligation_changes': {'borrowings': change(noncash_additions=100)}},
    {'operating_cash_flow_basis': 'before_operating_lease_payments'},
])
def test_incomplete_incompatible_or_double_counted_funding_is_unsupported(update):
    assert validate_target(request(**update), evidence()).status == 'unsupported'


def test_snapshot_request_cannot_silently_ignore_funding_and_forward_requires_every_row():
    raw = request()
    raw['capital_structure_assumption'] = 'unchanged_from_snapshot'
    assert validate_target(raw, evidence()).status == 'unsupported'
    raw = request()
    raw['scenarios'][0].pop('funding')
    assert validate_target(raw, evidence()).status == 'unsupported'


def test_independent_scenarios_have_independent_projected_capital():
    raw = request()
    second = deepcopy(raw['scenarios'][0])
    second['name'] = 'Funded'
    second['funding'].update(equity_proceeds=200, equity_issue_price=20)
    raw['scenarios'][0]['weight'] = second['weight'] = '0.5'
    raw['scenarios'].append(second)
    raw['weight_rationale'] = 'Equal illustrative subjective weights.'
    r = validate_target(raw, evidence())
    assert r.status == 'supported', r.reasons
    assert r.shares_outstanding is None and r.net_obligations is None
    assert [s.shares_outstanding for s in r.scenario_results] == [100, 110]


def test_negative_equity_guard_and_actual_share_basis_still_apply():
    assert validate_target(request(cash_capex=10000), evidence()).status == 'unsupported'
    assert validate_target(request(), evidence(shares={'metric': 'Diluted Weighted Average Shares'})).status == 'unsupported'


@pytest.mark.parametrize('movement', [change(cash_proceeds=10), change(converted_principal=10, conversion_price=5)])
def test_lease_additions_cannot_create_free_cash_or_conversion_shares(movement):
    raw = request(obligation_changes={'borrowings': change(), 'finance_equipment': movement})
    raw.update(perimeter='finance_equipment', multiple_perimeter='finance_equipment',
               obligation_ids_by_category={'borrowings': ['debt'], 'finance_equipment': ['finance', 'equipment']})
    assert validate_target(raw, evidence()).status == 'unsupported'


def test_funding_model_copy_and_saved_calculations_cannot_override_inputs():
    from tradingagents.agents.valuation import EVRevenueTarget
    raw = EVRevenueTarget.model_validate(request())
    bad_funding = raw.scenarios[0].funding.model_copy(update={'equity_proceeds': Decimal('-10')})
    bad_scenario = raw.scenarios[0].model_copy(update={'funding': bad_funding})
    assert validate_target(raw.model_copy(update={'scenarios': (bad_scenario,)}), evidence()).status == 'unsupported'
    saved = validate_target(request(), evidence()).model_dump(mode='json')
    saved['scenario_results'][0]['closing_cash'] = '999999'
    assert result(request()).closing_cash == 70


def test_any_unfunded_weighted_scenario_prevents_final_target_without_hiding_rows():
    raw = request()
    second = deepcopy(raw['scenarios'][0])
    second['name'] = 'Unfunded'
    second['funding']['cash_capex'] = 500
    raw['scenarios'][0]['weight'] = second['weight'] = '0.5'
    raw['scenarios'].append(second)
    raw['weight_rationale'] = 'Equal illustrative subjective weights.'
    value = validate_target(raw, evidence())
    assert value.status == 'unsupported' and value.target is None
    assert len(value.scenario_results) == 2
    assert [r.funding_gap for r in value.scenario_results] == [0, 350]


@pytest.mark.parametrize('rationale', [None, '', ' '])
def test_multiple_scenarios_require_explicit_weight_rationale(rationale):
    raw = request()
    second = deepcopy(raw['scenarios'][0])
    second['name'] = 'Second'
    raw['scenarios'][0]['weight'] = second['weight'] = '0.5'
    raw['scenarios'].append(second)
    if rationale is not None:
        raw['weight_rationale'] = rationale
    assert validate_target(raw, evidence()).status == 'unsupported'


def test_multiple_assumption_date_is_retained_and_cannot_be_future():
    from tests.test_valuation import pe_request
    for raw in (ev_request(), pe_request()):
        place = raw['scenarios'][0] if raw['method'] == 'ev_revenue' else raw
        place['multiple_assumption_date'] = '2026-10-20'
        assert validate_target(raw, evidence()).status == 'unsupported'
        place['multiple_assumption_date'] = '2026-10-19'
        value = validate_target(raw, evidence())
        assert value.status == 'supported', value.reasons
        retained = value.scenario_results[0] if value.method == 'ev_revenue' else value
        assert str(retained.multiple_assumption_date) == '2026-10-19'


def test_legacy_undated_sensitivity_remains_calculable_and_explicit():
    from tests.test_valuation import pe_request
    for raw in (ev_request(), pe_request()):
        value = validate_target(raw, evidence())
        assert value.status == 'supported', value.reasons
        assert any('undated' in warning.lower() for warning in value.warnings)
