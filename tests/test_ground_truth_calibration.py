"""Measured report bounds must agree across execution and conservative recovery."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.test_ground_truth_audit import Model, inventory, response, state
from tests.test_ground_truth_sources import fake_transport, source_state
from tradingagents import (
    ground_truth as audit,
    ground_truth_flow as flow,
    ground_truth_recovery as recovery,
)
from tradingagents.ground_truth_sources import acquire_sources


def test_measured_defaults_cover_the_complete_group_without_changing_source_or_reservation():
    assert (audit.DEFAULT_MAX_REQUESTS, audit.DEFAULT_MAX_SECONDS, audit.DEFAULT_MAX_TOKENS) == (192, 14400, 25_000_000)
    assert audit.DEFAULT_OUTPUT_TOKEN_RESERVATION == 65536
    result = audit.run_audit(state(), Model(response()), {'ground_truth_max_seconds': 14400, 'ground_truth_max_tokens': 25_000_000}, inventory=inventory())
    assert result['coverage']['reviewed_chunks'] == 1 and result['usage']['requests'] == 1


def test_default_and_explicit_shared_lifecycle_remainders_agree_after_large_report():
    progress = {'requests': 138, 'elapsed_seconds': 11445.364, 'budget_tokens': 16_879_262}
    explicit = {'ground_truth_max_requests': 192, 'ground_truth_max_seconds': 14400, 'ground_truth_max_tokens': 25_000_000}
    for config in ({}, explicit):
        remaining = flow._remaining_config({'ground_truth_execution': dict(progress)}, config)
        assert remaining['ground_truth_max_requests'] == 54
        assert remaining['ground_truth_max_seconds'] == pytest.approx(2954.636)
        assert remaining['ground_truth_max_tokens'] == 8_120_738
        model = Model(SimpleNamespace(usage_metadata={'input_tokens': 2, 'output_tokens': 3}))
        used = dict(progress)
        flow._BudgetedModel(model, used, config).invoke('One bounded PM assessment')
        assert len(model.calls) == 1 and used['budget_tokens'] == progress['budget_tokens'] + 5


@pytest.mark.parametrize('corrupt', [False, True])
def test_recovery_reserves_the_same_full_calibrated_allowance(tmp_path, corrupt):
    candidate = {**state(), 'run_id': str(uuid4())}
    config = {'results_dir': str(tmp_path), 'ground_truth_max_requests': 192,
              'ground_truth_max_seconds': 14400, 'ground_truth_max_tokens': 25_000_000}
    recovery.restore(candidate, config)
    assert recovery.checkpoint(candidate, config, reserve=True)
    path = recovery._path(candidate, config)
    snapshot = json.loads(path.read_text())['state']['ground_truth_execution']
    expected = {'requests': 192, 'elapsed_seconds': 14400, 'budget_tokens': 25_000_000}
    assert snapshot == expected
    if corrupt:
        path.write_text('{}')
    resumed = {**state(), 'run_id': candidate['run_id']}
    recovery.restore(resumed, config)
    assert resumed['ground_truth_execution'] == expected
    assert all(value == 0 for key, value in flow._remaining_config(resumed, config).items() if key.startswith('ground_truth_max_'))


def test_acquisition_keeps_its_existing_thirty_second_bound_with_larger_shared_allowance(monkeypatch):
    constructor, client = fake_transport(monkeypatch)
    result = acquire_sources(source_state(), {'ground_truth_audit': True, 'ground_truth_max_seconds': 14400})
    assert constructor.call_args.kwargs['max_seconds'] == 30
    assert client.fetch.call_count == 1 and result['ground_truth_source_acquisition']['requests'] == 1


@pytest.mark.parametrize('limits', [
    {'ground_truth_max_requests': 0, 'ground_truth_max_seconds': 0, 'ground_truth_max_tokens': 0},
    {'ground_truth_max_requests': 513, 'ground_truth_max_seconds': 14401, 'ground_truth_max_tokens': 25_000_001},
])
def test_zero_or_above_calibrated_ceiling_never_resets_to_fresh_authority(limits):
    remaining = flow._remaining_config({}, limits)
    assert all(remaining[key] == 0 for key in limits)
    model = Model(response())
    result = audit.run_audit(state(), model, limits, inventory=inventory())
    assert not model.calls and result['usage']['requests'] == 0
