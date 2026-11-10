# Decision-basis repair: evidence (run d58117ef)

Plan: `docs/superpowers/plans/2026-11-10-decision-basis-repair.md`. Base: `237930f9`.
Proof tool: `docs/reviews/decision-basis-repair-proof-tools/replay.py`; output in `replay-results.txt` beside it.
No network or model call was made.

## What changed

| Task | Change | Files |
|---|---|---|
| 1 | A case named by an accepted audit finding stays in the manager's priced list and in the displayed range, carrying the finding ids. The manager's own accept/reject entry decides whether it is in the weighted range. | `agents/scenario_decision.py`, `agents/decision_context.py`, `agents/shared_valuation.py`, `agents/output_validation.py` |
| 2 | The operational finding states the specific problem with the manager's answer, and separates "answer unusable" from "rating points away from its own weighted value without a reason". | `operational_audit.py` |
| 3 | The change note uses the same reader wording as the decision card. A reconsideration trigger read for the first time and found not met is not listed as a change. Older saved records, which hold only the status word, print "comparison not satisfied" instead of "breached". | `agents/decision_brief.py` |
| 4 | Each decision-card statement is its own paragraph; consecutive list items stay one list. | `agents/decision_context.py` |

## Replay of run d58117ef (ran)

| Item | Saved report | New code |
|---|---|---|
| Scenario decision | unaddressed | addressed |
| Weights | "sum to 0.15" | 0.55 / 0.30 / 0.15 |
| Accepted range | none | 42.93 to 103.25 USD/share |
| Weighted value | none | 70.84, -9.5% against the 78.30 close |
| Direction | none | near (inside the 10 percent band) |
| Rating check | none | rating does not point against the accepted scenarios |
| Flags | cases removed | base flagged by 2 findings, downside by 1, both shown |
| Displayed case range | 103.25 alone, "close is below" | 42.93 to 103.25, close within |
| Supported scenarios | 1 | 3 (2 flagged) |
| Operational score | 3/5, decision basis unaddressed | 5/5, no finding |
| Condition change note, recomputed from the prior record | three "unobserved to breached" | "15 tracked, none changed status" |

The HTML report for the saved run was rendered with the new code: the accepted range, rating check, change notes,
basis and valuation availability each render as separate paragraphs, and "below the conditional value" is absent.

## Replays of the five 2026-11-09 runs (ran)

Operational scores are unchanged on all five (4, 3, 5, 3, 5). None of them was asked the scenario question, so
their scenario decision is "not applicable" or "no priced cases". One of them (2a2e47dd) has a flagged case that now
appears in its displayed range (44.86 to 74.86) instead of being left out.

## Checks

- Full suite: 4,363 passed, 10 skipped, 1 deselected.
- `ruff check .`: clean.
- New tests: flagged weights kept and printed; a rejected flagged case leaves the range and the remaining weights
  must still sum to 1; the manager is told a finding does not remove a case; a first not-met reading is not a change
  and the stored word is never printed; card statements are separate paragraphs; the audit message names the problem.

## Plan adjustments

1. **Price-target statement corrected.** The plan said a flagged case can never become a published price target and
   that an existing block enforces this. That was wrong. The existing behaviour, pinned by an existing test, is that
   a case the manager adopts as its target keeps its calculated value and is printed under "Disputed PM-adopted
   calculation … not validated fair value". This build does not change that path. Only the words "excluded from
   conditional range" were removed from that notice, because the case is now shown in the range.
2. **Direction is "near", not "below".** The weighted value is 9.5 percent under the close and the existing
   threshold is 10 percent. No threshold was changed.
3. **No separate change to what the managers are shown.** Their condition list already used the reader wording; the
   raw word reached them only through the change note, which Task 3 fixes.
4. **Stored history check.** The word "breached" is written and read only in `memory/thesis.py`. The outcome
   tracker (`memory/publication_outcomes.py`) does not read condition statuses, so no stored outcome data is affected.
5. **Fallback wording for older records** added (not in the plan) so a re-rendered older report does not print the raw word.

## Tests whose expectations changed

They pinned the rule this plan replaces:
- `tests/test_disputed_case_range.py`: three tests now expect the flagged case in the range and in the count; the
  adopted-case test no longer expects the words "excluded from conditional range".
- `tests/test_scenario_decision.py`: the priced-case test now expects the flagged case to be listed with its flag.
- `tests/test_shared_valuation.py`: summary wording "flagged (…), shown in range".
- `tests/test_decision_brief.py`: the change row now carries the two reader labels.

## Known effects and limits

- "Supported scenarios" now counts flagged cases, with the flagged number beside it. The executive summary reads the
  same count.
- Older reports re-rendered with this code show "flagged" where they showed "excluded". Saved evidence snapshots are
  not rewritten.
- Not verified by a live run: that a future manager answer again weighs every case. The replay proves the saved
  answer is now accepted; it cannot prove the next model reply.

## Deferred

- Lease interest and rent on leases that start inside the case period, in the case arithmetic.
- A computed reference multiple.
- A shorter path for runs where price and filings are unchanged.
- Whether a flagged case should be barred from adoption as a price target (see adjustment 1).
