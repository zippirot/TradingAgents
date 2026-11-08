"""Reruns replace pending memory, without rewriting settled lessons."""
from uuid import uuid4

from tradingagents.memory.log import TradingMemoryLog


def test_pending_rerun_replaces_atomically_and_same_publication_is_idempotent(tmp_path):
    path = tmp_path / 'memory.md'
    memory = TradingMemoryLog({'memory_log_path': str(path)})
    first, second = str(uuid4()), str(uuid4())
    memory.store_decision('DOCN', '2026-11-04', 'Underweight at 09:10', 'Underweight', first)
    memory.store_decision('DOCN', '2026-11-04', 'Hold at 16:41', 'Hold', second)
    entries = memory.load_entries()
    assert len(entries) == 1
    assert entries[0]['decision_id'] == second
    assert entries[0]['decision'] == 'Hold at 16:41'
    before = path.read_bytes(), path.stat().st_mtime_ns
    memory.store_decision('DOCN', '2026-11-04', 'Different retry prose', 'Hold', second)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_replacement_during_settlement_rejects_stale_lesson(tmp_path):
    memory = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    first, second = str(uuid4()), str(uuid4())
    memory.store_decision('DOCN', '2026-11-04', 'Underweight original', 'Underweight', first)
    captured = memory.get_pending_entries()[0]
    memory.store_decision('DOCN', '2026-11-04', 'Hold revision', 'Hold', second)
    assert not memory.update_with_outcome('DOCN', '2026-11-04', .01, .005, 5,
                                         'Stale lesson', expected_entry=captured)
    fresh = memory.get_pending_entries()[0]
    assert fresh['decision_id'] == second
    assert memory.update_with_outcome('DOCN', '2026-11-04', .02, .006, 5,
                                      'Current lesson', expected_entry=fresh)
    entries = memory.load_entries()
    assert len(entries) == 1
    assert entries[0]['reflection'] == 'Current lesson'


def test_settlement_before_rerun_preserves_original_lesson(tmp_path):
    path = tmp_path / 'memory.md'
    memory = TradingMemoryLog({'memory_log_path': str(path)})
    first, second = str(uuid4()), str(uuid4())
    memory.store_decision('DOCN', '2026-11-04', 'Underweight original', 'Underweight', first)
    captured = memory.get_pending_entries()[0]
    assert memory.update_with_outcome('DOCN', '2026-11-04', .01, .005, 5,
                                      'Original lesson', expected_entry=captured)
    before = path.read_bytes()
    memory.store_decision('DOCN', '2026-11-04', 'Hold revision', 'Hold', second)
    assert path.read_bytes() == before
    entries = memory.load_entries()
    assert len(entries) == 1
    assert entries[0]['decision_id'] == first
    assert entries[0]['reflection'] == 'Original lesson'


def test_real_settlement_pass_cannot_apply_inflight_old_reflection_to_rerun(tmp_path, monkeypatch):
    from tradingagents.memory import settlement

    memory = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    first, second = str(uuid4()), str(uuid4())
    memory.store_decision('DOCN', '2026-11-04', 'Underweight original', 'Underweight', first)
    monkeypatch.setattr(settlement, '_returns_for_entry',
                        lambda *args, **kwargs: (.01, .005, 5, '2026-11-12', 'SPY'))

    class Reflector:
        def reflect_on_final_decision(self, **kwargs):
            assert kwargs['final_decision'] == 'Underweight original'
            memory.store_decision('DOCN', '2026-11-04', 'Hold revision', 'Hold', second)
            return 'Old reflection must not land'

    result = settlement.settle_pending('DOCN', memory, Reflector(), {})
    assert result.settled == [] and result.failed == []
    entries = memory.load_entries()
    assert len(entries) == 1
    assert entries[0]['pending'] and entries[0]['decision_id'] == second
    assert entries[0]['reflection'] == ''


def test_failed_atomic_replacement_leaves_original_pending_readable(tmp_path, monkeypatch):
    import pytest

    from tradingagents.memory import log

    path = tmp_path / 'memory.md'
    memory = TradingMemoryLog({'memory_log_path': str(path)})
    memory.store_decision('DOCN', '2026-11-04', 'Underweight original', 'Underweight', str(uuid4()))
    before = path.read_bytes()

    def interrupted(*args, **kwargs):
        raise OSError('interrupted replacement')

    monkeypatch.setattr(log, 'replace_file', interrupted)
    with pytest.raises(OSError, match='interrupted replacement'):
        memory.store_decision('DOCN', '2026-11-04', 'Hold revision', 'Hold', str(uuid4()))
    assert path.read_bytes() == before
    assert len(memory.get_pending_entries()) == 1


def test_pending_replacement_quarantines_partial_tail_and_preserves_other_entries(tmp_path):
    path = tmp_path / 'memory.md'
    memory = TradingMemoryLog({'memory_log_path': str(path)})
    memory.store_decision('OTHER', '2026-11-03', 'Buy unrelated', 'Buy', str(uuid4()))
    unrelated = path.read_bytes()
    memory.store_decision('DOCN', '2026-11-04', 'Underweight original', 'Underweight', str(uuid4()))
    partial = '[2026-11-04 | DOCN | Hold | pending]\n\nDECISION:\nInterrupted rerun'
    with path.open('a') as stream:
        stream.write(partial)
    latest = str(uuid4())
    memory.store_decision('DOCN', '2026-11-04', 'Hold completed rerun', 'Hold', latest)
    assert path.read_bytes().startswith(unrelated)
    entries = memory.load_entries()
    assert len(entries) == 2 and entries[-1]['decision_id'] == latest
    quarantines = list(tmp_path.glob('memory.md.partial-*.md'))
    assert len(quarantines) == 1 and quarantines[0].read_text() == partial
    assert partial not in path.read_text()
