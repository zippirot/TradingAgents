"""EX1 references resolve to a real companion for fresh and REVIEW exports."""
import json

import pytest

from tests.test_decision_page import inputs
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.reporting import evidence_snapshot, write_report_tree


def test_current_projection_names_diagnostics_companion():
    value = inputs()
    value['investment_debate_state'] = {'bull_history': 'Original bull research'}
    projected = enforce_publication(value)
    for text in (projected['investment_plan'], projected['final_trade_decision'],
                 projected['investment_debate_state']['bull_history']):
        assert 'evidence.json diagnostics' not in text
        assert 'diagnostics.json' in text


@pytest.mark.parametrize('review', [False, True])
def test_unpublished_export_writes_referenced_original_diagnostics(tmp_path, review):
    value = inputs()
    value['market_report'] = 'Original market research that must survive projection.'
    if review:
        value['evidence_quality'] = {'status': 'insufficient', 'checks': []}
    expected = evidence_snapshot(value).get('raw_diagnostics', {})
    assert expected
    path = write_report_tree(value, 'DOCN', tmp_path, html=True)
    companion = tmp_path / 'diagnostics.json'
    assert companion.is_file()
    diagnostics = json.loads(companion.read_text())
    for key, original in expected.items():
        if key == 'unvalidated_outputs':
            assert all(diagnostics[key].get(name) == text for name, text in original.items())
        else:
            assert diagnostics[key] == original
    assert diagnostics['unvalidated_outputs']['investment_plan'] == value['investment_plan']
    assert diagnostics['unvalidated_outputs']['market_report'] == value['market_report']
    assert diagnostics == json.loads((tmp_path / 'evidence.json').read_text())['raw_diagnostics']
    assert 'evidence.json diagnostics' not in path.read_text()
