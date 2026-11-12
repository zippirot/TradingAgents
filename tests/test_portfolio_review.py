"""Portfolio review: the file's review-only fields, the latest rating per ticker, direction and amounts."""
import json
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from tradingagents.portfolio import PortfolioContext, load_portfolio
from tradingagents.portfolio_review import amounts_review, direction_review, latest_ratings, render_review

WEIGHTS = {"Buy": 1.5, "Overweight": 1.25, "Hold": 1.0, "Underweight": 0.5, "Sell": 0}
LEGACY = {"cash": 5000, "currency": "USD", "positions": [{"ticker": "DOCN", "quantity": 100, "average_price": 90}]}
SIZED = {**LEGACY, "portfolio_value": 200000, "default_standard_weight": 0.05, "rating_weights": WEIGHTS}
EXTRA = {"watchlist": ["msft", "DOCN", "nvda"], "limits": {"max_position_weight": 0.1}}


# Task 1: the file ---------------------------------------------------------------

@pytest.mark.parametrize("base", [LEGACY, SIZED])
def test_existing_file_keeps_its_fingerprint_with_new_fields_present(base):
    extended = {**base, **EXTRA, "positions": [{**base["positions"][0], "sector": "Technology"}]}
    assert PortfolioContext.model_validate(extended).fingerprint() == PortfolioContext.model_validate(base).fingerprint()


def test_the_pinned_legacy_fingerprint_is_unchanged():
    assert PortfolioContext.model_validate({**LEGACY, **EXTRA}).fingerprint() == "8deac4f58a71"


def test_inputs_never_carry_watchlist_limits_or_sector():
    inputs = PortfolioContext.model_validate(
        {**SIZED, **EXTRA, "positions": [{"ticker": "DOCN", "quantity": 1, "sector": "Technology"}]}).inputs()
    assert "watchlist" not in inputs and "limits" not in inputs and "sector" not in inputs["positions"][0]


def test_limits_reject_out_of_range(tmp_path):
    path = tmp_path / "book.json"
    path.write_text(json.dumps({**LEGACY, "limits": {"max_position_weight": 1.5}}))
    with pytest.raises(ValueError, match="not usable"):
        load_portfolio(path)


def test_review_tickers_orders_held_then_watchlist_without_duplicates():
    assert PortfolioContext.model_validate({**LEGACY, **EXTRA}).review_tickers() == ["DOCN", "MSFT", "NVDA"]


# Task 2: latest rating ----------------------------------------------------------

TODAY = date(2026, 11, 11)


def record(ticker, as_of, rating, sequence=1):
    return {"ticker": ticker, "requested_as_of": as_of, "sequence": sequence, "canonical_rating": rating,
            "evidence_status": "limited", "run_id": f"run-{ticker}-{sequence}"}


def test_the_newest_record_wins_and_a_same_day_revision_with_a_higher_sequence_wins():
    records = [record("AAA", "2026-11-01", "Buy", 1), record("AAA", "2026-11-10", "Hold", 2),
               record("AAA", "2026-11-10", "Overweight", 3), record("BBB", "2026-10-01", "Sell", 4)]
    found = latest_ratings(records, ["AAA", "bbb"], TODAY, 30)
    assert found["AAA"] == {"status": "rated", "rating": "Overweight", "as_of": "2026-11-10", "age_days": 1,
                            "stale": False, "run_id": "run-AAA-3"}
    assert found["BBB"]["rating"] == "Sell" and found["BBB"]["age_days"] == 41 and found["BBB"]["stale"] is True


def test_a_latest_review_gives_no_rating_even_when_an_older_buy_exists_and_no_record_is_none():
    records = [record("AAA", "2026-10-01", "Buy", 1), record("AAA", "2026-11-10", "REVIEW", 2)]
    found = latest_ratings(records, ["AAA", "ZZZ"], TODAY, 30)
    assert found["AAA"]["status"] == "review" and found["AAA"]["rating"] is None and found["AAA"]["as_of"] == "2026-11-10"
    assert found["ZZZ"] == {"status": "none", "rating": None, "as_of": None, "age_days": None, "stale": False, "run_id": None}


def test_a_rating_one_day_past_the_age_limit_is_stale():
    found = latest_ratings([record("AAA", "2026-10-11", "Buy")], ["AAA"], TODAY, 30)
    assert found["AAA"]["age_days"] == 31 and found["AAA"]["stale"] is True
    assert latest_ratings([record("AAA", "2026-10-12", "Buy")], ["AAA"], TODAY, 30)["AAA"]["stale"] is False


# Task 3: direction --------------------------------------------------------------

