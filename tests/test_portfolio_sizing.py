"""Sizing becomes a number only from the caller's own portfolio inputs; without them nothing changes."""
import json
from decimal import Decimal

import pytest

from tradingagents.portfolio import (
    PortfolioContext,
    average_daily_move,
    default_portfolio_path,
    load_portfolio,
    render_sizing,
    sizing,
    sizing_from_state,
)

QUOTE = {"close": "80", "currency": "USD", "session_date": "2026-11-09"}
WEIGHTS = {"Buy": 1.5, "Overweight": 1.25, "Hold": 1.0, "Underweight": 0.5, "Sell": 0}
LEGACY = {"cash": 5000, "currency": "USD", "positions": [{"ticker": "DOCN", "quantity": 100, "average_price": 90}]}


def book(**fields):
    return PortfolioContext.model_validate({**LEGACY, **fields}).inputs()


def full(quantity=100, **fields):
    return book(**{"positions": [{"ticker": "DOCN", "quantity": quantity}], "portfolio_value": 200000,
                   "default_standard_weight": 0.05, "loss_budget": 0.01, "rating_weights": WEIGHTS, **fields})


# The file ---------------------------------------------------------------------

def test_a_file_with_only_positions_works_as_before_and_keeps_its_fingerprint():
    legacy = PortfolioContext.model_validate(LEGACY)
    assert legacy.fingerprint() == "8deac4f58a71"  # the digest this file had before the sizing fields existed
    assert "Current position in DOCN: 100 units, average price 90.00" in legacy.render("DOCN")
    assert sizing(legacy.inputs(), "DOCN", QUOTE) == {"status": "not_configured"}
    assert render_sizing(sizing(legacy.inputs(), "DOCN", QUOTE)) == []
    assert PortfolioContext.model_validate({**LEGACY, "portfolio_value": 200000}).fingerprint() != legacy.fingerprint()


@pytest.mark.parametrize("bad", [
    {"portfolio_value": 0}, {"portfolio_value": -5}, {"default_standard_weight": 1.5}, {"loss_budget": 0},
    {"rating_weights": {"Strong Buy": 2}}, {"rating_weights": {"Buy": -1}},
    {"positions": [{"ticker": "DOCN", "quantity": 1, "standard_weight": 2}]},
])
def test_a_malformed_file_fails_before_the_run(tmp_path, bad):
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps({**LEGACY, **bad}))
    with pytest.raises(ValueError, match="not usable"):
        load_portfolio(path)


def test_the_users_file_is_picked_up_only_when_it_exists(tmp_path, monkeypatch):
    from tradingagents import default_config

    path = tmp_path / "portfolio.json"
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "portfolio_path", str(path))
    assert default_portfolio_path() is None
    path.write_text(json.dumps(LEGACY))
    assert default_portfolio_path() == str(path)


def test_the_launcher_loads_the_users_file_and_an_explicit_file_wins(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import cli.main as main
    from tradingagents import default_config

    seen = []
    monkeypatch.setattr(main, "run_analysis", lambda checkpoint, portfolio, flags: seen.append(portfolio))
    runner = CliRunner()
    home, explicit = tmp_path / "portfolio.json", tmp_path / "other.json"
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "portfolio_path", str(home))
    assert runner.invoke(main.app, []).exit_code == 0 and seen == [None]
    home.write_text(json.dumps({**LEGACY, "portfolio_value": 200000}))
    explicit.write_text(json.dumps({**LEGACY, "portfolio_value": 300000}))
    runner.invoke(main.app, [])
    runner.invoke(main.app, ["--portfolio", str(explicit)])
    assert [p.portfolio_value for p in seen[1:]] == [200000, 300000]
    home.write_text("{not json")
    result = runner.invoke(main.app, [])
    assert result.exit_code == 1 and "not usable" in result.output and len(seen) == 3


# The arithmetic ---------------------------------------------------------------

