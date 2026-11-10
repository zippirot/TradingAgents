# Case stability: evidence

Plan: `docs/superpowers/plans/2026-11-10-case-stability-plan.md`. Base `4ee1cb7e` (staging and launcher).
Proof source: saved run `36c26c9d` (2026-11-10 12:50), replayed with no model call
(`docs/reviews/case-stability-proof-tools/replay-results.txt`).

## What changed

| Item | Change | Where |
|---|---|---|
| 1 | The fundamentals analyst is shown its cases from the last publication and the filings retained since, with the rule: keep each value unless a new fact changes it, and name the fact. | new `agents/prior_cases.py`; `graph/setup.py` (`_with_prior_cases`); `analysts/fundamentals_analyst.py` |
| 1 | When cases changed and no new filing was retained, the brief says so to the manager and the reader. | `agents/decision_brief.py` |
| 2 | The rating check also fires inside the 10% band when a bearish rating sits on cases returning more than the required return, or a bullish one on cases returning less. Same single resubmission; the card states the basis. | `agents/scenario_decision.py`, `agents/schemas.py` |
| 3 | A case named by an accepted finding about another role's statement carries a note saying its inputs and arithmetic are not disputed; it is not counted as a flagged scenario. Findings about the case's own inputs keep the existing wording. Range treatment is unchanged. | `agents/shared_valuation.py`, `agents/decision_context.py`, `agents/scenario_decision.py` |

## Replay of run 36c26c9d (ran)

| Check | Result |
|---|---|
| Rating check | Underweight, weighted value "near" the close, return gap +5.9 points: now "points against the accepted scenarios, which return more than the required return and no reason was given". The resubmission text states +15.7% a year against 9.86%. |
| Flag on the downside case | "corrects a statement the bear researcher made about this case; its inputs and arithmetic are not disputed". |
| What the next run's analyst is shown | Earlier decision 36c26c9d; no new filing; multiples carried 6.0 / 4.0 / 8.0; 9,572 characters of prompt text. |

## Not proven
- Whether the analyst model keeps the carried values. That needs a live run. No paid call was made.
- The saved run would now score 3/5 operationally if re-published, because its rating has no stated
  reason under the tightened check. A new run gets the one resubmission to supply it.

## Effects to know
- The analyst prompt grows by about 10,000 characters when an earlier decision exists.
- A first run for a company has nothing to carry and is unchanged.

## Verification (ran)
- `tests/test_case_stability.py`: 9 tests.
- Full suite 4,455 passed, 10 skipped; lint clean (before the audit).
