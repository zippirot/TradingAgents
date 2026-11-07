"""Replayable dated-price comparisons, never probability or timing predictions."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from html import escape

from tradingagents.agents.evidence_validation import obligation_checks
from tradingagents.agents.valuation import TargetResult, validate_target
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.disclosure_discovery import discover_disclosures
from tradingagents.dataflows.financial_evidence import EvidencePackage, derive_ttm
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.price_observation import validate_price_observation


def _unavailable(reason):
    return {'status': 'unavailable', 'reason': reason, 'rows': []}


def comparable_quote(state, package, unit, anchor):
    saved_quote = state.get('price_observation') or {}
    if saved_quote.get('status') == 'unavailable':
        raise ValueError(saved_quote.get('reason') or 'Dated price unavailable')
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
    if unit != quote['currency'] + '/shares':
        raise ValueError('Price and valuation currencies or share units differ')
    quote_date = date.fromisoformat(quote['session_date'])
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
    return quote


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
        if result.decision_use.suitability != 'conditional':
            return _unavailable('Decision-use suitability is not conditional: ' + result.decision_use.suitability)
        if ((result.method == 'ev_revenue' and any(s.multiple_assumption_date is None for s in result.scenario_results))
                or (result.method == 'pe' and result.multiple_assumption_date is None)):
            return _unavailable('Undated multiple assumption: arithmetic remains a conditional sensitivity; dated price/reverse comparison unavailable.')
        if result.method == 'ev_revenue':
            anchor = result.capital_snapshot_date
        else:
            identifier = request.eps_fact_id if hasattr(request, 'eps_fact_id') else request.get('eps_fact_id')
            fact = next((f for f in package.facts if f.fact_id == identifier), None)
            anchor = fact.period_end if fact else None
        quote = comparable_quote(state, package, result.unit, anchor)
        observed = Decimal(quote['close'])
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
                                                'adjustment_basis', 'source_id', 'url', 'content_hash', 'price_fallback') if k in quote},
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
    lines = ['### Conditional scenario comparison', '']
    if not record or record.get('status') != 'available':
        return '\n'.join(lines + ['Unavailable: ' + _cell((record or {}).get('reason', 'Dated comparison unavailable.'))])
    quote = record['price']
    lines += [f"Observed {_cell(display_number(quote['close']))} {_cell(quote['currency'])} on {_cell(quote['session_date'])} ({_cell(quote['session_status'])}); {_cell(record['label'])}.",
              _cell(record['horizon_note']),
              f"Decision date: {_cell(record.get('decision_date') or 'not specified')}; rerating assumption: {_cell(record.get('rerating_assumption') or 'not supplied')}.", '',
              'Scenario | Financial period | Capital date | Multiple assumption date | Conditional price | Conditional difference % | Price implies',
              '--- | --- | --- | --- | ---: | ---: | ---']
    if record.get('price', {}).get('price_fallback'):
        fallback = record['price']['price_fallback']
        lines.insert(2, "Price fallback: " + _cell(fallback['reason']) + "; latest completed session " +
                     _cell(fallback['latest_completed_session_date']) + "; selected " +
                     _cell(fallback['selected_session_date']) + ".")
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


def _price_implied_unavailable(reason, status='unavailable'):
    return {'status': status, 'reason': reason, 'rows': []}


def _decimal_text(value):
    rendered = format(value, 'f')
    return rendered.rstrip('0').rstrip('.') if '.' in rendered else rendered


def _capital_basis_date(package, quote):
    capital = quote.get('capital_snapshot_date')
    if not capital:
        raise ValueError('Dated capital basis unavailable')
    when = date.fromisoformat(capital)
    if when > date.fromisoformat(quote['session_date']):
        raise ValueError('Capital basis postdates observed close')
    if (not quote['coverage_complete'] or date.fromisoformat(quote['coverage_start']) > when
            or date.fromisoformat(quote['coverage_end']) < date.fromisoformat(quote['session_date'])):
        raise ValueError('Split coverage does not span capital basis to completed close')
    if any(when < date.fromisoformat(item['session_date']) <= package.as_of
           and Decimal(item['ratio']) != 1 for item in quote['splits']):
        raise ValueError('Split after capital snapshot makes share basis incompatible')
    return when


def _selected_shares(package, when):
    matches = [f for f in package.facts if f.metric == 'Common Shares Outstanding'
               and f.period_start is None and f.period_end == when and f.unit == 'shares'
               and f.value is not None and f.value > 0]
    if len(matches) != 1:
        return None
    return matches[0]


def _trailing_revenue(package, price_date, currency):
    by_id = {f.fact_id: f for f in package.facts}
    candidates = []
    for fact in package.facts:
        if (fact.metric != 'Revenue' or fact.formula_id != 'four_quarter_sum_v1'
                or fact.unit != currency or fact.period_end > price_date or fact.value is None):
            continue
        try:
            replayed = derive_ttm(tuple(by_id[i] for i in fact.input_fact_ids))
        except (KeyError, ValueError, ArithmeticError):
            continue
        if replayed == fact and fact.value > 0:
            candidates.append(fact)
    if not candidates:
        return None
    latest = max(f.period_end for f in candidates)
    matches = [f for f in candidates if f.period_end == latest]
    return matches[0] if len(matches) == 1 else None


def _source_only_claims(state, package, currency):
    """Return source-bound management claims, never analyst-proposed extraction."""
    if currency != 'USD':
        return {}
    source_by_id = {s.source_id: s for s in package.sources}
    disclosure = state.get('disclosure_evidence')
    if not isinstance(disclosure, dict):
        return {}
    packages = disclosure.get('packages') or ()
    if not isinstance(packages, (list, tuple)):
        return {}
    trusted = {}
    blocked = set()
    locators = {}
    for raw in packages:
        if not isinstance(raw, dict):
            continue
        for doc in raw.get('documents') or ():
            if not isinstance(doc, dict):
                continue
            source_id = doc.get('source_id')
            source = source_by_id.get(source_id)
            if source is None or source_id in blocked:
                continue
            filing = doc.get('filing') or {}
            if not isinstance(filing, dict):
                blocked.add(source_id)
                trusted.pop(source_id, None)
                continue
            identity = (doc.get('url'), doc.get('content_hash'), filing)
            valid = (raw.get('cik') == package.cik and raw.get('as_of') == str(package.as_of)
                     and filing.get('cik') == package.cik
                     and filing.get('filed_date') == str(source.filed_date)
                     and source.filed_date <= package.as_of
                     and (source.url, source.content_hash, source.accession, source.form, str(source.filed_date))
                     == (doc.get('url'), doc.get('content_hash'), filing.get('accession'),
                         filing.get('form'), filing.get('filed_date')))
            if not valid or (source_id in trusted and trusted[source_id][0] != identity):
                blocked.add(source_id)
                trusted.pop(source_id, None)
                continue
            blocks = locators.setdefault(source_id, {})
            for block in doc.get('blocks') or ():
                if not isinstance(block, dict) or not isinstance(block.get('locator'), str):
                    blocked.add(source_id)
                    break
                locator = block['locator']
                if locator in blocks and blocks[locator] != block:
                    blocked.add(source_id)
                    break
                blocks[locator] = block
            if source_id in blocked:
                trusted.pop(source_id, None)
                continue
            if source_id not in trusted:
                trusted[source_id] = (identity, [])
            trusted[source_id][1].append({**raw, 'documents': [doc]})
    if not trusted:
        return {}
    validated = []
    for _, source_packages in trusted.values():
        for source_package in source_packages:
            try:
                discovered = discover_disclosures((source_package,))
            except (ValueError, TypeError, KeyError):
                continue
            for claim in discovered.claims:
                if claim not in validated:
                    validated.append(claim)
    year = package.as_of.year
    wanted = {
        'revenue': ('Total revenue', f'full year {year}', 'guidance', 'exact'),
        'guided_shares': ('Fully diluted weighted average shares outstanding',
                          f'fourth quarter ending December 31, {year}', 'guidance', 'exact', 'million shares'),
        'growth_floor': ('revenue growth', str(year + 1), 'guidance', 'at_least', '%'),
    }
    claims = {}
    for name, spec in wanted.items():
        matches = [c for c in validated
                   if ((c.metric, c.period, c.kind, c.comparator) == spec if name == 'revenue'
                       else (c.metric, c.period, c.kind, c.comparator, c.unit) == spec)
                   and c.source_id in trusted and c.value > 0 and (c.upper_value is None or c.upper_value >= c.value)]
        if name == 'revenue':
            matches = [c for c in matches if c.unit in {'million', 'billion'}
                       and '$' in c.quote and c.upper_value is not None]
        elif name == 'guided_shares':
            matches = [c for c in matches if c.upper_value is not None]
        if len(matches) == 1:
            claims[name] = matches[0]
    return claims


def price_implied_valuation(state: dict) -> dict:
    """Build source-only price-implied multiples independently of model targets."""
    if state.get('asset_type', 'stock') != 'stock':
        return _price_implied_unavailable('Price-implied stock revenue multiples do not apply to this asset.', 'not_applicable')
    try:
        package = EvidencePackage.model_validate(state.get('financial_evidence'))
        if str(package.as_of) != state.get('trade_date'):
            raise ValueError('Financial evidence and analysis date differ')
        ticker = normalize_symbol(state['company_of_interest'])
        identity = state.get('issuer_identity') or {}
        if (identity.get('ticker') != ticker or identity.get('cik') != package.cik
                or identity.get('as_of') != str(package.as_of) or identity.get('source') != 'SEC issuer map'):
            raise ValueError('Verified issuer identity does not bind price and financial facts')
        saved = state.get('price_observation') or {}
        if saved.get('status') != 'available':
            raise ValueError(saved.get('reason') or 'Completed-session price unavailable')
        quote = validate_price_observation(saved, ticker, package.as_of)
        if quote['session_status'] != 'completed':
            raise ValueError('Completed-session price required')
        if quote['currency'] != 'USD':
            raise ValueError('Price/share currency compatibility unavailable')
        capital_date = _capital_basis_date(package, quote)
        shares = _selected_shares(package, capital_date)
        observed = Decimal(quote['close'])
        if observed <= 0:
            raise ValueError('Positive observed price required')
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        return _price_implied_unavailable(str(exc))

    with localcontext() as context:
        context.prec = 60
        equity = observed * shares.value if shares else None
        price_date = date.fromisoformat(quote['session_date'])
        trailing = _trailing_revenue(package, price_date, quote['currency'])
        claims = _source_only_claims(state, package, quote['currency'])
        guidance = claims.get('revenue')
        guided_shares = claims.get('guided_shares')
        growth = claims.get('growth_floor')
        guidance_scale = Decimal(1_000_000_000 if guidance and guidance.unit == 'billion' else 1_000_000)
        guidance_values = (guidance.value * guidance_scale,
                           guidance.upper_value * guidance_scale) if guidance else None
        share_values = (guided_shares.value * Decimal(1_000_000),
                        guided_shares.upper_value * Decimal(1_000_000)) if guided_shares else None
        if guidance_values and (guidance_values[0] <= 0 or guidance_values[1] < guidance_values[0]):
            guidance_values = None
        if share_values and (share_values[0] <= 0 or share_values[1] < share_values[0]):
            share_values = None
        precision = (state.get('filing_fact_extraction') or {}).get('rounding_quantum_by_fact')
        checks = obligation_checks(package, precision)
        by_id = {f.fact_id: f for f in package.facts}
        rows = []
        for name, check in zip(('borrowings_only', 'finance_equipment', 'all_classified_obligations'), checks, strict=True):
            row = {'perimeter': name, 'status': 'unavailable', 'reason': check.message,
                   'input_fact_ids': list(check.input_fact_ids), 'ratios': {}}
            selected = [by_id[i] for i in check.input_fact_ids if i in by_id]
            if (check.status == 'pass' and check.result is not None and check.unit == quote['currency']
                    and len(selected) == len(check.input_fact_ids)
                    and selected and all(f.period_end == capital_date for f in selected)):
                row.update(net_obligations_usd=str(check.result),
                               obligation_components=[{'metric': f.metric, 'value_usd': str(f.value),
                                                       'fact_id': f.fact_id, 'date': str(f.period_end)}
                                                      for f in selected[:-1]],
                               cash={'metric': selected[-1].metric, 'value_usd': str(selected[-1].value),
                                     'fact_id': selected[-1].fact_id, 'date': str(selected[-1].period_end)})
                numerator = equity + check.result if equity is not None else None
                if numerator is not None and numerator > 0:
                    row.update(status='available', reason=None, numerator_usd=str(numerator))
                    if trailing is not None:
                        row['ratios']['trailing_revenue'] = str(numerator / trailing.value)
                    if guidance_values:
                        low, high = guidance_values
                        row['ratios']['guidance_range'] = [str(numerator / high), str(numerator / low)]
                        if growth is not None and growth.value > 0:
                            row['ratios']['growth_floor_conditional_upper'] = str(
                                numerator / (low * (1 + growth.value / 100)))
                elif numerator is not None:
                    row['reason'] = 'Nonpositive obligation-adjusted numerator'
                else:
                    row['reason'] = 'Unique compatible dated outstanding-share fact unavailable'
                if share_values:
                    low_n = observed * share_values[0] + check.result
                    high_n = observed * share_values[1] + check.result
                    if low_n > 0:
                        sensitivity = {'numerator_range_usd': [str(low_n), str(high_n)], 'ratios': {}}
                        if trailing is not None:
                            sensitivity['ratios']['trailing_revenue_range'] = [
                                str(low_n / trailing.value), str(high_n / trailing.value)]
                        if guidance_values:
                            low, high = guidance_values
                            sensitivity['ratios']['guidance_range'] = [str(low_n / high), str(high_n / low)]
                            if growth is not None and growth.value > 0:
                                sensitivity['ratios']['growth_floor_conditional_upper'] = str(
                                    high_n / (low * (1 + growth.value / 100)))
                        row['guided_diluted_weighted_average_share_sensitivity'] = sensitivity
            elif check.status == 'pass':
                row['reason'] = 'Obligation and cash dates or currency differ from outstanding-share basis'
            rows.append(row)
        return {'status': 'available', 'reason': None, 'price': {k: quote[k] for k in
                    ('close', 'currency', 'session_date', 'session_status', 'exchange_timezone',
                     'retrieved_at', 'adjustment_basis', 'source_id', 'url', 'content_hash', 'price_fallback') if k in quote},
                'shares': {'value': str(shares.value), 'date': str(shares.period_end), 'fact_id': shares.fact_id,
                           'source_ids': list(shares.source_ids)} if shares else None,
                'capital_basis_date': str(capital_date),
                'equity_value_usd': str(equity) if equity is not None else None,
                'trailing_revenue_usd': str(trailing.value) if trailing else None,
                'trailing_revenue_period': [str(trailing.period_start), str(trailing.period_end)] if trailing else None,
                'trailing_revenue_fact_id': trailing.fact_id if trailing else None,
                'trailing_revenue_input_fact_ids': list(trailing.input_fact_ids) if trailing else [],
                'management_revenue_guidance_range_usd': [_decimal_text(x) for x in guidance_values] if guidance_values else None,
                'management_revenue_guidance_period': guidance.period if guidance else None,
                'guided_diluted_weighted_average_shares_range': [_decimal_text(x) for x in share_values] if share_values else None,
                'guided_share_period': guided_shares.period if guided_shares else None,
                'growth_floor_percent': str(growth.value) if growth else None,
                'growth_floor_period': growth.period if growth else None,
                'analysis_year': package.as_of.year,
                'disclosure_references': {name: {'source_id': claim.source_id, 'locator': claim.locator,
                    'period': claim.period, 'quote': claim.quote} for name, claim in claims.items()},
                'formulae': {
                    'equity_value': 'observed completed close * compatible dated shares outstanding',
                    'obligation_adjusted_value': 'equity value + listed obligations - dated unrestricted cash',
                    'trailing_revenue': 'sum four contiguous, compatible revenue quarters; never sum EPS or weighted shares',
                    'guidance_ratio_range': '[numerator / guidance high, numerator / guidance low]',
                    'guided_share_ratio_range': '[low-share numerator / revenue high, high-share numerator / revenue low]',
                    'growth_floor_conditional_upper': 'numerator / (declared guidance low * (1 + growth floor / 100)), only if guidance and fixed capital assumptions hold',
                },
                'rows': rows,
                'limitations': ['Completed close is dated, not an executable current quote.',
                                'Outstanding shares and obligation balances are dated; subsequent capital changes are unresolved.',
                                'Guidance is management forward-looking information, not realized revenue.',
                                'Q4 guided diluted weighted-average shares are a conditional sensitivity, not current shares outstanding.',
                                'These ratios do not establish fair value, expected return or a target.']}


def render_price_implied_valuation(record: dict) -> str:
    """Always show the independent section, including scoped unavailable reasons."""
    lines = ['### What the price implies', '']
    if record.get('status') != 'available':
        return '\n'.join(lines + ['Unavailable: ' + _cell(record.get('reason') or 'Source inputs unavailable')])
    price = record['price']
    guidance_period = record['management_revenue_guidance_period'] or f"full year {record['analysis_year']}"
    growth_period = record['growth_floor_period'] or str(record['analysis_year'] + 1)
    share_period = record['guided_share_period'] or f"fourth quarter ending December 31, {record['analysis_year']}"
    labels = {'borrowings_only': 'Borrowings less cash',
              'finance_equipment': 'Borrowings plus finance/equipment less cash',
              'all_classified_obligations': 'All classified obligations incl. operating leases less cash'}
    lines += ['Current source-only assessment from retained evidence; an older immutable publication is not rewritten.',
              f"Completed {_cell(price['session_date'])} close: {_number(price['close'])} {_cell(price['currency'])}; "
              + (f"dated outstanding shares: {_cell(record['shares']['value'])} as of {_cell(record['shares']['date'])}."
                 if record['shares'] else 'reported outstanding shares unavailable on the compatible capital date.'),
              f"Dated equity value (price × shares): {_number(record['equity_value_usd'])} USD. "
              'This is not an executable current market capitalization.', '',
              f'Obligation perimeter (enterprise value / revenue) | Components and cash (USD) | Enterprise value numerator USD | Trailing revenue | {_cell(guidance_period)} management guidance | {_cell(growth_period)} growth floor, conditional upper',
              '--- | --- | ---: | ---: | ---: | ---:']
    if record.get('price', {}).get('price_fallback'):
        fallback = record['price']['price_fallback']
        lines.insert(2, "Price fallback: " + _cell(fallback['reason']) + "; latest completed session " +
                     _cell(fallback['latest_completed_session_date']) + "; selected " +
                     _cell(fallback['selected_session_date']) + ".")
    for row in record['rows']:
        ratios = row.get('ratios') or {}
        label = _cell(labels.get(row['perimeter'], row['perimeter']))
        if row['status'] != 'available':
            components = ' + '.join(f"{_cell(f['metric'])} {_number(f['value_usd'])}" for f in row.get('obligation_components', []))
            if row.get('cash'):
                components += f" − cash {_number(row['cash']['value_usd'])}"
            lines.append(f"{label} | {components or 'unavailable'} | unavailable: {_cell(row['reason'])} | unavailable | unavailable | unavailable")
            continue
        guidance = ratios.get('guidance_range')
        components = ' + '.join(f"{_cell(f['metric'])} {_number(f['value_usd'])}" for f in row['obligation_components'])
        components += f" − cash {_number(row['cash']['value_usd'])}"
        lines.append(' | '.join((label, components, _number(row['numerator_usd']),
            _number(ratios['trailing_revenue']) + '×' if 'trailing_revenue' in ratios else 'unavailable',
            f"{_number(guidance[0])}–{_number(guidance[1])}×" if guidance else 'unavailable',
            '≤' + _number(ratios['growth_floor_conditional_upper']) + '×' if 'growth_floor_conditional_upper' in ratios else 'unavailable')))
    if record['trailing_revenue_usd']:
        period = record['trailing_revenue_period']
        lines += ['', f"Trailing revenue ({_cell(period[0])} to {_cell(period[1])}): {_number(record['trailing_revenue_usd'])} USD from compatible contiguous quarters; "
                  f"fact {_cell(record['trailing_revenue_fact_id'])}."]
    else:
        lines += ['', 'Trailing revenue unavailable: no compatible additive four-quarter record.']
    if record['management_revenue_guidance_range_usd']:
        low, high = record['management_revenue_guidance_range_usd']
        ref = record['disclosure_references']['revenue']
        lines.append(f"Management revenue guidance ({_cell(guidance_period)}): {_number(low)}–{_number(high)} USD; ratio range uses numerator/high to numerator/low. Source: {_cell(ref['source_id'])}, {_cell(ref['locator'])}.")
    else:
        lines.append(f'{_cell(guidance_period)} management revenue guidance unavailable from source-only discovery.')
    if record['growth_floor_percent'] and record['management_revenue_guidance_range_usd']:
        ref = record['disclosure_references']['growth_floor']
        lines.append(f"{_cell(growth_period)} conditional upper ratios use the low {_cell(guidance_period)} guidance base and management's at-least {_cell(record['growth_floor_percent'])}% growth statement; only if guidance is achieved and price, shares, obligations and cash remain fixed. They are not empirical bounds. Source: {_cell(ref['source_id'])}, {_cell(ref['locator'])}.")
    if record['guided_diluted_weighted_average_shares_range']:
        low, high = record['guided_diluted_weighted_average_shares_range']
        ref = record['disclosure_references']['guided_shares']
        lines += ['', f"Guided diluted weighted-average shares ({_cell(share_period)}): {_number(low)}–{_number(high)}; conditional sensitivity, not current shares outstanding. Source: {_cell(ref['source_id'])}, {_cell(ref['locator'])}.",
                  'Its numerator and multiple ranges use the low share count with the high revenue and the high share count with the low revenue.', '',
                  f'Perimeter (enterprise value / revenue) | Guided-share enterprise value numerator USD | Trailing revenue | {_cell(guidance_period)} guidance | Conditional {_cell(growth_period)} upper',
                  '--- | ---: | ---: | ---: | ---:']
        for row in record['rows']:
            sensitivity = row.get('guided_diluted_weighted_average_share_sensitivity')
            if sensitivity:
                ratios = sensitivity['ratios']
                numerator = sensitivity['numerator_range_usd']
                trailing = ratios.get('trailing_revenue_range')
                guidance = ratios.get('guidance_range')
                lines.append(' | '.join((
                    _cell(labels.get(row['perimeter'], row['perimeter'])),
                    f"{_number(numerator[0])}–{_number(numerator[1])}",
                    f"{_number(trailing[0])}–{_number(trailing[1])}×" if trailing else 'unavailable',
                    f"{_number(guidance[0])}–{_number(guidance[1])}×" if guidance else 'unavailable',
                    '≤' + _number(ratios['growth_floor_conditional_upper']) + '×'
                    if 'growth_floor_conditional_upper' in ratios else 'unavailable',
                )))
            else:
                lines.append(f"{_cell(labels.get(row['perimeter'], row['perimeter']))} | unavailable | unavailable | unavailable | unavailable")
    lines += ['', *(_cell(item) for item in record['limitations']),
              f"Price source: {_cell(price['source_id'])}; {_cell(price['adjustment_basis'])}.",
              'Source/fact IDs, dates, formulas and unavailable rows are retained in evidence.json.']
    return '\n'.join(lines)
