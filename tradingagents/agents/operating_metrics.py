"""Derived operating comparisons over exact, already-validated canonical facts.

No headline lookup, period annualization or nearest-quarter substitution occurs
here. Unsupported fiscal-calendar shifts remain unavailable without an explicit
comparable-period contract.
"""
from __future__ import annotations

import calendar
from decimal import localcontext

from tradingagents.agents.accounting_checks import Calculation
from tradingagents.dataflows.financial_evidence import EvidencePackage

_ROLES = {'Revenue', 'Operating Income', 'Net Income'}
_METHODS = ('revenue_yoy_growth_v1', 'operating_margin_v1', 'net_margin_v1')


def _quarter(fact):
    return fact.period_start is not None and 60 <= (fact.period_end - fact.period_start).days + 1 <= 115


def _previous_year(day):
    year = day.year - 1
    return day.replace(year=year, day=min(day.day, calendar.monthrange(year, day.month)[1]))


def _select(package, metric, start, end):
    candidates = [f for f in package.facts if f.metric == metric and f.period_start == start
                  and f.period_end == end and f.value is not None]
    if not candidates:
        raise ValueError(f'{metric} missing for exact period {start} to {end}')
    if len({(f.unit, f.basis, f.cik, f.as_of, f.value) for f in candidates}) != 1:
        raise ValueError(f'{metric} has conflicting exact values, currency or accounting basis')
    return min(candidates, key=lambda f: (f.origin != 'reported', f.fact_id))


def operating_metrics(package: EvidencePackage) -> list[Calculation]:
    """Latest standalone quarter: revenue YoY, operating margin and net margin.

    Equal duplicate facts are harmless; differing values are not reconciled using
    an invented rounding tolerance. Validated YTD-difference facts retain their
    existing input lineage and may supply a standalone quarter.
    """
    quarters = [f for f in package.facts if f.metric in _ROLES and _quarter(f)]
    latest_end = max((f.period_end for f in quarters), default=None)
    latest = [f for f in quarters if f.period_end == latest_end]
    starts = {f.period_start for f in latest}
    if latest_end is None or len(starts) != 1:
        message = 'Latest standalone-quarter operating period is missing or conflicting; no YTD/annual fallback'
        return [Calculation(method=m, status='unavailable', input_fact_ids=tuple(f.fact_id for f in latest),
                            reason_code='operating_period_unavailable', message=message) for m in _METHODS]
    start = starts.pop()
    prior_start, prior_end = _previous_year(start), _previous_year(latest_end)
    outputs = []
    specifications = (
        (_METHODS[0], 'Revenue', start, latest_end, 'Revenue', prior_start, prior_end,
         f'Derived revenue YoY growth: {start} to {latest_end} versus {prior_start} to {prior_end}'),
        (_METHODS[1], 'Operating Income', start, latest_end, 'Revenue', start, latest_end,
         f'Derived operating margin: {start} to {latest_end}'),
        (_METHODS[2], 'Net Income', start, latest_end, 'Revenue', start, latest_end,
         f'Derived net margin: {start} to {latest_end}'),
    )
    for method, numerator_role, numerator_start, numerator_end, denominator_role, denominator_start, denominator_end, label in specifications:
        ids = []
        try:
            numerator = _select(package, numerator_role, numerator_start, numerator_end)
            ids.append(numerator.fact_id)
            denominator = _select(package, denominator_role, denominator_start, denominator_end)
            ids.append(denominator.fact_id)
            if ((numerator.unit, numerator.basis, numerator.cik, numerator.as_of)
                    != (denominator.unit, denominator.basis, denominator.cik, denominator.as_of)
                    or numerator.cik != package.cik or numerator.as_of != package.as_of
                    or len(numerator.unit) != 3 or not numerator.unit.isupper()):
                raise ValueError('Comparable currency, accounting basis, issuer and source cutoff required')
            if denominator.value == 0:
                raise ValueError('Nonzero denominator required; no inferred growth or margin')
            with localcontext() as context:
                context.prec = 50
                value = numerator.value / denominator.value
                if method == _METHODS[0]:
                    value -= 1
                value *= 100
            outputs.append(Calculation(method=method, status='pass', result=value, unit='percent',
                input_fact_ids=tuple(ids), reason_code='calculated', message=label + '; exact comparable canonical facts'))
        except (ValueError, ArithmeticError) as exc:
            outputs.append(Calculation(method=method, status='unavailable', input_fact_ids=tuple(ids),
                reason_code='operating_comparison_unavailable', message=label + ': ' + str(exc)))
    return outputs
