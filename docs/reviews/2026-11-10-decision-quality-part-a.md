# Decision-quality Part A: evidence

Plan: `docs/superpowers/plans/2026-11-10-decision-quality-next-step-plan.md`, Part A. Base `b7c26758`.
Proof source: saved run `7822a890` (2026-11-10), replayed and re-exported with no model call.

## What changed

| Item | Change | Where |
|---|---|---|
| A1 | The in-run auditor now receives, per case, what code computed: the same-basis history line, the funding line and the guidance-floor line (`computed_by_code`, each capped at 1,500 characters), and is told a claim restating it is supported. | `audit_pass.py` |
| A2 | One description of how the multiple is applied ("applied at the period end to that period's revenue") replaces "forward from the analysis date" / "trailing at the future valuation date" in the stored case, the case card, the decision card and the analyst prompt. Ranges for cases given different period words stay separate, as before. | `valuation_cases.py`, `shared_valuation.py`, `decision_context.py`, `fundamentals_analyst.py` |
| A3 | A stated finance-payment total within 0.1% of the filing's schedule counts as stated. Both figures are still recorded. | `valuation_cases.py` |
| A4 | A Trader "Sell" under an Underweight research recommendation reads "Reduce" (and "Buy" under Overweight reads "Add") in the Trader text the risk analysts see and on the decision card. The stored action is unchanged. | `case_reference.py`, `trader.py`, `decision_context.py` |
| A5 | The two fixed "qualitative only" sizing sentences now say no allocation is published and that a sizing ratio is arithmetic on the accepted cases. | `output_validation.py` |
| A6 | Each case's revenue forecast is stated against the guidance-floor arithmetic (above, at, or below, by how much). A note only; it never rejects a case. Withheld when any input is missing or the periods do not line up. | `case_reference.py`, `shared_valuation.py`, `scenario_decision.py` |

## Replay of run 7822a890 (ran)

| Expected | Result |
|---|---|
| Funding "assessed" on all three cases | Assessed on all three (schedule 320,453,000; stated 320,428,000). "Funding partial" appears 0 times in the re-export; "Funding assessed" 12 times. |
| Auditor input carries the reference lines | All three case items carry `computed_by_code` with the same-basis line (low 4.84x, median 7.84x, high 16.46x), funding and floor lines. |
| Trader line reads "Reduce" | Trader text: "Reading of this action: Reduce (the Trader's Sell under the research rating Underweight)". Decision card prints the same reading. |
| Base case carries the floor note | Base 1.930B is 0.14% below the 1.9328B floor; downside 12.04% below; upside 6.06% above. |
| Old case label gone | "forward from the analysis date" 0 times; the new description 14 times. |

The re-export scores 3/5 operationally for the known reason that a saved executive summary cannot be
reused in a re-export ("The executive summary is unavailable"). It is not a Part A effect.

## Found during proof and fixed

The first replay printed no "Reduce" reading: the Research Manager's plan labels its call
"Recommendation", not "Rating". The reading now uses the plan's Recommendation line (falling back to a
Rating label), and gives no reading when two different recommendations appear.

## Existing tests changed

| Test | Why |
|---|---|
| `test_case_valuation.py::test_trailing_at_future_date_never_rendered_or_pooled_as_forward` | Asserts the new single description; still asserts the two cases are not pooled into one range. |
| `test_portfolio_sizing.py::test_the_fixed_qualitative_sentence_...` | Pins the reworded sentences. |
| `docs/reviews/valuation-build2-proof-tools/live_cli.py` | Independent recomputation expects the new description. |
| `docs/reviews/valuation-build2-proof-tools/continue_cli.py` | The historical checkpoint drill compares a saved record with today's replay; it now sets aside the label wording and the new floor note, as it already does for the funding and history fields. Everything else must still match exactly. |

## Verification (ran)

- New tests: `tests/test_decision_quality_part_a.py`, 14 tests (3 added at audit closure).
- Full suite and lint: see the commit message for the counts on the committed tree.

## Independent audit (654a6569) and closure

Three Medium findings, no Critical or High. Each was reproduced with a failing test, then fixed.

| Finding | Reproduced | Fix |
|---|---|---|
| F1. The prompt told the auditor to cite a case ID as the evidence label, but the validator rejected case IDs as unknown labels, so such a finding was discarded. | Yes (ran) | Case IDs established on replay are accepted as evidence labels; an invented ID is still rejected. |
| F2. The plan said to stop asking the analyst for the period word if it is only a label; it was still required. | Yes (ran) | The analyst is no longer asked. The field defaults to its old value, so saved requests replay with the same case ID and price. |
| F3. The Reduce/Add reading was missed when the Trader's free-text fallback used "FINAL TRANSACTION PROPOSAL" instead of "Action". | Yes (ran) | The reading follows every label the fallback accepts; two different actions give no reading. |

After closure: 4,445 passed, 10 skipped; lint clean.

## Not proven

- A1's effect on the auditor model's findings needs a live run. Offline proof shows only that the
  input now contains the lines.
- No paid model call was made.

## Deferred

- Saved runs whose cases used different period words keep separate ranges, as before. New runs no longer
  produce the second word.
- `assumption_history.py` still prints the stored period word in assumption-change text.
- `docs/reviews/decision-inputs-proof-tools/replay.py` still prints a check for the old sizing sentence
  (a historical script, not run by any test).
