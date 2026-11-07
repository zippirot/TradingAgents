"""Attempt directories, save recovery and retained state paths are operator behavior."""
import json
from pathlib import Path

import pytest

from cli import run


def test_two_runs_same_day_keep_both_report_sets(tmp_path):
    cfg = {'results_dir': str(tmp_path)}
    first = run._run_directory(cfg, 'DOCN', '2026-11-07', '11111111-1111-4111-8111-111111111111')
    second = run._run_directory(cfg, 'DOCN', '2026-11-07', '22222222-2222-4222-8222-222222222222')
    assert first != second and first.parent == second.parent == tmp_path / 'DOCN/2026-11-07'
    for path, text in ((first, 'first'), (second, 'second')):
        (path / 'reports').mkdir(parents=True)
        (path / 'reports/complete_report.md').write_text(text)
    assert (first / 'reports/complete_report.md').read_text() == 'first'


def test_relative_save_path_lands_under_results_reports(tmp_path):
    default = tmp_path / 'default'
    assert run._resolve_save_path('custom', default, tmp_path) == tmp_path / 'reports/custom'
    assert run._resolve_save_path('', default, tmp_path) == default
    for invalid in ('y', 'no', 'xy', '../outside'):
        with pytest.raises(ValueError):
            run._resolve_save_path(invalid, default, tmp_path)


def test_save_path_y_is_rejected_and_default_used(monkeypatch, tmp_path):
    answers = iter(['Y', 'y', 'no'])
    monkeypatch.setattr(run.typer, 'prompt', lambda *a, **k: next(answers))
    seen = []
    class Graph:
        config = {'results_dir': str(tmp_path)}
        def default_report_path(self, ticker): return tmp_path / 'reports'
        def save_reports(self, state, ticker, save_path, html=True):
            seen.append(save_path)
            return save_path / 'complete_report.md'
    assert run._offer_reports({}, Graph(), 'DOCN', show=False, html=False)
    assert seen == [tmp_path / 'reports']
    assert not (tmp_path / 'y').exists()


def test_report_save_failure_is_logged_with_traceback_and_retried_once(monkeypatch, tmp_path):
    from cli.run_logging import cleanup_run_logging, configure_run_logging
    log = configure_run_logging(tmp_path)
    answers = iter(['Y', '', 'Y', 'recovered'])
    monkeypatch.setattr(run.typer, 'prompt', lambda *a, **k: next(answers))
    seen = []
    class Graph:
        config = {'results_dir': str(tmp_path)}
        def default_report_path(self, ticker): return tmp_path / 'reports'
        def save_reports(self, state, ticker, path, html=True):
            seen.append(path)
            if len(seen) == 1:
                raise OSError('DUMMY_PROVIDER_SECRET')
            return path / 'complete_report.md'
    try:
        assert run._offer_reports({}, Graph(), 'DOCN', show=False, html=False)
    finally:
        cleanup_run_logging()
    assert seen == [tmp_path / 'reports', tmp_path / 'reports/recovered']
    text = log.read_text()
    assert 'Report save failed' in text and 'Traceback' in text and 'OSError' in text
    assert 'DUMMY_PROVIDER_SECRET' not in text


def test_unattended_save_failure_never_prompts(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run.typer, 'prompt', lambda *a, **k: pytest.fail('unattended prompt'))
    class Graph:
        config = {'results_dir': str(tmp_path)}
        def default_report_path(self, ticker): return tmp_path / 'reports'
        def save_reports(self, *args, **kwargs): raise OSError('DUMMY_SECRET')
    assert not run._offer_reports({}, Graph(), 'DOCN', save=True, show=False, html=False)
    assert 'DUMMY_SECRET' not in capsys.readouterr().out


def test_state_log_is_written_per_run_and_as_latest(monkeypatch, tmp_path):
    from tests.test_shared_source_brief import source_state
    from tradingagents.agents.evidence_validation import review_terminal_state
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    state = source_state(monkeypatch)
    state.update(review_terminal_state({'status': 'insufficient', 'checks': []}))
    state.update(dict.fromkeys(('market_report','news_report','sentiment_report','fundamentals_report'), ''))
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {'results_dir': str(tmp_path)}
    graph.run_settings = lambda: {}
    ids = ('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222')
    for identity in ids:
        state['run_id'] = identity
        graph._log_state(state['trade_date'], state)
    folder = tmp_path / 'DOCN/TradingAgentsStrategy_logs'
    latest = folder / f"full_states_log_{state['trade_date']}.json"
    assert json.loads(latest.read_text())['run_id'] == ids[1]
    for identity in ids:
        assert json.loads((folder / f"full_states_log_{state['trade_date']}_{identity[:8]}.json").read_text())['run_id'] == identity


def test_run_settings_include_source_revision_and_effort(monkeypatch):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory import publication
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"llm_provider": "openrouter", "openai_reasoning_effort": "high"}
    graph.selected_analysts = ["market"]
    monkeypatch.setattr(publication, "runtime_versions", lambda: {"code": "a" * 64})
    settings = graph.run_settings()
    assert settings["source_hash"] == "a" * 64
    assert settings["openai_reasoning_effort"] == "high"
    assert "backend_url" not in settings


def test_save_retry_cannot_reuse_the_failed_path(monkeypatch, tmp_path):
    first = tmp_path / 'reports-retry'
    answers = iter(['Y', str(first), 'Y', str(first)])
    monkeypatch.setattr(run.typer, 'prompt', lambda *a, **k: next(answers))
    paths = []
    class Graph:
        config = {'results_dir': str(tmp_path)}
        def default_report_path(self, ticker): return tmp_path / 'reports'
        def save_reports(self, state, ticker, path, html=True):
            paths.append(path)
            if len(paths) == 1:
                raise OSError('retry fixture')
            return path / 'complete_report.md'
    assert run._offer_reports({}, Graph(), 'DOCN', show=False, html=False)
    assert len(paths) == 2 and paths[0].resolve() != paths[1].resolve()


def test_enter_keeps_default_with_relative_results_directory(monkeypatch):
    root = Path('results/DOCN/2026-11-06/120000-12345678')
    default = root / 'reports'
    # Typer returns its displayed default when the operator presses Enter.
    monkeypatch.setattr(run.typer, 'prompt', lambda *args, **kwargs: kwargs['default'])
    assert run._prompt_save_path(default, root) == default.resolve()
