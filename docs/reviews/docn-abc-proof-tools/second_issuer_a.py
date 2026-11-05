"""Read-only second-issuer SEC/evidence-gate proof; no model calls."""
import argparse
import json

import live_cli

parser = argparse.ArgumentParser()
parser.add_argument('--ticker', default='NVDA', choices=('NVDA', 'MSFT'))
args = parser.parse_args()
live_cli.WORK = live_cli.PROOF_ROOT / ('a-second-issuer-' + args.ticker.lower())
live_cli.configure()

class NoPaidRequests:
    def before(self, request):
        if request.headers.get('authorization') or 'openrouter.ai' in request.url.host:
            raise RuntimeError('No paid requests permitted in source proof')
        return None

    def after(self, ticket, response):
        pass

live_cli.install_guard(NoPaidRequests())

from tradingagents.agents.evidence_validation import create_evidence_gate  # noqa: E402

state = {'company_of_interest': args.ticker, 'trade_date': '2026-11-04',
         'asset_type': 'stock', 'fundamentals_report': ''}
result = create_evidence_gate(['fundamentals'])(state)
(live_cli.WORK / 'gate-result.json').write_text(json.dumps(result, indent=2))
if args.ticker == 'NVDA':
    claims = result['disclosure_evidence']['extraction']['claims']
    revenue = next(c for c in claims if c['metric'] == 'Revenue')
    assert revenue['value'] == '108.0' and revenue['tolerance_percent'] == '2'
    assert revenue['comparator'] == 'central_estimate' and revenue['upper_value'] is None
    assert revenue['period'] == 'third quarter of fiscal 2027' and 'China' in revenue['quote']
    assert '±2%' in result['canonical_financial_context']
    assert result.get('final_rating') == 'REVIEW'  # Missing core coverage remains honest.

print(json.dumps({'status': result['evidence_quality']['status'],
                  'sources': len(result.get('financial_evidence', {}).get('sources', [])),
                  'documents': len(result.get('filing_evidence', {}).get('documents', [])),
                  'accepted_disclosures': len(result.get('disclosure_evidence', {}).get('extraction', {}).get('claims', [])),
                  'model_calls': 0}))