@pytest.mark.parametrize(("quantity", "weight", "standing"), [
    (100, "0.04", "below"), (125, "0.05", "at"), (130, "0.052", "at"), (132, "0.0528", "above"), (0, "0", "below"),
])
def test_current_weight_and_standing_against_standard(quantity, weight, standing):
    result = sizing(full(quantity), "docn", QUOTE)
    assert result["status"] == "available"
    assert Decimal(result["current_weight"]) == Decimal(weight) and result["standing"] == standing


def test_each_rating_gets_a_target_weight_and_the_units_between_here_and_there():
    result = sizing(full(100), "DOCN", QUOTE, rating="Underweight")
    rows = {row["rating"]: (Decimal(row["target_weight"]), row["units_change"]) for row in result["targets"]}
    # Standard 5% of 200,000 is 10,000, or 125 units at 80.
    assert rows == {"Buy": (Decimal("0.075"), "88"), "Overweight": (Decimal("0.0625"), "56"),
                    "Hold": (Decimal("0.05"), "25"), "Underweight": (Decimal("0.025"), "-38"),
                    "Sell": (Decimal(0), "-100")}
    assert result["final"]["rating"] == "Underweight"
    lines = render_sizing(result, final=True)
    assert "- For the final rating Underweight on your scale: 2.5% of the portfolio (about 38 units fewer than you hold)." in lines
    before = "\n".join(render_sizing(sizing(full(100), "DOCN", QUOTE)))
    assert "Buy 7.5% of the portfolio (about 88 units more than you hold)" in before
    assert "Sell 0.0% of the portfolio (about 100 units fewer than you hold)" in before


def test_a_position_standard_weight_overrides_the_default():
    inputs = book(positions=[{"ticker": "DOCN", "quantity": 100, "standard_weight": 0.02}], portfolio_value=200000,
                  default_standard_weight=0.05)
    result = sizing(inputs, "DOCN", QUOTE)
    assert result["standard_weight"] == "0.02" and result["standing"] == "above"


def test_missing_inputs_are_said_not_assumed():
    lines = "\n".join(render_sizing(sizing(book(portfolio_value=200000), "DOCN", QUOTE), final=True))
    assert "100 units, 4.0% of the portfolio." in lines
    assert "Standard weight: not supplied" in lines and "Loss budget: not supplied" in lines
    no_scale = "\n".join(render_sizing(sizing(book(portfolio_value=200000, default_standard_weight=0.05),
                                              "DOCN", QUOTE), final=True))
    assert "no rating_weights supplied, so no target weight is stated" in no_scale
    partial = sizing(full(rating_weights={"Hold": 1}), "DOCN", QUOTE, rating="Sell")
    assert "your rating_weights has no entry for the final rating" in "\n".join(render_sizing(partial, final=True))


def test_loss_at_review_levels_and_one_daily_move_is_compared_with_the_budget():
    closes = [100 * (1.02 if index % 2 else 1) for index in range(20)]
    result = sizing(full(250), "DOCN", QUOTE, levels=["70", "40", "90", "bad"], closes=closes)
    rows = result["loss"]["rows"]
    # 250 units: a fall to 70 loses 2,500 of 200,000 (1.25%); to 40, 10,000 (5%). 90 is above the close: no loss.
    assert [(row["kind"], row.get("level"), Decimal(row["loss"]), row["inside"]) for row in rows[:2]] == [
        ("level", "70", Decimal("0.0125"), False), ("level", "40", Decimal("0.05"), False)]
    assert rows[2]["kind"] == "daily_move" and rows[2]["inside"] is True
    assert Decimal(rows[2]["move"]) == average_daily_move(closes)
    text = "\n".join(render_sizing(result))
    assert "at the advisory review level 70.00 USD the position loses 1.25%, OUTSIDE the budget" in text
    assert "at one average daily move (2.0%, mean absolute close-to-close change over 14 sessions)" in text
    assert "these are not stops" in text
    small = sizing(full(100), "DOCN", QUOTE, levels=["70"])
    assert small["loss"]["rows"] == [{"kind": "level", "level": "70", "loss": "0.005", "inside": True}]
    assert "average daily move unavailable" in "\n".join(render_sizing(small))


