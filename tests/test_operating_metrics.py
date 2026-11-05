"""Operating comparisons use matching discrete periods, not adjacent quarters or headlines."""
from datetime import date
from decimal import Decimal

from tradingagents.agents.operating_metrics import operating_metrics
from tradingagents.dataflows.financial_evidence import (
    EvidencePackage,
    FinancialFact,
    SourceRecord,
    add_period_calculations,
)


def fact(key, metric, value, start, end, **updates):
    return FinancialFact(fact_id=key, metric=metric, value=value, period_start=start, period_end=end,
                         as_of='2026-11-04', cik='0001582961', unit='USD', source_ids=('s',), locator=key,
                         **updates)


def package(*facts):
    source = SourceRecord(source_id='s', cik='0001582961', url='https://www.sec.gov/fixture',
        filed_date='2026-11-03', retrieved_at='2026-11-04T12:00:00Z', content_hash='a'*64,
        locator='exact statement values', accession='0001582961-26-000001', form='10-Q')
    return EvidencePackage(cik='0001582961', as_of='2026-11-04', sources=(source,), facts=facts)


def regular():
    return package(fact('revenue', 'Revenue', '321200000', '2026-07-01', '2026-09-30'),
        fact('prior', 'Revenue', '230000000', '2025-07-01', '2025-09-30'),
        fact('operating', 'Operating Income', '32120000', '2026-07-01', '2026-09-30'),
        fact('net', 'Net Income', '-16060000', '2026-07-01', '2026-09-30'))


def test_exact_yoy_and_margins_include_periods_and_input_lineage():
    outcomes = operating_metrics(regular())
    assert [o.status for o in outcomes] == ['pass'] * 3
    assert abs(outcomes[0].result - Decimal('39.65217391304347826086956522')) < Decimal('0.000000000001')
    assert [o.result for o in outcomes[1:]] == [Decimal('10'), Decimal('-5')]
    assert all(o.unit == 'percent' and 'Derived' in o.message and '2026-07-01' in o.message for o in outcomes)
    assert outcomes[0].input_fact_ids == ('revenue', 'prior')
    assert outcomes[1].input_fact_ids == ('operating', 'revenue')


def test_previous_quarter_or_cumulative_period_is_not_a_yoy_comparator():
    p = regular()
    for replacement in [fact('prior', 'Revenue', '230000000', '2026-04-01', '2026-06-30'),
                        fact('prior', 'Revenue', '690000000', '2025-01-01', '2025-09-30')]:
        modified = p.model_copy(update={'facts': tuple(replacement if f.fact_id == 'prior' else f for f in p.facts)})
        outcome = operating_metrics(modified)[0]
        assert outcome.status == 'unavailable' and outcome.result is None


def test_zero_missing_and_conflicting_values_stay_unavailable():
    p = regular()
    for value in (Decimal(0), None):
        prior = p.facts[1].model_copy(update={'value': value, 'missing_reason': 'not retrieved' if value is None else None})
        outcomes = operating_metrics(p.model_copy(update={'facts': (p.facts[0], prior, *p.facts[2:])}))
        assert outcomes[0].status == 'unavailable'
    conflict = p.facts[0].model_copy(update={'fact_id': 'conflict', 'value': Decimal('321000000')})
    assert all(o.status == 'unavailable' for o in operating_metrics(p.model_copy(update={'facts': (*p.facts, conflict)})))


def test_different_currency_basis_or_period_cannot_make_a_margin():
    p = regular()
    for update in ({'unit': 'EUR'}, {'basis': 'management-adjusted'}, {'period_start': date(2026, 1, 1)}):
        changed = p.facts[2].model_copy(update=update)
        outcomes = operating_metrics(p.model_copy(update={'facts': (*p.facts[:2], changed, p.facts[3])}))
        assert outcomes[1].status == 'unavailable'


def test_validated_ytd_difference_is_a_standalone_quarter_with_lineage():
    p = package(fact('curr9', 'Revenue', '900', '2026-01-01', '2026-09-30'),
                fact('curr6', 'Revenue', '600', '2026-01-01', '2026-06-30'),
                fact('prior9', 'Revenue', '750', '2025-01-01', '2025-09-30'),
                fact('prior6', 'Revenue', '500', '2025-01-01', '2025-06-30'))
    enriched = add_period_calculations(p)
    outcome = operating_metrics(enriched)[0]
    assert outcome.status == 'pass' and outcome.result == Decimal('20')
    by_id = {f.fact_id: f for f in enriched.facts}
    assert all(by_id[i].origin == 'derived' and by_id[i].input_fact_ids for i in outcome.input_fact_ids)


def test_leap_year_comparable_quarter_uses_calendar_dates_not_fixed_day_count():
    p = package(fact('current', 'Revenue', '110', '2024-01-01', '2024-03-31'),
                fact('prior', 'Revenue', '100', '2023-01-01', '2023-03-31'))
    outcome = operating_metrics(p)[0]
    assert outcome.status == 'pass' and outcome.result == Decimal('10')
