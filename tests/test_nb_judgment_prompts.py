"""Retained Nb.1 requires independent risk directions and round responses."""

from unittest.mock import MagicMock

import pytest

from tests.test_debate_opening import _risk_state
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator

RISK_ROLES = [(create_aggressive_debator, 0), (create_conservative_debator, 1),
              (create_neutral_debator, 2)]


@pytest.mark.parametrize("factory,offset", RISK_ROLES)
@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_risk_roles_choose_direction_and_answer_points_in_the_actual_round(factory, offset,
                                                                         round_number):
    state = _risk_state()
    state["risk_debate_state"]["count"] = (round_number - 1) * 3 + offset
    state["run_settings"] = {"max_risk_discuss_rounds": 3}
    llm = MagicMock()
    llm.invoke.return_value.content = "1. Hold; wait for evidence."
    factory(llm)(state)
    prompt = llm.invoke.call_args.args[0]
    assert f"Risk round {round_number} of 3" in prompt
    assert "direction your risk lens supports, including if that differs from the Trader" in prompt
    assert "create a compelling case for the trader's decision" not in prompt
    if round_number == 1:
        assert "Before critiquing the Trader" in prompt
        assert "your own direction (add / hold / reduce / exit)" in prompt
        assert "evidence that would change it" in prompt
    else:
        assert "other roles' numbered points" in prompt
        assert "answer or concede each" in prompt
    assert ("This is your final round" in prompt) == (round_number == 3)
    if round_number == 3:
        assert "what remains unresolved rather than restating" in prompt
