"""Net income for a filer that tags only consolidated profit and has no noncontrolling interest (Broadcom).

With no other owner in the books, consolidated profit is the parent's net income. The bridge is a derived
fact naming the profit it came from; it is refused when the package holds any noncontrolling figure.
"""
import pytest

from tests.test_face_liabilities import _package
from tradingagents.agents.evidence_validation import validate_calculation_lineage
from tradingagents.dataflows.financial_evidence import FinancialFact, derive_profit_as_parent_income


def _flow(metric, value, fact_id=None):
    return FinancialFact(fact_id=fact_id or metric, metric=metric, value=value, unit="USD", cik="0000789019",
                         period_start="2026-05-04", period_end="2026-08-02", as_of="2026-11-11",
                         source_ids=("s",), locator=metric)


def test_consolidated_profit_is_the_parents_net_income_when_there_is_no_other_owner():
    profit = _flow("Consolidated Profit (Loss)", 2974)
    income = derive_profit_as_parent_income(profit, ())
    assert income.metric == "Net Income" and income.value == 2974 and income.origin == "derived"
    assert income.input_fact_ids == (profit.fact_id,) and (income.period_start, income.period_end) == (profit.period_start, profit.period_end)
    package = _package(profit, income)
    assert validate_calculation_lineage(package) == []


def test_any_noncontrolling_figure_in_the_package_refuses_the_bridge():
    profit = _flow("Consolidated Profit (Loss)", 2974)
    for other in (_flow("Net Income Attributable to Noncontrolling Interests", 5),
                  _flow("Noncontrolling Interests", 60).model_copy(update={"period_start": None})):
        with pytest.raises(ValueError, match="noncontrolling"):
            derive_profit_as_parent_income(profit, (other,))
    # And a package that gains one after the fact no longer validates.
    income = derive_profit_as_parent_income(profit, ())
    stale = _package(profit, income, _flow("Net Income Attributable to Noncontrolling Interests", 5))
    assert any("noncontrolling" in reason for reason in validate_calculation_lineage(stale))


def test_income_available_to_common_holders_that_differs_from_profit_refuses_the_bridge():
    profit = _flow("Consolidated Profit (Loss)", 2974)
    with pytest.raises(ValueError, match="differs from consolidated profit"):
        derive_profit_as_parent_income(profit, (_flow("Basic Earnings Numerator", 2970),))
    assert derive_profit_as_parent_income(profit, (_flow("Basic Earnings Numerator", 2974),)).value == 2974
