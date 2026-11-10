"""Stated percentages are recomputed from the figures in the same sentence; anything ambiguous is left alone."""
from tradingagents.agents.arithmetic_check import arithmetic_note, check_percentages

REAL = ("- 2026-10-13: 128.21\n- 2026-11-05: 70.70, on 7.82M shares\n"
        "- **Size of the drop:** By my arithmetic from those dated closes, 79.52 is about 56% below the 181.29 "
        "peak close and about 43% below the 2026-10-13 close.\n")


def test_the_slip_from_the_real_run_is_caught_and_the_correct_figure_beside_it_is_not():
    found = check_percentages(REAL)
    assert [(row["stated"], row["computed"]) for row in found] == [(43.0, 38.0)]
    note = arithmetic_note(REAL)
    assert "Arithmetic check (by code, not a model)" in note
    assert "Stated 43%; 79.52 against 128.21 (2026-10-13) gives 38%." in note


def test_from_to_with_one_percentage_is_checked():
    assert check_percentages("RPO fell from $893.8M to $799.7M, down 10.53%.") == []
    wrong = check_percentages("RPO fell from $893.8M to $799.7M, down 15%.")
    assert [(row["stated"], row["computed"]) for row in wrong] == [(15.0, 10.5)]
    assert check_percentages("The index rose from 336.298 to 337.476, up about 0.35% in the month.") == []
    assert check_percentages("The multiple went from 14.26 to 8.50, a decline of roughly 40%.") == []


def test_what_cannot_be_read_with_certainty_is_left_alone():
    for text in (
        "78.30 is about 30% below the 200 SMA and about 32% below the 50 SMA.",          # indicator names
        "78.30 is about 30% below the 50-day average.",
        "Fed funds rose from 3.63% to 3.88%, up 25%.",                                    # figures are percentages
        "Revenue rose from 229.6 to 321.2, with gross margin at 50.15%.",                 # percentage is unrelated
        "Revenue rose from 229.6 to 321.2, up 40% as margin fell 10%.",                   # two percentages
        "Cash went from $254.6M to $1.2B, up 80%.",                                       # different units
        "79.52 is about 43% below the 2026-10-13 close.",                                 # the close is not listed
        "- 2026-10-13: 128.21\n- 2026-10-13: 130.00\n79.52 is about 43% below the 2026-10-13 close.",  # two values
        "The stock is about 43% below the 128.21 close.",                                 # no subject figure
        "", None, 42,
    ):
        assert check_percentages(text) == [], text
    assert arithmetic_note("Nothing to check here.") == ""


def test_the_note_is_capped():
    text = "\n".join(f"It fell from {100 + i} to 50, down 10%." for i in range(9))
    assert len(check_percentages(text)) == 5


def test_an_analysts_finished_report_carries_the_note_and_a_clean_one_is_untouched():
    from langchain_core.messages import AIMessage, HumanMessage

    from tradingagents.graph.analyst_execution import AnalystNodeSpec
    from tradingagents.graph.setup import _analyst_graph

    def run(report):
        spec = AnalystNodeSpec("market", "Market Analyst", "market_report", ())
        return _analyst_graph(spec, lambda state: {"messages": [AIMessage(content=report)], "market_report": report},
                              2).invoke({"company_of_interest": "DOCN", "trade_date": "2026-11-10",
                                         "messages": [HumanMessage(content="DOCN")]})["market_report"]

    noted = run(REAL)
    assert noted.startswith(REAL) and "Stated 43%; 79.52 against 128.21 (2026-10-13) gives 38%." in noted
    assert run("Close is 79.52.") == "Close is 79.52."
