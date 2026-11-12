"""The look-back outcome table: price change after a rating, less the market's, at 21 and 63 sessions."""
from scripts.lookback_outcomes import change, outcomes, rank_correlation, summary


def _series(step, length=70):
    return [100 * (1 + step) ** day for day in range(length)]


def test_change_is_measured_in_sessions_and_is_unknown_until_they_have_traded():
    closes = [100.0, 101.0, 102.0]
    assert round(change(closes, 2), 6) == 2.0 and change(closes, 3) is None and change([], 1) is None


def test_excess_is_the_stock_less_the_market_and_the_summary_counts_right_calls():
    prices = {"UP": _series(0.004), "DOWN": _series(-0.002), "SPY": _series(0.001)}
    rows = [{"ticker": "UP", "date": "2026-06-01", "rating": "Underweight", "valuation_vs_close": -10.0},
            {"ticker": "DOWN", "date": "2026-06-01", "rating": "Underweight", "valuation_vs_close": -20.0},
            {"ticker": "UP", "date": "2026-07-01", "rating": "Overweight", "valuation_vs_close": 5.0},
            {"ticker": "DOWN", "date": "2026-07-01", "rating": "Hold", "valuation_vs_close": -1.0}]
    scored = outcomes(rows, fetch=lambda ticker, day: prices[ticker])
    assert scored[0]["excess_21"] > 0 > scored[1]["excess_21"]
    result = summary(scored)["horizons"][21]
    assert result["scored"] == 4 and result["directional_right"] == "2 of 3"
    assert result["by_rating"]["Underweight"]["count"] == 2 and result["by_rating"]["Underweight"]["share_below_market"] == 0.5
    assert result["valuation_rank_correlation"] is not None


def test_rank_correlation_needs_four_pairs_and_reads_a_perfect_order_as_one():
    assert rank_correlation([(1, 1), (2, 2), (3, 3)]) is None
    assert rank_correlation([(1, 10), (2, 20), (3, 30), (4, 40)]) == 1.0
    assert rank_correlation([(1, 40), (2, 30), (3, 20), (4, 10)]) == -1.0
