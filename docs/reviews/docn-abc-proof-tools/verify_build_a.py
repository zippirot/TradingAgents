"""Fresh-process acceptance of live-03 state/report/publication; paid HTTP blocked."""
import hashlib
import json
from html.parser import HTMLParser

import live_cli

live_cli.WORK = live_cli.PROOF_ROOT / 'live-03'
live_cli.configure()
live_cli.verify_config()

class NoPaidRequests:
    def before(self, request):
        if request.headers.get('authorization') or 'openrouter.ai' in request.url.host:
            raise RuntimeError('Paid requests forbidden during acceptance readback')
        return None

    def after(self, ticket, response):
        pass

live_cli.install_guard(NoPaidRequests())

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.memory.publication import load_evidence, load_record  # noqa: E402
from tradingagents.memory.publication_outcomes import load_outcomes  # noqa: E402

work = live_cli.WORK
state_path = work / 'results/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-04.json'
state = json.loads(state_path.read_text())
source = json.loads((work / 'source_sha256.json').read_text())
assert all(hashlib.sha256((live_cli.ROOT / path).read_bytes()).hexdigest() == digest
           for path, digest in source['files'].items())
report = next((work / 'results/reports').glob('DOCN_*'))
markdown = (report / 'complete_report.md').read_text()
html = (report / 'complete_report.html').read_text()
evidence = json.loads((report / 'evidence.json').read_text())

class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)

parser = Text()
parser.feed(html)
html_text = ' '.join(parser.parts)
record = load_record(DEFAULT_CONFIG, state['publication_record']['decision_id'])
assert record['canonical_rating'] == state['final_rating'] == 'Underweight'
assert record['published_at'] == state['publication_record']['published_at']
assert record['evidence_status'] == state['evidence_quality']['status'] == 'limited'
assert record['evaluation_mode'] == 'prospective'
assert state['publication_record']['decision_id'] in markdown and state['publication_record']['decision_id'] in html_text
snapshot = load_evidence(DEFAULT_CONFIG, record)
assert snapshot['financial_calculations'] == evidence['financial_calculations'] == state['financial_calculations']
assert snapshot['disclosure_evidence'] == evidence['disclosure_evidence'] == state['disclosure_evidence']
expected = {'ocf_less_capex_and_financing_principal_v1': '153818000',
            'ocf_less_capex_principal_and_acquisitions_v1': '149022000',
            'signed_investing_components_to_total_v1': '-381974000',
            'cash_flows_plus_fx_to_cash_change_v1': '411619000',
            'opening_plus_change_to_cash_including_restricted_v1': '666252000'}
calculations = {c['method']: c for c in state['financial_calculations']}
for method, value in expected.items():
    assert calculations[method]['status'] == 'pass' and calculations[method]['result'] == value
    assert value in markdown and value in html_text
assert len(state['disclosure_evidence']['extraction']['claims']) == 15
rpo = state['disclosure_evidence']['kpi_comparisons'][0]
assert rpo['status'] == 'pass' and rpo['absolute_change'] == '-94121000'
assert '-10.53%' in markdown and '-10.53%' in html_text
raw = state['unvalidated_outputs']['investment_debate_state']
for role in ('bull_history', 'bear_history'):
    assert '149.0 million' in raw[role] and '893.8 million' in raw[role]
    assert '60%' in raw[role] and ('outlook' in raw[role] or 'guidance' in raw[role])
assert state['news_coverage']['independent_news']['status'] == 'available'
assert state['news_coverage']['optional_macro']['status'] == 'unavailable'
assert state['issuer_event_evidence']['coverage']['issuer_events']['status'] == 'accepted_values_available'
assert markdown.count('### Evidence reference appendix') == 1
memory = work / 'memory/trading_memory.md'
before = memory.read_bytes()
assert record['decision_id'].encode() in before and b'Underweight' in before
app = TradingAgentsGraph(config=dict(DEFAULT_CONFIG))
settled = app.settle_all_pending()
assert not settled.failed and not settled.settled and not settled.endpoint_settled
outcomes = load_outcomes(DEFAULT_CONFIG, record)
assert all(endpoint['status'] == 'pending' for endpoint in outcomes['endpoints'].values())
assert memory.read_bytes() == before
paths = [state_path, report / 'complete_report.md', report / 'complete_report.html', report / 'evidence.json',
         report / 'quality.json', memory]
receipt = {'source_head': source['head'], 'decision_id': record['decision_id'], 'published_at': record['published_at'],
           'rating': record['canonical_rating'], 'quality': record['evidence_status'],
           'source_manifest_matches': True, 'cash_checks': expected, 'rpo_delta': rpo['absolute_change'],
           'first_bull_bear_use_verified': True, 'news_coverage': state['news_coverage'],
           'model_calls': 0, 'pending_endpoints': list(outcomes['endpoints']), 'memory_unchanged': True,
           'artifact_sha256': {str(p.relative_to(live_cli.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
           'limits': ['HTML structure/text inspected; no browser screenshot',
                      'Live news was available; outage fallback covered by focused fault-injection tests',
                      'Shared valuation and final target unavailable; Build B acceptance remains outstanding']}
(work / 'build-a-acceptance.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps({key: receipt[key] for key in ('source_head', 'decision_id', 'rating', 'quality', 'pending_endpoints', 'memory_unchanged')}))
