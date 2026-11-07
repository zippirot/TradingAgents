"""Offline private-input proof. Run from the repository with PYTHONPATH=.

Reads saved DOCN state/cache; writes only a temporary clone and /tmp receipt.
No network or model providers are permitted. Private inputs are not bundled.
"""

import hashlib
import json
import shutil
import socket
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tradingagents.agents.assumption_history import assumption_changes
from tradingagents.agents.decision_context import prepare_decision_context
from tradingagents.agents.valuation_comparison import price_implied_valuation
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.vendors import sec_documents as sec
from tradingagents.memory import publication
from tradingagents.reporting import write_report_tree


def no_network(*args, **kwargs):
    raise AssertionError("network forbidden")


socket.socket.connect = no_network
src = (
    Path.home()
    / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-07.json"
)
s = json.loads(src.read_text())
root = Path(tempfile.mkdtemp(prefix="numbers-proof-"))
shutil.copytree(Path.home() / ".tradingagents/logs/publications", root / "publications")
cfg = {"results_dir": str(root)}
changes = assumption_changes(cfg, "DOCN", s)
assert changes["status"] == "available", changes
assert changes["prior_decision_id"] == s["prior_thesis"]["publication_id"], changes
rec = publication.load_record(cfg, changes["prior_decision_id"])
prior = publication.load_evidence(cfg, rec)
a = s["prior_thesis"]["conditions"]
b = s["thesis"]["prior_conditions"]
ids = [c["condition_id"] for c in a]
assert set(ids) == {c["condition_id"] for c in b}
assert all(c["disposition"] == "kept" for c in b)
assert len(ids) == 4
before = price_implied_valuation(s)
assert before["management_revenue_guidance_range_usd"] == ["1208000000", "1211000000"]
s["decision_context"] = prepare_decision_context(s)
s["decision_context"]["assumption_changes"] = changes
# A re-export comparison is retained data. Export must never recalculate it.
s.pop("publication_record", None)
s["run_id"] = "afe00104-8505-4f40-bb0c-1d4f9a468b20"
new_record = publication.publish(cfg, s, "DOCN", s["trade_date"])
s["publication_record"] = {
    k: new_record[k] for k in ("decision_id", "published_at", "record_sha256")
}
later = deepcopy(s)
later.pop("publication_record")
later["run_id"] = "afe00104-8505-4f40-bb0c-1d4f9a468b21"
with patch.object(
    publication, "list_records", side_effect=AssertionError("export consulted mutable history")
):
    write_report_tree(s, "DOCN", root / "first", publication_config=cfg)
publication.publish(cfg, later, "DOCN", later["trade_date"])
with patch.object(
    publication, "list_records", side_effect=AssertionError("export consulted mutable history")
):
    write_report_tree(s, "DOCN", root / "second", publication_config=cfg)
for ext in ("md", "html"):
    text = (root / "second" / f"complete_report.{ext}").read_text()
    assert "Changed since 2026-11-06" in text
    assert "Changed since" in text
# Run real acquisition with the only substituted boundary being immutable cached HTTP bytes.
fetched = []


def cached(self, url):
    p = (
        Path.home()
        / ".tradingagents/cache/sec_documents"
        / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    )
    v = json.loads(p.read_text())
    assert v["url"] == url and hashlib.sha256(v["text"].encode()).hexdigest() == v["content_hash"]
    fetched.append(url)
    return v


with (
    patch.object(sec, "cik_for", return_value=s["financial_evidence"]["cik"]),
    patch.object(sec.DocumentClient, "fetch", cached),
):
    package = sec.get_filing_evidence("DOCN", "2026-11-07")
releases = [
    d
    for d in package.documents
    if "pressrelease" in d.url and str(d.filing.filed_date) == "2026-11-03"
]
assert releases, [(d.url, str(d.filing.filed_date)) for d in package.documents]
guidance = [
    {"source_id": d.source_id, "locator": b.locator, "text": b.text}
    for d in releases
    for b in d.blocks
    if "1,208" in b.text or "1.208" in b.text
]
assert guidance
namespace = {}
exec(
    subprocess.check_output(
        ["git", "show", "9ba8aa9c:tradingagents/agents/valuation_outlooks.py"], text=True
    ),
    namespace,
)
assert namespace["grounded_outlooks"](s) == grounded_outlooks(s) == ()
assert (
    before["management_revenue_guidance_range_usd"]
    == s["price_implied_valuation"]["management_revenue_guidance_range_usd"]
)
receipt = {
    "source_state_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
    "disposable_root": str(root),
    "prior_decision_id": changes["prior_decision_id"],
    "prior_as_of": changes["prior_as_of"],
    "comparison": changes,
    "a7": {
        "parent_version": s["prior_thesis"]["version_id"],
        "child_version": s["thesis"]["version_id"],
        "condition_ids": ids,
        "dispositions": [r["disposition"] for r in s["thesis"]["prior_conditions"]],
    },
    "source_only_guidance": {k: v for k, v in before.items() if k.startswith("management")},
    "adapter_outlooks": {
        "baseline": len(namespace["grounded_outlooks"](s)),
        "candidate": len(grounded_outlooks(s)),
    },
    "a3": {
        "documents": len(package.documents),
        "characters": sum(len(b.text) for d in package.documents for b in d.blocks),
        "fetch_count": len(fetched),
        "guidance": guidance,
    },
    "exports": [str(root / "second" / f"complete_report.{ext}") for ext in ("md", "html")],
}
Path("/tmp/numbers-replay.json").write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt, indent=2))
