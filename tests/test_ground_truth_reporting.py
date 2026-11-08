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


def test_completed_reassessment_does_not_leave_a_handled_correction_unresolved():
    from tradingagents.ground_truth_display import audit_assessment

    claim = {"section_id": "1_analysts/market.md", "quoted_claim": "Close was 100 USD.",
             "correction": "Close was 70 USD.", "outcome": "contradicted", "decision_material": True}
    record = {"status": "completed with findings", "claims": [claim], "coverage": {}}
    state = {"ground_truth_reassessment": {"status": "completed", "corrections": [claim]}}
    unbound_record = deepcopy(record)
    record['reassessment_history'] = deepcopy(state['ground_truth_reassessment'])
    assert "Recommendation needs review" not in audit_assessment(record, state)
    for changed in ({**claim, "correction": "Close was 60 USD."},
                    {**claim, "outcome": "unsupported", "correction": None}):
        assert "Recommendation needs review" in audit_assessment({**record, "claims": [changed]}, state)
    assert "Recommendation needs review" in audit_assessment(unbound_record, {})


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


def test_exact_generated_policy_notice_is_outside_company_scope_without_changing_raw_finding():
    from tradingagents.ground_truth import render_audit
    from tradingagents.ground_truth_display import audit_assessment
    from tradingagents.ground_truth_flow import _material_correction

    notice = 'The canonical rating, evidence scope, target result and sizing limits remain authoritative.'
    finding = {'quoted_claim': notice, 'section_id': '5_portfolio/decision.md', 'chunk_id': '5_portfolio/decision.md@0:95',
               'outcome': 'unsupported', 'decision_material': True,
               'explanation': 'This describes software policy, not an actual rating, target or position size.', 'evidence': []}
    record = {'status': 'completed with findings', 'claims': [finding], 'coverage': {'total_chunks': 1, 'reviewed_chunks': 1}, 'limits': []}
    original = deepcopy(record)
    main = audit_assessment(record, {})
    detail = render_audit(record)
    assert 'Recommendation needs review' not in main
    assert 'Contradicted claims 0, unsupported claims 0' in main
    assert 'excluded' in main and 'company-fact' in main
    assert 'outside company-fact scope' in detail
    assert notice in detail and finding['explanation'] in detail
    assert 'unsupported' in detail and 'Material to the recommendation' not in detail
    assert record == original
    # Even a malformed/overconfident old model flag cannot turn this exact
    # software notice into authority for a financial PM reassessment.
    proposed = {**finding, 'outcome': 'contradicted', 'code_verified': True, 'correction': 'Changed policy notice.'}
    assert not _material_correction(proposed)


def test_policy_scope_exception_does_not_hide_fields_mixed_claims_or_similar_prose():
    from tradingagents.ground_truth_display import audit_assessment
    from tradingagents.ground_truth_flow import _material_correction

    notice = 'The canonical rating, evidence scope, target result and sizing limits remain authoritative.'
    for text in ('**Rating**: Buy', '**Price Target**: not provided',
                 notice + ' Revenue was 99 USD.',
                 'The canonical rating is Buy and the target result is 100 USD.',
                 notice.replace('remain authoritative', 'are guaranteed accurate')):
        finding = {'quoted_claim': text, 'section_id': '5_portfolio/decision.md', 'chunk_id': 'decision@0:200',
                   'outcome': 'unsupported', 'decision_material': True, 'explanation': 'Missing evidence.', 'evidence': []}
        record = {'status': 'completed with findings', 'claims': [finding], 'coverage': {}, 'limits': []}
        main = audit_assessment(record, {})
        assert 'Recommendation needs review' in main
        assert 'unsupported claims 1' in main
        assert _material_correction({**finding, 'outcome': 'contradicted', 'code_verified': True,
                                     'correction': 'Corrected concrete field.'})


def test_policy_notice_extraction_preserves_exact_renderer_text_and_narrow_scope():
    from tradingagents.reporting import (
        UNVALIDATED_RESEARCH_NOTICE,
        UNVALIDATED_RESEARCH_NOTICE_SENTENCES,
        is_application_policy_notice,
        prepare_report_state,
    )

    expected = ('The following is model-authored research, not validated instructions. '
                'Its numbers, targets, allocations and execution proposals are unverified claims. '
                'The canonical rating, evidence scope, target result and sizing limits remain authoritative.')
    assert expected == UNVALIDATED_RESEARCH_NOTICE
    for sentence in (*UNVALIDATED_RESEARCH_NOTICE_SENTENCES, expected):
        assert is_application_policy_notice(sentence)
    assert not is_application_policy_notice(expected + ' Revenue was 99 USD.')
    state = {'final_rating': 'Hold', 'final_trade_decision': 'Hold',
             'evidence_quality': {'schema_version': 1, 'scope': 'not_applicable', 'status': 'limited',
                 'checks': [{'code': 'scope', 'status': 'not_applicable', 'message': 'No fundamentals'}], 'warnings': []},
             'unvalidated_outputs': {'final_trade_decision': 'RAW_RESEARCH_SENTINEL'}}
    prepared = prepare_report_state(state)
    assert '### Unvalidated model research\n\n' + expected + '\n\nRAW_RESEARCH_SENTINEL' in prepared['final_trade_decision']