def book(held=None, watch=(), value=100000, cash=10000, sectors=None, standard=0.05, **limits):
    """``held`` maps ticker to quantity; every price in these tests is 100, so 50 units is 5% of 100,000."""
    held = {"AAA": 50} if held is None else held
    positions = [{"ticker": t, "quantity": q, **({"sector": sectors[t]} if sectors and t in sectors else {})}
                 for t, q in held.items()]
    data = {"currency": "USD", "cash": cash, "positions": positions, "watchlist": list(watch),
            "portfolio_value": value, "default_standard_weight": standard, "rating_weights": WEIGHTS}
    if limits:
        data["limits"] = limits
    return PortfolioContext.model_validate(data)


def rated(rating, stale=False, status="rated"):
    return {"status": status, "rating": rating, "as_of": "2026-11-10", "age_days": 40 if stale else 1, "stale": stale,
            "run_id": "r"}


def quotes(*tickers, close="100", currency="USD"):
    return {t: {"status": "available", "close": close, "currency": currency, "session_date": "2026-11-11"} for t in tickers}


def row(review, ticker):
    return next(r for r in review["rows"] if r["ticker"] == ticker)


def test_a_stock_with_no_rating_a_review_a_short_or_no_price_is_not_reviewed_and_the_others_still_are():
    b = book({"AAA": 50, "REV": 10, "SHT": -5, "NOP": 10, "EUR": 10}, watch=["NEW"])
    ratings = {"AAA": rated("Hold"), "REV": rated(None, status="review"), "SHT": rated("Buy"), "NOP": rated("Buy"),
               "EUR": rated("Buy"), "NEW": {"status": "none", "rating": None, "as_of": None, "age_days": None,
                                            "stale": False, "run_id": None}}
    q = {**quotes("AAA", "REV", "SHT", "NEW"), "NOP": {"status": "unavailable", "reason": "Yahoo price history unavailable"},
         **quotes("EUR", currency="EUR")}
    review = direction_review(b, ratings, q, {})
    assert row(review, "AAA")["direction"] == "Hold"
    assert row(review, "REV")["direction"] == "Not reviewed" and "No rating (analysis stopped at REVIEW)" in row(review, "REV")["note"]
    assert "short position, not reviewed" in row(review, "SHT")["note"]
    assert "Yahoo price history unavailable" in row(review, "NOP")["note"]
    assert "price is in EUR" in row(review, "EUR")["note"]
    assert "No rating" in row(review, "NEW")["note"] and row(review, "NEW")["direction"] == "Not reviewed"


@pytest.mark.parametrize(("rating", "direction"), [("Buy", "Buy"), ("Overweight", "Buy"), ("Hold", "No action"),
                                                   ("Underweight", "No action"), ("Sell", "No action")])
def test_a_stock_not_held_is_a_buy_only_when_rated_buy_or_overweight(rating, direction):
    review = direction_review(book(watch=["NEW"]), {"AAA": rated("Hold"), "NEW": rated(rating)}, quotes("AAA", "NEW"), {})
    assert row(review, "NEW")["direction"] == direction and row(review, "NEW")["held"] is False


@pytest.mark.parametrize(("units", "rating", "direction"), [
    (50, "Sell", "Exit"), (50, "Buy", "Add"), (50, "Hold", "Hold"), (52, "Hold", "Hold"), (80, "Hold", "Trim"),
    (50, "Underweight", "Trim"), (25, "Underweight", "Hold")])
def test_a_held_stock_moves_toward_its_target_weight(units, rating, direction):
    review = direction_review(book({"AAA": units}), {"AAA": rated(rating)}, quotes("AAA"), {})
    assert row(review, "AAA")["direction"] == direction


@pytest.mark.parametrize(("rating", "direction"), [("Buy", "Add"), ("Overweight", "Add"), ("Hold", "Hold"),
                                                   ("Underweight", "Trim"), ("Sell", "Exit")])
def test_without_weights_a_held_stock_follows_its_rating_and_says_weights_were_not_supplied(rating, direction):
    plain = PortfolioContext.model_validate({"currency": "USD", "positions": [{"ticker": "AAA", "quantity": 5}]})
    found = row(direction_review(plain, {"AAA": rated(rating)}, quotes("AAA"), {}), "AAA")
    assert found["direction"] == direction and "were not supplied" in found["note"] and found["target_weight"] is None


def test_top_rated_stock_at_position_limit_is_hold_with_a_reason():
    review = direction_review(book({"AAA": 100}, standard=0.10, max_position_weight=0.10), {"AAA": rated("Buy")}, quotes("AAA"),
                              {"AAA": "Technology"})
    assert row(review, "AAA")["direction"] == "Hold" and "at position limit" in row(review, "AAA")["note"]


