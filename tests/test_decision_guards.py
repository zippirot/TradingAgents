"""Guards found by DeepSeek run 2d2e3856: a misread return hurdle, a positive result filed as supporting a
bearish rating, a price trigger dropped for a missing currency, and a summary lost to a prose answer."""
import json
from uuid import uuid4

from tests.test_price_observation import install
from tests.test_report_summary import FakeLLM, report, valid_payload
from tests.test_required_return import RETURN, _three
from tests.test_scenario_decision import _accept, _state
from tests.test_thesis import condition
from tradingagents.agents.scenario_decision import render, retry_feedback, summarize
from tradingagents.dataflows.vendors.yahoo import price_observation as prices
from tradingagents.memory import thesis
from tradingagents.report_summary import build_summary_input, generate_summary

UPSIDE_HEAVY = [_accept("base", 0.25), _accept("down", 0.05), _accept("up", 0.7)]
MISREAD = ("Weighted accepted scenario value today is 7.3% above the close, below the required return of ~9.88% "
           "annualized. The all-leases sensitivity sits below the close.")


def _bearish(reason):
    return {**_state(UPSIDE_HEAVY, rating="Underweight", reason=reason), "trade_date": "2026-11-10",
            "required_return": RETURN}


def test_a_reason_that_says_the_hurdle_is_missed_when_code_says_it_is_cleared_is_sent_back_once():
    summary = summarize(_bearish(MISREAD), _three())
    assert float(summary["return_gap_points"]) > 0 and summary["consistency"] == "explained"
    assert summary["reason_conflict"] is True
    feedback = retry_feedback(_bearish(MISREAD), _three())
    assert "Your rating_basis_reason says the accepted scenarios fall short of the required return" in feedback
    assert "a year against a required" in feedback and "Resubmit the complete decision" in feedback
    text = "\n".join(render(summary))
    assert "Code note on that reason: it says the required return is not met" in text


def test_a_reason_that_starts_from_the_code_figure_stands_without_a_note():
    reason = ("The accepted cases clear the required return, but the full lease stack is not in them and the position "
              "is far above its standard weight.")
    summary = summarize(_bearish(reason), _three())
    assert summary["consistency"] == "explained" and summary["reason_conflict"] is False
    assert retry_feedback(_bearish(reason), _three()) == ""
    assert "Code note on that reason" not in "\n".join(render(summary))


def test_a_bullish_reason_claiming_the_hurdle_is_cleared_when_it_is_not_gets_the_mirror_note():
    weak = [_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]
    state = {**_state(weak, rating="Buy", reason="The weighted case exceeds the required return comfortably."),
             "trade_date": "2026-11-10", "required_return": RETURN}
    summary = summarize(state, _three())
    assert float(summary["return_gap_points"]) < 0 and summary["reason_conflict"] is True
    assert "it says the required return is met" in "\n".join(render(summary))


def test_a_good_result_filed_as_supporting_a_bearish_rating_is_named():
    good = condition(thesis_role="supports_thesis")                       # Revenue >= 100
    trigger = condition(metric="Gross Margin", metric_definition="Gross Margin", unit="percent", threshold="50")
    assert thesis.role_conflicts("Underweight", [good, trigger]) == [
        'Revenue >= 100 USD is filed as supporting the Underweight rating, but a higher Revenue is good news for '
        'the company.']
    assert thesis.role_conflicts("Overweight", [good]) == [] and thesis.role_conflicts("Hold", [good]) == []
    low = condition(thesis_role="supports_thesis", comparator="<")
    assert thesis.role_conflicts("Buy", [low]) == [
        'Revenue < 100 USD is filed as supporting the Buy rating, but a lower Revenue is bad news for the company.']
    assert thesis.role_conflicts("Sell", [low]) == [] and thesis.role_conflicts("Sell", "x") == []
    feedback = thesis.role_feedback("Underweight", [good])
    assert "supports_thesis means the result supports the rating you give now" in feedback
    assert thesis.role_feedback("Underweight", [trigger]) == ""


