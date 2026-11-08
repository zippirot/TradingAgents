"""Coverage messages stay actionable without duplicate warnings or gate changes."""
from tests.test_evidence_gate import complete_evidence
from tradingagents.agents.evidence_validation import REQUIRED_FINANCIAL_CHECKS, assess_financial_package, evidence_quality


def test_evidence_warning_messages_are_deduplicated_without_losing_checks():
    checks = [{'code': code, 'status': 'pass', 'message': 'checked'} for code in REQUIRED_FINANCIAL_CHECKS]
    checks += [{'code': code, 'status': 'unavailable', 'message': 'EPS bridge needs source precision'}
               for code in ('eps1', 'eps2')]
    result = evidence_quality(checks)
    assert result['status'] == 'limited'
    assert result['warnings'] == ['EPS bridge needs source precision']
    assert len(result['checks']) == len(checks)


def test_model_submission_rejections_are_separate_from_source_coverage_gaps():
    facts, docs = complete_evidence()
    docs = docs.model_copy(update={'gaps': ('Document text limit reached; Financial Outlook guidance run omitted',)})
    state = {'fundamentals_report': '```disclosures\n[{"bad": "input"}]\n```'}
    result = assess_financial_package(state, facts, docs)
    warning = '\n'.join(result['evidence_quality']['warnings'])
    assert 'Model submission rejected' in warning
    assert 'Source coverage gap: Document text limit reached' in warning
    assert 'No supported operating KPI or guidance record extracted' in warning
