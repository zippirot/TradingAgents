"""Offline transport and budget checks; never opens a network connection."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import httpx2
import live_cli


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proof_root = Path(self.temp.name)
        self.work = self.proof_root / "live-01"
        self.patcher = patch.multiple(live_cli, PROOF_ROOT=self.proof_root, WORK=self.work,
                                      LEDGER=self.proof_root / "cost_ledger.jsonl")
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.guard = live_cli.Guard()

    def request(self, **changes):
        body = {"model": live_cli.MODEL, "max_tokens": live_cli.MAX_OUTPUT, "messages": [{"role": "user", "content": "fixture"}]}
        body.update(changes)
        return httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions", json=body)

    def test_success_releases_reservation_and_records_usage(self):
        ticket = self.guard.before(self.request())
        self.assertGreater(ticket[1], 0)
        self.assertEqual(live_cli.history()[0]["framing_tokens"], 1024 + 64)
        self.assertEqual(live_cli.history()[0]["input_bound_tokens"],
                         live_cli.history()[0]["bytes"] + 1024 + 64)
        response = httpx.Response(200, json={"usage": {"prompt_tokens": 20, "completion_tokens": 30}})
        self.guard.after(ticket, response)
        self.assertAlmostEqual(live_cli.committed_usd(live_cli.history()), 20 * 0.0000025 + 30 * 0.0000075)
        self.assertEqual([e["type"] for e in live_cli.history()], ["reserve", "settle", "release"])

    def test_stream_and_failure_keep_full_reservation(self):
        stream = self.guard.before(self.request(stream=True))
        self.guard.after(stream, httpx.Response(200, content=b"data: fixture\n\n"))
        failed = self.guard.before(self.request())
        self.guard.after(failed, httpx.Response(429, json={"error": "fixture"}))
        self.assertAlmostEqual(live_cli.committed_usd(live_cli.history()), stream[1] + failed[1])

    def test_rejects_wrong_model_cap_and_exhausted_budget(self):
        with self.assertRaisesRegex(RuntimeError, "Unexpected model"):
            self.guard.before(self.request(model="other"))
        with self.assertRaisesRegex(RuntimeError, "output cap"):
            self.guard.before(self.request(max_tokens=32_768))
        live_cli.append({"type": "reserve", "usd": 69.90, "request": 999})
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            self.guard.before(self.request())

    def test_other_host_is_not_billed(self):
        req = httpx.Request("GET", "https://www.sec.gov/files", headers={"User-Agent": "fixture"})
        self.assertIsNone(self.guard.before(req))
        self.assertFalse(live_cli.history())

    def test_other_paid_endpoints_are_blocked(self):
        with self.assertRaisesRegex(RuntimeError, "Authenticated non-OpenRouter"):
            self.guard.before(httpx.Request("POST", "https://api.openai.com/v1/chat/completions",
                                           headers={"Authorization": "Bearer fixture"}, json={}))
        with self.assertRaisesRegex(RuntimeError, "Unexpected OpenRouter endpoint"):
            self.guard.before(httpx.Request("POST", "https://openrouter.ai/api/v1/responses", json={}))
        self.assertFalse(live_cli.history())

    def test_shared_ledger_and_unique_ids_across_run_names(self):
        first = self.guard.before(self.request())
        live_cli.WORK = live_cli.work_for_run("live-02")
        second_guard = live_cli.Guard()
        second = second_guard.before(self.request())
        self.assertEqual((first[0], second[0]), (1, 2))
        self.assertEqual(len(live_cli.history()), 2)
        self.assertEqual(live_cli.LEDGER.parent, self.proof_root)
        self.assertAlmostEqual(live_cli.committed_usd(live_cli.history()), first[1] + second[1])
        with self.assertRaises(ValueError):
            live_cli.work_for_run("../escape")
        with self.assertRaises(ValueError):
            live_cli.work_for_run("nested/path")

    def test_source_record_includes_head_and_runner(self):
        live_cli.configure()
        live_cli.verify_config()
        live_cli.source_record()
        record = json.loads((self.work / "source_sha256.json").read_text())
        self.assertEqual(len(record["head"]), 40)
        self.assertIn("tradingagents/agents/researchers/bull_researcher.py", record["files"])
        self.assertIn("docs/reviews/docn-abc-proof-tools/live_cli.py", record["files"])
        self.assertIn("tests/test_evidence_presentation.py", record["files"])
        self.assertEqual(record["configuration"]["quick_think_llm"], live_cli.MODEL)
        self.assertEqual(record["configuration"]["max_tokens"], live_cli.MAX_OUTPUT)
        self.assertTrue(record["runtime"]["tradingagents_package"].endswith("/tradingagents/__init__.py"))

    def test_public_catalog_rates_checked_before_paid_run(self):
        self.work.mkdir()
        pricing = {"prompt": "0.000001", "completion": "0.000005",
                   "input_cache_read": "0.00000005", "input_cache_write": "0.00000125",
                   "web_search": "0.01", "overrides": [{"min_prompt_tokens": 272000,
                   "prompt": "0.000002", "completion": "0.0000075",
                   "input_cache_read": "0.0000001", "input_cache_write": "0.0000025"}]}

        def catalog():
            return io.BytesIO(json.dumps({"data": [{"id": live_cli.MODEL, "pricing": pricing}]}).encode())

        with patch.object(live_cli, "urlopen", return_value=catalog()):
            snapshot = live_cli.pricing_snapshot()
        self.assertEqual(snapshot["model"], live_cli.MODEL)
        self.assertEqual(len(snapshot["base_and_overrides"]), 2)
        self.assertTrue((self.work / "pricing_snapshot.json").is_file())
        pricing["overrides"][0]["completion"] = "0.000008"
        with patch.object(live_cli, "urlopen", return_value=catalog()), self.assertRaisesRegex(
            RuntimeError, "completion price exceeds"
        ):
            live_cli.pricing_snapshot()
        pricing["overrides"][0]["completion"] = "0.0000075"
        pricing["request"] = "0.01"
        with patch.object(live_cli, "urlopen", return_value=catalog()), self.assertRaisesRegex(
            RuntimeError, "Unbudgeted model pricing field"
        ):
            live_cli.pricing_snapshot()

    def test_installed_sdk_httpx2_transport_is_guarded(self):
        original_sync = (httpx.Client.send, httpx2.Client.send)
        original_async = (httpx.AsyncClient.send, httpx2.AsyncClient.send)
        try:
            live_cli.install_guard(self.guard)
            transport = httpx2.MockTransport(lambda request: httpx2.Response(
                200, json={"usage": {"prompt_tokens": 20, "completion_tokens": 30}}))
            with httpx2.Client(transport=transport) as client:
                response = client.post("https://openrouter.ai/api/v1/chat/completions", json={
                    "model": live_cli.MODEL, "max_tokens": live_cli.MAX_OUTPUT,
                    "messages": [{"role": "user", "content": "fixture"}],
                })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.guard.request_count, 1)
            self.assertEqual([e["type"] for e in live_cli.history()], ["reserve", "settle", "release"])
        finally:
            httpx.Client.send, httpx2.Client.send = original_sync
            httpx.AsyncClient.send, httpx2.AsyncClient.send = original_async


def test_argument_validation_does_not_import_application_configuration():
    import subprocess
    import sys
    script = (
        "import sys; import live_cli; "
        "sys.argv=['live_cli','--analysis-date','2026-11-04']; "
        "live_cli.main(); "
        "assert 'tradingagents.default_config' not in sys.modules"
    )
    subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).parent, check=True,
                   capture_output=True, text=True)


class ExtendedAuthorityTests(unittest.TestCase):
    def baseline(self):
        events = [{'type': 'attempt', 'number': n, 'run_name': f'live-{n:02}'} for n in range(1, 8)]
        events += [{'type': 'settle', 'usd': 18.410925, 'request': 1},
                   {'type': 'attempt_end', 'number': 7, 'committed_usd': 18.410925}]
        return events

    def test_new_authority_is_four_attempts_with_at_most_two_deep(self):
        events = self.baseline()
        self.assertEqual(live_cli.validate_attempt(events, 'live-08', 5), 8)
        events.append({'type': 'attempt', 'number': 8, 'run_name': 'live-08', 'depth': 5})
        events.append({'type': 'attempt', 'number': 9, 'run_name': 'live-09', 'depth': 5})
        with self.assertRaisesRegex(RuntimeError, 'Deep'):
            live_cli.validate_attempt(events, 'live-10', 5)
        self.assertEqual(live_cli.validate_attempt(events, 'live-10', 1), 10)
        events += [{'type': 'attempt', 'number': n, 'run_name': f'live-{n}', 'depth': 1} for n in (10, 11)]
        with self.assertRaisesRegex(RuntimeError, 'Eleven'):
            live_cli.validate_attempt(events, 'retry-12', 1)

    def test_missing_prior_ledger_and_reused_run_names_cannot_reset_authority(self):
        with self.assertRaisesRegex(RuntimeError, 'baseline'):
            live_cli.validate_attempt([], 'live-08', 1)
        with self.assertRaisesRegex(RuntimeError, 'already used'):
            live_cli.validate_attempt(self.baseline(), 'live-01', 1)
        events = self.baseline()
        events[-2]['usd'] = 1.0
        with self.assertRaisesRegex(RuntimeError, 'baseline'):
            live_cli.validate_attempt(events, 'live-08', 1)

    def test_incremental_budget_is_fixed_across_run_names(self):
        self.assertAlmostEqual(live_cli.CAP_USD, 68.410925)
        events = self.baseline() + [{'type': 'reserve', 'usd': 50., 'request': 2}]
        with self.assertRaisesRegex(RuntimeError, 'ceiling'):
            live_cli.validate_attempt(events, 'fresh-name', 1)

    def test_claim_preserves_seeded_publications_but_never_reuses_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / 'fresh'
            (work / 'results/publications/records').mkdir(parents=True)
            seed = work / 'results/publications/records/prior.json'
            seed.write_text('{}')
            (work / 'cli.stdout.log').touch()
            live_cli.claim_workdir(work, {'ticker': 'DOCN', 'depth': 5})
            self.assertEqual(json.loads((work / 'run_claim.json').read_text())['depth'], 5)
            self.assertEqual(seed.read_text(), '{}')
            with self.assertRaisesRegex(RuntimeError, 'existing proof'):
                live_cli.claim_workdir(work, {'ticker': 'OTHER', 'depth': 1})
            other = Path(temp) / 'old'
            other.mkdir()
            (other / 'source_sha256.json').write_text('retained')
            with self.assertRaisesRegex(RuntimeError, 'existing proof'):
                live_cli.claim_workdir(other, {'ticker': 'DOCN', 'depth': 1})
            self.assertEqual((other / 'source_sha256.json').read_text(), 'retained')

    def test_ticker_and_depth_are_bounded_without_paid_setup(self):
        import subprocess
        import sys
        runner = str(Path(live_cli.__file__).resolve())
        for ticker, depth in [('AAPL', 'deep'), ('600000.SS', 'shallow')]:
            result = subprocess.run([sys.executable, runner, '--ticker', ticker, '--depth', depth],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        for args in [('--ticker', '../escape'), ('--depth', '10')]:
            result = subprocess.run([sys.executable, runner, *args], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


class RuntimeEvidenceTests(unittest.TestCase):
    def test_declared_seed_receipts_are_not_execution_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'seed-continuity.json').write_text('{"seed":true}')
            (work / 'engineering-seed.json').write_text('{"historical_opinion":false}')
            live_cli.claim_workdir(work, {'depth': 1})
            self.assertTrue((work / 'seed-continuity.json').is_file())

    def test_round_observer_forwards_original_objects_and_records_actual_turns(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        first = (['message'], {'investment_debate_state': {'count': 1}})
        second = ([], {'investment_debate_state': {'count': 10}, 'risk_debate_state': {'count': 15}})
        def stream(*args, **kwargs):
            yield first
            yield second
        with tempfile.TemporaryDirectory() as temp, patch.object(live_cli, 'WORK', Path(temp)), \
                patch.object(live_cli, 'DEPTH', 5), patch.object(TradingAgentsGraph, 'stream_run', stream):
            live_cli.install_round_observer()
            result = list(TradingAgentsGraph.stream_run(object()))
            self.assertIs(result[0], first)
            self.assertIs(result[1], second)
            saved = json.loads((Path(temp) / 'executed_rounds.json').read_text())
            self.assertEqual(saved['research_counts'], [1, 10])
            self.assertEqual(saved['research_count_max'], 10)
            self.assertEqual(saved['risk_count_max'], 15)
            self.assertEqual(saved['expected_research_turns'], 10)
            self.assertEqual(saved['expected_risk_turns'], 15)
            self.assertTrue(saved['stream_completed'])
            self.assertIsNone(saved['error_type'])

    def test_round_observer_retains_partial_counts_and_original_failure(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        error = RuntimeError('fixture error')
        first = ([], {'risk_debate_state': {'count': 2}})
        def stream(*args, **kwargs):
            yield first
            raise error
        with tempfile.TemporaryDirectory() as temp, patch.object(live_cli, 'WORK', Path(temp)), \
                patch.object(TradingAgentsGraph, 'stream_run', stream):
            live_cli.install_round_observer()
            result = TradingAgentsGraph.stream_run(object())
            self.assertIs(next(result), first)
            with self.assertRaises(RuntimeError) as caught:
                next(result)
            self.assertIs(caught.exception, error)
            saved = json.loads((Path(temp) / 'executed_rounds.json').read_text())
            self.assertFalse(saved['stream_completed'])
            self.assertEqual(saved['risk_counts'], [2])
            self.assertEqual(saved['error_type'], 'RuntimeError')

    def test_both_depths_reach_real_cli_config_and_source_manifest(self):
        import subprocess
        import sys
        for depth in (1, 5):
            with tempfile.TemporaryDirectory() as temp:
                script = '''import json,sys
from pathlib import Path
import live_cli
live_cli.WORK=Path(sys.argv[1]); live_cli.DEPTH=int(sys.argv[2]); live_cli.TICKER='AAPL'
live_cli.configure(); live_cli.verify_config(); live_cli.install_run_config_guard()
import cli.run
selection={'research_depth':1,'quick_think_llm':live_cli.MODEL,'deep_think_llm':live_cli.MODEL,
           'backend_url':'https://openrouter.ai/api/v1','llm_provider':'openrouter'}
config=cli.run._build_run_config(selection,True)
assert config['max_debate_rounds']==live_cli.DEPTH
assert config['max_risk_discuss_rounds']==live_cli.DEPTH
live_cli.source_record()
config['max_risk_discuss_rounds']=99
try: live_cli.verify_config(config)
except RuntimeError: pass
else: raise AssertionError('wrong actual depth accepted')
'''
                subprocess.run([sys.executable, '-c', script, temp, str(depth)],
                               cwd=Path(live_cli.__file__).parent, check=True, capture_output=True, text=True)
                manifest = json.loads((Path(temp) / 'source_sha256.json').read_text())['configuration']
                actual = json.loads((Path(temp) / 'actual_run_config.json').read_text())
                self.assertEqual(manifest['ticker'], 'AAPL')
                self.assertEqual(manifest['depth'], depth)
                self.assertEqual(manifest['analysis_timezone'], 'America/Denver')
                self.assertEqual(actual['max_debate_rounds'], depth)
                self.assertEqual(actual['max_risk_discuss_rounds'], depth)


if __name__ == "__main__":
    unittest.main()
