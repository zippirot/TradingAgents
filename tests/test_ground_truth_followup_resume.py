"""Incomplete source follow-ups cannot be promoted through cache reuse."""
import json

import pytest

from tests.test_ground_truth_audit import state
from tradingagents import ground_truth as audit


def output(quote, outcome="unsupported", evidence=None):
    return {"no_material_claims": False, "claims": [{"quoted_claim": quote, "outcome": outcome,
             "explanation": "Retained sources leave a scope question.", "evidence": evidence or []}]}


def setup(monkeypatch, sibling=False):
    candidate = state()
    candidate["filing_evidence"]["documents"][0]["blocks"].append(
        {"locator": "additional", "text": "Revenue was 100 USD. Additional period definition."})
    sources, _ = audit._source_index(candidate)
    first = {key: row for key, row in sources.items() if row["locator"] == "table-1"}
    monkeypatch.setattr(audit, "_select_sources", lambda text, sources, cap: (first, 1))
    rows = [("PM", "decision.md", "Revenue was 100 USD.")]
    if sibling:
        rows.append(("Sibling", "sibling.md", "Last claim is 10 USD."))
    parts = [("Decision", "5_portfolio", rows)]
    return candidate, parts


class Reviewer:
    def __init__(self, failure=None):
        self.failure, self.calls = failure, []

    def invoke(self, prompt):
        chunk = json.loads(prompt.split("REPORT CHUNK:\n")[1].split("\nSUPPLIED SOURCES")[0])
        self.calls.append(chunk)
        if "sibling.md" in chunk["section_id"]:
            return output(chunk["text"], "supported", [{"source_id": "doc-1", "locator": "table-1", "quote": chunk["text"]}])
        if chunk["section_id"] == "summary/summary.md":
            return {"claims": [], "no_material_claims": True}
        if chunk.get("review_claims"):
            if self.failure == "missing":
                return {"claims": [], "no_material_claims": True}
            if self.failure == "citation":
                return output(chunk["text"], evidence=[{"source_id": "doc-1", "locator": "invented", "quote": chunk["text"]}])
        return output(chunk["text"])


@pytest.mark.parametrize("failure", ["missing", "citation", "budget"])
def test_incomplete_followup_rechecks_its_chunk_before_resume_can_complete(monkeypatch, failure):
    candidate, parts = setup(monkeypatch)
    inv = audit.build_inventory(candidate, parts=parts, summary_text="")
    reviewer = Reviewer(failure)
    config = {"ground_truth_max_requests": 1} if failure == "budget" else {}
    initial = audit.run_audit(candidate, reviewer, config, inventory=inv)
    assert initial["status"] == "partial"
    assert initial["claims"][0]["quoted_claim"] == "Revenue was 100 USD."
    assert initial["coverage"]["reviewed_chunks"] == 0
    assert initial["coverage"]["remaining_chunks"] == [inv["chunks"][0]["chunk_id"]]
    fresh = Reviewer()
    resumed = audit.run_audit(candidate, fresh, inventory=inv, prior_audit=initial)
    assert len(fresh.calls) == 2
    assert resumed["coverage"]["reused_chunk_ids"] == []
    assert resumed["coverage"]["reviewed_chunks"] == 1
    assert resumed["status"] == "completed with findings"


def test_completed_sibling_reuses_while_only_unfinished_followup_rechecks(monkeypatch):
    candidate, parts = setup(monkeypatch, sibling=True)
    inv = audit.build_inventory(candidate, parts=parts, summary_text="")
    initial = audit.run_audit(candidate, Reviewer("missing"), inventory=inv)
    sibling = next(c["chunk_id"] for c in inv["chunks"] if "sibling.md" in c["section_id"])
    assert initial["coverage"]["reviewed_chunk_ids"] == [sibling]
    reviewer = Reviewer()
    resumed = audit.run_audit(candidate, reviewer, inventory=inv, prior_audit=initial)
    assert len(reviewer.calls) == 2
    assert all("sibling.md" not in c["section_id"] for c in reviewer.calls)
    assert resumed["coverage"]["reused_chunk_ids"] == [sibling]
    assert len(resumed["claims"]) == 2
    assert resumed["coverage"]["reviewed_chunks"] == 2


def test_post_summary_implicit_prior_cannot_clear_prepublication_budget_failure(monkeypatch):
    candidate, parts = setup(monkeypatch)
    pre = audit.build_inventory(candidate, parts=parts, summary_text="")
    candidate["ground_truth_prepublication"] = audit.run_audit(
        candidate, Reviewer(), {"ground_truth_max_requests": 1}, inventory=pre)
    final = audit.build_inventory(candidate, parts=parts, summary_text="Concluding qualitative summary.")
    reviewer = Reviewer()
    result = audit.run_audit(candidate, reviewer, inventory=final)
    assert len(reviewer.calls) == 3
    assert result["coverage"]["reused_chunk_ids"] == []
    assert result["coverage"]["reviewed_chunks"] == 2


def test_schema_four_success_metadata_cannot_reuse_or_export_as_current(monkeypatch):
    candidate, parts = setup(monkeypatch)
    inv = audit.build_inventory(candidate, parts=parts, summary_text="")
    old = audit.run_audit(candidate, Reviewer(), inventory=inv)
    old["schema_version"] = 4
    audit.seal_audit(old)
    assert audit.resolve_audit(candidate, old, inventory=inv)["status"] == "unavailable"
    fresh = Reviewer()
    result = audit.run_audit(candidate, fresh, inventory=inv, prior_audit=old)
    assert len(fresh.calls) == 2 and result["coverage"]["reused_chunk_ids"] == []
