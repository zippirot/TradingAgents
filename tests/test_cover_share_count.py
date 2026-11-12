"""A filer that states its share count only on the cover page, dated after the balance date (Walmart).

The cover count is a filed figure. It is used for the balance date only when it is dated shortly after
it and agrees with the same filing's weighted-average share count for the period ending on that date;
the result is a derived fact that names both inputs, so every later step can say where it came from.
"""
from datetime import date, timedelta

from tests.test_face_liabilities import BASE, END, UNIT, _package, _share_fact, _widen
from tradingagents.agents.evidence_validation import validate_calculation_lineage
from tradingagents.dataflows.financial_evidence import COVER_SHARES_FORMULA

LATER = END + timedelta(days=26)
START = END - timedelta(days=91)


def _contexts(cover=LATER):
    entity = '<entity><identifier scheme="x">1</identifier></entity>'
    return (f'<context id="cover">{entity}<period><instant>{cover}</instant></period></context>'
            f'<context id="quarter">{entity}<period><startDate>{START}</startDate><endDate>{END}</endDate></period></context>'
            f'<context id="half">{entity}<period><startDate>{START - timedelta(days=90)}</startDate><endDate>{END}</endDate></period></context>')


def _shares(extra):
    package, _ = _widen(_package(*BASE), extra=UNIT + extra)
    return [f for f in package.facts if f.metric == "Common Shares Outstanding"], package


AVERAGE = _share_fact("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", 7954, "quarter") \
    + _share_fact("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", 7962, "half")


def test_a_cover_count_dated_after_the_balance_date_is_used_when_the_quarter_average_agrees():
    (shares,), package = _shares(_contexts() + _share_fact("dei:EntityCommonStockSharesOutstanding", 7934, "cover") + AVERAGE)
    assert shares.value == 7934 and shares.unit == "shares" and shares.period_end == END
    assert shares.origin == "derived" and shares.formula_id == COVER_SHARES_FORMULA
    cover, average = (next(f for f in package.facts if f.fact_id == ident) for ident in shares.input_fact_ids)
    assert cover.metric == "Cover Shares Outstanding" and cover.period_end == LATER and str(LATER) in cover.locator
    # The quarter's average is the check, not the six-month one.
    assert average.value == 7954 and average.period_start == START
    assert validate_calculation_lineage(package) == []


def test_a_cover_count_is_refused_without_an_agreeing_average_or_when_dated_too_far_away():
    cover = _share_fact("dei:EntityCommonStockSharesOutstanding", 7934, "cover")
    assert _shares(_contexts() + cover)[0] == []                                        # nothing to check it against
    far = _share_fact("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", 8200, "quarter")
    assert _shares(_contexts() + cover + far)[0] == []                                  # more than 2% apart
    assert _shares(_contexts(END + timedelta(days=150)) + cover + AVERAGE)[0] == []    # dated too long after
    assert _shares(_contexts(date(2025, 12, 31)) + cover + AVERAGE)[0] == []           # dated before: another period


def test_a_tagged_balance_date_count_still_wins_over_the_cover():
    (shares,), _ = _shares(_contexts() + _share_fact("us-gaap:CommonStockSharesOutstanding", 7940)
                           + _share_fact("dei:EntityCommonStockSharesOutstanding", 7934, "cover") + AVERAGE)
    assert shares.value == 7940 and shares.origin == "reported"


def test_a_case_priced_on_a_cover_count_says_so_beside_its_value():
    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state
    from tradingagents.agents.shared_valuation import prepare_shared_valuation
    from tradingagents.dataflows.financial_evidence import EvidencePackage, derive_shares_from_cover

    saved = state([revenue_case()])
    plain = prepare_shared_valuation(saved)
    package = EvidencePackage.model_validate(saved["financial_evidence"])
    shares = next(f for f in package.facts if f.fact_id == "shares")
    cover = shares.model_copy(update={"fact_id": "cover", "metric": "Cover Shares Outstanding",
                                      "period_end": shares.period_end + timedelta(days=20)})
    average = shares.model_copy(update={"fact_id": "average", "metric": "Weighted Average Basic Shares",
                                        "period_start": shares.period_end - timedelta(days=91)})
    derived = derive_shares_from_cover((cover, average)).model_copy(update={"fact_id": "shares"})
    facts = [derived if f.fact_id == "shares" else f for f in package.facts] + [cover, average]
    saved["financial_evidence"] = package.model_copy(update={"facts": tuple(facts)}).model_dump(mode="json")
    record = prepare_shared_valuation(saved)
    row, before = record["rows"][0]["result"], plain["rows"][0]["result"]
    assert row["target"] == before["target"]
    assert any(line.startswith("share count:") and "cover-page count dated" in line for line in row["assumptions"])
    assert not any(line.startswith("share count:") for line in before["assumptions"])