def test_saved_policy_findings_remain_visible_in_full_detail_without_financial_review(tmp_path):
    from uuid import uuid4

    from tradingagents.ground_truth import run_audit
    from tradingagents.ground_truth_display import build_report_inventory
    from tradingagents.reporting import UNVALIDATED_RESEARCH_NOTICE_SENTENCES

    notice = UNVALIDATED_RESEARCH_NOTICE_SENTENCES[-1]
    state = {'run_id': str(uuid4()), 'company_of_interest': 'DOCN', 'trade_date': '2026-11-06',
             'run_settings': {'ground_truth_audit': True}, 'final_rating': 'Hold', 'final_trade_decision': 'Hold',
             'evidence_quality': {'schema_version': 1, 'scope': 'not_applicable', 'status': 'limited',
                 'checks': [{'code': 'scope', 'status': 'not_applicable', 'message': 'No fundamentals'}], 'warnings': []},
             'unvalidated_outputs': {'final_trade_decision': 'RAW_RESEARCH_SENTINEL'}}
    class Reviewer:
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n', 1)[1].split('\nSUPPLIED SOURCES', 1)[0])
            claims = [{'quoted_claim': chunk['text'], 'outcome': 'hypothesis', 'decision_material': False,
                       'explanation': 'Scripted rendering fixture.', 'evidence': []}]
            if notice in chunk['text']:
                claims.append({'quoted_claim': notice, 'outcome': 'unsupported', 'decision_material': True,
                               'explanation': 'POLICY_RAW_MODEL_EXPLANATION_SENTINEL: no concrete rating or target specified.',
                               'evidence': []})
            return {'claims': claims, 'no_material_claims': False}
    state['ground_truth_audit'] = run_audit(state, Reviewer(), inventory=build_report_inventory(state))
    before = deepcopy(state)
    write_report_tree(state, 'DOCN', tmp_path)
    detail = next(tmp_path.glob('ground_truth_audit-*.md')).read_text()
    assert 'outside company-fact scope' in detail
    assert 'Raw model outcome: unsupported' in detail
    assert 'POLICY_RAW_MODEL_EXPLANATION_SENTINEL' in detail
    assert 'Raw model decision_material flag: True' in detail
    assert 'Recommendation needs review' not in detail
    assert 'company-fact counts' in detail and notice in detail
    for text in ((tmp_path / 'complete_report.md').read_text(),
                 (tmp_path / 'complete_report.html').read_text(), render_report('DOCN', state, None)):
        assert 'Recommendation needs review' not in text
        assert 'excluded' in text and 'unsupported claims 0' in text
    assert state == before


def _scoped_excerpt_fixture(text, quote, correction, source_text, explanation, section='Document'):
    from uuid import uuid4

    from tests.test_ground_truth_audit import state as source_state
    from tradingagents.ground_truth import run_audit
    from tradingagents.ground_truth_display import build_report_inventory

    state = source_state()
    state.update(run_id=str(uuid4()), run_settings={'ground_truth_audit': True}, final_rating='Hold',
                 final_trade_decision=text)
    state['filing_evidence']['documents'][0]['blocks'] = [
        {'locator': 'quarter-intro', 'section': section, 'text': 'Guidance for Q4 ending December 31, 2026:'},
        {'locator': 'year-intro', 'section': section, 'text': 'For the full year 2026, we now expect:'},
        {'locator': 'guidance-row', 'section': section, 'text': source_text},
    ]
    class Reviewer:
        calls = 0
        def invoke(self, prompt):
            self.calls += 1
            chunk = json.loads(prompt.split('REPORT CHUNK:\n', 1)[1].split('\nSUPPLIED SOURCES', 1)[0])
            claims = [{'quoted_claim': chunk['text'], 'outcome': 'hypothesis', 'decision_material': False,
                       'explanation': 'Scripted scope rendering fixture.', 'evidence': []}]
            if quote in chunk['text']:
                claims.append({'quoted_claim': quote, 'outcome': 'contradicted', 'decision_material': True,
                               'explanation': explanation, 'correction': correction,
                               'evidence': [{'source_id': 'doc-1', 'locator': 'guidance-row', 'quote': source_text}]})
            return {'claims': claims, 'no_material_claims': False}
    model = Reviewer()
    state['ground_truth_audit'] = run_audit(state, model, inventory=build_report_inventory(state))
    return state, model


