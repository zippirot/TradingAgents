# Decision inputs: what changed, track record, portfolio sizing

Plan: `docs/superpowers/plans/2026-11-10-tradingagents-decision-inputs-plan.md`, decisions made by the user 2026-11-10. Base `e2db2dd6` (`staging` = `origin/staging`). Branch `claude/decision-inputs-20261110`, worktree `~/Worktrees/decision-inputs`. Not merged, pushed or installed. No paid model call was made in this build.

| Task | Commit | Change | Main files |
|---|---|---|---|
| Q2 | `5d2e83fe` | Comparison with the earlier decision no longer fails whole. A "Since the last decision" brief is built from saved records before the Research Manager; the Portfolio Manager must say what the changes mean and code checks the answer against the two ratings. | `agents/assumption_history.py`, new `agents/decision_brief.py`, `agents/managers/*.py`, `agents/schemas.py`, `agents/decision_context.py`, `agents/output_validation.py`, `graph/setup.py`, `operational_audit.py` |
| Q3 | `23581fae` | Scorecard of settled outcomes replaces the pending table in the managers' input and sits above the table in the report. Old memory shown to the managers loses sentences that put a figure on sizing. | `memory/publication_outcomes.py`, `graph/trading_graph.py`, `agents/evidence_presentation.py`, `memory/log.py` |
| Q1 | `5b92159c` | Optional portfolio inputs; auto-load of `~/.tradingagents/portfolio.json`; "Position and sizing" block for the agents and the report; the published record keeps only the file's fingerprint. | `portfolio.py`, `cli/main.py`, `default_config.py`, `agents/context.py`, `reporting.py`, `report_html.py`, `agents/output_validation.py` |

## Reconciliation with the decision-basis build (`e2db2dd6`)

The plan was written against `3e517089`. The decision-basis build had since changed the Portfolio Manager step, its schema and the decision card. Nothing in it was changed in behaviour:

- The manager's one correction attempt is shared. Feedback about the scenario cases and feedback about the change reading go back in a single second call; there is never a third.
- The change reading uses the same pattern as the scenario view: a lenient optional field on the fresh-call contract, a `change_contract` marker on the retained answer so decisions made before this build are not judged, and a score-3 finding when the answer is unusable.
- The brief reuses the decision-basis `priced_cases` reader for then-and-now case values.
- One existing fixture changed: the real-graph test `test_thesis_graph_roles` has an earlier decision on record, so its fixture manager now supplies a change reading; the test also asserts the brief reaches the manager and the page. All decision-basis tests pass unchanged.

## Verification (builder-run)

- New tests: `tests/test_decision_brief.py` (32), `tests/test_scorecard.py` (11), `tests/test_portfolio_sizing.py` (30). Each file was run against the code before its task and failed (collection error on the missing module or function, or 10 of 10 failing for the scorecard), then passed.
- Full suite on the final tree: see "Final state" below. `ruff check .` clean.
- Offline replays, `docs/reviews/decision-inputs-proof-tools/replay.py`, outputs beside it:

| Replay | Input | Result |
|---|---|---|
| `changes` | saved runs eea86100, 86aa515f, c463bdac against the real publication store, read only | The two runs whose saved comparison said "unavailable (ValidationError)" now compare. Each run gets a brief: earlier decision time and rating, price then and now with the stale flag, no new filing, condition changes, case values then and now. |
| `record` | real outcome store, read only; a temporary copy with every 5-session window settled by hand-made prices; real memory log, read only | Real store: no settled outcome, 20 windows pending. Settled copy: DOCN Underweight, 5 sessions, 4 calls, 4 of 4, -6.00%, "too few to conclude". Real 2026-10-19 memory entry no longer carries "30-35%"; one withheld note. |
| `sizing` | saved run c463bdac with `sample-portfolio.json` (made-up holdings) | Block for the agents and for the report at the 2026-11-09 close of 78.30 USD; Markdown and HTML carry it; the published decision text and evidence snapshot contain the fingerprint and none of the inputs or computed figures; with no file the fixed sentence is present and there is no block. |

