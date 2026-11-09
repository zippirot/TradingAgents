"""Material unresolved factual issues are visible in the shared assessment."""
from copy import deepcopy

import pytest

from tradingagents.ground_truth_display import audit_assessment


def claim(number, *, material=True, outcome='unsupported'):
    return {'quoted_claim': f'Revenue claim {number} was 99 million USD.',
            'section_id': '5_portfolio/decision.md', 'chunk_id': f'5_portfolio/decision.md@{number}:100',
            'outcome': outcome, 'decision_material': material,
            'explanation': 'The dated source gives a different value.',
            'correction': 'Revenue was 20 million USD.' if outcome == 'contradicted' else None,
            'evidence': [{'source_id': 'sec-source', 'locator': 'table-1',
                          'url': 'https://www.sec.gov/Archives/edgar/data/1582961/example.htm',
                          'quote': 'Revenue was 20 million USD.'}]}


def record(claims, status='partial'):
    return {'status': status, 'claims': claims,
            'coverage': {'total_chunks': 9, 'reviewed_chunks': 8, 'source_gaps': []}, 'limits': []}


def test_main_assessment_lists_first_three_material_passages_and_remainder():
    findings = [claim(0, material=False), *(claim(n) for n in range(1, 6))]
    text = audit_assessment(record(findings), {})
    for number in range(1, 4):
        assert f'Revenue claim {number} was 99 million USD.' in text
        assert f'5_portfolio/decision.md@{number}:100' in text
    assert 'Revenue claim 0' not in text and 'Revenue claim 4' not in text
    assert '2 additional material' in text
    assert 'Full Ground Truth Audit' in text
    assert 'https://www.sec.gov/Archives/' in text
    assert 'partial' in text and 'Reviewed 8 of 9' in text


def test_handled_correction_is_suppressed_while_unsupported_claim_remains():
    handled = claim(1, outcome='contradicted')
    unresolved = claim(2)
    state = {'ground_truth_reassessment': {'status': 'completed', 'corrections': [deepcopy(handled)]}}
    bound = {**record([handled, unresolved]), 'reassessment_history': deepcopy(state['ground_truth_reassessment'])}
    text = audit_assessment(bound, state)
    assert 'Revenue claim 1' not in text
    assert 'Revenue claim 2 was 99 million USD.' in text
    assert 'Recommendation needs review' in text


@pytest.mark.parametrize('status', ['partial', 'unavailable'])
def test_assessment_escapes_passage_and_location_and_retains_units(status):
    finding = claim(1)
    finding['quoted_claim'] = '<script>alert(1)</script> Revenue 99 USD [fake](javascript:bad)'
    finding['chunk_id'] = '<location>[fake]'
    text = audit_assessment(record([finding], status), {})
    assert f'Status **{status}**' in text
    assert '<script>' not in text and '<location>' not in text
    assert '&lt;script&gt;' in text and '99 USD' in text
    assert r'\[fake\]' in text


def test_full_detail_preserves_nonmaterial_and_handled_findings():
    from tradingagents.ground_truth import render_audit

    findings = [claim(0, material=False), claim(1, outcome='contradicted'), claim(2)]
    detail = render_audit(record(findings))
    assert all(f'Revenue claim {number}' in detail for number in (0, 1, 2))
    assert detail.index('Revenue claim 1') < detail.index('Revenue claim 0')
    assert 'Material to the recommendation' in detail
    assert '20 million USD' in detail and 'https://www.sec.gov/Archives/' in detail