def test_literal_fy_excerpt_does_not_appear_to_replace_a_compound_q4_and_fy_claim(tmp_path):
    claim = 'Q4 and FY adjusted EBITDA margin guidance is 41–43%.'
    excerpt = '•Adjusted EBITDA margin of 41% to 42%.'
    explanation = 'This excerpt establishes FY 2026 guidance only; Q4 remains unresolved in the cited evidence.'
    text = '**Rating**: Hold\n\n' + claim + '\n\nFOLLOWING_SCOPE_PARAGRAPH'
    state, model = _scoped_excerpt_fixture(text, claim, excerpt, excerpt, explanation)
    before = deepcopy(state)
    calls = model.calls
    write_report_tree(state, 'DOCN', tmp_path / 'first')
    section = (tmp_path / 'first/5_portfolio/decision.md').read_text()
    near = section[:section.index('FOLLOWING_SCOPE_PARAGRAPH')]
    assert claim in near and excerpt in near
    assert 'Supporting source excerpt:' in near
    assert 'Auditor scope assessment' in near and explanation in near
    assert 'Nearest source introduction: For the full year 2026' in near
    assert '[Source guidance-row; available 2026-11-03](https://www.sec.gov/' in near
    assert 'filing_report_date' not in near and 'preceding_introductions' not in near
    assert 'Field-validated correction:' not in near
    html = render_report('DOCN', state, None)
    boundary = html.index('FOLLOWING_SCOPE_PARAGRAPH')
    near_html = html[max(0, boundary - 10000):boundary]
    assert '41–43%' in near_html and '41% to 42%' in near_html
    assert 'FY 2026' in near_html and 'Q4 remains unresolved' in near_html
    detail = next((tmp_path / 'first').glob('ground_truth_audit-*.md')).read_text()
    assert 'Supporting source excerpt:' in detail and explanation in detail
    write_report_tree(state, 'DOCN', tmp_path / 'reexport')
    assert model.calls == calls and state == before


def test_numeric_table_excerpt_retains_thousands_and_period_scope_at_passage(tmp_path):
    row = '| Revenue | 39 USD |'
    table = '| Metric | Value |\n| --- | --- |\n' + row + '\n| Cash | 8 USD |'
    source = ('| Metric (USD thousands) | FY 2026 | FY 2025 |\n| --- | --- | --- |\n| Revenue | 37 | 20 |'
              '\n<script>UNTRUSTED_SCOPE_SENTINEL</script> [unsafe](javascript:alert(1))')
    explanation = 'The source reports 37 in USD thousands for FY 2026, not 37 USD; the report row needs a unit-aware correction.'
    state, model = _scoped_excerpt_fixture('**Rating**: Hold\n\n' + table + '\n\nTABLE_SCOPE_END',
                                           row, '37', source, explanation, section='FY 2026; USD thousands')
    before = deepcopy(state)
    calls = model.calls
    write_report_tree(state, 'DOCN', tmp_path)
    section = (tmp_path / '5_portfolio/decision.md').read_text()
    assert table in section  # No note or converted amount is inserted inside a table row.
    assert section.index('Supporting source excerpt: 37') > section.index('| Cash | 8 USD |')
    assert explanation in section and 'Source section: FY 2026; USD thousands' in section
    assert 'FY 2026' in section
    detail = next(tmp_path.glob('ground_truth_audit-*.md')).read_text()
    assert 'Metric (USD thousands)' in detail and 'FY 2025' in detail
    assert 'Field-validated correction: 37' not in section
    assert '<script>' not in section and '[unsafe](javascript:' not in section
    html = render_report('DOCN', state, None)
    boundary = html.index('TABLE_SCOPE_END')
    near = html[max(0, boundary - 10000):boundary]
    assert 'USD thousands' in near and 'not 37 USD' in near
    assert '39 USD' in near and 'Supporting source excerpt: 37' in near
    assert '<script>UNTRUSTED_SCOPE_SENTINEL</script>' not in html and 'href="javascript:' not in html
    assert model.calls == calls and state == before


