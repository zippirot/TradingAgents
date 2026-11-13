"""A declared sum that misses by one unit of the figures' real rounding still holds.

McDonald's, 2026-11-13 (user decision): its cash-flow figures are tagged to the hundred thousand but stated in
whole millions; the financing total missed the sum of its lines by exactly 1,000,000 and three past-date runs
stopped. Boundary: the allowance is one unit of the coarsest unit the figures are actually stated in, never
more, and never when the figures are stated to the last dollar.
"""
from datetime import date
from decimal import Decimal

import pytest

from tradingagents.dataflows.filed_instance import (
    InstanceError,
    InstanceFact,
    _check,
    rounding_allowance,
    stated_unit,
)


def _fact(concept, value, decimals=-5):
    return InstanceFact(concept=concept, value=Decimal(value), unit="USD", start=date(2026, 1, 1), end=date(2026, 3, 31),
                        dimensions=(), decimals=decimals)


def _values(total, *lines):
    facts = {"t": _fact("t", total), **{f"l{i}": _fact(f"l{i}", v) for i, v in enumerate(lines)}}
    return facts, [(f"l{i}", Decimal(1)) for i in range(len(lines))]


def test_the_unit_is_the_one_the_figures_are_really_stated_in():
    assert stated_unit([Decimal("-1225000000"), Decimal("1000000"), Decimal("396000000")]) == Decimal(1000000)
    assert stated_unit([Decimal("1234567"), Decimal("1000000")]) == 1
    assert stated_unit([Decimal(0)]) == 1


def test_a_sum_off_by_one_real_unit_holds_and_two_does_not():
    values, children = _values("-1225000000", "-791000000", "-435000000")      # lines sum to -1,226,000,000
    _check(values, "t", children)
    values, children = _values("-1225000000", "-791000000", "-436000000")      # two millions out
    with pytest.raises(InstanceError, match="does not hold"):
        _check(values, "t", children)


def test_figures_stated_to_the_dollar_get_no_added_allowance():
    values, children = _values("101", "60", "43")                              # two dollars out, tagged to the dollar
    with pytest.raises(InstanceError, match="does not hold"):
        _check({key: _fact(key, fact.value, 0) for key, fact in values.items()}, "t", children)


def test_round_figures_tagged_to_the_dollar_get_nothing():
    """A filer that tags figures as exact means them exactly, even when they happen to be round."""
    assert rounding_allowance([Decimal(1000000), Decimal(2000000)], [0, 0]) == 0
    assert rounding_allowance([Decimal(1000000), Decimal(2000000)], [-5, None]) == 0
    assert rounding_allowance([Decimal(1000000), Decimal(2000000)], [-5, -5]) == Decimal(1000000)
