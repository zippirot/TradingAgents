"""Advisory intent survives the compiled graph, publication and restart.

Only external model/vendor responses and the upstream canonical-evidence boundary
are scripted. Memory, graph nodes, observation, PM prompt, canonical publication,
immutable storage and restart are the production implementations.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pandas as pd
import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from tests.test_graph_end_to_end import STRUCTURED, ScriptedModel, _graph, offline  # noqa: F401
from tests.test_thesis import condition, state as financial_state
from tradingagents.agents import schemas
from tradingagents.graph import setup
from tradingagents.memory import publication, settlement, thesis


class ThesisModel(ScriptedModel):
    prompts: list = Field(default_factory=list)
    condition_id: str = ''

    def with_structured_output(self, schema, **kwargs):
        def answer(prompt):
            self._count()
            if schema in (schemas.PortfolioDecision, schemas.RequiredHorizonPortfolioDecision):
                self.prompts.append(str(prompt))
                return schema(
                    rating='Overweight', executive_summary='Research decision', time_horizon='3–6 months',
                    investment_thesis='The forward hypothesis remains advisory.',
                    # The earlier decision is listed for the manager, who must say what the changes mean.
                    change_assessment={'status': 'no_material_change', 'reason': 'No new filing or price move.'},
                    thesis_candidate={'conditions': None, 'dispositions': [{
                        'condition_id': self.condition_id, 'disposition': 'kept',
                        'reason': 'Keep monitoring; this comparison does not determine the rating.'}]})
            return STRUCTURED[schema]
        return RunnableLambda(answer)


@pytest.mark.usefixtures('offline')
@pytest.mark.parametrize('role,label', [
    ('supports_thesis', 'Support condition breached'),
    ('reconsideration_trigger', 'Reconsideration trigger not met'),
])
def test_pending_thesis_roles_cross_real_graph_and_restart(tmp_path, monkeypatch, role, label):
    now = datetime(2026, 11, 4, 22, tzinfo=UTC)
    monkeypatch.setattr(publication, '_utcnow', lambda: now)
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
    from tradingagents.dataflows import date_window
    monkeypatch.setattr(date_window, 'get_current_date', lambda: '2026-11-04')
    # Empty market responses keep all outcome windows pending without bypassing
    # the actual settlement/memory read node or calling any reflection model.
    monkeypatch.setattr(settlement, 'get_closes', lambda *a, **k: pd.Series(dtype=float))
    canonical = {**financial_state('99'), 'evidence_quality': {'status': 'limited'},
                 'canonical_financial_context': 'Accepted Revenue: 99 USD; source s; fact f.'}
    monkeypatch.setattr(setup, 'create_evidence_gate', lambda selected: lambda state: dict(canonical))
    model = ThesisModel(structured=True)
    graph = _graph(tmp_path, monkeypatch, model)
    seed = {**graph.create_run_state('NVDA', '2026-11-04'), **canonical,
            'run_id': str(uuid4()), 'final_rating': 'Overweight',
            'thesis_candidate': {'conditions': [condition(thesis_role=role)]}}
    graph.record_decision('NVDA', '2026-11-04', seed)
    original = publication.list_records(graph.config, 'NVDA')[0]
    identifier = seed['thesis']['conditions'][0]['condition_id']
    model.condition_id = identifier
    assert all(v['status'] == 'pending' for v in original['endpoints'].values())

    result, signal = graph.propagate('NVDA', '2026-11-04')
    assert signal == result['final_rating'] == 'Overweight'
    assert result['prior_thesis']['version_id'] == seed['thesis']['version_id']
    observed = result['prior_thesis']['observations'][0]
    assert observed['status'] == 'breached'  # stored predicate truth, not trading authority
    assert observed['thesis_role'] == role
    assert observed['source_ids'] == ['s']
    assert label in result['thesis_context']
    assert len(model.prompts) == 1
    assert '**Since the last decision** (2026-11-04 22:00 UTC, rating Overweight' in model.prompts[0]
    assert 'Change check: consistent with the two ratings.' in result['final_trade_decision']
    assert identifier in model.prompts[0] and label in model.prompts[0]
    assert 'A trigger not met is not a failed thesis' in ' '.join(model.prompts[0].split())
    assert 'advisory, not binding' in model.prompts[0]
    assert label in result['final_trade_decision']
    if role != 'supports_thesis':
        assert 'Support condition breached' not in result['final_trade_decision']
    current = result['thesis']
    assert current['parent_version_id'] == seed['thesis']['version_id']
    assert current['conditions'][0]['thesis_role'] == role
    assert current['prior_conditions'][0]['disposition'] == 'kept'
    assert 'Keep monitoring' in current['prior_conditions'][0]['disposition_reason']
    record = next(r for r in publication.list_records(graph.config, 'NVDA')
                  if r['decision_id'] == result['publication_record']['decision_id'])
    assert record['thesis_version_id'] == current['version_id']
    assert publication.load_evidence(graph.config, record)['thesis'] == current
    assert all(v['status'] == 'pending' for v in record['endpoints'].values())
    assert publication.list_records(graph.config, 'NVDA')[0] == original

    # Fresh graph instance reads durable publication, not an in-process prior.
    restarted = _graph(tmp_path, monkeypatch, ThesisModel(structured=True))
    restored = restarted._memory_step(restarted.create_run_state('NVDA', '2026-11-04'))
    assert restored['prior_thesis']['version_id'] == current['version_id']
    assert restored['prior_thesis']['conditions'][0]['thesis_role'] == role
    assert restored['prior_thesis']['conditions'][0]['condition_id'] == identifier
    entries = restarted.memory_log.load_entries()
    assert len(entries) == 1 and entries[0]['pending']
    assert entries[0]['decision_id'] == record['decision_id']
    assert record['thesis_version_id'] == restored['prior_thesis']['version_id']
    assert original['eligibility']['primary'] and not record['eligibility']['primary']
    assert thesis.load_latest_thesis(graph.config, 'NVDA', '2026-11-04T21:59:59Z') is None
