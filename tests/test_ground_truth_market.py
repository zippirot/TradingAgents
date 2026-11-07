"""Retained market audit inputs are validated without retrieval."""
from copy import deepcopy
from datetime import datetime

import pytest

from tests.test_price_observation import install
from tests.test_valuation_reference_flow import flow_fixture
from tradingagents.agents import valuation_reference_flow as flow
from tradingagents.dataflows.vendors.yahoo import expectations, price_observation
from tradingagents.ground_truth_market import market_sources


def test_dated_completed_price_replayed_and_future_cutoff_or_tamper_rejected(monkeypatch):
    install(monkeypatch)
    price = price_observation.get_price_observation('DOCN', '2026-11-04')
    state = {'company_of_interest': 'DOCN', 'trade_date': '2026-11-04', 'price_observation': price}
    monkeypatch.setattr(price_observation.yf, 'Ticker', lambda *_: pytest.fail('no retrieval'))
    sources, gaps = market_sources(state)
    assert not gaps
    row = next(iter(sources.values()))
    assert row['source_id'] == price['source_id']
    assert '2026-11-03' in row['text'] and '84' in row['text']
    assert 'historical split-adjusted' in row['text']
    assert row['kind'] == 'validated retained market observation'
    changed = deepcopy(state)
    changed['price_observation']['close'] = '999'
    assert not market_sources(changed)[0] and market_sources(changed)[1]
    changed = {**state, 'company_of_interest': 'OTHER'}
    assert not market_sources(changed)[0]
    changed = {**state, 'market_observation_cutoff': '2026-11-04T19:00:00+00:00'}
    assert not market_sources(changed)[0]


def test_reference_rederived_rows_keep_basis_lineage_and_reject_mutated_projection(monkeypatch):
    state, config, _, _ = flow_fixture(monkeypatch)
    state.update(flow.acquire_reference_inputs(state, config))
    state.pop('vendor_expectations', None)  # This fixture intentionally omits consensus.
    sources, gaps = market_sources(state)
    assert not gaps
    rows = [row for row in sources.values() if row['kind'] == 'reproduced valuation reference']
    assert len(rows) > 4
    assert all(len(row['text']) < 6000 for row in rows)
    text = '\n'.join(row['text'] for row in rows)
    assert 'equity value / trailing revenue' in text
    assert '2026-09-30' in text and 'median' in text
    bad = deepcopy(state)
    bad['valuation_reference']['subject']['multiple'] = '999'
    sources, gaps = market_sources(bad)
    assert not any(row['kind'] == 'reproduced valuation reference' for row in sources.values())
    assert gaps


def test_expectations_remain_attributed_and_hash_or_date_mismatch_excludes(monkeypatch):
    from tests.test_vendor_expectations import FakeTicker
    monkeypatch.setattr(expectations.yf, 'Ticker', FakeTicker)
    record = expectations.get_vendor_expectations('DOCN', '2026-11-05',
        observed_at=datetime.fromisoformat('2026-11-05T18:00:00+00:00')).model_dump(mode='json')
    state = {'company_of_interest': 'DOCN', 'trade_date': '2026-11-05', 'vendor_expectations': record}
    sources, gaps = market_sources(state)
    assert not gaps and sources
    assert all(row['kind'] == 'attributed vendor output' for row in sources.values())
    assert 'vendor consensus, unverified' in '\n'.join(row['text'] for row in sources.values())
    for field, value in [('ticker', 'OTHER'), ('snapshot_hash', 'a' * 64)]:
        changed = deepcopy(state)
        changed['vendor_expectations'][field] = value
        assert not market_sources(changed)[0] and market_sources(changed)[1]
    changed = {**state, 'analysis_clock': {'cutoff_utc': '2026-11-05T17:00:00+00:00'}}
    assert not market_sources(changed)[0]
