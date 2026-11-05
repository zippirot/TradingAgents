"""Explicit isolated legacy proof: prepare, then settle in a fresh process.

Uses real graph construction and Yahoo prices; all paid HTTP requests blocked.
The original user memory is read only; its known reflection is copied verbatim.
"""
import argparse
import hashlib
import json
from pathlib import Path

import live_cli

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=('prepare', 'settle'))
parser.add_argument('--run-name', default='early-c-settlement')
args = parser.parse_args()
live_cli.WORK = live_cli.work_for_run(args.run_name)
live_cli.configure()
live_cli.verify_config()


class NoPaidRequests:
    def before(self, request):
        if request.headers.get('authorization') or 'openrouter.ai' in request.url.host:
            raise RuntimeError('No paid model requests permitted in settlement proof')
        return None

    def after(self, ticket, response):
        pass


live_cli.install_guard(NoPaidRequests())

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.memory.log import TradingMemoryLog  # noqa: E402
from tradingagents.memory.publication import import_legacy_entry, list_records  # noqa: E402
from tradingagents.memory.publication_outcomes import load_outcomes  # noqa: E402

config = dict(DEFAULT_CONFIG)
work = live_cli.WORK
mode = args.mode
if mode == 'prepare':
    source = Path.home() / '.tradingagents/memory/trading_memory.md'
    content = source.read_text()
    raw = next(part for part in content.split(TradingMemoryLog._SEPARATOR)
               if part.strip().startswith('[2026-10-19 | DOCN |'))
    target = Path(config['memory_log_path'])
    if target.exists():
        raise RuntimeError('Proof memory already prepared; use settle to resume')
    target.write_text(raw.strip() + TradingMemoryLog._SEPARATOR)
    entry = TradingMemoryLog(config).load_entries()[0]
    assert entry['resolved'] == '2026-10-27' and not entry['pending']
    record = import_legacy_entry(config, entry, source_label=source.name,
                                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    receipt = {'decision_id': record['decision_id'], 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'published_at': record['published_at'], 'imported_at': record['imported_at'],
               'mode': record['evaluation_mode'], 'reflection_preserved': True}
    (work / 'prepare.json').write_text(json.dumps(receipt, indent=2))
else:
    assert mode == 'settle'
    before = Path(config['memory_log_path']).read_bytes()
    graph = TradingAgentsGraph(config=config)
    result = graph.settle_all_pending()
    record = list_records(config)[0]
    outcomes = load_outcomes(config, record)
    assert not result.failed, result.failed
    assert outcomes['endpoints']['5_sessions']['status'] == 'resolved'
    assert outcomes['endpoints']['21_sessions']['status'] == 'pending'
    assert outcomes['endpoints']['63_sessions']['status'] == 'pending'
    if record.get('evaluation_protocol'):
        assert set(outcomes['endpoints']) == {'5_sessions', '21_sessions', '63_sessions', '3_calendar_months', '6_calendar_months'}
        assert outcomes['endpoints']['3_calendar_months']['status'] == 'pending'
        assert outcomes['endpoints']['6_calendar_months']['status'] == 'pending'
    assert record['published_at'] is None and record['evaluation_mode'] == 'legacy'
    assert Path(config['memory_log_path']).read_bytes() == before
    receipt = {'endpoint_settled': result.endpoint_settled, 'failed': result.failed,
               'publication': record, 'outcomes': outcomes, 'memory_unchanged': True}
    destination = work / ('settlement-repeat.json' if (work / 'settlement.json').exists() else 'settlement.json')
    destination.write_text(json.dumps(receipt, indent=2))
print(json.dumps({'mode': mode, 'decision_id': receipt.get('decision_id') or record['decision_id'],
                  'paid_requests_allowed': False}))
