"""Real B artifact/restart acceptance; no paid calls and no invented observations."""
import argparse
import hashlib
import json
from html.parser import HTMLParser

import live_cli

parser = argparse.ArgumentParser()
parser.add_argument('--run-name', default='live-04')
args = parser.parse_args()
live_cli.WORK = live_cli.work_for_run(args.run_name)
live_cli.configure()
live_cli.verify_config()


class NoPaidRequests:
    def before(self, request):
        if request.headers.get('authorization') or 'openrouter.ai' in request.url.host:
            raise RuntimeError('Paid requests forbidden during B acceptance readback')
        return None

    def after(self, ticket, response):
        pass


live_cli.install_guard(NoPaidRequests())

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.memory.publication import load_evidence, load_record  # noqa: E402
from tradingagents.memory.publication_outcomes import load_outcomes  # noqa: E402
from tradingagents.memory.thesis import observe_conditions, render_prior_thesis  # noqa: E402

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


reader = Text()
reader.feed(html)
html_text = ' '.join(reader.parts)
record = load_record(DEFAULT_CONFIG, state['publication_record']['decision_id'])
snapshot = load_evidence(DEFAULT_CONFIG, record)
assert record['canonical_rating'] == state['final_rating'] == state['decision_context']['rating']
assert record['evidence_status'] == state['evidence_quality']['status'] in {'sufficient', 'limited'}
assert record['thesis_version_id'] == state['thesis_version_id'] == state['thesis']['version_id']
if state.get('prior_thesis'):
    assert state['thesis']['parent_version_id'] == state['prior_thesis']['version_id']
    expected = {row['condition_id'] for row in state['prior_thesis']['conditions']}
    actual = state['thesis']['prior_conditions']
    assert {row['condition_id'] for row in actual} == expected
    assert all(row['disposition_reason'] and row['disposition_reason'] != 'reason not supplied' for row in actual)
else:
    assert state['thesis']['conditions'], 'Initial live publication must contain an actual advisory condition'
for field in ('thesis', 'decision_context', 'price_observation', 'valuation_price_comparison',
              'shared_valuation_scenarios', 'issuer_identity', 'event_comparison'):
    assert snapshot[field] == evidence[field] == state[field], field
rows = state['shared_valuation_scenarios']['rows']
assert any(row['result']['status'] == 'supported' and row['comparison']['status'] == 'available'
           for row in rows), 'A missing target/table alone is not B valuation acceptance'
assert state['price_observation']['status'] == 'available'
assert state['issuer_identity']['cik'] == state['financial_evidence']['cik']
for text in (markdown, html_text):
    for required in ('Research decision card', 'What the price implies', 'Thesis continuity',
                     record['decision_id'], state['final_rating']):
        assert required in text, required
memory = work / 'memory/trading_memory.md'
before = memory.read_bytes()
app = TradingAgentsGraph(config=dict(DEFAULT_CONFIG))
context = app._memory_step({'company_of_interest': 'DOCN', 'trade_date': state['trade_date']})
prior = context['prior_thesis']
assert prior['version_id'] == state['thesis_version_id']
assert prior['conditions'] == state['thesis']['conditions']
observations = observe_conditions(prior, state)
assert len(observations) == len(prior['conditions'])
shown = render_prior_thesis({**prior, 'observations': observations})
assert 'advisory' in shown and all(row['condition_id'] in shown for row in observations)
outcomes = load_outcomes(DEFAULT_CONFIG, record)
assert outcomes['thesis_version_id'] == state['thesis_version_id']
assert all(endpoint['status'] == 'pending' for endpoint in outcomes['endpoints'].values())
assert memory.read_bytes() == before
paths = [state_path, report/'complete_report.md', report/'complete_report.html',
         report/'evidence.json', report/'quality.json', memory]
receipt = {'source_head': source['head'], 'decision_id': record['decision_id'],
           'published_at': record['published_at'], 'rating': record['canonical_rating'],
           'quality': record['evidence_status'], 'thesis_version_id': state['thesis_version_id'],
           'conditions_count': len(prior['conditions']), 'fresh_process_prior_readback': True,
           'prior_thesis_version_id': (state.get('prior_thesis') or {}).get('version_id'),
           'prior_dispositions': state['thesis'].get('prior_conditions', []),
           'observations': observations, 'source_manifest_matches': True,
           'supported_price_comparisons': sum(row['result']['status']=='supported' and row['comparison']['status']=='available' for row in rows),
           'target_status': state['target_validation']['status'], 'model_calls': 0,
           'pending_endpoints': list(outcomes['endpoints']), 'memory_unchanged': True,
           'artifact_sha256': {str(p.relative_to(live_cli.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
           'limits': ['HTML structure/text inspected; no browser screenshot',
                      'Second CLI disposition is proven only when prior_thesis_version_id and prior_dispositions are present',
                      'Future investment performance remains pending']}
(work/'build-b-readback.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps({key:receipt[key] for key in ('source_head','decision_id','rating','thesis_version_id','conditions_count','supported_price_comparisons','memory_unchanged')}))
