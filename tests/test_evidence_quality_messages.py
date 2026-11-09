"""Coverage messages stay actionable without duplicate warnings or gate changes."""
import pytest

from tests.test_evidence_gate import complete_evidence
from tradingagents.agents.evidence_validation import (
    REQUIRED_FINANCIAL_CHECKS,
    assess_financial_package,
    evidence_quality,
)


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


def test_shared_brief_formats_source_price_without_binary_float_noise(monkeypatch):
    from datetime import datetime

    from tests.test_price_observation import install
    from tests.test_shared_source_brief import source_state
    from tradingagents.agents.context import build_shared_source_brief
    from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation

    state = source_state(monkeypatch)
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-06-30", "2026-10-19"), closes=(70, 72.4800033569336),
            metadata={"currentTradingPeriod": {"regular": {
                "end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    state['price_observation'] = get_price_observation('DOCN', '2026-10-19', '2026-06-30')
    assert state['price_observation']['status'] == 'available'
    text = build_shared_source_brief(state)
    assert 'Canonical completed price: 72.48 USD' in text
    assert '72.4800033569336' not in text
    assert state['price_observation']['close'] == '72.4800033569336'


@pytest.mark.parametrize('precision,close,display', [(4, 72.4800033569336, '72.4800'), (0, 0.00003, '3.00E-5')])
def test_shared_brief_uses_provider_price_precision_when_retained(monkeypatch, precision, close, display):
    from datetime import datetime

    from tests.test_price_observation import install
    from tests.test_shared_source_brief import source_state
    from tradingagents.agents.context import build_shared_source_brief
    from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation

    state = source_state(monkeypatch)
    install(monkeypatch, now='2026-10-19T22:00:00+00:00',
            dates=('2026-06-30', '2026-10-19'), closes=(70, close),
            metadata={'priceHint': precision, 'currentTradingPeriod': {'regular': {
                'end': datetime.fromisoformat('2026-10-19T21:00:00+00:00')}}})
    state['price_observation'] = get_price_observation('DOCN', '2026-10-19', '2026-06-30')
    assert state['price_observation']['price_precision'] == precision
    assert f'Canonical completed price: {display} USD' in build_shared_source_brief(state)


def test_provider_price_precision_is_retained_through_source_replay(tmp_path, monkeypatch):
    from tests.test_price_observation import install
    from tests.test_source_replay import SCOPE, recorder
    from tradingagents.dataflows.vendors.yahoo import price_observation as prices
    from tradingagents.source_replay import ReplaySession, session_context

    install(monkeypatch, metadata={'priceHint': 4})
    scope = {**SCOPE, 'analysis_date': '2026-11-04'}
    baseline = ReplaySession(recorder(tmp_path / 'baseline', monkeypatch), scope)
    with session_context(baseline):
        original = prices.get_price_observation('DOCN', '2026-11-04')
    baseline.finish(True)
    assert original['price_precision'] == 4
    monkeypatch.setattr(prices.yf, 'Ticker', lambda *args: (_ for _ in ()).throw(AssertionError('live call')))
    replay = ReplaySession(recorder(tmp_path / 'candidate', monkeypatch), scope, baseline=tmp_path / 'baseline')
    with session_context(replay):
        candidate = prices.get_price_observation('DOCN', '2026-11-04')
    assert candidate == original
    assert replay.status == 'replayed' and not replay.misses


def test_price_precision_cannot_be_added_without_its_source_metadata(monkeypatch):
    from tests.test_price_observation import install
    from tradingagents.dataflows.vendors.yahoo.price_observation import (
        get_price_observation,
        validate_price_observation,
    )

    install(monkeypatch, metadata={'priceHint': 'not a precision'})
    quote = get_price_observation('DOCN', '2026-11-04')
    assert 'price_precision' not in quote
    quote['price_precision'] = 4
    with pytest.raises(ValueError, match='retained payload mismatch'):
        validate_price_observation(quote, 'DOCN', '2026-11-04')
