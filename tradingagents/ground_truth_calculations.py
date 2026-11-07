"""Replay existing accounting calculations over previously trusted source facts."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, localcontext

from pydantic import ValidationError

from tradingagents.agents.accounting_checks import Calculation
from tradingagents.agents.evidence_validation import assess_financial_package
from tradingagents.dataflows.financial_evidence import EvidencePackage
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def calculation_sources(state, validated_sources=None):
    """Expose matching rederived results only when every input already has trust.

    The caller supplies the canonical source index after issuer, URL and cutoff
    validation. This helper cannot add a primary fact or new rating authority.
    """
    retained = state.get('financial_calculations') or []
    if not retained:
        return {}, []
    trusted = {source['fact']['fact_id']: source for source in (validated_sources or {}).values()
               if source.get('kind') == 'canonical financial fields' and isinstance(source.get('fact'), dict)}
    if not trusted:
        return {}, ['Retained financial calculations lack trusted canonical input sources.']
    try:
        package = EvidencePackage.model_validate(state.get('financial_evidence'))
        documents = (DisclosurePackage.model_validate(state['filing_evidence'])
                     if state.get('filing_evidence') else None)
        if str(package.as_of) != str(state.get('trade_date')):
            raise ValueError('calculation cutoff mismatch')
        result = assess_financial_package(state, package, documents, source_only=True)
        recalculated = [Calculation.model_validate(row) for row in result['financial_calculations']]
        facts = {fact['fact_id']: fact for fact in result['financial_evidence']['facts']}
    except (ValidationError, ValueError, TypeError, KeyError):
        return {}, ['Retained financial calculations could not be replayed from the scoped source package.']
    sources, gaps = {}, []
    for row in retained:
        try:
            calculation = Calculation.model_validate(row)
        except (ValidationError, TypeError):
            gaps.append('A retained financial calculation is malformed.')
            continue
        if calculation.status != 'pass' or calculation.result is None:
            continue
        if calculation not in recalculated or not calculation.input_fact_ids:
            gaps.append('Retained financial calculation differs from source replay: ' + calculation.method)
            continue
        inputs = [facts.get(ident) for ident in calculation.input_fact_ids]
        if any(fact is None or ident not in trusted or trusted[ident]['fact'] != fact
               for ident, fact in zip(calculation.input_fact_ids, inputs, strict=True)):
            gaps.append('Financial calculation has an untrusted or changed input: ' + calculation.method)
            continue
        validated = [trusted[ident] for ident in calculation.input_fact_ids]
        if any(not isinstance(source.get('known_at'), str) or not source.get('url') for source in validated):
            gaps.append('Financial calculation input provenance is incomplete: ' + calculation.method)
            continue
        canonical = calculation.model_dump(mode='json')
        payload = {'calculation': canonical, 'inputs': inputs,
                   'definition': calculation.message,
                   'input_sources': [{'source_id': source['source_id'], 'locator': source['locator'],
                                     'url': source['url'], 'known_at': source['known_at']} for source in validated]}
        if calculation.unit and len(calculation.unit) == 3 and calculation.unit.isupper():
            with localcontext() as context:
                context.prec = 50
                payload['result_in_millions'] = format(calculation.result / Decimal(1_000_000), 'f') + ' million ' + calculation.unit
        identity = 'calculation-' + hashlib.sha256(_json(payload).encode()).hexdigest()
        sources[(identity, calculation.method)] = {
            'source_id': identity, 'locator': calculation.method, 'text': _json(payload),
            'url': validated[0]['url'], 'known_at': max(source['known_at'] for source in validated),
            'kind': 'reproduced financial calculation', 'truncated': False,
            'calculation': canonical, 'inputs': inputs,
        }
    return sources, list(dict.fromkeys(gaps))
