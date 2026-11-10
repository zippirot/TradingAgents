# Decision-quality Part B: evidence

Plan: `docs/superpowers/plans/2026-11-10-decision-quality-next-step-plan.md`, Part B. Built on Part A
(`6e6d195d`). Proof source: saved run `7822a890`, replayed with a constructed manager answer. No model call.

## What was built

The Portfolio Manager's existing call gains one field, `event_view`. Nothing else is asked of any model.

| Step | Behaviour | Where |
|---|---|---|
| Asked when usable | Only when at least two cases are priced, a required return is recorded and the earlier decision left open conditions. The prompt lists those conditions by ID and states the horizon date. | `portfolio_manager.py`, `event_view.render_for_manager` |
| The answer | One to three events: condition ID, expected date, which result is favourable, the case weights held after the favourable and after the adverse outcome, a reason. | `schemas.py` |
| Checks | The condition is open in this run; the date is after the analysis date and inside the horizon; each weight set names every accepted case once and sums to 1; the favourable set is worth more than the adverse set. | `event_view.assess` |
| Arithmetic | Each accepted case is brought back from its period end to the horizon date at the required return. Each weight set is priced and compared with the close. | `event_view.assess` |
| Implied odds | Where today's weighted value sits between the adverse and favourable values. Outside 0 to 100% means the three sets disagree. | `event_view.assess` |
| One correction | An unusable answer is sent back in the existing single resubmission, together with any rating correction. No extra call. | `scenario_decision.retry_feedback` |
| Score | Still unusable after that: operational score 3 (`event_view_unaddressed`). Runs that were not asked are not judged. | `operational_audit.py` |
| Report | A paragraph and one line per event on the decision card. | `event_view.render`, `scenario_decision.render` |
| Later runs | The "since the last decision" block states which outcome occurred, the weights the earlier decision said it would then hold, and the weights held now; or that an event is overdue. | `decision_brief.py`, `decision_context.py` |

## Replay of run 7822a890 (ran; output in `event-view-proof-tools/replay-results.txt`)

The answer used is constructed for the proof. No saved run contains a real one.

| Check | Result |
|---|---|
| Saved run as it is | Not asked, not judged (`not_applicable`). |
| What the manager would be shown | 12 open conditions by ID; horizon date 2027-05-10. |
| Today's weights (50 / 30 / 20) at the horizon | 68.19, -12.9% against the 78.30 close. |
| Q4 revenue at or above the guidance low, by 2027-02-25 | 75.37 (-3.7%) if favourable; 56.71 (-27.6%) if adverse; today's weights imply about 62% favourable. |
| Notes settlement disclosure, by 2026-12-15 | 69.60 (-11.1%) if favourable; 63.89 (-18.4%) if adverse; about 75% favourable. |
| Inconsistent answer | Sent back with the figures: today's 68.19 lies outside the 56.71 to 61.00 the two sets give. |
| Missing answer | Reported; score 3 if not corrected. |

## Design choices made at build time

- **Odds from values, not weights.** With three cases the weights alone do not give one number. The
  implied odds are taken on the weighted value at the horizon, the same quantity the reader is shown.
- **The horizon is the configured one** (six months from the analysis date), not a horizon the manager
  overrides in prose.
- **A list, not a table.** The decision card separates lines into paragraphs, which breaks tables.
- **Not asked with fewer than two accepted cases**, or when a case's period ends before the horizon
  date: the weights could not move or the value could not be stated.

## Limits

- **Follow-through is automatic only for measured conditions** (a reported metric or a price level).
  Conditions written as events, such as the notes settlement disclosure, are never read as resolved by
  code today, so they show as pending and then overdue. "Favourable if met" is also the manager's own
  reading for such a condition.
- **The manager's behaviour is unproven.** Whether the model fills the field well, and whether the
  events it picks are the decisive ones, needs a live run. No paid call was made.
- The first run for a company has no earlier conditions, so it is not asked.

## Verification (ran)

- `tests/test_event_view.py`: 35 tests (arithmetic, every check, the manager call and its one
  correction, the score, the later-run follow-through).
- Full suite and lint on the committed tree: see the commit message.
