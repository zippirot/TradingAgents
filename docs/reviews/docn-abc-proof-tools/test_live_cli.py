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


if __name__ == "__main__":
    unittest.main()


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
