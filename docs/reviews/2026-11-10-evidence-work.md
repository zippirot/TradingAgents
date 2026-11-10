# Evidence work (Part D2, D3) and Reddit key support: evidence

Plan: `docs/superpowers/plans/2026-11-10-evidence-work-plan.md`. Base `0fe86cc4`.

| Item | What was built | Proof |
|---|---|---|
| Reddit key | With `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` set, the search runs through Reddit's API (public posts only). Without them, the public feed as before. | `tests/test_reddit_api_key.py` (4). Not proven against live Reddit: no key exists yet. |
| D2 | The scorecard places each settled close at 21 and 63 sessions below, inside or above the range the decision accepted, and above or below its weighted value, both carried to the exit date at the decision's stated required return. | `tests/test_scorecard.py` (4 new). On the real store: 0 rows, nothing has settled. |
| D3 | `python -m tradingagents.screen TICKER...`: source collection and the seven required source checks, no model. | `tests/test_screen.py` (2); live run below. |
| Fix found by D3 | The source step crashed (`KeyError: 'disclosure_evidence'`) when excerpt packages conflicted and an RPO comparison existed. Seven of sixteen companies hit it. | Failing test first, `tests/test_shared_source_brief.py`. |
| Arithmetic check | A stated percentage that its sentence's own two figures do not give is noted at the end of the analyst's report, by code. | `tests/test_arithmetic_check.py` (7). On the saved reports of the five runs of 2026-11-10 it flags one sentence: the market analyst's "about 43% below the 2026-10-13 close" in run 6fe6324b (the closes give 38%), which the paid auditor also found. One false alarm seen during the build ("below the 200 SMA") is excluded and tested. |

## Screen result, 2026-11-10 (ran; free SEC and price requests only)
Sixteen mid-sized US software and cloud companies. One passes: DOCN. Full output:
`docs/reviews/evidence-work-proof/screen-2026-11-10.json`.

Most common reasons a company stops: obligation category missing with no sourced zero; lease or
equipment principal payments not found; equity-movement table not found; conflicting document metadata;
filing text over the 120,000-character package limit. These are the causes recorded for MSFT and CAT
in the large-filer plan (on hold); the screen shows they are not limited to very large filers.

## Limits
- D2 uses the same sample rules as the scorecard: only the first decision of a day counts. Of the saved
  DOCN decisions, the only primary one with a scenario record (d58117ef) did not have an accepted range,
  so the first placed result needs a future first-of-day run to reach 21 sessions.
- A split or dividend between the decision and the exit is not reconciled in D2.
- The arithmetic check reads two sentence shapes only; it would not have caught the CPI annualisation slip in the same run.
- The screen leaves out the one required check that reads a model's report.

## Verification (ran)
Full suite at the final commit: 4,484 passed, 10 skipped. Lint clean.

## Independent audit (GPT-6 Astra, run 972a7a03, $0.42)
Two medium findings, both in the arithmetic check, both reproduced with a failing test and fixed.

| Finding | Fix |
|---|---|
| A sentence with two subjects ("80 is 20% below 100, while 60 is 40% below 100") used the first subject for both and "corrected" a right figure | A sentence with more than one subject is left alone |
| A dated figure with a unit ("128.21M on 2026-10-13") was read as that day's close | Unit-bearing figures are never closes and make the date ambiguous; only the listing forms "DATE: value" and "value (DATE)" are read |

No finding on the Reddit key path, the range scoring, the screen or the crash fix.
