"""Replay actual live-02 SEC inputs through current A gate, without network or models."""
import hashlib
import json
from pathlib import Path

from tradingagents.agents.evidence_validation import assess_financial_package
from tradingagents.agents.kpi_comparisons import compare_rpo
from tradingagents.dataflows.financial_evidence import EvidencePackage
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

root = Path(__file__).resolve().parents[3]
source = root / 'results/docn-abc/live-02/results/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-04.json'
state = json.loads(source.read_text())
raw = state['financial_evidence']
# Restore only the saved companyfacts inputs and their existing derivations.
# Prior gate table projections must be recomputed using the current extractor.
sources = [s for s in raw['sources'] if s['url'] == 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001582961.json']
source_ids = {s['source_id'] for s in sources}
facts = [f for f in raw['facts'] if set(f['source_ids']) <= source_ids]
while True:
    ids = {f['fact_id'] for f in facts}
    complete = [f for f in facts if set(f['input_fact_ids']) <= ids]
    if len(complete) == len(facts):
        break
    facts = complete
package = EvidencePackage.model_validate({**raw, 'sources': sources, 'facts': facts, 'warnings': ()})
docs = DisclosurePackage.model_validate(state['filing_evidence'])
original_report = state['financial_claim_validation']['raw_report']
rpo_source = root / 'results/docn-abc/a-prior-source/rpo-comparison.json'
rpo_record = json.loads(rpo_source.read_text())
rpo = compare_rpo(*(DisclosurePackage.model_validate(rpo_record['source_packages'][key])
                    for key in ('current', 'prior')))
assert rpo['status'] == 'pass' and rpo['absolute_change'] == '-94121000'
update = assess_financial_package({**state, 'fundamentals_report': original_report}, package, docs,
                                  rpo_comparison=rpo)
assert '-10.53%' in update['canonical_financial_context']
assert '39.87 (rounded for display)' in update['canonical_financial_context']
calculations = {c['method']: c for c in update['financial_calculations']}
expected = {'ocf_less_capex_and_financing_principal_v1': '153818000',
            'ocf_less_capex_principal_and_acquisitions_v1': '149022000',
            'signed_investing_components_to_total_v1': '-381974000',
            'cash_flows_plus_fx_to_cash_change_v1': '411619000',
            'opening_plus_change_to_cash_including_restricted_v1': '666252000'}
for method, value in expected.items():
    assert calculations[method]['status'] == 'pass', calculations[method]
    assert calculations[method]['result'] == value, calculations[method]
receipt = {'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
           'source': str(source.relative_to(root)), 'rpo_source_sha256': hashlib.sha256(rpo_source.read_bytes()).hexdigest(), 'network_calls': 0, 'model_calls': 0,
           'companyfacts_source_count': len(sources), 'companyfacts_fact_count': len(facts),
           'checks': update['evidence_quality'], 'calculations': update['financial_calculations'],
           'disclosures': update['disclosure_evidence']}
target = root / 'results/docn-abc/a-evidence-replay'
target.mkdir(parents=True, exist_ok=True)
(target / 'disclosure-cash.json').write_text(json.dumps(receipt, indent=2))
(target / 'canonical-context.md').write_text(update['canonical_financial_context'])
print(json.dumps({'status': update['evidence_quality']['status'],
                  'cash_checks': {k: calculations[k]['result'] for k in expected},
                  'other_cash': {k: v['result'] for k, v in calculations.items() if 'cash' in k or 'financ' in k},
                  'accepted_disclosures': len(update['disclosure_evidence']['extraction']['claims'])}))
