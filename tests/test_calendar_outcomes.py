"""Calendar endpoints retain nominal dates, actual sessions and original policy."""
from datetime import UTC, datetime
from uuid import uuid4

import pandas as pd
import pytest

from tradingagents.memory import publication, publication_outcomes as outcomes, settlement


def prices(monkeypatch, dates, missing_benchmark=()):
    index = pd.to_datetime(dates).tz_localize('America/New_York')
    stock = pd.Series([100. + i for i in range(len(index))], index=index)
    benchmark = pd.Series([400. + i for i in range(len(index))], index=index)
    benchmark = benchmark.drop([pd.Timestamp(day, tz='America/New_York') for day in missing_benchmark])
    monkeypatch.setattr(settlement, 'get_closes', lambda ticker, *args: stock if ticker == 'DOCN' else benchmark)


@pytest.mark.parametrize('entry,months,nominal,exit_date', [
    ('2023-11-30',3,'2024-02-29','2024-02-29'),
    ('2024-01-31',3,'2024-04-30','2024-05-01'),
    ('2023-08-31',6,'2024-02-29','2024-02-29'),
    ('2024-03-31',3,'2024-06-30','2024-07-01'),
])
def test_calendar_monthend_leap_and_first_completed_eligible_session(monkeypatch, entry, months, nominal, exit_date):
    prices(monkeypatch, [entry, exit_date, '2024-08-01'])
    result = settlement.fetch_outcome('DOCN', (pd.Timestamp(entry)-pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                                      None, calendar_months=months, benchmark_alignment='exact_sessions', prices_before='2024-08-01')
    assert result['nominal_exit_date'] == nominal
    assert result['exit']['date'] == exit_date and result['holding_days'] == 1
    assert result['calendar_months'] == months and result['horizon_type'] == 'calendar_months'
    assert result['benchmark_entry']['date'] == entry and result['benchmark_exit']['date'] == exit_date


def test_new_exact_alignment_is_pending_but_legacy_asof_policy_remains(monkeypatch):
    prices(monkeypatch, ['2024-01-30','2024-01-31','2024-02-01','2024-02-02'], ['2024-01-31'])
    assert settlement.fetch_outcome('DOCN','2024-01-30',1,benchmark_alignment='exact_sessions') is None
    legacy = settlement.fetch_outcome('DOCN','2024-01-30',1)
    assert legacy['benchmark_entry']['date'] == '2024-01-30'


def test_calendar_waits_for_complete_exit_and_publication_session(monkeypatch):
    prices(monkeypatch, ['2024-01-30','2024-01-31','2024-02-01','2024-05-01','2024-05-02'])
    options = {'calendar_months': 3, 'benchmark_alignment': 'exact_sessions',
                   'published_at': '2024-02-01T01:00:00+00:00'} # Jan31 evening in New York
    assert settlement.fetch_outcome('DOCN','2024-01-30',None,prices_before='2024-05-01',**options) is None
    result = settlement.fetch_outcome('DOCN','2024-01-30',None,prices_before='2024-05-02',**options)
    assert result['entry']['date'] == '2024-02-01'
    assert result['nominal_exit_date'] == result['exit']['date'] == '2024-05-01'


def publish(config, monkeypatch):
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2024,1,30,22,tzinfo=UTC))
    monkeypatch.setattr(publication, 'get_current_date', lambda:'2024-01-30')
    state = {'run_id':str(uuid4()),'final_rating':'Hold','final_trade_decision':'Hold',
             'evidence_quality':{'status':'limited'},'thesis_version_id':'fixed-thesis'}
    return publication.publish(config,state,'DOCN','2024-01-30'), state


def test_new_record_protocol_and_old_publication_reexport_stay_immutable(tmp_path, monkeypatch):
    import json
    config = {'results_dir':str(tmp_path)}
    record, state = publish(config,monkeypatch)
    assert len(record['endpoints']) == 5
    assert record['evaluation_protocol'] == publication.EVALUATION_PROTOCOL
    assert outcomes.endpoint_group_key(record['endpoints']['3_calendar_months']) == ('calendar_months',3)
    assert 'calendar months' in outcomes.endpoint_label(record['endpoints']['3_calendar_months'])
    # Reconstruct an old compatible record: existing payload hash stays identical.
    old = dict(record)
    old.pop('evaluation_protocol')
    old['endpoints'] = {name:{k:v for k,v in endpoint.items() if k in {'holding_days','status','benchmark','entry_policy'}}
                        for name,endpoint in old['endpoints'].items() if name.endswith('_sessions')}
    old['record_sha256'] = publication._digest({k:v for k,v in old.items() if k != 'record_sha256'})
    path = publication.record_root(config)/'records'/f"{old['decision_id']}.json"
    path.write_text(json.dumps(old))
    assert publication.publish(config,state,'DOCN','2024-01-30') == old
    assert outcomes.endpoint_group_key(old['endpoints']['63_sessions']) == ('trading_sessions',63)


