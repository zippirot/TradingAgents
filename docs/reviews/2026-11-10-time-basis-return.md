# Build 1, time basis and return: evidence

Plan: `docs/superpowers/plans/2026-11-10-decision-quality-gap-plan.md` (Build 1). Base: Build 3 at `425ff70a`.
Proof tool: `docs/reviews/time-basis-return-proof-tools/replay.py`; output in `replay-results.txt` beside it.
No network or model call was made.

## What changed

| Plan item | Change | Files |
|---|---|---|
| 1 Required return | Delivered in Build 3; reused. | |
| 2 Value today and yearly return | Each priced case states its yearly return from the dated close to its period end, beside its period-end value and value today. | `agents/scenario_return.py` (new), `agents/scenario_decision.py` |
| 3 Rating check on one time basis | When a required return is recorded, direction and the rating check use the weighted value today against the close. The card also states the weighted case's yearly return against the required return. Without a required return the check stays on period-end values, as before. | `agents/scenario_decision.py` |
| 4 Where the return comes from | Per share, each case's change from the close is split into revenue, the multiple, and shares and net obligations, applied in that order so the parts sum exactly. Today's multiple is the price-implied multiple of the last twelve months' revenue on the case's own obligation basis. | `agents/scenario_return.py`, `agents/scenario_decision.py` |
| 5 How sturdy the call is | The value today under equal weights, and the weight the highest accepted case would need for the weighted value today to equal the close. | same |
| Manager's input | The Portfolio Manager is shown each case's value today and the required return, and is told the check uses values today. Only when a required return is recorded. | `agents/scenario_decision.py`, `agents/managers/portfolio_manager.py` |

Not changed: the 10 percent direction threshold, the rules for which ratings owe a reason, the weights
rule, operational scoring, case arithmetic.

## Replay of run d58117ef with the run's own yield, 4.86% plus 5 points (ran)

| Item | Period-end basis (before) | One time basis (now) |
|---|---|---|
| Weighted value | 70.84, -9.5% against the 78.30 close | 63.64 today, -18.7% against the close |
| Direction | near | below |
| Rating check for Underweight | not against | not against |
| Weighted yearly return against required | not stated | -8.4% against 9.86%, a gap of -18.3 points |

| Case | Yearly return from the close | Revenue | Multiple | Shares and net obligations | Total |
|---|---|---|---|---|---|
| Base | -1.2% | +58.84 | 8.19x to 4.70x: -57.68 | -2.24 | -1.08 |
| Downside | -40.9% | +41.48 | 8.19x to 3.00x: -74.79 | -2.06 | -35.37 |
| Upside | +27.4% | +65.78 | 8.19x to 6.00x: -38.04 | -2.79 | +24.95 |

Weights: with equal weights the value today is 66.90, -14.6% against the close. The upside case would
need a weight of 58%, against the 15% given, for the weighted value today to equal the close.

The same run without a required return keeps direction "near" on period-end values. The five 2026-11-09
runs keep their scenario status and operational scores (4, 3, 5, 3, 5) and print no time-basis line.

## Behaviour that changes for a reader

- A bullish rating on a weighted value that is "near" the close at the period end but more than 10% below
  it today now owes a reason (and the manager is asked for one on the existing single retry). Covered by a test.
- Re-exported older runs gain the yearly-return figure per case and, where the saved run holds the
  price-implied valuation, the return-parts block. Both are arithmetic on saved data.

## Checks

- Full suite at the audited commit: 4,409 passed, 10 skipped, 1 deselected; after closure 4,411. `ruff check .`: clean.
- New tests (`tests/test_scenario_return.py`, 18): yearly return; check on values today with the return
  gap; a Buy that owes a reason only on today's basis; fallback to period-end values; equal-weight value
  and break-even weight including the unreachable and not-needed cases; return parts summing exactly;
  eight situations where parts are withheld; equity basis; the card block; the manager's input with and
  without a recorded return; a rejected case.
- One Build 3 test expectation was updated: direction for the saved run is now "below" on values today.

## Plan adjustments

1. **Today's multiple is stated on trailing revenue.** The plan said "change in the multiple from what
   today's price implies". A case applies its multiple to revenue of the twelve months ending at its period
   end, so the like-for-like figure for today is price-implied enterprise value over the last twelve
   months' revenue (8.19x). The split therefore reads "revenue grows, the multiple falls from 8.19x to 4.70x".
2. **Return parts are withheld, not approximated,** when the case cannot be rebuilt exactly from its own
   revenue, multiple, net obligations and shares, or when the price-implied valuation used another close
   or lacks the case's obligation basis.
3. **The return gap is stated only when all accepted cases share one period end.**

## Not verified

- A live run. In particular, how the manager weighs cases once it sees values today.
- Remote CI (unpushed).

## Deferred

- Build 2: like-for-like reference for the multiple, peer coverage, funding bounds.
- Build 3 item 3d: portfolio-file additions.

## Independent audit and closure (2026-11-10)

Audit of `4bc69a67` by GPT-6 Astra (run 13ca82d7, 25 turns, $0.70): two Medium findings, no High or Critical.

| Finding | Verdict | Action |
|---|---|---|
| Yearly returns and the return gap ran from the analysis date, not from the date of the close they are measured against. | Confirmed, reproduced by a new test that failed on `4bc69a67`. One day's difference on the saved run (-41.0% became -40.9%), larger when the close is older. | Fixed: per-case and weighted yearly returns run from the close's session date. Value today is still brought back to the analysis date. An undated close gives no yearly return. |
| When every case was rejected, per-case yearly returns and the return split disappeared, although each case still had everything needed. | Confirmed, reproduced by a new test. | Fixed, with one deliberate difference from the auditor's suggestion (below). |

**Where the fix differs from the suggestion.** The auditor proposed measuring each case against its own quote. An
existing rule, pinned by an existing test, is that no price comparison is printed when the accepted cases were
validated against different closes. Per-case figures therefore use one shared close: the one the accepted cases
share, or, with nothing accepted, the one every quoted case shares. A case validated against a different close,
or none, gets no figure.

Closure checks (ran): full suite 4,411 passed, 10 skipped, 1 deselected; `ruff check .` clean; replay of d58117ef
shows weighted value today 63.64, direction below, gap -18.3 points, unchanged apart from the two yearly figures above.