def test_no_position_has_nothing_at_risk_and_a_short_loses_above_the_close():
    flat = sizing(full(0), "DOCN", QUOTE, levels=["70"])
    assert flat["loss"]["rows"] == [] and "no position, so nothing is at risk" in "\n".join(render_sizing(flat))
    short = sizing(full(-100), "DOCN", QUOTE, levels=["70", "90"])
    assert [row["level"] for row in short["loss"]["rows"]] == ["90"]


@pytest.mark.parametrize(("quote", "reason"), [
    ({}, "no completed close"), ({"close": "0", "session_date": "2026-11-09"}, "no completed close"),
    ({**QUOTE, "currency": "EUR"}, "the portfolio file is in USD and the price is in EUR"),
])
def test_no_usable_or_comparable_price_computes_nothing_and_says_why(quote, reason):
    result = sizing(full(), "DOCN", quote)
    assert result["status"] == "unavailable" and reason in result["reason"]
    assert render_sizing(result)[0].startswith("**Position and sizing**: not computed; ")


def test_amounts_are_hidden_unless_the_file_asks_for_them():
    hidden = "\n".join(render_sizing(sizing(full(100), "DOCN", QUOTE, levels=["70"], rating="Sell"), final=True))
    assert "8,000" not in hidden and "USD)" not in hidden.split("\n", 1)[1]
    shown = "\n".join(render_sizing(sizing(full(100, show_amounts=True), "DOCN", QUOTE, levels=["70"], rating="Sell"),
                                    final=True))
    assert "100 units, 4.0% of the portfolio, 8,000.00 USD." in shown
    assert "(about 100 units fewer than you hold, 8,000.00 USD)" in shown and "loses 0.50%, 1,000.00 USD, inside" in shown


# The run ----------------------------------------------------------------------

def _state(inputs=None, **extra):
    bars = [{"timestamp": f"2026-10-{day:02d}T00:00:00-04:00", "close": str(80 + day % 2)} for day in range(1, 21)]
    state = {"company_of_interest": "DOCN", "portfolio_context": "Portfolio at the analysis date:\n- x",
             "price_observation": {**QUOTE, "raw_source": {"bars": bars + [
                 {"timestamp": "2026-11-10T00:00:00-05:00", "close": "999"}]}},
             "prior_thesis": {"conditions": [{"kind": "price_level", "threshold": "70"},
                                             {"kind": "metric", "threshold": "55.5"}]},
             "thesis": {"conditions": [{"kind": "price_level", "threshold": "60"}]}, **extra}
    if inputs is not None:
        state["portfolio_inputs"] = inputs
    return state


def test_agents_get_the_block_from_the_earlier_thesis_levels_and_only_closes_up_to_the_session():
    from tradingagents.agents.context import get_portfolio_context_from_state

    result = sizing_from_state(_state(full(100)))
    assert [row.get("level") for row in result["loss"]["rows"]] == ["70", None]
    assert Decimal(result["loss"]["rows"][1]["move"]) < Decimal("0.02")  # the 999 bar after the session is not read
    text = get_portfolio_context_from_state(_state(full(100)))
    assert text.startswith("Portfolio at the analysis date:") and "**Position and sizing**" in text
    assert "What each rating means on your scale" in text and "computed from the caller's own inputs" in text
    assert get_portfolio_context_from_state(_state()) == "Portfolio at the analysis date:\n- x"
    assert get_portfolio_context_from_state(_state(book())) == "Portfolio at the analysis date:\n- x"
    assert "not provided" in get_portfolio_context_from_state({})


def test_run_state_carries_the_inputs_only_when_a_portfolio_is_given():
    from tradingagents.graph.propagation import Propagator
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.propagator = Propagator()
    graph.config = {}
    graph.resolve_instrument_context = lambda *a: ""
    graph._initial_run_metrics = dict
    graph.run_settings = dict
    graph._analysis_cutoff = lambda day: {"cutoff_utc": "2026-11-10T06:59:59+00:00", "analysis_timezone": "America/Denver"}
    assert "portfolio_inputs" not in graph.create_run_state("DOCN", "2026-11-09")
    given = PortfolioContext.model_validate({**LEGACY, "portfolio_value": 200000})
    state = graph.create_run_state("DOCN", "2026-11-09", portfolio=given)
    assert state["portfolio_inputs"]["portfolio_value"] == 200000
    assert state["portfolio_inputs"]["fingerprint"] == given.fingerprint()


