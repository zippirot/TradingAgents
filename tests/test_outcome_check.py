"""The outcome check: one command that runs the fixed past-date set and reports whether views were right."""
from scripts import outcome_check

SET = {"dates": ["2026-05-01", "2026-06-01"], "tickers": ["MSFT", "JPM"]}


def test_a_run_already_saved_under_the_label_is_not_repeated(tmp_path):
    assert outcome_check.plan(SET, "base", tmp_path) == [("MSFT", "2026-05-01"), ("JPM", "2026-05-01"),
                                                         ("MSFT", "2026-06-01"), ("JPM", "2026-06-01")]
    saved = tmp_path / "logs-oc-base-20260501" / "MSFT" / "TradingAgentsStrategy_logs"
    saved.mkdir(parents=True)
    (saved / "full_states_log_2026-05-01.json").write_text("{}")
    assert ("MSFT", "2026-05-01") not in outcome_check.plan(SET, "base", tmp_path)
    assert len(outcome_check.plan(SET, "other", tmp_path)) == 4          # another label has its own runs


def test_each_run_goes_to_its_labels_folder_and_keeps_its_own_state_file(tmp_path):
    line = outcome_check.command("JPM", "2026-06-01", "base", tmp_path)
    assert line[line.index("--fresh") + 1] == "oc-base-20260601" and "--skip-cost" in line
    assert line[line.index("--state") + 1] == str(tmp_path / "oc-state-base.json")


def test_the_report_sets_two_labels_side_by_side():
    def block(mean, right):
        return {"horizons": {63: {"scored": 3, "by_stock_view": {"Attractive": {"count": 2, "mean_excess": mean,
                                                                           "share_below_market": 0.5}},
                                  "directional_right": right, "valuation_rank_correlation": 0.5}}}
    text = "\n".join(outcome_check.lines(block(12.5, "2 of 3"), block(10.0, "1 of 3"), ("new", "base")))
    assert "Attractive   +12.5 points, 2 views, 1 below the market | +10.0 points, 2 views, 1 below the market" in text
    assert "direction right  2 of 3 | 1 of 3" in text and "(new | base)" in text
    assert "none" in "\n".join(outcome_check.lines(block(1.0, "0 of 0")))    # a view with no rows says so
