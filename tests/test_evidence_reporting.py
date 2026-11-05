"""Evidence exports stay source-grounded and fail visibly on required writes."""

import json
from pathlib import Path

import pytest

from tradingagents.reporting import write_report_tree


def state(**changes):
    result = {
        "trade_date": "2026-10-19",
        "fundamentals_report": "Buy DOCN with target $96. Unvalidated narrative.",
        "market_report": "Buy with target $96 from chart.",
        "final_trade_decision": "**Rating**: Buy\n\nTarget $96.",
        "evidence_quality": {
            "schema_version": 1,
            "scope": "Selected US SEC-filer fundamentals",
            "status": "insufficient",
            "checks": [
                {"code": "balance_sheet", "status": "pass", "message": "Assets reconcile"},
                {
                    "code": "material_claims",
                    "status": "unavailable",
                    "message": "Claim unsupported",
                },
            ],
            "warnings": ["Source excerpt truncated"],
        },
        "financial_evidence": {
            "facts": [{"fact_id": "f", "value": "123.456"}],
            "sources": [{"source_id": "s"}],
        },
        "filing_evidence": {"documents": [{"source_id": "doc", "content_hash": "abc"}]},
        "financial_calculations": [
            {
                "method": "assets_equals_liabilities_plus_equity_v1",
                "status": "pass",
                "result": "123.456",
                "unit": "USD",
                "input_fact_ids": ["f"],
                "message": "Exact",
            }
        ],
        "financial_claim_validation": {"raw_report": "Model said $96.", "status": "unavailable"},
        "target_validation": {"status": "unavailable", "reason": "unsupported target"},
        "unvalidated_outputs": {"investment_plan": "Buy target $96"},
    }
    result.update(changes)
    return result


def test_review_export_has_deterministic_evidence_and_no_buy_decision(tmp_path):
    write_report_tree(state(), "DOCN", tmp_path)
    md = (tmp_path / "complete_report.md").read_text()
    html = (tmp_path / "complete_report.html").read_text()
    quality = json.loads((tmp_path / "quality.json").read_text())
    evidence = json.loads((tmp_path / "evidence.json").read_text())
    assert "- Rating: REVIEW" in md
    assert "Target $96" not in md and "Target $96" not in html
    assert "Evidence and Quality" in md and "Evidence and Quality" in html
    assert "Assets reconcile" in md and "Claim unsupported" in html
    assert "123.46" in md and "123.46" in html
    assert evidence["financial_calculations"][0]["result"] == "123.456"
    assert "Source excerpt truncated" in md and "Source excerpt truncated" in html
    assert quality["status"] == "insufficient"
    assert evidence["financial_evidence"]["facts"][0]["value"] == "123.456"
    assert evidence["filing_evidence"]["documents"][0]["source_id"] == "doc"
    assert evidence["financial_calculations"][0]["input_fact_ids"] == ["f"]
    assert evidence["target_validation"]["status"] == "unsupported"
    assert evidence["target_validation"]["target"] is None
    assert evidence["raw_diagnostics"]["unvalidated_outputs"]["target_validation"]["status"] == "unavailable"
    assert (
        evidence["raw_diagnostics"]["financial_claim_validation"]["raw_report"] == "Model said $96."
    )
    assert evidence["raw_diagnostics"]["unvalidated_outputs"]["investment_plan"] == "Buy target $96"
    assert (
        "Buy DOCN with target $96"
        in evidence["raw_diagnostics"]["unvalidated_outputs"]["fundamentals_report"]
    )
    assert (
        md.index("I. Analyst Team Reports")
        < md.index("V. Portfolio Manager Decision")
        < md.index("VI. Evidence and Quality")
    )


def test_legacy_export_is_marked_without_rewriting_old_decision(tmp_path):
    legacy = {"trade_date": "2024-01-01", "final_trade_decision": "**Rating**: Hold\nOld decision"}
    write_report_tree(legacy, "AAPL", tmp_path, html=True)
    md = (tmp_path / "complete_report.md").read_text()
    page = (tmp_path / "complete_report.html").read_text()
    assert "Old decision" in md and "Old decision" in page
    assert "Legacy export" in md and "Legacy export" in page
    assert json.loads((tmp_path / "quality.json").read_text())["status"] == "unvalidated"


def test_required_json_write_failure_raises_and_preserves_prior_file(tmp_path, monkeypatch):
    from tradingagents.dataflows import files

    old = tmp_path / "quality.json"
    old.write_text('{"old": true}')
    real_replace = files.os.replace

    def fail_json(source, dest):
        if Path(dest).name == "quality.json":
            raise PermissionError("locked")
        return real_replace(source, dest)

    monkeypatch.setattr(files.os, "replace", fail_json)
    with pytest.raises(PermissionError, match="locked"):
        write_report_tree(state(), "DOCN", tmp_path, html=False)
    assert old.read_text() == '{"old": true}'
    assert not list(tmp_path.glob("quality.json.*.tmp"))


def test_direct_html_render_applies_review_boundary():
    from tradingagents.report_html import render_report
    from tradingagents.reporting import _report_parts

    unsafe = state()
    page = render_report("DOCN", unsafe, None, _report_parts(unsafe))
    assert "Target $96" not in page
    assert "REVIEW" in page
    assert "Evidence and Quality" in page
