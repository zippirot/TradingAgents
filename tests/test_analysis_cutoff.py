"""The research clock is separate from instrument price sessions."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from tradingagents.dataflows.date_window import resolve_analysis_cutoff


@pytest.mark.parametrize(('day', 'zone', 'expected'), [
    ('2026-11-04', 'America/Denver', '2026-11-05T06:59:59.999999+00:00'),
    ('2026-07-04', 'America/Denver', '2026-07-05T05:59:59.999999+00:00'),
    ('2026-03-08', 'America/Denver', '2026-03-09T05:59:59.999999+00:00'),
    ('2026-11-01', 'America/Denver', '2026-11-02T06:59:59.999999+00:00'),
    ('2026-11-04', 'America/New_York', '2026-11-05T04:59:59.999999+00:00'),
    ('2026-11-04', 'UTC', '2026-11-04T23:59:59.999999+00:00'),
])
def test_date_only_cutoff_uses_named_analysis_clock(day, zone, expected):
    assert resolve_analysis_cutoff(day, zone)['cutoff_utc'] == expected


def test_exact_cutoff_and_unknown_zone_fallback():
    exact = '2026-11-05T04:07:17.629658+00:00'
    assert resolve_analysis_cutoff('2026-11-04', 'America/Denver', exact)['cutoff_utc'] == exact
    assert resolve_analysis_cutoff('2026-11-04', 'Unknown/Zone')['cutoff_utc'] == '2026-11-04T23:59:59.999999+00:00'
    assert resolve_analysis_cutoff('2026-11-04', 'Unknown/Zone')['analysis_timezone'] == 'UTC'
    with pytest.raises(ValueError, match='timezone'):
        resolve_analysis_cutoff('2026-11-04', 'America/Denver', '2026-11-05T04:07:17')


def test_cutoff_makes_real_saved_docn_evening_publication_visible_at_boundary():
    # Retained build-A record: 2026-11-04 21:07:17.629658 in Denver.
    published = datetime.fromisoformat('2026-11-05T04:07:17.629658+00:00')
    denver = datetime.fromisoformat(resolve_analysis_cutoff('2026-11-04', 'America/Denver')['cutoff_utc'])
    new_york = datetime.fromisoformat(resolve_analysis_cutoff('2026-11-04', 'America/New_York')['cutoff_utc'])
    utc = datetime.fromisoformat(resolve_analysis_cutoff('2026-11-04', 'UTC')['cutoff_utc'])
    assert utc < published <= new_york < denver
    assert published <= datetime.fromisoformat(resolve_analysis_cutoff('2026-11-04', 'UTC', published.isoformat())['cutoff_utc'])
    from tradingagents.memory.publication_outcomes import _known_by
    assert _known_by(denver.isoformat(), denver)
    assert not _known_by((denver + timedelta(microseconds=1)).isoformat(), denver)


def test_graph_reuses_state_cutoff_for_all_three_memory_views(tmp_path, monkeypatch):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory import thesis

    graph = object.__new__(TradingAgentsGraph)
    graph.config = {'results_dir': str(tmp_path), 'analysis_timezone': 'America/Denver'}
    seen = []
    graph.settle_all_pending = lambda wait=False: SimpleNamespace(failed=[])
    graph.memory_log = SimpleNamespace(
        get_past_context=lambda ticker, as_of, **kwargs: seen.append(('lessons', as_of)) or '',
        load_entries=lambda: [],
    )
    graph.outcome_summary = lambda ticker, as_of, limit: seen.append(('outcomes', as_of)) or ''
    monkeypatch.setattr(thesis, 'load_latest_thesis',
                        lambda config, ticker, known_at: seen.append(('thesis', known_at)) or None)
    exact = '2026-11-05T04:07:17.629658+00:00'
    state = {'company_of_interest': 'DOCN', 'trade_date': '2026-11-04',
             'analysis_clock': {'analysis_timezone': 'America/Denver', 'cutoff_utc': exact}}
    result = graph._memory_step(state)
    assert seen == [(name, exact) for name in ('lessons', 'outcomes', 'thesis')]
    assert result['analysis_clock'] == state['analysis_clock']


def test_current_day_can_quote_existing_legacy_but_replay_cannot(tmp_path, monkeypatch):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory import TradingMemoryLog, thesis

    zone = ZoneInfo('America/Denver')
    today = datetime.now(zone).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    log = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    log.store_decision('DOCN', yesterday, 'Rating: Buy\nlegacy research')
    log.update_with_outcome('DOCN', yesterday, .05, .02, 5,
                            'legacy reflection', resolution_date=yesterday)
    path = tmp_path / 'memory.md'
    known_at = log.load_entries()[0]['known_at']
    path.write_text(path.read_text().replace(f' | known_at:{known_at}', ''))
    tomorrow = (today + timedelta(days=1)).isoformat()
    log.store_decision('AAPL', today.isoformat(), 'Rating: Sell\nfuture research')
    log.update_with_outcome('AAPL', today.isoformat(), .01, .01, 5,
                            'future lesson', resolution_date=tomorrow)
    future_known_at = log.load_entries()[-1]['known_at']
    path.write_text(path.read_text().replace(f' | known_at:{future_known_at}', ''))
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {'results_dir': str(tmp_path), 'analysis_timezone': 'America/Denver'}
    graph.memory_log = log
    graph.settle_all_pending = lambda wait=False: SimpleNamespace(failed=[])
    graph.outcome_summary = lambda *args, **kwargs: ''
    monkeypatch.setattr(thesis, 'load_latest_thesis', lambda *args: None)

    current = graph._memory_step({'company_of_interest': 'DOCN', 'trade_date': today.isoformat(),
                                  'analysis_clock': resolve_analysis_cutoff(today.isoformat(), 'America/Denver')})
    assert 'legacy reflection' in current['past_context']
    assert 'future lesson' not in current['past_context']
    assert 'publication time unknown' in current['thesis_context']

    earlier = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    past_instant = graph._memory_step({'company_of_interest': 'DOCN', 'trade_date': today.isoformat(),
                                      'analysis_clock': resolve_analysis_cutoff(today.isoformat(),
                                                                               'America/Denver', earlier)})
    assert past_instant['past_context'] == '' and past_instant['thesis_context'] == ''
    assert log.get_past_context('DOCN', as_of=earlier, allow_unstamped_legacy=True) == ''

    replay = graph._memory_step({'company_of_interest': 'DOCN', 'trade_date': yesterday,
                                 'analysis_clock': resolve_analysis_cutoff(yesterday, 'America/Denver')})
    assert replay['past_context'] == '' and replay['thesis_context'] == ''


def test_legacy_thesis_loaded_after_cutoff_is_not_presented(tmp_path, monkeypatch):
    import tradingagents.graph.trading_graph as graph_module
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory import thesis

    before = datetime(2026, 11, 5, 20, 0, 0, tzinfo=UTC)
    cutoff = (before + timedelta(seconds=1)).isoformat()

    class Clock(datetime):
        read_time = before

        @classmethod
        def now(cls, tz=None):
            return cls.read_time.astimezone(tz)

    monkeypatch.setattr(graph_module, 'datetime', Clock)
    monkeypatch.setattr(thesis, 'load_latest_thesis', lambda *args: None)
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {'results_dir': str(tmp_path), 'analysis_timezone': 'America/Denver'}
    graph.settle_all_pending = lambda wait=False: (
        setattr(Clock, 'read_time', before + timedelta(seconds=2))
        or SimpleNamespace(failed=[]))
    graph.memory_log = SimpleNamespace(
        get_past_context=lambda *args, **kwargs: '',
        load_entries=lambda: [{'ticker': 'DOCN', 'date': '2026-11-04',
                               'decision': 'Rating: Buy\nnew after cutoff'}],
    )
    graph.outcome_summary = lambda *args, **kwargs: ''
    state = {'company_of_interest': 'DOCN', 'trade_date': '2026-11-05',
             'analysis_clock': {'analysis_timezone': 'America/Denver', 'cutoff_utc': cutoff}}
    assert graph._memory_step(state)['thesis_context'] == ''
