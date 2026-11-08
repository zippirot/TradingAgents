"""Repeated report assertions require fresh, uniquely located repair findings."""
import json

import pytest

from tests.test_ground_truth_audit import state
from tradingagents import ground_truth as gt


def inventory(text):
    return gt.build_inventory(state(), parts=[('Decision', '5_portfolio', [('PM', 'decision.md', text)])], summary_text='')


def response(claims):
    return {'claims': claims, 'no_material_claims': not claims}


def claim(quote, **extra):
    return {'quoted_claim': quote, 'outcome': 'unsupported', 'explanation': 'Private scripted scope assessment.', **extra}


class Reviewer:
    def __init__(self, failure=False):
        self.calls = []
        self.failure = failure
    def invoke(self, prompt):
        chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
        self.calls.append(chunk)
        if chunk.get('review_claims'):
            return response([] if self.failure else [claim(quote) for quote in chunk['review_claims']])
        return response([claim('Revenue was 100 USD.', outcome='supported', evidence=[{'source_id': 'doc-1', 'locator': 'table-1', 'quote': 'Revenue was 100 USD.'}])])


@pytest.mark.parametrize('repeated', ['Revenue was 100 USD.', '| Revenue | 100 USD |', '**Price Target**: not provided', 'Period: 2026-09-30.'])
def test_exact_duplicate_occurrences_receive_unique_context_targets(repeated):
    text = 'Scenario A\n' + repeated + '\n\nScenario B\n' + repeated
    chunk = inventory(text)['chunks'][0]
    targets = gt._omitted_targets(chunk, [])
    assert targets
    spans = []
    for target in targets:
        quote = target['quoted_claim']
        assert quote in text and text.count(quote) == 1 and len(quote) <= 6000
        assert 'Scenario' in quote
        start = text.index(quote)
        spans.append((start, start + len(quote)))
    for match in list(gt._NUMBER.finditer(gt._coverage_text(text))) + list(gt._CRITICAL_FIELD.finditer(text)):
        assert any(a <= match.start() and match.end() <= b for a, b in spans)


def test_repair_requires_fresh_disposition_for_entire_expanded_quote_and_keeps_neighbor():
    text = 'Revenue was 100 USD.\n\nFirst case\n| Cash | 9 USD |\n\nSecond case\n| Cash | 9 USD |'
    model = Reviewer()
    result = gt.run_audit(state(), model, inventory=inventory(text))
    assert len(model.calls) == 2
    assert result['coverage']['reviewed_chunks'] == 1
    assert result['claims'][0]['quoted_claim'] == 'Revenue was 100 USD.'
    expanded = model.calls[1]['review_claims']
    assert all('case' in quote for quote in expanded)
    assert {c['quoted_claim'] for c in result['claims'][1:]} == set(expanded)


@pytest.mark.parametrize('mode', ['missing', 'budget'])
def test_failed_expanded_repair_stays_pending_and_resume_actually_rechecks(mode):
    text = 'Revenue was 100 USD.\n\nFirst case\n| Cash | 9 USD |\n\nSecond case\n| Cash | 9 USD |'
    inv = inventory(text)
    initial = gt.run_audit(state(), Reviewer(failure=True), {'ground_truth_max_requests': 1} if mode == 'budget' else {}, inventory=inv)
    assert initial['status'] == 'partial' and initial['coverage']['reviewed_chunks'] == 0
    assert initial['unresolved_repairs']
    fresh = Reviewer()
    result = gt.run_audit(state(), fresh, inventory=inv, prior_audit=initial)
    assert len(fresh.calls) == 2 and result['coverage']['reviewed_chunks'] == 1


def test_overlong_irreducible_duplicate_target_remains_unrepairable():
    quote = 'Revenue 100 USD.'
    text = quote + '\n' + 'x' * 6100 + '\n' + quote
    chunk = {'text': text, 'start': 0}
    assert gt._omitted_targets(chunk, []) == []


@pytest.mark.parametrize('failure', ['wrong_context', 'wrong_evidence'])
def test_repair_cannot_accept_wrong_context_or_fabricated_evidence(failure):
    class BadReviewer(Reviewer):
        def invoke(self, prompt):
            result = super().invoke(prompt)
            if self.calls[-1].get('review_claims'):
                if failure == 'wrong_context':
                    return response([claim('| Cash | 9 USD |')])
                return response([claim(quote, outcome='supported', evidence=[
                    {'source_id': 'doc-1', 'locator': 'table-1', 'quote': 'Fabricated cash scope'}])
                    for quote in self.calls[-1]['review_claims']])
            return result
    text = 'Revenue was 100 USD.\n\nFirst case\n| Cash | 9 USD |\n\nSecond case\n| Cash | 9 USD |'
    result = gt.run_audit(state(), BadReviewer(), inventory=inventory(text))
    assert result['coverage']['reviewed_chunks'] == 0 and result['status'] == 'partial'
    assert len(result['claims']) == 1 and result['claims'][0]['outcome'] == 'supported'
    assert result['unresolved_repairs']


def test_existing_target_allowance_stays_bounded_and_leftovers_stay_partial():
    class ManyReviewer:
        def __init__(self):
            self.calls = []
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
            self.calls.append(chunk)
            return response([claim(quote) for quote in chunk.get('review_claims', [])])
    text = '\n'.join(f'Unique item {i} was {i + 1000} USD.' for i in range(120))
    model = ManyReviewer()
    result = gt.run_audit(state(), model, inventory=inventory(text))
    assert len(model.calls) == 2 and len(model.calls[1]['review_claims']) == 100
    assert result['status'] == 'partial' and result['coverage']['reviewed_chunks'] == 0
    assert len(result['unresolved_repairs']) == 20