def _published(monkeypatch, inputs):
    from tests.test_decision_brief import _finished
    from tradingagents.agents.output_validation import enforce_publication

    state = _finished(monkeypatch, "Underweight", {"status": "strengthens", "reason": "Margin fell again."})
    del state["decision_brief"]
    state["trader_investment_plan"] = "Proposal"
    if inputs is not None:
        state["portfolio_inputs"] = inputs
    return state, enforce_publication(state)


def test_the_fixed_qualitative_sentence_stays_without_inputs_and_is_replaced_with_them(monkeypatch):
    fixed = ("Position sizing: no validated numerical allocation; any sizing ratio above is "
             "arithmetic on the accepted cases.")
    _state_, plain = _published(monkeypatch, None)
    assert fixed in plain["final_trade_decision"] and "portfolio_fingerprint" not in plain["decision_context"]
    assert plain["trader_investment_plan"].startswith("Position sizing: no numerical allocation is published without verified portfolio")
    _state_, legacy = _published(monkeypatch, book())
    assert legacy["final_trade_decision"] == plain["final_trade_decision"]
    inputs = full(100)
    _state_, sized = _published(monkeypatch, inputs)
    line = ("Position sizing: see the Position and sizing block in the report, arithmetic on the portfolio inputs "
            f"supplied for this run (file fingerprint {inputs['fingerprint']}); not an order.")
    assert line in sized["final_trade_decision"] and fixed not in sized["final_trade_decision"]
    assert sized["trader_investment_plan"].startswith(line)
    assert sized["decision_context"]["portfolio_fingerprint"] == inputs["fingerprint"]


def test_the_report_opens_with_the_block_and_the_published_record_holds_only_the_fingerprint(monkeypatch):
    from tradingagents.reporting import (
        evidence_snapshot,
        position_sizing_note,
        prepare_report_state,
    )

    inputs = full(100)
    state, sized = _published(monkeypatch, inputs)
    done = {**state, **sized}
    note = position_sizing_note(done)
    assert note.startswith("**Position and sizing** (arithmetic on your portfolio file, file fingerprint ")
    assert "For the final rating Underweight on your scale" in note and "not an order" in note
    prepared = prepare_report_state(done)
    assert prepared["final_trade_decision"].startswith(note)
    # What is published: the canonical decision text and the evidence snapshot.
    published = json.dumps([sized["final_trade_decision"], evidence_snapshot(done)])
    assert inputs["fingerprint"] in published
    for private in ("200000", "portfolio_value", "loss_budget", "rating_weights", "100 units", "4.0% of the portfolio"):
        assert private not in published
    plain_state, plain = _published(monkeypatch, None)
    assert position_sizing_note({**plain_state, **plain}) == ""
    assert "Position and sizing" not in prepare_report_state({**plain_state, **plain})["final_trade_decision"]


def test_markdown_and_html_reports_carry_the_block_once_each_at_the_top(monkeypatch, tmp_path):
    from tradingagents.reporting import write_report_tree

    state, sized = _published(monkeypatch, full(100))
    write_report_tree({**state, **sized}, "DOCN", tmp_path / "with")
    text = (tmp_path / "with" / "complete_report.md").read_text()
    page = (tmp_path / "with" / "complete_report.html").read_text()
    assert text.index("**Position and sizing**") < text.index("## ") and "Position and sizing</strong>" in page
    assert "For the final rating Underweight on your scale" in text and "units more than you hold" in page
    plain_state, plain = _published(monkeypatch, None)
    write_report_tree({**plain_state, **plain}, "DOCN", tmp_path / "without")
    for name in ("complete_report.md", "complete_report.html"):
        assert "Position and sizing" not in (tmp_path / "without" / name).read_text()


