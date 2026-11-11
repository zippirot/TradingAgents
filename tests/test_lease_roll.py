"""Lease balances carried forward from what a filing states, for any company, with the assumptions named."""
from datetime import date
from decimal import Decimal

import pytest

from tradingagents.agents.lease_roll import implied_rate, roll_new_leases, roll_schedule

AS_OF, END = date(2026, 9, 30), date(2027, 12, 31)
# The schedule DigitalOcean filed for 2026-09-30; the made-up companies below check nothing depends on it.
FILED = {"as_of": AS_OF, "years": {"2026": Decimal("70428000"), "2027": Decimal("250025000"), "2028": Decimal("249102000"),
                                   "2029": Decimal("245219000"), "2030": Decimal("164738000"), "2031": Decimal("79664000")}}
TOTALS = {"total": Decimal("1059176000"), "interest": Decimal("-135577000")}
LEASE = {"undiscounted_amount": "2955158", "unit": "USD thousands", "as_of": "2026-09-30",
         "commencement_start": "2026-11", "commencement_end": "2028-06", "weighted_average_term_years": "11.1"}


def test_the_roll_reproduces_the_filed_balance_and_splits_payments_into_interest_and_principal():
    roll = roll_schedule(FILED, TOTALS, AS_OF, END)
    assert roll["opening"] == Decimal("923599000")            # total less imputed interest, as filed
    assert roll["paid"] == Decimal("320453000")               # the rest of 2026 plus all of 2027
    assert roll["principal"] + roll["interest"] == roll["paid"]
    assert roll["closing"] == roll["opening"] - roll["principal"]
    assert 0.05 < roll["rate"] < 0.08 and Decimal("50000000") < roll["interest"] < Decimal("80000000")


def test_rolling_to_the_last_scheduled_day_repays_everything_and_all_interest():
    roll = roll_schedule(FILED, TOTALS, AS_OF, date(2031, 12, 31))
    assert roll["closing"] == 0 and roll["paid"] == TOTALS["total"]
    assert abs(roll["interest"] - 135577000) <= 1


def test_a_made_up_company_with_one_level_schedule():
    schedule = {"as_of": date(2025, 12, 31), "years": {"2026": Decimal(110), "2027": Decimal(121)}}
    # 110 and 121 paid mid-year at 10% are worth 104.88 + 104.88 at the end of 2025.
    rate = implied_rate(schedule["years"], Decimal(231), Decimal("-21.2382"), date(2025, 12, 31))
    assert rate == pytest.approx(0.10, abs=1e-4)


def test_what_cannot_be_rolled_is_none_never_a_guess():
    partial = {"as_of": AS_OF, "years": {"2026": Decimal(70428000)}}
    for schedule, totals, end in ((None, TOTALS, END), (FILED, None, END), (FILED, {}, END), (partial, TOTALS, END),
                                  ({**FILED, "as_of": date(2026, 6, 30)}, TOTALS, END), (FILED, TOTALS, AS_OF),
                                  (FILED, {"total": Decimal(5), "interest": Decimal(1)}, END),
                                  (FILED, {"total": Decimal("1059176000"), "interest": Decimal(0)}, END)):
        assert roll_schedule(schedule, totals, AS_OF, end) is None


def test_new_leases_give_rent_and_a_liability_with_a_low_and_a_high():
    new = roll_new_leases([LEASE], AS_OF, END, 0.0667)
    assert new["annual_run_rate"] == Decimal("266230450")       # 2,955.158M over 11.1 years
    rent, owed = new["rent"], new["liability"]
    # Nothing is paid if every lease starts after the period end is impossible here; the least is a start in June 2028.
    assert rent["low"] == 0 and rent["low"] < rent["central"] < rent["high"]
    assert rent["high"] == Decimal(round(266230450.45 * (END - date(2026, 11, 1)).days / 365))
    assert owed["low"] == 0 and owed["central"] > 0 and owed["high"] < Decimal("2955158000")
    assert roll_new_leases([LEASE], AS_OF, END, None)["liability"] is None


def test_a_window_that_closes_before_the_period_end_has_every_lease_paying():
    early = {**LEASE, "commencement_start": "2026-11", "commencement_end": "2026-12"}
    rent = roll_new_leases([early], AS_OF, END, 0.05)["rent"]
    assert rent["low"] > 0 and rent["low"] < rent["central"] < rent["high"]


def test_a_company_with_no_leases_awaiting_commencement_or_unreadable_ones_gets_none():
    for leases in (None, [], [{}], ["x"], [{**LEASE, "as_of": "2026-06-30"}], [{**LEASE, "unit": "EUR"}],
                   [{**LEASE, "weighted_average_term_years": "0"}], [{**LEASE, "commencement_end": "2026-01"}],
                   [{**LEASE, "undiscounted_amount": "n/a"}]):
        assert roll_new_leases(leases, AS_OF, END, 0.05) is None