def test_a_surviving_role_conflict_is_shown_on_the_card_and_the_label_names_the_rating():
    saved = thesis.prepare_thesis({'conditions': [condition(thesis_role="supports_thesis")]}, None, 'Underweight',
                                  '2026-11-04', str(uuid4()))
    assert any(w.startswith('Role check: Revenue >= 100 USD is filed as supporting') for w in saved['warnings'])
    assert thesis.condition_role_label(saved['conditions'][0]) == 'Supports the current rating'
    assert thesis.visible_warnings([*saved['warnings'], 'Condition x aliases: y', 'Condition at index 2 stated but not retained: z']) == [
        w for w in saved['warnings'] if w.startswith('Role check: ')] + ['Condition at index 2 stated but not retained: z']


def test_a_price_trigger_without_a_currency_takes_the_validated_quote_currency(monkeypatch):
    install(monkeypatch, now='2026-11-04T22:00:00+00:00')
    quote = prices.get_price_observation('DOCN', '2026-11-04')
    price = {'thesis_role': 'reconsideration_trigger', 'kind': 'price_level', 'comparator': '<', 'threshold': 69.78,
             'expiry': '2027-05-10', 'rationale': 'Support area'}
    saved = thesis.prepare_thesis({'conditions': [price]}, None, 'Underweight', '2026-11-04', str(uuid4()),
                                  price_observation=quote, ticker='DOCN')
    assert saved['conditions'][0]['kind'] == 'price_level' and saved['conditions'][0]['currency'] == 'USD'
    assert not any('stated but not retained' in w for w in saved['warnings'])
    assert any('quote currency was not stated' in w for w in saved['warnings'])
    # Without a validated quote there is nothing to take it from, and a stated wrong currency is still refused.
    for kwargs, item in (({}, price), ({'price_observation': quote, 'ticker': 'DOCN'}, {**price, 'currency': 'EUR'})):
        dropped = thesis.prepare_thesis({'conditions': [item]}, None, 'Underweight', '2026-11-04', str(uuid4()), **kwargs)
        assert dropped['conditions'] == [] and any('stated but not retained' in w for w in dropped['warnings'])


class _Prose(FakeLLM):
    """A model that cannot be made to call the tool: prose first, the JSON object when asked plainly."""

    def with_structured_output(self, schema, include_raw=True):
        outer = self

        class Bound:
            def invoke(self, prompt):
                outer.calls.append(("structured", prompt))
                return {"raw": object(), "parsed": None, "parsing_error": None}
        return Bound()

    def invoke(self, prompt):
        self.calls.append(("plain", prompt))
        return type("Response", (), {"content": self.payload})()


def test_a_summary_answered_in_prose_is_asked_for_once_more_as_plain_json():
    model = _Prose("Here it is:\n```json\n" + json.dumps(valid_payload()) + "\n```")
    record = generate_summary(build_summary_input(*report()), model)
    assert record["status"] == "completed" and [kind for kind, _ in model.calls] == ["structured", "plain"]
    retry = model.calls[1][1]
    assert "one JSON object" in retry and "every one of these section keys" in retry and "6_evidence" in retry


def test_a_summary_that_fails_twice_stays_unavailable_and_a_good_first_answer_is_not_asked_again():
    bad = _Prose("I cannot produce that.")
    record = generate_summary(build_summary_input(*report()), bad)
    assert record["status"] == "unavailable" and record["error_category"] == "malformed_response"
    assert len(bad.calls) == 2
    good = FakeLLM(valid_payload())
    assert generate_summary(build_summary_input(*report()), good)["status"] == "completed" and len(good.calls) == 1


def test_the_portfolio_manager_step_sends_a_misfiled_role_back_once_and_keeps_the_answer():
    from tests.test_portfolio_valuation import decision, invoke
    misfiled = decision(rating="Underweight", thesis_candidate={
        "rationale": "Obligations outweigh growth.", "conditions": [condition(thesis_role="supports_thesis")]})
    result, llm = invoke(misfiled)
    calls = llm.with_structured_output.return_value.invoke.call_args_list
    assert len(calls) == 2 and "Condition roles: Revenue >= 100 USD is filed as supporting" in calls[1].args[0]
    assert result["final_rating"] == "Underweight"
    clean = decision(rating="Underweight", thesis_candidate={
        "rationale": "Obligations outweigh growth.", "conditions": [condition()]})
    _, llm = invoke(clean)
    assert len(llm.with_structured_output.return_value.invoke.call_args_list) == 1
