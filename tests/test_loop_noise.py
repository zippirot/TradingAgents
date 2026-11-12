"""Repeat runs of one company give the spread a later change must beat."""
from scripts.loop_noise import FACTORS, summarize


def _run(rating, decision):
    return {"ticker": "wmt", "rating": rating,
            "scores": {"Decision": decision, "Research": 6.0, **dict.fromkeys(FACTORS, decision)}}


def test_repeats_report_rating_agreement_and_the_spread_of_each_score():
    result = summarize([_run("Hold", 5.5), _run("Hold", 6.1), _run("Underweight", 5.0)])["WMT"]
    assert result["rating_agreement"] == "2 of 3" and result["ratings"] == {"Hold": 2, "Underweight": 1}
    assert result["scores"]["Decision"] == {"mean": 5.53, "spread": 1.1}
    assert result["scores"]["Research"]["spread"] == 0.0