def test_calendar_recovery_and_coincident_windows_preserve_thesis(tmp_path, monkeypatch):
    config = {'results_dir':str(tmp_path)}
    record, _ = publish(config,monkeypatch)
    # This frozen weekday calendar excludes Feb19, so 63 sessions after Jan31 is Apr30.
    dates = pd.bdate_range('2024-01-31','2024-08-01').strftime('%Y-%m-%d').tolist()
    dates.remove('2024-02-19')
    prices(monkeypatch,dates)
    monkeypatch.setattr(outcomes,'get_current_date',lambda:'2024-08-02')
    real_write = outcomes._write
    count = 0
    def interrupt(path, payload):
        nonlocal count
        count += 1
        if count == 4:
            raise OSError('simulated interruption')
        return real_write(path,payload)
    monkeypatch.setattr(outcomes,'_write',interrupt)
    first = outcomes.settle_publications(config)
    assert first['failed']
    before = outcomes.load_outcomes(config,record)
    resolved = {name for name,row in before['endpoints'].items() if row['status']=='resolved'}
    monkeypatch.setattr(outcomes,'_write',real_write)
    second = outcomes.settle_publications(config)
    assert all(name not in resolved for _,name in second['settled'])
    saved = outcomes.load_outcomes(config,record)
    assert saved['thesis_version_id'] == 'fixed-thesis'
    assert all(row['status']=='resolved' for row in saved['endpoints'].values())
    a,b = saved['endpoints']['63_sessions'],saved['endpoints']['3_calendar_months']
    assert a['outcome']['observation_window_id'] == b['outcome']['observation_window_id']
    assert a.get('coincident_with') or b.get('coincident_with')
    assert outcomes.settle_publications(config)['settled'] == []


def test_calendar_request_extends_from_delayed_actual_entry(monkeypatch):
    index = pd.to_datetime(['2024-03-04','2024-06-04']).tz_localize('America/New_York')
    series = pd.Series([100.,110.],index=index)
    calls = []
    def fetch(ticker,start,end):
        calls.append((ticker,start,end))
        return series[(series.index.tz_localize(None) >= pd.Timestamp(start)) &
                      (series.index.tz_localize(None) <= pd.Timestamp(end))]
    monkeypatch.setattr(settlement,'get_closes',fetch)
    result = settlement.fetch_outcome('DOCN','2024-01-30',None,calendar_months=3,
                                      benchmark_alignment='exact_sessions',prices_before='2024-08-01')
    assert result is not None
    assert result['nominal_exit_date'] == result['exit']['date'] == '2024-06-04'
    assert len([call for call in calls if call[0]=='DOCN']) == 2


def test_calendar_exact_exit_gap_stays_pending_and_later_windows_independent(tmp_path, monkeypatch):
    config = {'results_dir':str(tmp_path)}
    record, _ = publish(config,monkeypatch)
    dates = pd.bdate_range('2024-01-31','2024-08-01').strftime('%Y-%m-%d').tolist()
    prices(monkeypatch, dates, ['2024-04-30'])
    monkeypatch.setattr(outcomes,'get_current_date',lambda:'2024-08-02')
    outcomes.settle_publications(config)
    saved = outcomes.load_outcomes(config,record)
    assert saved['endpoints']['3_calendar_months']['status'] == 'pending'
    assert saved['endpoints']['6_calendar_months']['status'] == 'resolved'
    assert saved['endpoints']['5_sessions']['status'] == 'resolved'
    # Later retrieval must never masquerade as a lesson known at its old exit.
    old = outcomes.render_outcome_summary(config,as_of='2024-08-02')
    assert '3 calendar months' in old and '6 calendar months' in old
    assert '| resolved |' not in old


def test_concurrent_calendar_settlement_fetches_each_resolved_endpoint_once(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    config = {'results_dir':str(tmp_path)}
    record, _ = publish(config,monkeypatch)
    prices(monkeypatch,pd.bdate_range('2024-01-31','2024-08-01').strftime('%Y-%m-%d').tolist())
    monkeypatch.setattr(outcomes,'get_current_date',lambda:'2024-08-02')
    original, calls = outcomes.fetch_outcome, []
    def track(*args, **kwargs):
        calls.append((args[2],kwargs.get('calendar_months')))
        return original(*args,**kwargs)
    monkeypatch.setattr(outcomes,'fetch_outcome',track)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: outcomes.settle_publications(config),range(3)))
    assert len(calls) == len(set(calls)) == 5
    assert sum(len(r['settled']) for r in results) == 5
    assert outcomes.load_outcomes(config,record)['thesis_version_id'] == 'fixed-thesis'
