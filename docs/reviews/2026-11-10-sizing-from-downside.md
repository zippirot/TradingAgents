# Build 3, sizing from the downside: evidence

Plan: `docs/superpowers/plans/2026-11-10-decision-quality-gap-plan.md` (Build 3 task list). Base: `c4aa8a40`.
Proof tool: `docs/reviews/sizing-from-downside-proof-tools/replay.py`; output in `replay-results.txt` beside it.
No model call was made. One free data request was made to FRED to confirm the yield fetch works.

## Scope decided by the user

Built: 3a required return, 3b value today, 3c sizing rule without holdings, 3e proof.
Left out at the user's instruction ("leave the portfolio file out for now"): 3d, the additions to the
portfolio-file sizing block. Nothing in the existing portfolio-file path was changed.

## What changed

| Item | Change | Files |
|---|---|---|
| 3a | At source acquisition the run retrieves the 10-year Treasury yield (FRED `DGS10`) as published by the analysis date and adds the configured premium (`required_return_premium`, default 0.05). The record is saved in run state, the run log and the evidence record. A failed or missing retrieval is recorded as unavailable; no yield is assumed. The request goes through the existing record-and-replay mechanism for outside inputs. | `agents/required_return.py` (new), `dataflows/vendors/fred.py`, `agents/evidence_validation.py`, `agents/state.py`, `reporting.py`, `graph/trading_graph.py`, `default_config.py` |
| 3b | Each priced case in the scenario summary carries its value brought back from its period end to the analysis date at the required return. Printed beside the period-end value. | `agents/scenario_decision.py` |
| 3c | From the lowest accepted case's value today: its fall from the dated close, and the largest position weight for each 1% of portfolio loss accepted. Printed on the decision card with the required return and its source. | `agents/scenario_decision.py` |

Not changed: the range, weighted value, direction and rating check still use period-end values (that is
Build 1). The Portfolio Manager's prompt is unchanged. Operational scoring is unchanged.

## Replay of run d58117ef (ran)

The saved run predates this build, so it holds no retrieved yield. The replay supplies the yield that
run's own macro section reports, 4.86% on 2026-11-06. A live fetch for 2026-11-10 returned the same
observation.

| Case | Period end (2027-12-31) | Value today at 9.86% a year | Weight |
|---|---|---|---|
| Base | 77.22 | 69.37 | 0.55 |
| Downside | 42.93 | 38.56 | 0.30 |
| Upside | 103.25 | 92.76 | 0.15 |

Sizing rule printed: in the downside case the position is worth 38.56 today, 50.7% below the 78.30 close;
for each 1% of a portfolio accepted as a loss in that case, the position can be at most 2.0% of the portfolio.

Unchanged on the same replay: weighted value 70.84, direction near, rating check consistent, operational score 5.
With no record (the run as saved) the card is identical to before this build. With an unavailable record
the card prints one line saying so and states no value today or rule.

## Checks

- Full suite: 4,383 passed, 10 skipped, 1 deselected. `ruff check .`: clean.
- New tests (`tests/test_required_return.py`): record from a retrieved yield; unusable, out-of-range or
  later-dated yields; premium bounds; no source configured; source failure; point-in-time request
  parameters; value-today arithmetic and refusals; the saved run's three values and rule; a rejected
  downside; a lowest case above the close; no record, unavailable record and corrupt record; all rejected;
  no comparable close; the record kept in the run log and evidence record; the real acquisition step
  recording it once and surviving a source failure.

## Plan adjustments

1. **3d left out** by the user.
2. **Which case sets the rule.** The plan said "the downside case the manager accepted". The code uses the
   lowest accepted value today, whatever its label, so a mislabelled or unlabelled case cannot hide the
   worst accepted outcome.
3. **The card's opening sentence** now says values today use the required return and that the range,
   weighted value and rating check still use period-end values.
4. **Checkpoints.** The new setting is part of a run's identity, like every other setting that changes
   output. A run interrupted before this build is installed will start fresh instead of resuming. The
   historical checkpoint drill (`tests/test_build2_continuation_proof.py`) lists the new setting among
   those added since its saved checkpoint, following the existing precedent for the horizon setting.
5. **A defect found by a new test and fixed before commit:** a corrupt saved record crashed the card line.
   It is now reported as unavailable.

## Not verified

- A live run end to end. The acquisition step is tested with stubbed sources; the yield fetch was
  exercised once against the real source outside a run.
- Replayed comparisons against baselines recorded before this build: the yield request is absent from
  those baselines. How the comparison reports that was not exercised.
- Remote CI (unpushed).

## Deferred

- 3d portfolio-file additions.
- Using value today in the range, weighted value and rating check (Build 1).
