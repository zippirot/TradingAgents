"""Replayable dated-price comparisons, never probability or timing predictions."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from html import escape

from tradingagents.agents.valuation import TargetResult, validate_target
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.financial_evidence import EvidencePackage
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.price_observation import validate_price_observation


def _unavailable(reason):
    return {'status': 'unavailable', 'reason': reason, 'rows': []}


def compare_valuation(state: dict, result: TargetResult, request) -> dict:
    """Recalculate saved requests and revalidate the retained quote; never fetch.

    ``result`` is accepted for caller compatibility, but persisted calculated
    values are not authority. Only the replayed request/evidence supplies numbers.
    """
    try:
        package = EvidencePackage.model_validate(state.get('financial_evidence'))
        if str(package.as_of) != state.get('trade_date'):
            raise ValueError('Financial evidence and analysis date differ')
        result = validate_target(request, package, grounded_outlooks(state))
        if result.status != 'supported':
            return _unavailable('; '.join(result.reasons) or 'Supported valuation unavailable')
        if ((result.method == 'ev_revenue' and any(s.multiple_assumption_date is None for s in result.scenario_results))
                or (result.method == 'pe' and result.multiple_assumption_date is None)):
            return _unavailable('Undated multiple assumption: arithmetic remains a conditional sensitivity; dated price/reverse comparison unavailable.')
        saved_quote = state.get('price_observation') or {}
        if saved_quote.get('status') == 'unavailable':
            return _unavailable(saved_quote.get('reason') or 'Dated price unavailable')
        ticker = state.get('company_of_interest') or state.get('ticker')
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError('Run ticker unavailable for price identity validation')
        ticker = normalize_symbol(ticker)
        identity = state.get('issuer_identity') or {}
        if (not isinstance(identity, dict)
                or identity.get('ticker') != ticker
                or identity.get('cik') != package.cik
                or identity.get('as_of') != str(package.as_of)
                or identity.get('source') != 'SEC issuer map'):
            raise ValueError('Verified issuer identity does not bind these financial facts to the price ticker')
        quote = validate_price_observation(saved_quote, ticker, package.as_of)
        if result.unit != quote['currency'] + '/shares':
            raise ValueError('Price and valuation currencies or share units differ')
        observed = Decimal(quote['close'])
        quote_date = date.fromisoformat(quote['session_date'])
        if result.method == 'ev_revenue':
            anchor = result.capital_snapshot_date
        else:
            identifier = request.eps_fact_id if hasattr(request, 'eps_fact_id') else request.get('eps_fact_id')
            fact = next((f for f in package.facts if f.fact_id == identifier), None)
            anchor = fact.period_end if fact else None
        if anchor is None or anchor > quote_date:
            raise ValueError('Source share-basis date is unavailable or later than observed price')
        if (not quote['coverage_complete'] or date.fromisoformat(quote['coverage_start']) > anchor
                or date.fromisoformat(quote['coverage_end']) < quote_date):
            raise ValueError('Insufficient split coverage from original capital/share-basis date to quote')
        # Today's observed split may already adjust yesterday's completed close,
        # even while today's session remains incomplete. Check through the cutoff.
        if any(anchor < date.fromisoformat(s['session_date']) <= package.as_of and Decimal(s['ratio']) != 1
               for s in quote['splits']):
            raise ValueError('Observed split after original capital/share-basis date; comparison unavailable without a validated restated share basis')
        rows = []
        with localcontext() as context:
            context.prec = 60
            if result.method == 'ev_revenue':
                for scenario in result.scenario_results:
                    shares = scenario.shares_outstanding
                    obligations = scenario.net_obligations
                    if (shares is None or shares <= 0 or obligations is None or scenario.capital_date is None
                            or scenario.revenue <= 0 or scenario.multiple <= 0 or scenario.funding_gap):
                        raise ValueError('Complete funded scenario capital and positive valuation inputs required')
                    implied_ev = observed * shares + obligations
                    rows.append({
                        'name': scenario.name, 'method': result.method,
                        'multiple_assumption_date': str(scenario.multiple_assumption_date),
                        'scenario_price': str(scenario.price),
                        'conditional_return_percent': str(100 * (scenario.price / observed - 1)),
                        'price_date': quote['session_date'], 'capital_date': str(scenario.capital_date),
                        'forecast_start': str(scenario.forecast_period_start), 'forecast_end': str(scenario.forecast_period_end),
                        'shares_outstanding': str(shares), 'net_obligations': str(obligations),
                        'implied_enterprise_value': str(implied_ev),
                        'implied_multiple': str(implied_ev / scenario.revenue),
                        'implied_revenue': str(implied_ev / scenario.multiple),
                        'assumed_multiple': str(scenario.multiple), 'forecast_revenue': str(scenario.revenue),
                        'assumptions': list(scenario.funding_assumptions),
                    })
            elif result.method == 'pe':
                if result.earnings_value is None or result.earnings_value <= 0 or result.target is None:
                    raise ValueError('Positive compatible earnings required for implied P/E')
                rows.append({'name': 'P/E', 'method': result.method, 'scenario_price': str(result.target),
                             'conditional_return_percent': str(100 * (result.target / observed - 1)),
                             'price_date': quote['session_date'], 'capital_date': None,
                             'forecast_start': str(result.valuation_period_start), 'forecast_end': str(result.valuation_period_end),
                             'implied_pe': str(observed / result.earnings_value),
                             'eps_basis': result.eps_basis, 'accounting_basis': result.accounting_basis,
                             'multiple_assumption_date': str(result.multiple_assumption_date),
                             'assumptions': list(result.assumptions)})
            else:
                raise ValueError('Valuation method has no supported comparison')
        if not rows:
            raise ValueError('No supported valuation rows')
        later_capital = any(r['capital_date'] and result.decision_date and
                            date.fromisoformat(r['capital_date']) > result.decision_date for r in rows)
        linked = result.decision_date is not None and bool(result.rerating_assumption) and not later_capital
        note = ('Explicit rerating assumption links these conditional values to the decision date; this is not a calibrated forecast.'
                if linked else 'Conditional sensitivity only: no dated rerating link is supplied, or projected capital occurs after the decision date. No discounting or near-term target is inferred.')
        return {'status': 'available', 'reason': None, 'rows': rows,
                'label': 'conditional decision-date scenario' if linked else 'conditional sensitivity',
                'decision_date': str(result.decision_date) if result.decision_date else None,
                'rerating_assumption': result.rerating_assumption, 'horizon_note': note,
                'weight_rationale': result.weight_rationale,
                'price': {k: quote[k] for k in ('close', 'currency', 'session_date', 'session_status',
                                                'adjustment_basis', 'source_id', 'url', 'content_hash')},
                'assumptions': list(result.assumptions),
                'limitations': ['Conditional price differences are not expected returns or calibrated probabilities.',
                                'No discounting applied; future financial periods remain distinct from decision dates.']}
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        return _unavailable(str(exc))


def _cell(value):
    return escape(' '.join(str(value).split())).replace('|', r'\|')


def display_number(value):
    """Bound presentation precision only; preserve tiny nonzero/large magnitudes."""
    if value is None:
        return 'unavailable'
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if not number.is_finite():
        return 'unavailable'
    if number and (abs(number) < Decimal('0.01') or abs(number) >= Decimal('1e12')):
        return f'{number:.2E}'
    return f'{number:.2f}'


_number = display_number


def render_valuation_comparison(record: dict) -> str:
    """Render only a freshly replayed comparison supplied by the caller."""
    lines = ['### What the price implies', '']
    if not record or record.get('status') != 'available':
        return '\n'.join(lines + ['Unavailable: ' + _cell((record or {}).get('reason', 'Dated comparison unavailable.'))])
    quote = record['price']
    lines += [f"Observed {_cell(display_number(quote['close']))} {_cell(quote['currency'])} on {_cell(quote['session_date'])} ({_cell(quote['session_status'])}); {_cell(record['label'])}.",
              _cell(record['horizon_note']),
              f"Decision date: {_cell(record.get('decision_date') or 'not specified')}; rerating assumption: {_cell(record.get('rerating_assumption') or 'not supplied')}.", '',
              'Scenario | Financial period | Capital date | Multiple assumption date | Conditional price | Conditional difference % | Price implies',
              '--- | --- | --- | --- | ---: | ---: | ---']
    for row in record['rows']:
        implied = (f"EV/revenue {_number(row['implied_multiple'])}×; revenue {_number(row['implied_revenue'])} at {_number(row['assumed_multiple'])}×"
                   if row['method'] == 'ev_revenue' else f"P/E {_number(row['implied_pe'])}× ({row['eps_basis']}, {row['accounting_basis']})")
        lines.append(' | '.join(_cell(v) for v in (row['name'], f"{row['forecast_start']} to {row['forecast_end']}",
                     row['capital_date'] or 'not applicable', row['multiple_assumption_date'], _number(row['scenario_price']),
                     _number(row['conditional_return_percent']), implied)))
    if record.get('weight_rationale'):
        lines += ['', 'Subjective weight rationale: ' + _cell(record['weight_rationale'])]
    lines += ['', *(_cell(item) for item in record['limitations']),
              f"Price source: {_cell(quote['url'])}; {_cell(quote['adjustment_basis'])}."]
    return '\n'.join(lines)
