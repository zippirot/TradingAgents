"""Ground Truth Audit is an explicit choice for each run."""
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from cli import main, prefs, selections
from cli.run import _build_run_config
from tests.test_cli_config_precedence import SELECTIONS


@pytest.mark.parametrize('flag', [True, False])
def test_explicit_flag_reaches_run_without_prompt(monkeypatch, flag):
    seen = {}
    monkeypatch.setattr(main, 'run_analysis', lambda **kwargs: seen.update(kwargs))
    option = '--ground-truth-audit' if flag else '--no-ground-truth-audit'
    result = CliRunner().invoke(main.app, [option])
    assert result.exit_code == 0, result.output
    assert seen['flags']['ground_truth_audit'] is flag
    assert _build_run_config({**SELECTIONS, 'ground_truth_audit': flag}, None)['ground_truth_audit'] is flag


def test_previous_yes_does_not_enable_next_interactive_run(monkeypatch):
    monkeypatch.setattr(selections, 'sys', SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True)))
    questions = []
    monkeypatch.setattr(selections.typer, 'confirm', lambda text, **kwargs: questions.append((text, kwargs)) or kwargs['default'])
    assert selections.select_ground_truth_audit({}) is False
    assert questions[0][1]['default'] is False
    assert 'Ground Truth Audit' in questions[0][0]
    assert 'ground_truth_audit' not in prefs.REMEMBERED


def test_unattended_omission_is_no_without_prompt(monkeypatch):
    monkeypatch.setattr(selections, 'sys', SimpleNamespace(stdin=None))
    monkeypatch.setattr(selections.typer, 'confirm', lambda *a, **k: pytest.fail('unexpected prompt'))
    assert selections.select_ground_truth_audit({}) is False
    assert _build_run_config(SELECTIONS, None)['ground_truth_audit'] is False


def test_selection_flow_ignores_remembered_yes_and_can_opt_in(monkeypatch):
    from tests.test_cli_headless import FLAGS, UNATTENDED_ENV

    for name, value in UNATTENDED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(selections, '_check_tier_providers', lambda *a: None)
    monkeypatch.setattr(selections.updates, 'enabled', lambda: False)
    monkeypatch.setattr(selections, 'sys', SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True)))
    answers = iter([False, True])
    defaults = []

    def answer(text, **kwargs):
        defaults.append(kwargs['default'])
        return next(answers)

    monkeypatch.setattr(selections.typer, 'confirm', answer)
    previous = {'ground_truth_audit': True}
    assert selections._prompt_selections(previous, FLAGS)['ground_truth_audit'] is False
    assert selections._prompt_selections(previous, FLAGS)['ground_truth_audit'] is True
    assert defaults == [False, False]