def test_a_stock_above_its_position_limit_is_a_trim_whatever_the_rating_but_an_exit_stays_an_exit():
    b = book({"AAA": 150, "BBB": 150}, max_position_weight=0.10)
    review = direction_review(b, {"AAA": rated("Buy"), "BBB": rated("Sell")}, quotes("AAA", "BBB"), {})
    assert row(review, "AAA")["direction"] == "Trim" and "above position limit" in row(review, "AAA")["note"]
    assert row(review, "BBB")["direction"] == "Exit"


def test_a_sector_at_its_limit_stops_buying_in_it_and_an_unknown_sector_is_left_out_and_said():
    b = book({"AAA": 50, "BBB": 150, "UNK": 10}, watch=["NEW", "OTH"], max_sector_weight=0.20)
    ratings = {t: rated("Buy") for t in ("AAA", "BBB", "UNK", "NEW", "OTH")}
    sectors = {"AAA": "Technology", "BBB": "Technology", "NEW": "Technology", "OTH": "Energy", "UNK": None}
    review = direction_review(b, ratings, quotes("AAA", "BBB", "UNK", "NEW", "OTH"), sectors)
    assert review["sector_weights"] == {"Technology": "0.2"}
    assert row(review, "AAA")["direction"] == "Hold" and "sector at limit" in row(review, "AAA")["note"]
    assert row(review, "NEW")["direction"] == "No action" and "sector at limit" in row(review, "NEW")["note"]
    assert row(review, "OTH")["direction"] == "Buy"
    assert row(review, "UNK")["direction"] == "Add" and "sector unknown" in row(review, "UNK")["note"]


def test_a_sector_named_on_the_position_overrides_the_vendors():
    b = book({"AAA": 50}, sectors={"AAA": "Utilities"})
    assert row(direction_review(b, {"AAA": rated("Hold")}, quotes("AAA"), {"AAA": "Technology"}), "AAA")["sector"] == "Utilities"


def test_warnings_for_low_cash_holdings_above_the_stated_value_and_stale_ratings():
    b = book({"AAA": 1200}, cash=1000, min_cash_weight=0.05)
    review = direction_review(b, {"AAA": rated("Hold", stale=True)}, quotes("AAA"), {})
    text = " | ".join(review["warnings"])
    assert "Cash is 1.0% of the portfolio, below your minimum of 5.0%" in text
    assert "more than the portfolio_value in your file" in text and "weights use portfolio_value" in text
    assert "stale" in text and "AAA" in text
    assert direction_review(book(), {"AAA": rated("Hold")}, quotes("AAA"), {})["warnings"] == []


def test_buys_and_adds_are_ranked_by_rating_then_by_the_largest_shortfall():
    b = book({"AAA": 50, "BBB": 10}, watch=["NEW", "OVR"])
    ratings = {"AAA": rated("Buy"), "BBB": rated("Overweight"), "NEW": rated("Buy"), "OVR": rated("Overweight")}
    review = direction_review(b, ratings, quotes("AAA", "BBB", "NEW", "OVR"), {})
    ranked = sorted((r for r in review["rows"] if r["rank"]), key=lambda r: r["rank"])
    # Buy before Overweight; within Buy, NEW is 7.5% short and AAA 2.5%; within Overweight, OVR 6.25% and BBB 5.25%.
    assert [r["ticker"] for r in ranked] == ["NEW", "AAA", "OVR", "BBB"]


# Task 4: amounts ----------------------------------------------------------------

def amounts(b, ratings, sectors=None):
    names = b.review_tickers()
    direction = direction_review(b, ratings, quotes(*names), sectors or {})
    return direction, amounts_review(direction, b, quotes(*names))


def amount_row(result, ticker):
    return next(r for r in result["rows"] if r["ticker"] == ticker)


def test_sales_fund_purchases_and_units_are_whole():
    b = book({"OUT": 200, "AAA": 50}, cash=0)
    direction, result = amounts(b, {"OUT": rated("Sell"), "AAA": rated("Buy")})
    assert result["status"] == "available"
    assert amount_row(result, "OUT") == {"ticker": "OUT", "direction": "Exit", "units": "-200", "amount": "-20000.00",
                                         "resulting_weight": "0", "note": "sells the whole position"}
    # AAA is at 5% and Buy means 7.5%: 2.5% of 100,000 is 2,500, 25 units at 100.
    assert amount_row(result, "AAA")["units"] == "25" and amount_row(result, "AAA")["amount"] == "2500.00"
    assert result["cash_before"] == "0.00" and result["cash_after"] == "17500.00"


