"""Fresh-process final C readback; no paid calls or invented historical metadata."""
import argparse
import hashlib
import json
from html.parser import HTMLParser

import live_cli

parser = argparse.ArgumentParser()
parser.add_argument('--run-name', default='live-06')
args = parser.parse_args()
live_cli.WORK = live_cli.work_for_run(args.run_name)
live_cli.configure()
live_cli.verify_config()


class NoPaidRequests:
    def before(self, request):
        if request.headers.get('authorization') or 'openrouter.ai' in request.url.host:
            raise RuntimeError('Paid requests forbidden during C readback')
        return None

    def after(self, ticket, response):
        pass


live_cli.install_guard(NoPaidRequests())
from tradingagents.backtest import evaluate_publications, render_publication_evaluation  # noqa: E402
from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.memory.publication import load_evidence, load_record  # noqa: E402
from tradingagents.memory.publication_outcomes import load_outcomes  # noqa: E402

work = live_cli.WORK
source = json.loads((work / 'source_sha256.json').read_text())
assert all(hashlib.sha256((live_cli.ROOT / path).read_bytes()).hexdigest() == digest
           for path, digest in source['files'].items())
as_of = source['configuration']['analysis_date']
state_path = work / f'results/DOCN/TradingAgentsStrategy_logs/full_states_log_{as_of}.json'
state = json.loads(state_path.read_text())
record = load_record(DEFAULT_CONFIG, state['publication_record']['decision_id'])
snapshot = load_evidence(DEFAULT_CONFIG, record)
assert record['canonical_rating'] == state['final_rating'] == state['decision_context']['rating']
assert record['evaluation_mode'] == 'prospective' and record['published_at']
assert record['evaluation_protocol']['version'] == 1
assert record['thesis_version_id'] == state['thesis_version_id'] == state['thesis']['version_id']
assert len({row['condition_id'] for row in state['thesis']['conditions']}) == len(state['thesis']['conditions'])
report = next((work / 'results/reports').glob('DOCN_*'))
evidence = json.loads((report / 'evidence.json').read_text())
for field in ('thesis', 'decision_context', 'price_observation', 'valuation_price_comparison',
              'shared_valuation_scenarios', 'issuer_identity', 'event_comparison'):
    assert snapshot[field] == state[field] == evidence[field], field


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


reader = Text()
reader.feed((report / 'complete_report.html').read_text())
for text in ((report / 'complete_report.md').read_text(), ' '.join(reader.parts)):
    assert record['decision_id'] in text and state['final_rating'] in text
    assert 'Research decision card' in text and 'Thesis continuity' in text
memory = work / 'memory/trading_memory.md'
before = memory.read_bytes()
app = TradingAgentsGraph(config=dict(DEFAULT_CONFIG))
context = app._memory_step({'company_of_interest': 'DOCN', 'trade_date': as_of})
assert context['prior_thesis']['version_id'] == state['thesis_version_id']
assert memory.read_bytes() == before
outcomes = load_outcomes(DEFAULT_CONFIG, record)
assert outcomes['thesis_version_id'] == state['thesis_version_id']
assert set(outcomes['endpoints']) == {'5_sessions', '21_sessions', '63_sessions', '3_calendar_months', '6_calendar_months'}
assert all(row['status'] == 'pending' for row in outcomes['endpoints'].values())
evaluation = evaluate_publications(DEFAULT_CONFIG)
assert not evaluation['integrity_errors'] and not evaluation['attempts']['errors']
assert evaluation['attempts']['completed'] == 1 and evaluation['attempts']['failed'] == 0
assert any(row['decision_id'] == record['decision_id'] for row in evaluation['publications'])
(work / 'evaluation.json').write_text(json.dumps(evaluation, indent=2))
(work / 'evaluation.md').write_text(render_publication_evaluation(evaluation))
paths = [state_path, report/'complete_report.md', report/'complete_report.html', report/'evidence.json', memory]
receipt = {'source_head': source['head'], 'source_manifest_sha256': hashlib.sha256((work/'source_sha256.json').read_bytes()).hexdigest(),
           'decision_id': record['decision_id'], 'published_at': record['published_at'], 'rating': record['canonical_rating'],
           'thesis_version_id': record['thesis_version_id'], 'five_endpoints_pending': True,
           'fresh_graph_readback': True, 'memory_unchanged': True, 'paid_calls': 0,
           'evaluation_attempts': evaluation['attempts'],
           'artifact_sha256': {str(path.relative_to(live_cli.ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
(work / 'build-c-readback.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))
