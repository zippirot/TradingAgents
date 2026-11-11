# Funded case model, Stage 1: evidence

Plan: `docs/superpowers/plans/2026-11-10-funded-case-model-plan.md` (Stage 1 only). Base `f17e04f8`.
Proof source: saved run `6fe6324b`, repriced with no model call
(`docs/reviews/funded-case-proof-tools/replay-results.txt`).

## What changed

| Item | Change | Where |
|---|---|---|
| Lease arithmetic | A filed payment schedule is split into interest and principal at the rate the schedule itself implies; leases awaiting commencement give rent paid and the amount still owed at the period end, with a low and a high. Three stated assumptions, named in the module. No company in the code. | `agents/lease_roll.py` |
| Cash completed by code | Two optional answers on a case's capital: is operating cash after lease interest, and does it include rent on leases that commence. Interest counted twice is added back; rent left out is deducted. Unanswered, the case prices exactly as before and the questions stay open beside it. | `agents/valuation_cases.py` (`funded_cash`, `price_case`, `funding_limit`) |
| Lease-inclusive values | The finance-lease balance is carried to the period end on the filed schedule when the schedule reproduces the filed balance (within 0.1%); operating leases stay as filed plus what leases commencing in the period will still owe. Otherwise held as filed, as before. | `agents/shared_valuation.py` (`_rolled_leases`) |
| Analyst instructions | Asks for the two answers; says code completes cash; removes the stale line "Funding feasibility remains unassessed". A carried case may answer them without that counting as a change. | `analysts/fundamentals_analyst.py`, `agents/prior_cases.py` |

## Replay on DOCN's saved cases (ran)

| Reading | Base | Downside | Upside |
|---|---|---|---|
| As saved (neither question answered) | 101.17 | 59.14 | 141.53 |
| After interest: yes; includes new rent: no | 100.80 | 58.79 | 141.16 |
| After interest: yes; includes new rent: yes | 101.70 | 59.64 | 142.07 |
| After interest: no; includes new rent: no | 100.26 | 58.28 | 140.63 |

Filed schedule: implied rate 6.67% a year; 320.5M USD paid through 2027, of which 64.3M interest and 256.2M principal.
New rent through 2027: 108.7M USD central, 0 to 310.0M across the commencement window.

Lease-inclusive values, base case: with finance leases 93.50 to 95.62; with all leases 87.96 to 78.63. The second
now counts 1,379M USD still owed at the period end on leases commencing in the window (0 to 2,042M).

## Effects to know
- On the main (borrowings-only) values the change is under one dollar a share. The larger movement is in the
  all-leases value, which now sits below the 2026-11-10 close of 79.52 for the base case. It rests on the three
  stated assumptions and on a classification the filing does not give.
- Lease-inclusive values change for every run from installation, answered or not. Main values change only when the
  analyst answers the questions.

## Not proven
- Whether the analyst answers the two questions, and sensibly. Needs a live run. No paid call was made.
- Real filings of a second company: only DOCN passes the source checks today. Other shapes are covered by
  made-up inputs in `tests/test_lease_roll.py` and `tests/test_funded_cash.py`.

## Verification (ran)
- `tests/test_lease_roll.py` (7), `tests/test_funded_cash.py` (8). Full suite: 4,499 passed, 10 skipped. Lint clean.