def test_where_the_portfolio_file_lives_does_not_invalidate_a_saved_checkpoint():
    """The file's contents are in the run signature through its fingerprint; its location is not a run input."""
    from tradingagents.graph.trading_graph import _NOT_IN_SIGNATURE

    assert "portfolio_path" in _NOT_IN_SIGNATURE


ECHO = "Hold 100 units, 4.0% of the portfolio; trim toward a 2.5% target weight worth $5,000."


def test_figures_a_manager_repeats_from_the_block_do_not_reach_the_published_record(monkeypatch, tmp_path):
    """Independent audit, High: the agents are shown the figures, and their prose is published."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from tests.test_decision_brief import _finished
    from tradingagents.agents.output_validation import enforce_publication
    from tradingagents.memory import publication
    from tradingagents.reporting import prepare_report_state

    def run(inputs):
        state = _finished(monkeypatch, "Underweight", {"status": "strengthens", "reason": "Margin fell 2%. " + ECHO})
        answer = state["unvalidated_outputs"]["portfolio_manager"]
        answer["structured"].update(executive_summary=ECHO, investment_thesis="Revenue grew 39.87%. " + ECHO)
        answer["thesis_candidate"] = {"rationale": ECHO, "conditions": [
            {"kind": "event", "description": "Note settles", "rationale": ECHO, "thesis_role": "supports_thesis"}]}
        state.update(run_id=str(uuid4()), thesis={"schema_version": 1, "rationale": "Margin thesis. " + ECHO})
        if inputs is not None:
            state["portfolio_inputs"] = inputs
        state.update(enforce_publication(state))
        monkeypatch.setattr(publication, "_utcnow", lambda: datetime(2026, 10, 19, 22, tzinfo=UTC))
        config = {"results_dir": str(tmp_path / str(inputs is None))}
        record = publication.publish(config, state, "DOCN", state["trade_date"])
        return state, json.dumps([record, publication.load_evidence(config, record)])

    state, published = run(full(100))
    for private in ("100 units", "4.0% of the portfolio", "2.5% target weight", "$5,000"):
        assert private not in published
    # Evidence figures and the rest of the prose stay; the withholding is said once per text.
    assert "Revenue grew 39.87%." in published and "Margin fell 2%." in published and "Margin thesis." in published
    assert "Figures stated against the caller's portfolio are withheld from the published record." in published
    assert state["portfolio_inputs"]["fingerprint"] in published
    # The reader's own report still opens with the computed block.
    assert prepare_report_state(state)["final_trade_decision"].startswith("**Position and sizing**")
    # A run that was shown no portfolio figures publishes its prose untouched.
    _plain_, untouched = run(None)
    assert "100 units, 4.0% of the portfolio" in untouched and "withheld from the published record" not in untouched
    _legacy_, same = run(book())
    assert "100 units, 4.0% of the portfolio" in same


def test_case_weights_and_ordinary_wording_are_not_mistaken_for_portfolio_figures():
    from tradingagents.agents.evidence_presentation import (
        PORTFOLIO_WITHHELD,
        without_portfolio_figures,
    )
    kept = ["Retain prior subjective weight; 6x borrowings-only and approximately $1.93bn 2027 revenue are plausible.",
            "Subjective scenario weights remain 45% base, 45% downside and 10% upside, unchanged since the prior decision.",
            "The all-leases sensitivity changes the perimeter while holding the 6x multiple fixed.",
            "With equal weights the value today is 88.99."]
    for sentence in kept:
        assert without_portfolio_figures(sentence) == sentence
    hidden = ["Reduce DOCN from 35.8% of the portfolio toward the 2.5% underweight allocation.",
              "Cut to a 2.5% weight, about 1,304 fewer units.", "The current holding is 1,402 shares.",
              "Holdings of 1,402 remain above the 5% standard weight."]
    for sentence in hidden:
        assert without_portfolio_figures(sentence).strip() == PORTFOLIO_WITHHELD