def test_the_cash_floor_is_respected_and_running_out_leaves_the_lower_row_unfunded():
    b = book({"AAA": 50}, watch=["NEW"], cash=13050, min_cash_weight=0.05)
    direction, result = amounts(b, {"AAA": rated("Buy"), "NEW": rated("Buy")})
    # 13,050 less the 5,000 floor is 8,050. NEW ranks first and wants 7,500; AAA wants 2,500 and gets 5 units.
    assert amount_row(result, "NEW")["units"] == "75" and amount_row(result, "NEW")["note"] == "funded"
    assert amount_row(result, "AAA")["units"] == "5" and "partly funded" in amount_row(result, "AAA")["note"]
    assert result["cash_after"] == "5050.00" and result["cash_floor"] == "5000.00"
    broke = book({"AAA": 50}, watch=["NEW"], cash=5000, min_cash_weight=0.05)
    _, none = amounts(broke, {"AAA": rated("Buy"), "NEW": rated("Buy")})
    assert amount_row(none, "AAA")["units"] == "0" and "not funded" in amount_row(none, "AAA")["note"]
    assert amount_row(none, "NEW")["units"] == "0" and none["cash_after"] == "5000.00"


def test_a_sector_limit_partly_fills_a_row_and_a_position_limit_caps_one():
    b = book({"AAA": 50, "BBB": 100}, watch=["NEW"], cash=50000, max_sector_weight=0.20, max_position_weight=0.06)
    sectors = {"AAA": "Technology", "BBB": "Technology", "NEW": "Technology"}
    direction, result = amounts(b, {"AAA": rated("Hold"), "BBB": rated("Hold"), "NEW": rated("Buy")}, sectors)
    # BBB at 10% is above the 6% position limit and trims to 5% (its Hold target). Technology is then 10%.
    assert amount_row(result, "BBB")["units"] == "-50"
    # NEW wants 7.5% but the position limit is 6%.
    assert amount_row(result, "NEW")["units"] == "60" and "capped by position limit" in amount_row(result, "NEW")["note"]
    tight = book({"AAA": 50, "BBB": 100}, watch=["NEW"], cash=50000, max_sector_weight=0.17)
    _, capped = amounts(tight, {"AAA": rated("Hold"), "BBB": rated("Hold"), "NEW": rated("Buy")}, sectors)
    # BBB trims to 5%, leaving Technology at 10%; it may reach 17%, so NEW gets 7% of 100,000: 70 units.
    assert amount_row(capped, "BBB")["direction"] == "Trim" and amount_row(capped, "BBB")["units"] == "-50"
    assert amount_row(capped, "NEW")["units"] == "70" and "capped by sector limit" in amount_row(capped, "NEW")["note"]


def test_units_round_down_and_missing_inputs_make_amounts_unavailable_without_touching_direction():
    b = book({"AAA": 50}, cash=10000)
    names = b.review_tickers()
    q = quotes(*names, close="130")
    direction = direction_review(b, {"AAA": rated("Buy")}, q, {})
    before = deepcopy(direction)
    result = amounts_review(direction, b, q)
    # 50 units at 130 is 6.5%; Buy means 7.5%; 1,000 buys 7 whole units.
    assert amount_row(result, "AAA")["units"] == "7" and Decimal(amount_row(result, "AAA")["amount"]) == Decimal("910.00")
    assert direction == before
    no_cash = PortfolioContext.model_validate({**b.model_dump(), "cash": None})
    missing = amounts_review(direction, no_cash, q)
    assert missing["status"] == "unavailable" and "cash" in missing["reason"] and direction == before


# Task 5: rendering --------------------------------------------------------------

def test_level_one_has_no_amounts_and_level_two_is_a_separate_work_in_progress_section():
    b = book({"AAA": 50}, watch=["NEW", "NON"], cash=20000)
    ratings = {"AAA": rated("Buy", stale=True), "NEW": rated("Buy"),
               "NON": {"status": "none", "rating": None, "as_of": None, "age_days": None, "stale": False, "run_id": None}}
    q = quotes("AAA", "NEW", "NON")
    direction = direction_review(b, ratings, q, {})
    text = render_review(direction, amounts_review(direction, b, q), fingerprint=b.fingerprint(), generated="2026-11-11 17:00")
    one, two = text.split("## Level 2")
    assert "## Level 1: Direction" in one and "not an order" in one and "stale" in one
    assert "USD" not in one.split("## Level 1")[1] and "7500" not in one and "7,500" not in one
    assert two.startswith(": Recommended amounts (work in progress)") and "7,500.00 USD" in two and "Cash before" in two
    assert "No rating yet: NON" in text and "tradingagents batch NON" in text
    plain = PortfolioContext.model_validate({"currency": "USD", "positions": [{"ticker": "AAA", "quantity": 5}]})
    direction = direction_review(plain, {"AAA": rated("Buy")}, quotes("AAA"), {})
    text = render_review(direction, amounts_review(direction, plain, quotes("AAA")), fingerprint="x", generated="now")
    assert "Not computed: " in text.split("## Level 2")[1]