def test_cli_markdown_and_html_use_the_same_main_assessment(tmp_path, monkeypatch):
    import json
    from io import StringIO

    from rich.console import Console

    from cli import display
    from tradingagents import ground_truth_display
    from tradingagents.ground_truth import run_audit
    from tradingagents.ground_truth_display import build_report_inventory
    from tradingagents.report_html import render_report
    from tradingagents.reporting import write_report_tree

    state = {'run_id': 'display-proof', 'company_of_interest': 'DOCN', 'trade_date': '2026-11-06',
             'run_settings': {'ground_truth_audit': True}, 'market_report': 'Material unit claim 42 USD.',
             'final_trade_decision': 'Hold', 'final_rating': 'Hold'}
    class Reviewer:
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
            return {'no_material_claims': False, 'claims': [{
                'quoted_claim': chunk['text'], 'outcome': 'unsupported', 'decision_material': True,
                'explanation': 'This passage needs source review.', 'evidence': []}]}
    state['ground_truth_audit'] = run_audit(state, Reviewer(), inventory=build_report_inventory(state))
    actual = ground_truth_display.audit_assessment
    calls = []
    def marked(record, state):
        calls.append(record)
        return 'SHARED_MATERIAL_ASSESSMENT\n\n' + actual(record, state)
    monkeypatch.setattr(ground_truth_display, 'audit_assessment', marked)
    write_report_tree(state, 'DOCN', tmp_path)
    assert calls
    assert 'SHARED_MATERIAL_ASSESSMENT' in (tmp_path / 'complete_report.md').read_text()
    assert 'SHARED_MATERIAL_ASSESSMENT' in (tmp_path / 'complete_report.html').read_text()
    calls.clear()
    assert 'SHARED_MATERIAL_ASSESSMENT' in render_report('DOCN', state, None)
    assert calls
    calls.clear()
    output = StringIO()
    monkeypatch.setattr(display, 'console', Console(file=output, width=180))
    display.display_complete_report(state)
    assert calls and 'SHARED_MATERIAL_ASSESSMENT' in output.getvalue()


@pytest.mark.parametrize('url', ['https://[bad', 'javascript:alert(1)'])
def test_malformed_or_unsafe_retained_url_does_not_cancel_assessment_or_export(tmp_path, url):
    import json

    from tradingagents.ground_truth import run_audit, seal_audit
    from tradingagents.ground_truth_display import build_report_inventory
    from tradingagents.reporting import write_report_tree

    finding = claim(1)
    finding['evidence'][0]['url'] = url
    text = audit_assessment(record([finding]), {})
    assert 'Revenue claim 1 was 99 million USD.' in text
    assert '](javascript:' not in text
    state = {'run_id': 'malformed-url', 'company_of_interest': 'DOCN', 'trade_date': '2026-11-06',
             'run_settings': {'ground_truth_audit': True}, 'final_trade_decision': 'Hold'}
    class Reviewer:
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
            return {'no_material_claims': False, 'claims': [{
                'quoted_claim': chunk['text'], 'outcome': 'unsupported', 'decision_material': True,
                'explanation': 'Retained source needs review.', 'evidence': []}]}
    saved = run_audit(state, Reviewer(), inventory=build_report_inventory(state))
    # Even an internally checksummed older companion can contain a bad address.
    saved['claims'][0]['evidence'] = [{'url': url, 'source_id': 'old-ref', 'locator': 'passage',
                                     'quote': 'Retained quote', 'known_at': None, 'kind': 'retained source'}]
    state['ground_truth_audit'] = seal_audit(saved)
    write_report_tree(state, 'DOCN', tmp_path)
    assert (tmp_path / 'complete_report.md').is_file()
    html = (tmp_path / 'complete_report.html').read_text()
    assert 'Retained source needs review.' in html
    assert 'href="javascript:' not in html


def _corrected(final_text):
    handled = claim(1, outcome='contradicted')
    state = {'final_trade_decision': final_text,
             'ground_truth_reassessment': {'status': 'completed', 'corrections': [deepcopy(handled)]}}
    return {**record([handled]), 'reassessment_history': deepcopy(state['ground_truth_reassessment'])}, state


def test_pm_repeating_the_corrected_claim_keeps_the_review_warning():
    bound, state = _corrected('We keep Hold. Revenue claim 1 was 99 million USD.')
    text = audit_assessment(bound, state)
    assert 'Revenue claim 1' in text and 'Recommendation needs review' in text


def test_pm_removing_the_claim_clears_the_review_warning():
    bound, state = _corrected('We keep Hold. Revenue was 20 million USD.')
    text = audit_assessment(bound, state)
    assert 'Revenue claim 1' not in text and 'Recommendation needs review' not in text


def test_justified_unchanged_rating_is_not_flagged_for_the_rating_alone():
    bound, state = _corrected('Hold is retained because margins, not revenue, decide it. Revenue was 20 million USD.')
    state['final_rating'] = 'Hold'
    assert 'Recommendation needs review' not in audit_assessment(bound, state)
