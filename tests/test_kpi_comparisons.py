"""RPO changes require compatible exact source values, not rounded headlines."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tradingagents.agents.kpi_comparisons import compare_rpo
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage


@pytest.fixture
def quarters():
    root = Path(__file__).parent / 'fixtures'
    prior = DisclosurePackage.model_validate(json.loads((root / 'docn_2026q2/prior_quarter_rpo.json').read_text())['package'])
    current = DisclosurePackage.model_validate(json.loads((root / 'docn_2026q3/rpo_context.json').read_text())['package'])
    return current, prior


def change_fact(package, **changes):
    doc = package.documents[0]
    fact = doc.rpo_facts[0].model_copy(update=changes)
    return package.model_copy(update={'documents': (doc.model_copy(update={'rpo_facts': (fact,)}),)})


def test_recorded_comparison_preserves_exact_values_and_lineage(quarters):
    current, prior = quarters
    result = compare_rpo(current, prior)
    assert result['status'] == 'pass'
    assert result['current_value'] == '799707000'
    assert result['prior_value'] == '893828000'
    assert result['absolute_change'] == '-94121000'
    assert round(float(result['percentage_change']), 2) == -10.53
    assert '-10.53%' in result['text']
    assert 'cause' in result['text']
    assert result['sources']['current']['fact']['locator'] == 'inline-fact-f-600'
    assert result['source_packages']['prior'] == prior.model_dump(mode='json')


@pytest.mark.parametrize('fault', ['missing', 'currency', 'value', 'period', 'recognition', 'issuer', 'cutoff', 'future_filing', 'conflicting', 'amendment'])
def test_incompatible_or_unverified_inputs_are_unavailable(quarters, fault):
    current, prior = quarters
    if fault == 'missing':
        prior = prior.model_copy(update={'documents': ()})
    elif fault == 'currency':
        prior = change_fact(prior, currency='EUR')
    elif fault == 'value':
        prior = change_fact(prior, value=Decimal('1'))
    elif fault == 'period':
        prior = change_fact(prior, period_end=date(2025, 12, 31))
    elif fault == 'recognition':
        prior = change_fact(prior, recognition_start=None)
    elif fault == 'issuer':
        prior = prior.model_copy(update={'cik': '0000320193'})
    elif fault == 'cutoff':
        prior = prior.model_copy(update={'as_of': date(2026, 11, 3)})
    elif fault == 'future_filing':
        doc = prior.documents[0]
        prior = prior.model_copy(update={'documents': (doc.model_copy(update={'filing': doc.filing.model_copy(update={'filed_date':date(2026, 11, 5)})}),)})
    elif fault == 'conflicting':
        doc = prior.documents[0]
        prior = prior.model_copy(update={'documents': (doc.model_copy(update={'rpo_facts': (*doc.rpo_facts, doc.rpo_facts[0].model_copy(update={'value': Decimal('1')}))}),)})
    else:
        doc = prior.documents[0]
        amendment = doc.model_copy(update={'filing': doc.filing.model_copy(update={'form':'10-Q/A'})})
        prior = prior.model_copy(update={'documents': (*prior.documents, amendment)})
    result = compare_rpo(current, prior)
    assert result['status'] == 'unavailable'
    assert result['absolute_change'] is None and result['percentage_change'] is None
    assert result['reason']


def test_no_disclosed_rpo_does_not_trigger_retrieval(quarters, monkeypatch):
    from tradingagents.agents.kpi_comparisons import retrieve_rpo_comparison
    from tradingagents.dataflows.vendors import sec_documents
    current, _ = quarters
    doc = current.documents[0].model_copy(update={'rpo_facts': (), 'blocks': ()})
    current = current.model_copy(update={'documents': (doc,)})
    monkeypatch.setattr(sec_documents, 'get_current_quarter_rpo_evidence', lambda *a: pytest.fail('unexpected current retrieval'))
    monkeypatch.setattr(sec_documents, 'get_prior_quarter_evidence', lambda *a: pytest.fail('unexpected prior retrieval'))
    result = retrieve_rpo_comparison('DOCN', current)
    assert result['status'] == 'unavailable' and 'bounded retrieved excerpts' in result['reason']


def test_existing_comparable_source_facts_need_no_retrieval(quarters, monkeypatch):
    from tradingagents.agents.kpi_comparisons import retrieve_rpo_comparison
    from tradingagents.dataflows.vendors import sec_documents
    current, prior = quarters
    combined = current.model_copy(update={'documents': (*current.documents, *prior.documents),
                                          'selected_accessions': (*current.selected_accessions, *prior.selected_accessions)})
    monkeypatch.setattr(sec_documents, 'get_current_quarter_rpo_evidence', lambda *a: pytest.fail('unexpected current retrieval'))
    monkeypatch.setattr(sec_documents, 'get_prior_quarter_evidence', lambda *a: pytest.fail('unexpected prior retrieval'))
    assert retrieve_rpo_comparison('DOCN', combined)['status'] == 'pass'


def test_zero_prior_total_never_becomes_infinite_percentage(quarters):
    current, prior = quarters
    doc = prior.documents[0]
    fact = doc.rpo_facts[0]
    cell = fact.exact_html.replace('>893,828</', '>0</')
    assert cell != fact.exact_html
    zero = fact.model_copy(update={'value': Decimal(0), 'display_value': '0', 'exact_html': cell,
                                  'character_end': fact.character_start + len(cell)})
    prior = prior.model_copy(update={'documents': (doc.model_copy(update={'rpo_facts': (zero,)}),)})
    result = compare_rpo(current, prior)
    assert result['status'] == 'unavailable'
    assert 'positive' in result['reason']
    assert result['percentage_change'] is None


def test_missing_prior_acquisition_is_visible_without_inventing_zero(quarters, monkeypatch):
    from tradingagents.agents.kpi_comparisons import retrieve_rpo_comparison
    from tradingagents.dataflows.vendors import sec_documents
    current, _ = quarters
    monkeypatch.setattr(sec_documents, 'get_current_quarter_rpo_evidence', lambda *a: pytest.fail('valid current must be reused'))
    def failed(*args):
        raise TimeoutError('private provider details')
    monkeypatch.setattr(sec_documents, 'get_prior_quarter_evidence', failed)
    result = retrieve_rpo_comparison('DOCN', current)
    assert result['status'] == 'unavailable'
    assert result['prior_value'] is None
    assert 'TimeoutError' in result['reason'] and 'private' not in result['text']


def test_missing_current_fact_is_supplemented_before_prior_fetch(quarters, monkeypatch):
    from tradingagents.agents.kpi_comparisons import retrieve_rpo_comparison
    from tradingagents.dataflows.vendors import sec_documents
    current, prior = quarters
    missing = current.model_copy(update={'documents': (current.documents[0].model_copy(update={'rpo_facts': ()}),)})
    calls = []
    def supplement(package):
        calls.append('current')
        assert package == missing
        return current
    def previous(ticker, asof, period):
        calls.append('prior')
        assert (ticker, asof, period) == ('DOCN', '2026-11-04', '2026-09-30')
        return prior
    monkeypatch.setattr(sec_documents, 'get_current_quarter_rpo_evidence', supplement)
    monkeypatch.setattr(sec_documents, 'get_prior_quarter_evidence', previous)
    assert retrieve_rpo_comparison('DOCN', missing)['status'] == 'pass'
    assert calls == ['current', 'prior']
