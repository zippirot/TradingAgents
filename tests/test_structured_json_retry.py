"""A model that answers a structured step in prose is asked once more for plain JSON before falling back."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from tradingagents.agents.schemas import TraderProposal
from tradingagents.agents.structured import JSON_RETRY, bind_structured, invoke_structured

GOOD = json.dumps({"action": "Sell", "reasoning": "Trim.", "reference_sale_level": 84.57})


def _llm(first, reply=None, error=None):
    llm, bound = MagicMock(), MagicMock()
    llm.with_structured_output.return_value = bound
    bound.invoke.side_effect = error
    bound.invoke.return_value = first
    llm.invoke.return_value = SimpleNamespace(content=reply)
    return llm, bound


def test_a_prose_answer_is_retried_as_plain_json_and_read():
    for unread in ({"raw": "prose", "parsed": None, "parsing_error": None},
                   {"raw": "prose", "parsed": None, "parsing_error": ValueError("bad")}, None):
        llm, _ = _llm(unread, "Here it is:\n```json\n" + GOOD + "\n```")
        proposal = invoke_structured(bind_structured(llm, TraderProposal, "Trader"), "Decide.", "Trader")
        assert proposal.action.value == "Sell" and proposal.reference_sale_level == 84.57
        asked = llm.invoke.call_args[0][0]
        assert asked.startswith("Decide.\n\n" + JSON_RETRY) and '"reference_sale_level"' in asked
        assert llm.invoke.call_count == 1


def test_a_message_list_prompt_gets_the_request_as_one_more_user_message():
    llm, _ = _llm({"raw": "prose", "parsed": None, "parsing_error": None}, GOOD)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    assert invoke_structured(bind_structured(llm, TraderProposal, "Trader"), messages, "Trader") is not None
    asked = llm.invoke.call_args[0][0]
    assert asked[:2] == messages and asked[2]["role"] == "user" and asked[2]["content"].startswith(JSON_RETRY)
    assert len(messages) == 2          # the caller's prompt is not changed, so its own fallback sends the original


def test_a_retry_that_still_cannot_be_read_leaves_the_first_outcome_for_the_fallback():
    for reply in ("Still prose.", '{"action": "Maybe"}', "{not json}", None):
        llm, _ = _llm({"raw": "prose", "parsed": None, "parsing_error": None}, reply)
        assert invoke_structured(bind_structured(llm, TraderProposal, "Trader"), "Decide.", "Trader") is None


def test_a_structured_answer_or_a_provider_error_makes_no_extra_call():
    parsed = TraderProposal(action="Hold", reasoning="Wait.")
    llm, _ = _llm({"raw": "r", "parsed": parsed, "parsing_error": None})
    assert invoke_structured(bind_structured(llm, TraderProposal, "Trader"), "Decide.", "Trader") is parsed
    assert llm.invoke.call_count == 0
    failing, _ = _llm(None, GOOD, error=RuntimeError("provider down"))
    assert invoke_structured(bind_structured(failing, TraderProposal, "Trader"), "Decide.", "Trader") is None
    assert failing.invoke.call_count == 0


def test_every_structured_role_schema_can_be_stated_and_read_back():
    from tradingagents.agents import schemas
    for name in ("TraderProposal", "ResearchPlan", "PortfolioDecision"):
        schema = getattr(schemas, name)
        assert json.dumps(schema.model_json_schema())
