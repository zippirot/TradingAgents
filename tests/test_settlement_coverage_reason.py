"""A cutoff-clipped request must not conceal unresolved price coverage."""
import pandas as pd
import pytest

from tests.test_mature_session_settlement import provider
from tradingagents.memory import settlement


def test_first_request_at_cutoff_reports_potentially_mature_missing_coverage(monkeypatch):
    calls = provider(monkeypatch, pd.to_datetime(['2026-01-06']))
    # Jan 6 + five daily sessions could finish Jan 11, before Jan 14. The
    # initial estimated request already reaches the cutoff; extending cannot
    # resolve whether the absent bars mean missing data or a suspension.
    with pytest.raises(settlement.SettlementCoverageError, match='Insufficient completed instrument sessions') as caught:
        settlement.fetch_outcome('600000.SS', '2026-01-05', 5, prices_before='2026-01-14')
    assert '2026-01-14' in str(caught.value) and '1 observed' in str(caught.value)
    assert calls == [('600000.SS', '2026-01-05', '2026-01-14')]


def test_first_request_at_cutoff_genuinely_immature_window_stays_pending(monkeypatch):
    calls = provider(monkeypatch, pd.to_datetime(['2026-01-06']))
    assert settlement.fetch_outcome('600000.SS', '2026-01-05', 5, prices_before='2026-01-10') is None
    assert calls == [('600000.SS', '2026-01-05', '2026-01-10')]


def test_legacy_missing_coverage_keeps_tuple_and_visible_warning(monkeypatch, caplog):
    from tradingagents.dataflows import date_window
    monkeypatch.setattr(date_window, 'get_current_date', lambda: '2026-01-14')
    provider(monkeypatch, pd.to_datetime(['2026-01-06']))
    assert settlement.fetch_returns('600000.SS', '2026-01-05', 5) == (None, None, None, None)
    assert 'Legacy settlement pending: Insufficient completed instrument sessions' in caplog.text
