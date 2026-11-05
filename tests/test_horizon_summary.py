"""Visible horizons retain pending status, sample selection and known-at cutoffs."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tradingagents.memory import publication, publication_outcomes as outcomes


@pytest.fixture
def published(tmp_path, monkeypatch):
    config = {'results_dir': str(tmp_path)}
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 10, 19, 22, tzinfo=UTC))
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-10-19')
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-04')
    def add(rating='Underweight', asof='2026-10-19', mode='prospective'):
        state = {'run_id': str(uuid4()), 'final_rating': rating, 'evaluation_mode': mode,
                 'final_trade_decision': rating, 'evidence_quality': {'status': 'limited'}}
        return publication.publish(config, state, 'DOCN', asof)
    return config, add


def settle_short(config, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 4, 18, tzinfo=UTC).astimezone(tz)
    monkeypatch.setattr(outcomes, 'datetime', Clock)
    def prices(ticker, cutoff, days, benchmark, **kwargs):
        if days != 5:
            return None
        return {'raw_return': .05, 'alpha_return': .03, 'benchmark_return': .02,
                'holding_days': 5, 'resolution_date': '2026-10-27',
                'ticker': ticker, 'benchmark': benchmark,
                'entry': {'date': '2026-10-20', 'price': 100.},
                'exit': {'date': '2026-10-27', 'price': 105.},
                'benchmark_entry': {'date': '2026-10-20', 'price': 400.},
                'benchmark_exit': {'date': '2026-10-27', 'price': 408.},
                'price_source': 'frozen fixture', 'price_adjustment': 'adjusted'}
    monkeypatch.setattr(outcomes, 'fetch_outcome', prices)
    outcomes.settle_publications(config)


def test_summary_separates_measured_short_window_from_pending_longer_horizons(published, monkeypatch):
    config, add = published
    record = add()
    settle_short(config, monkeypatch)
    text = outcomes.render_outcome_summary(config)
    assert record['decision_id'] in text
    assert 'Underweight' in text and 'prospective' in text
    assert '| 5 sessions | resolved | +5.00% | SPY +2.00% | +3.00%' in text
    assert '| 21 sessions | pending | — | — | —' in text
    assert '| 63 sessions | pending | — | — | —' in text
    assert '2026-10-20 → 2026-10-27' in text
    assert '63 sessions is not three calendar months' in text
    assert 'not portfolio P&L' in text


def test_review_is_visible_in_coverage_and_revisions_do_not_become_extra_samples(published):
    config, add = published
    review, primary, revision, historical = add('REVIEW'), add(), add('Hold'), add(asof='2026-09-01', mode='historical')
    text = outcomes.render_outcome_summary(config)
    assert '4 publications; 2 primary eligible observations; 1 ineligible; 1 revisions excluded' in text
    assert review['decision_id'] in text and '| ineligible |' in text
    assert primary['decision_id'] in text and historical['decision_id'] in text
    assert revision['decision_id'] not in text
    assert 'historical' in text


def test_asof_never_exposes_publications_or_outcomes_before_known_at(published, monkeypatch):
    config, add = published
    record = add()
    settle_short(config, monkeypatch)
    assert record['decision_id'] not in outcomes.render_outcome_summary(config, as_of='2026-10-19T21:59:59+00:00')
    text = outcomes.render_outcome_summary(config, as_of='2026-10-28')
    assert record['decision_id'] in text
    assert '+5.00%' not in text  # retrieved and persisted later than this cutoff
    assert '| 5 sessions | pending |' in text
    assert '+5.00%' not in outcomes.render_outcome_summary(config, as_of='2026-11-04T17:59:59+00:00')
    assert '+5.00%' in outcomes.render_outcome_summary(config, as_of='2026-11-04T18:00:00+00:00')
    with pytest.raises(ValueError, match='timezone'):
        outcomes.render_outcome_summary(config, as_of='2026-10-19T23:00:00')


def test_bounded_summary_discloses_omission_and_corruption_is_not_hidden(published):
    config, add = published
    first, second = add(), add(asof='2026-10-18')
    text = outcomes.render_outcome_summary(config, limit=1)
    assert first['decision_id'] not in text and second['decision_id'] in text
    assert 'Showing latest 1 of 2 tabled publications' in text
    with pytest.raises(ValueError, match='positive integer'):
        outcomes.render_outcome_summary(config, limit=0)
    path = publication.record_root(config) / 'outcomes' / f"{second['decision_id']}.json"
    path.parent.mkdir()
    path.write_text('{}')
    with pytest.raises(ValueError, match='integrity'):
        outcomes.render_outcome_summary(config)


def test_legacy_visibility_uses_import_time_without_inventing_publication_time(published):
    config, _ = published
    record = publication.import_legacy_entry(config, {
        'ticker': 'DOCN', 'date': '2026-09-01', 'rating': 'Underweight',
        'decision': 'Recorded legacy Underweight', 'raw': '+6.9%',
        'alpha': '+6.9%', 'holding': '5d', 'resolved': '2026-09-09',
    }, source_label='Legacy memory fixture', source_sha256='a' * 64)
    assert record['decision_id'] not in outcomes.render_outcome_summary(config, as_of='2026-10-18')
    text = outcomes.render_outcome_summary(config, as_of='2026-10-19')
    assert record['decision_id'] in text
    assert 'legacy' in text and 'unknown (legacy publication time not recorded)' in text
    assert '+6.9%' not in text  # original rounded memory is not a measured endpoint
    assert '| 5 sessions | pending | — | — | —' in text
