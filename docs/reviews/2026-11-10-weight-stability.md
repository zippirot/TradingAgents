# Weight stability: evidence

Plan: `docs/superpowers/plans/2026-11-10-weight-stability-plan.md`. Base `89f4e502` (staging and launcher).
Proof source: saved runs `36c26c9d` and `b9dde628`, replayed with no model call
(`docs/reviews/weight-stability-proof-tools/replay-results.txt`).

## What changed

| Item | Change | Where |
|---|---|---|
| 1 | The since-last-decision record carries the earlier decision's case weights. The manager's prompt lists them with the rule to keep each unless a new fact changes it. | `agents/decision_brief.py` (`_case_weights`, `render`) |
| 1 | The decision card shows earlier and current weights, matched by role (else by name), and labels a change when no new filing was retained. Unmatched case sets are shown without a change claim. | `agents/decision_brief.py` (`attach_weights`), `agents/decision_context.py` |
| 2 | A finding linked to a case disputes it only when it quotes the case's own inputs; a statement by any known role, the fundamentals analyst included, is worded as a corrected statement and not counted as a flagged scenario. | `agents/shared_valuation.py` |

## Replay (ran)

| Check | Result |
|---|---|
| Card of run b9dde628 against 36c26c9d | "Case weights: base 50%, downside 35%, upside 15% then; base 45%, downside 45%, upside 10% now. Weights changed and no new filing was retained between the two runs. Where no new fact is named for a change, the earlier weight remains the reference." |
| What the next run's manager is shown | "Your case weights in that decision: base 45%, downside 45%, upside 10%. Keep each weight unless a fact that is new since that decision changes it…" |
| Base case flags in b9dde628 | Both findings now read as corrected statements (conservative risk analyst, fundamentals analyst); flagged scenarios counted: 0. |

## Not proven
- Whether the manager keeps the carried weights. That needs a live run. No paid call was made.

## Effects to know
- If the manager keeps 45 / 45 / 10, the rating check passes as it did in run b9dde628. If it moves the
  weights it must name a new fact, and the card says so when no filing is new.
- There is no send-back for a changed weight; the label is the consequence.

## Verification (ran)
- `tests/test_weight_stability.py`: 7 tests.
- Full suite and lint on the committed tree: see the commit message.
