"""Code says how the Trader's levels read and where its size comes from; the Trader cannot restate either."""
from unittest.mock import MagicMock

from tests.test_portfolio_sizing import QUOTE, full
from tradingagents.agents.schemas import SIZING_WITHHELD, TraderProposal
from tradingagents.agents.trader.trader import LEVELS_RULE, SIZED_NOTE, _code_notes, create_trader

PLAN = ("**Recommendation**: Underweight\n\n**Rationale**: Bear wins.\n\n"
        "**Strategic Actions**: Trim gradually. Reassess toward neutral only on revenue, margin, RPO and a "
        "financing plan together.")


def _run(proposal, **state):
    llm, structured = MagicMock(), MagicMock()
    llm.with_structured_output.return_value = structured
    structured.invoke.return_value = proposal
    base = {"company_of_interest": "DOCN", "investment_plan": PLAN, "market_report": "", **state}
    output = create_trader(llm)(base)["trader_investment_plan"]
    return output, structured.invoke.call_args[0][0]


SELL = TraderProposal(action="Sell", reasoning="Trim.", reference_sale_level=84.57, advisory_invalidation_level=85.87,
                      position_sizing="Cut to 2.5% of the portfolio in stages.")


def test_every_proposal_with_a_level_is_followed_by_the_fixed_rule_before_the_carried_plan():
    output, messages = _run(SELL)
    assert LEVELS_RULE in output and output.index(LEVELS_RULE) < output.index("Trim gradually.")
    assert "changes timing only and never the rating" in LEVELS_RULE and "does not halt a change in size" in LEVELS_RULE
    system = messages[0]["content"]
    assert "Do not write your own conditions for changing or reassessing the rating" in system
    assert "never inside them" in system
    hold, _ = _run(TraderProposal(action="Hold", reasoning="Wait."))
    assert LEVELS_RULE not in hold          # no level, nothing to read


def test_without_a_portfolio_file_sizing_stays_qualitative_as_before():
    output, messages = _run(SELL)
    assert SIZING_WITHHELD in output and "Size (by code" not in output
    assert "holdings and loss budget are unknown" in messages[1]["content"]


def test_with_a_portfolio_file_the_trader_is_told_holdings_are_known_and_code_names_the_target():
    state = {"portfolio_context": "Current position in DOCN: 100 units.", "portfolio_inputs": full(100),
             "price_observation": QUOTE}
    output, messages = _run(SELL, **state)
    user = messages[1]["content"]
    assert "holdings and the loss budget are known" in user and "are unknown" not in user
    assert SIZING_WITHHELD not in output and SIZED_NOTE in output
    assert ("Size (by code, from the portfolio file): the research rating is Underweight, so this action moves the "
            "position toward the Underweight target in the Position and sizing block.") in output
    # The Trader's own figure never survives; the published filter has nothing of the caller's to hide here.
    assert "2.5%" not in output


def test_a_plan_whose_rating_cannot_be_read_says_so_and_free_text_gets_the_same_notes():
    text = _code_notes("**Action**: Sell\n**Reference Sale Level**: 84.57", "no rating here", True)
    assert "the research rating could not be read from the plan" in text and text.endswith(LEVELS_RULE)
    assert _code_notes("**Action**: Hold", PLAN, False) == "**Action**: Hold"