def test_strict_field_bound_correction_keeps_complete_units_period_and_stronger_label():
    from tests.test_ground_truth_audit import financial_state
    from tradingagents.ground_truth import _source_index, _validate_claim, corrected_text

    state = financial_state()
    sources, _ = _source_index(state)
    source = next(source for source in sources.values() if source.get('fact', {}).get('fact_id') == 'revenue')
    fact = source['fact']
    old = 'Revenue: 99 USD; 2026-07-01 to 2026-09-30; US-GAAP.'
    corrected = 'Revenue: 100 USD; 2026-07-01 to 2026-09-30; US-GAAP.'
    finding = _validate_claim({
        'quoted_claim': old, 'outcome': 'contradicted', 'explanation': 'The complete dated canonical field differs.',
        'correction': corrected,
        'fact_check': {**{key: fact[key] for key in ('fact_id', 'metric', 'value', 'unit', 'period_start', 'period_end', 'basis')},
                       'claimed_value': '99'},
        'evidence': [{'source_id': source['source_id'], 'locator': source['locator'], 'quote': source['text']}],
    }, {'chunk_id': 'decision@0:60', 'section_id': 'decision', 'start': 0, 'text': old}, sources)
    assert finding['code_verified'] is True
    output = corrected_text('decision', old, {'claims': [finding]})
    assert old in output and corrected in output
    assert 'Field-validated correction:' in output and 'Supporting source excerpt:' not in output
    assert 'USD' in output and '2026-07-01' in output and '2026-09-30' in output


def test_generic_code_or_arithmetic_flag_does_not_claim_a_field_validated_replacement():
    from tradingagents.ground_truth import corrected_text

    text = 'Profit was 100 USD.'
    finding = {'section_id': 'decision', 'chunk_id': 'decision@0:19', 'quoted_claim': text,
               'character_start': 0, 'character_end': len(text), 'outcome': 'contradicted',
               'correction': '110 USD', 'code_verified': True,
               'verification': {'arithmetic_reproduced': True, 'financial_fields_validated': False},
               'explanation': 'The cash-flow sum does not establish the asserted profit measure.', 'evidence': []}
    result = corrected_text('decision', text, {'claims': [finding]})
    assert text in result and 'Supporting source excerpt: 110 USD' in result
    assert 'Field-validated correction:' not in result
    assert finding['explanation'] in result


def test_full_audit_lists_reviewed_and_not_fully_reviewed_locations_without_claiming_support():
    from tradingagents.ground_truth import render_audit
    from tradingagents.report_html import _markdown

    remaining = ['5_portfolio/decision.md@6000:9000', 'summary/summary.md@0:500']
    record = {'status': 'partial', 'claims': [], 'coverage': {
        'total_chunks': 3, 'reviewed_chunks': 1,
        'reviewed_chunk_ids': ['1_analysts/market.md@0:6000'], 'remaining_chunks': remaining,
        'source_gaps': ['A dated source was missing.']}, 'limits': []}
    text = render_audit(record)
    assert 'Reviewed chunk locations' in text and 'Not fully reviewed' in text
    assert 'partial or unattempted' in text
    assert 'Reviewed chunks can still contain unsupported or contradicted claims.' in text
    assert '1_analysts/market.md@0:6000' in text
    assert all(location in text for location in remaining)
    html = _markdown().render(text)
    assert all(location in html for location in remaining)
    assert 'A dated source was missing.' in text
    for coverage in ({}, {'total_chunks': 0, 'reviewed_chunks': 0, 'remaining_chunks': []},
                     {'total_chunks': 1, 'reviewed_chunks': 0, 'source_gaps': ['No sources']}):
        assert 'Full Ground Truth Audit' in render_audit({**record, 'coverage': coverage})


def test_passage_scope_is_plain_literal_context_with_links_while_full_detail_keeps_metadata():
    from tradingagents.ground_truth import _correction_annotation, render_audit

    identifier = 'a' * 64
    source = {'source_id': identifier, 'locator': 'table-7', 'known_at': '2026-11-03',
              'url': 'https://www.sec.gov/Archives/edgar/data/1582961/example.htm',
              'quote': '| Revenue | 37 |', 'kind': 'filing passage',
              'context': {'source_section': 'Revenue table',
                          'table_headers': ['Metric (USD thousands) | FY 2026 | FY 2025', '--- | --- | ---'],
                          'preceding_introductions': [{'text': 'For the full year 2026:'}],
                          'filing_report_date': '2026-11-02'}}
    finding = {'quoted_claim': 'Revenue was 39 USD.', 'correction': '37', 'code_verified': False,
               'chunk_id': 'decision@0:20', 'outcome': 'contradicted', 'decision_material': True,
               'explanation': 'The source amount uses thousands; this is not a full USD replacement.',
               'evidence': [source]}
    note = _correction_annotation(finding)
    assert 'Table heading: Metric (USD thousands) | FY 2026 | FY 2025' in note
    assert 'Nearest source introduction: For the full year 2026:' in note
    assert '[Source table-7; available 2026-11-03](https://www.sec.gov/' in note
    assert identifier not in note and 'filing_report_date' not in note and '2026-11-02' not in note
    assert '--- | ---' not in note
    detail = render_audit({'status': 'completed with findings', 'claims': [finding], 'coverage': {}})
    assert identifier in detail and 'filing_report_date' in detail and '2026-11-02' in detail