Reproduced first, as the plan required: `assumption_changes` against run 86aa515f. The cause was not an unreadable case but a retained case whose `capital.obligations.borrowings` entry had no `assumption` label (the defect the 86aa515f repair fixed for pricing). The comparison validated the raw request strictly, so one case failed the whole comparison.

## Plan adjustments

- **Base.** Built from `e2db2dd6`, not `3e517089`; see the reconciliation above.
- **Q2 cause and fix.** A case retained without the label is compared as an estimate, the same way it is now priced. Any other unusable case is named and only that case is left out; while a case is unusable on either side, "added" and "dropped" rows are not printed, because a case missing for being unreadable is not evidence it was added or dropped.
- **Q2 timing.** The brief is built once, before the Research Manager, from the cases as the analyst submitted them. A revision the Research Manager then makes is not in the brief; the decision card's existing "Changed since" rows still reflect the final cases.
- **Q2 earlier decision.** "The last decision of any earlier run" means the last publication that carried a rating. A run that ended in REVIEW is not a decision to compare with.
- **Q2 condition noise.** A condition going from "unobserved" (new when first proposed) to "unknown" (not yet reported) is not listed as a change.
- **Q2 rule detail.** Same rating with "weakens" is allowed (the case got weaker but not enough to move the rating). Same rating with "reverses" is rejected. A different rating must be "weakens" or "reverses".
- **Q3 Hold.** Hold has no direction, so it is counted and averaged but not scored right or wrong.
- **Q3 memory filter.** The existing numeric-sizing filter drops every sentence containing a percentage or a currency amount. Applied to a whole past decision it would remove the evidence ("revenue grew 39.87%"). The memory view therefore drops a sentence only when it both states a figure and speaks of sizing (weight, allocation, position, exposure, stake, trim, hedge, remainder, residual, or a "-size" word). On the real 2026-10-19 entry it removes eight sentences: the allocation, the trim and hedge levels and the legacy margin gates; the thesis text stays.
- **Q3 empty case.** With no recommendation on record the scorecard adds nothing.
- **Q1 daily range.** The retained price observation holds daily closes only, no highs and lows. The block uses one average daily move, the mean absolute close-to-close change over 14 sessions, and says so. With fewer than 15 retained closes it says the figure is unavailable.
- **Q1 "at standard".** Within 5 percent of the standard weight counts as at standard; the block states this.
- **Q1 wording.** The gap to a rating's weight reads "about N units more (or fewer) than you hold", not "buy" or "sell".
- **Q1 amounts setting.** `"show_amounts": true` in the file.
- **Q1 where the block lives.** It is computed when the report is prepared and placed above the decision in Markdown and HTML. It is not written into the canonical decision text or the decision card, which go into the published record; those carry a one-line pointer with the fingerprint.
- **Q1 Trader figures.** The Trader's own numeric sizing is still withheld. The computed block is the only sizing figure the system states.
- **Q1 auto-load scope.** The analysis command only. The backtest keeps its explicit `--portfolio`, since a current book applied to past dates would mislead.
- **Q1 checkpoint signature.** `portfolio_path` is excluded from the run signature like the other file locations; the file's contents already enter it through the fingerprint. A file with none of the new fields keeps the fingerprint it had.

## Deferred

- **Settlement confirmation.** The first 5-session result for the 2026-11-05 decision matures about 2026-11-12. Check after that date that a normal run records it. Not done; it cannot be done yet.

## Known limits

- Not proven without a paid run: how the managers word the change reading and use the sizing block and scorecard.
- The agents see the sizing block, and their own prose is retained in the run's local diagnostics. If a model repeats a figure from the block, that sentence is in the local evidence file. The system itself writes only the fingerprint.
- The 2026-10-19 result (+6.9 percent) exists only in the legacy memory log, not in the outcome store, so the scorecard says no call has settled while the memory entry shows that result.
- The scorecard counts overlapping windows and same-ticker calls as separate calls, as the outcome table does; the "too few to conclude" line is a count threshold, not a significance test.
- A position's loss is computed for the units held now, not for the units a rating would imply.
