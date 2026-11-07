"""Offline report routes disclose missing or stale opted-in factual reviews."""
import json
from copy import deepcopy

from tradingagents.report_html import render_report
from tradingagents.reporting import write_report_tree


def test_disabled_legacy_export_has_no_ground_truth_work(tmp_path, monkeypatch):
    from tradingagents import ground_truth_display

    def unexpected(*args, **kwargs):
        raise AssertionError("disabled export must not construct an audit")

    monkeypatch.setattr(ground_truth_display, "build_report_inventory", unexpected)
    state = {"trade_date": "2026-11-06", "company_of_interest": "DOCN",
             "final_trade_decision": "Hold", "final_rating": "Hold"}
    write_report_tree(state, "DOCN", tmp_path)
    assert not list(tmp_path.glob("ground_truth_audit*"))
    assert "Ground Truth Audit" not in (tmp_path / "complete_report.md").read_text()


def test_enabled_missing_audit_is_disclosed_in_both_formats_without_mutation(tmp_path):
    state = {"trade_date": "2026-11-06", "company_of_interest": "DOCN", "run_id": "run-1",
             "run_settings": {"ground_truth_audit": True},
             "final_trade_decision": "Hold", "final_rating": "Hold"}
    original = deepcopy(state)
    write_report_tree(state, "DOCN", tmp_path)
    for name in ("complete_report.md", "complete_report.html"):
        text = (tmp_path / name).read_text()
        assert "Ground Truth" in text
        assert "unavailable" in text.lower()
    companions = list(tmp_path.glob("ground_truth_audit-*.md"))
    assert len(companions) == 1
    assert companions[0].name in (tmp_path / "complete_report.html").read_text()
    assert state == original


def test_direct_html_discloses_missing_audit_without_promising_a_companion():
    state = {"trade_date": "2026-11-06", "company_of_interest": "DOCN",
             "run_settings": {"ground_truth_audit": True}, "final_trade_decision": "Hold"}
    page = render_report("DOCN", state, None)
    assert "Ground Truth" in page
    assert "unavailable" in page.lower()
    assert "ground_truth_audit-" not in page


def test_matching_saved_audit_survives_export_and_changed_claim_invalidates_it(tmp_path):
    from tradingagents.ground_truth import run_audit
    from tradingagents.ground_truth_display import build_report_inventory

    class Reviewer:
        def invoke(self, prompt):
            chunk = json.loads(prompt.split("REPORT CHUNK:\n", 1)[1].split("\nSUPPLIED SOURCES", 1)[0])
            return {"claims": [{"quoted_claim": chunk["text"], "outcome": "unsupported",
                                "explanation": "Evidence needs review.", "evidence": []}],
                    "no_material_claims": False}

    state = {"trade_date": "2026-11-06", "company_of_interest": "DOCN", "run_id": "r1",
             "run_settings": {"ground_truth_audit": True},
             "market_report": "Distinct final claim 123.", "final_trade_decision": "Hold"}
    state["ground_truth_audit"] = run_audit(state, Reviewer(), inventory=build_report_inventory(state))
    before = deepcopy(state)
    write_report_tree(state, "DOCN", tmp_path / "first")
    assert "Evidence needs review." in (tmp_path / "first/complete_report.md").read_text()
    assert state == before
    state["market_report"] = "A revised claim 456."
    write_report_tree(state, "DOCN", tmp_path / "second")
    page = (tmp_path / "second/complete_report.md").read_text()
    assert "unavailable" in page.lower()
    assert "Evidence needs review." not in page


def test_audit_companion_write_failure_preserves_research_without_stale_link(tmp_path, monkeypatch):
    from tradingagents import reporting

    original_write = reporting._write_text

    def failed_companion(path, text):
        if path.name.startswith("ground_truth_audit-"):
            raise OSError("fixture audit-only disk failure")
        return original_write(path, text)

    monkeypatch.setattr(reporting, "_write_text", failed_companion)
    state = {"company_of_interest": "DOCN", "trade_date": "2026-11-06",
             "run_settings": {"ground_truth_audit": True}, "final_trade_decision": "Hold"}
    write_report_tree(state, "DOCN", tmp_path)
    for filename in ("complete_report.md", "complete_report.html"):
        text = (tmp_path / filename).read_text()
        assert "Hold" in text and "unavailable" in text.lower()
        assert "ground_truth_audit-" not in text


def test_published_diagnostic_references_keep_matching_audit_on_both_exports(tmp_path):
    from uuid import uuid4

    from tests.test_publication_graph import graph_and_state
    from tradingagents.ground_truth import run_audit
    from tradingagents.ground_truth_display import build_report_inventory

    app, state = graph_and_state(tmp_path)
    state.update(run_id=str(uuid4()), run_settings={'ground_truth_audit': True},
                 market_report='The analyst original belongs in diagnostics.')
    app.record_decision('DOCN', state['trade_date'], state)

    class Reviewer:
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
            return {'claims': [{'quoted_claim': chunk['text'], 'outcome': 'unsupported',
                                'explanation': 'Retained fixture source gap.', 'evidence': []}],
                    'no_material_claims': False}

    state['ground_truth_audit'] = run_audit(state, Reviewer(), inventory=build_report_inventory(state))
    assert state['ground_truth_audit']['status'] == 'partial'
    before = deepcopy(state)
    write_report_tree(state, 'DOCN', tmp_path / 'published', publication_config=app.config)
    detail = next((tmp_path / 'published').glob('ground_truth_audit-*.md')).read_text()
    assert 'Status: **partial**.' in detail
    assert 'stale or invalid' not in detail
    assert (tmp_path / 'published/diagnostics.json').is_file()
    for suffix in ('md', 'html'):
        text = (tmp_path / f'published/complete_report.{suffix}').read_text()
        assert 'Retained fixture source gap.' in text
        assert 'diagnostics.json' in text
        assert 'evidence.json diagnostics' not in text
    direct = render_report('DOCN', state, None)
    assert 'Retained fixture source gap.' in direct
    assert 'Saved audit unavailable' not in direct
    assert state == before


def test_summary_reference_normalization_preserves_saved_summary_inputs():
    from tradingagents.ground_truth import run_audit
    from tradingagents.ground_truth_display import build_report_inventory, project_report

    state = {'run_id': 'normalized-summary', 'trade_date': '2026-11-06',
             'publication_record': {'decision_id': 'published'},
             'run_settings': {'ground_truth_audit': True}}
    parts = [('Decision', '5_portfolio', [('PM', 'decision.md', 'See evidence.json diagnostics.')])]
    summary = {'process': 'A retained report.', 'sentences': ['See evidence.json diagnostics.']}
    original_summary = deepcopy(summary)
    original_parts = deepcopy(parts)
    class Reviewer:
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
            return {'claims': [{'quoted_claim': chunk['text'], 'outcome': 'unsupported',
                                'explanation': 'Fixture reference checked.', 'evidence': []}],
                    'no_material_claims': False}
    inventory = build_report_inventory(state, parts, summary)
    assert all('evidence.json diagnostics' not in c['text'] for c in inventory['chunks'])
    state['ground_truth_audit'] = run_audit(state, Reviewer(), inventory=inventory)
    _parts, projected, text, record = project_report(state, parts, summary)
    assert record['status'] == state['ground_truth_audit']['status']
    assert 'evidence.json diagnostics' not in projected['_ground_truth_text']
    assert 'diagnostics.json' in projected['_ground_truth_text']
    assert parts == original_parts and summary == original_summary
