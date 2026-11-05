"""Replay actual B5 proposal through real persistence after the identity correction.

This is a deterministic engineering replay, explicitly historical; no new model
opinion, publication timestamp, market observation or investment result is invented.
"""
import hashlib
import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import live_cli

live_cli.WORK = live_cli.PROOF_ROOT / 'b-thesis-recovery'
assert not live_cli.WORK.exists(), 'Use the existing receipt; investigate failures before another replay'
source_root = live_cli.PROOF_ROOT / 'live-05'
source_state_path = source_root / 'results/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-04.json'
source_state = json.loads(source_state_path.read_text())
protected = [p for name in ('live-04', 'live-05')
             for p in (live_cli.PROOF_ROOT/name/'results/publications').rglob('*.json')]
protected += [source_state_path, source_root/'memory/trading_memory.md']
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
live_cli.configure()
live_cli.verify_config()
shutil.copytree(source_root/'results/publications', live_cli.WORK/'results/publications',
                ignore=shutil.ignore_patterns('*.lock'))
shutil.copyfile(source_root/'memory/trading_memory.md', live_cli.WORK/'memory/trading_memory.md')


class NoRequests:
    def before(self, request):
        raise RuntimeError('No network/model calls permitted during deterministic B identity recovery')

    def after(self, ticket, response):
        pass


live_cli.install_guard(NoRequests())

from tradingagents.agents.output_validation import enforce_publication  # noqa: E402
from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.memory.publication import load_evidence, load_record, runtime_versions  # noqa: E402
from tradingagents.memory.thesis import load_latest_thesis, observe_conditions  # noqa: E402
from tradingagents.reporting import write_report_tree  # noqa: E402

config = {**DEFAULT_CONFIG, 'evaluation_mode': 'historical'}
prior = load_latest_thesis(config, 'DOCN', datetime.now(UTC))
assert prior['version_id'] == source_state['thesis_version_id']
assert len(prior['conditions']) == 4, 'Recorded bug must remain visible in immutable original'
assert len(observe_conditions(prior, source_state)) == 2
# Same-run re-export must not re-key or silently rewrite the old published thesis.
assert enforce_publication(source_state)['thesis'] == source_state['thesis']
replay = deepcopy(source_state)
for key in ('thesis', 'thesis_version_id', 'publication_record'):
    replay.pop(key, None)
replay.update(run_id=str(uuid4()), prior_thesis=prior, evaluation_mode='historical',
              publication_versions=runtime_versions())
app = TradingAgentsGraph(config=config)
app.record_decision('DOCN', '2026-11-04', replay)
record = load_record(config, replay['publication_record']['decision_id'])
assert record['evaluation_mode'] == 'historical'
assert record['published_at'] != source_state['publication_record']['published_at']
assert record['thesis_version_id'] == replay['thesis_version_id']
assert replay['thesis']['parent_version_id'] == prior['version_id']
assert len(replay['thesis']['conditions']) == 2
original_ids = {row['condition_id'] for row in source_state['prior_thesis']['conditions']}
assert {row['condition_id'] for row in replay['thesis']['conditions']} == original_ids
assert all(row['disposition'] == 'kept' and row['status'] == 'unknown'
           and row['disposition_reason'] != 'reason not supplied'
           for row in replay['thesis']['prior_conditions'])
assert load_evidence(config, record)['thesis'] == replay['thesis']
report = live_cli.WORK/'report'
write_report_tree(replay, 'DOCN', report)
assert json.loads((report/'evidence.json').read_text())['thesis'] == replay['thesis']
assert 'Thesis continuity' in (report/'complete_report.md').read_text()
# Real repeated publication and a second graph instance retain the corrected version.
app.record_decision('DOCN', '2026-11-04', replay)
second = TradingAgentsGraph(config=config)
loaded = load_latest_thesis(second.config, 'DOCN', datetime.now(UTC))
assert loaded['version_id'] == replay['thesis_version_id'] and len(loaded['conditions']) == 2
assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
receipt = {'kind': 'deterministic historical engineering replay; not another live model proof',
           'source_versions': runtime_versions(), 'source_decision_id': source_state['run_id'],
           'decision_id': record['decision_id'], 'published_at': record['published_at'],
           'original_thesis_version': prior['version_id'], 'new_thesis_version': replay['thesis_version_id'],
           'old_conditions': 4, 'new_conditions': 2, 'preserved_condition_ids': sorted(original_ids),
           'same_run_old_thesis_preserved': True, 'repeated_publication_passed': True,
           'second_graph_readback_passed': True, 'original_artifacts_unchanged': before,
           'model_calls': 0, 'network_calls': 0, 'future_outcomes': 'pending',
           'report_files': [str(p.relative_to(live_cli.ROOT)) for p in report.iterdir() if p.is_file()]}
(live_cli.WORK/'acceptance.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps({k:receipt[k] for k in ('decision_id','old_conditions','new_conditions','repeated_publication_passed','second_graph_readback_passed','model_calls')}))
