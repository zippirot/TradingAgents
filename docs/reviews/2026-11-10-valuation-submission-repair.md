# Build R: valuation submission check-and-retry

Plan: `docs/superpowers/plans/2026-11-10-tradingagents-valuation-submission-repair-plan.md`, approved 2026-11-10 (one real correction call approved; a successful correction scores 5). Base `242582db` (`origin/staging`). Branch `claude/valuation-repair-r-20261110`, worktree `~/Worktrees/valuation-repair-r`. Not merged, pushed or installed.

| Task | Change | Files |
|---|---|---|
| R1 | A submission that fails as a whole gets its own sentence and a `submission_error` kind (`unreadable`, `missing_block`, `duplicate_block`, `oversized`, `duplicate_names`, `too_many`). Invalid JSON reports the parser message and the nearby text. A field beside `name` and `request` is named. Which submissions are accepted is unchanged. | `agents/shared_valuation.py` |
| R2 | `prepare_with_correction`: when the block is unreadable or any case is rejected, the analyst's own model gets the original block, the exact reasons and the required shape, once. The corrected cases pass the same validation and replace the original only if they price more cases and leave every already-priced case identical. Each corrected case carries a note. The correction is saved with a hash of the report it belongs to, so every later replay (research manager, decision card, audit, publication) prices the corrected cases. A model error or a bad correction leaves the original record with a stated reason. Called from the Evidence Check step. | `agents/shared_valuation.py`, `graph/setup.py` |
| R3 | An unreadable, uncorrected block scores 3. A successful correction keeps 5 and is listed under "Recovered issues" in the operational audit. | `operational_audit.py` |

## Verification (builder-run)

- `tests/test_valuation_repair.py`: 30 tests. The first 25: 17 failed against the unchanged code plus a stub. The 5 added for the audit findings failed before their fix. All pass.
- Full suite on the final tree: 4196 passed, 10 skipped, 1 deselected. `ruff check .` clean.
- Offline replay, `docs/reviews/valuation-repair-proof-tools/replay.py`, output in `replay-results.txt`:
  - Runs `2a2e47dd` and `86aa515f`: both submissions now price as written on current code (Builds W and Z), so no correction is attempted.
  - Run `c463bdac`: as submitted, "Valuation block is not valid JSON: Expecting ',' delimiter near ...". With a stub returning a correct block: one call, case priced at 74.16 USD/share, correction note, score 5. With a stub returning the same bad block: original record, "Correction attempt did not produce an accepted case.", score 3.
- One real call, approved by the user: the rejected `c463bdac` block sent through `prepare_with_correction` to the run's quick model (`anthropic/claude-opus-5.5` on OpenRouter). The model returned a corrected block; it passed validation and priced at 74.16 USD/share, the same value as the hand-corrected block.

One existing expectation changed: `test_explicit_empty_proposal_is_distinct_from_malformed_payload` pinned the word "malformed" from the old generic sentence; it now expects `submission_error == "unreadable"` and the JSON message.

## Independent audit

Run e44d606a on `699eae7d` (GPT-6 Astra, 24 turns, $0.80, 7.5 minutes): no Critical or High, four Medium. Closed in the commit after `699eae7d`.

| Finding | Disposition | Correction |
|---|---|---|
| 1 A correction could drop a rejected case and the run still scored 5 | confirmed (read; failing test written and run) | When the original submission was readable, the corrected block must contain exactly the same case names. A correction that drops a case is refused. |
| 2 A correction into an unpriced funding diagnostic counted as a recovery | partially confirmed (failing test run) | Acceptance now counts cases that gain a price, not rows. Not adopted: scoring a genuine funding-gap diagnostic as a rejected case. A funding gap is an analytic result, not an operational failure; that scoring is unchanged from Build Z. |
| 3 The failed-correction reason was lost on replay | confirmed (ran) | The attempt's outcome is saved with the hash of its report and re-attached on every replay. No second attempt is made once one is on record. |
| 4 An accepted Research Manager revision removed the correction note | confirmed (ran) | A surviving case keeps a note that the analyst's case had been corrected, with the cause. |

After closure: 5 new tests red then green; full suite 4196 passed; ruff clean; replay unchanged. No second audit: the corrections are bounded and tested.

## Plan adjustments

- R3: a successful correction is derived from the saved record and listed under "Recovered issues", not added as a new observation code. No new recording path was needed.
- R1 adds a sixth kind, `too_many`, for more than three cases.

## Known limits

- One attempt only. A second failure leaves the case unpriced and the score at 3.
- A report with no valuation block at all is not retried and does not lower the score: nothing shows a case was lost.
- The correction model is instructed to change only what the reasons name. That is checked for cases that were already priced, which must stay identical. For a case that was unreadable there is no priced original to compare with; the note on the table says it was corrected.
- No full live run was made. The correction step was proven on one real block with one real call.
