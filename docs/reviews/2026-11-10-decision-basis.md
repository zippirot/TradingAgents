# Build Q: a decision made from priced scenarios

Plan: `docs/superpowers/plans/2026-11-10-tradingagents-decision-basis-plan.md`, approved 2026-11-10 with all five recommendations. Base `3e517089` (`origin/staging`). Branch `claude/decision-basis-q-20261110`, worktree `~/Worktrees/decision-basis-q`. Not merged, pushed or installed.

| Task | Change | Files |
|---|---|---|
| Q1 | `funding_check`: each revenue case is compared with the filing's finance-lease and equipment payment schedule (`lease_maturities`, split out of the existing renderer) and any retained note maturing by the case date. Status `assessed`, `partial` with the exact shortfall, or `unassessed`. The blanket "Funding feasibility unassessed" warning is gone. New cash-change sources `finance_payments` and `capex`. | `agents/valuation_cases.py`, `agents/retained_kpi_context.py`, `agents/shared_valuation.py`, analyst prompt |
| Q2 | `reference_position`: each case restated as equity value over forecast revenue and placed in the own-history range; `history_context` adds trailing growth and gross margin per history quarter where facts exist. | new `agents/case_reference.py`, `agents/shared_valuation.py` |
| Q3 | Analyst asked for base, downside and optional upside cases with `scenario_role`. `scenario_view` and `rating_basis_reason` on the manager's decision; `scenario_decision.summarize` computes range, weighted value, direction (10 percent) and a rating check from replayed cases; one correction attempt; decision-card block; operational score 3 when cases are unaddressed or a contrary rating is unexplained. Price targets keep the strict path. | new `agents/scenario_decision.py`, `agents/schemas.py`, `agents/managers/portfolio_manager.py`, `agents/decision_context.py`, `operational_audit.py`, analyst prompt |

## Verification (builder-run)

- New tests: `tests/test_case_funding.py`, `tests/test_case_reference.py`, `tests/test_scenario_decision.py`. Full suite on the final tree, after audit closure: 4280 passed, 10 skipped, 1 deselected. `ruff check .` clean.
- Offline replay of saved run `eea86100`, `docs/reviews/decision-basis-proof-tools/replay.py`, output in `replay-results.txt`: both cases priced as before (74.45 and 52.75); funding `partial`, naming 320.5M USD of scheduled payments through 2027-12-31 not stated; positions 4.66 times (median to high) and 3.65 times (low to median); history median earned at about 15 percent trailing growth and 60 percent gross margin.
- Paid proof, approved by the user, `live-results.txt`: thirteen Portfolio Manager re-runs on the reconstructed manager-time state of `eea86100` with the run's deep model. About 1.4 USD of the 10 USD approved (eleven calls metered at 1.19 USD by the OpenRouter key counter; two earlier calls not metered).

| Set | Code | Cases as | Calls | Result |
|---|---|---|---|---|
| 1 | as first built | saved | 2 | valid answer on the first call; both cases rejected on funding |
| 2 | as first built | funding stated | 2 | both rejected on funding, citing rent on uncommenced leases and no assumed issuance |
| 3 | experiment outside product code: size of the limit plus rejection standard | funding stated | 2 | both accepted, weights 0.70 to 0.75 and 0.25 to 0.30 |
| 4 | experiment: rejection standard only | funding stated | 2 | both accepted, 0.75 and 0.25 |
| 5 | final | funding stated | 2 | both accepted, 0.7 and 0.3; weighted 67.94, 13.2 percent below the 78.31 close; rating check consistent |
| 6 | final | saved | 1 | both accepted, 0.7 and 0.3; same weighted value |
| 7 | final, after audit closure | saved | 2 | both accepted, 0.7 and 0.3; weighted 67.94, 13.2 percent below the close; rating check consistent |

In sets 5, 6 and 7 the manager answered on the first call each time and kept Underweight.

## Independent audit

Run 9f2855ff on `e4e11a91` (GPT-6 Astra, 29 turns, $1.63, 15 minutes): one High, three Medium, one Low. All five reproduced by running them, then closed in the next commit.

| Finding | Reproduced | Correction |
|---|---|---|
| High: the comparison with the price read any available close, so a quote in another currency could be compared | Ran: a EUR close gave a percentage and a direction against a USD case | The summary uses only the close each accepted case was validated against on replay, and only when every accepted case shares it and its currency matches the case unit. Otherwise the range is stated with no percentage, direction or rating check. |
| Medium: a malformed case identity crashed the manager step | Ran: TypeError and KeyError | Identities are type-checked first; a bad entry is a stated problem and gets the one correction attempt. |
| Medium: a free-text fallback decision was treated as pre-contract | Ran: status not applicable | The fallback record carries the contract marker; the card says the cases were not addressed and the score records it. |
| Medium: funding could be `assessed` on a schedule that did not reach the case date | Ran: one stated year, 2029 case, `assessed` | Every year from the snapshot to the case date must be stated, else `unassessed` with the reason. |
| Low: the card omitted each case's reference position | Ran | Each card line states the band. |

Auditor's open point, not a defect: the plan said the scenario summary would be saved in the publication record; it is recomputed from retained inputs instead (see adjustments). That substitution needs the user's acceptance.

After closure: 16 new or changed tests red then green; full suite 4280 passed; ruff clean; offline replay unchanged except the added reference text; two further live re-runs on the final code (set 7). No second audit: the corrections are bounded and tested. Audit record: `~/Claude/audits/docs/superpowers/audits/2026-11-10-build-q-decision-basis/`.

## Plan adjustments

- **Rejection standard added (Q3).** The plan required a rejected case to name the input rejected. Live sets 1 and 2 showed that is not enough: the manager rejected every case on limits common to all of them. The prompt now says such limits go into weights and the downside case, and a case is rejected only when the manager can state the value the rejected input should take. Without it the plan's acceptance (card shows range, weighted value, direction and check) is not met. It is prompt wording only; code cannot verify that a stated value is given.
- **Funding status when the split is absent (Q1).** The plan said a case with no split stays `unassessed`. Where the schedule is retained the case is `partial` and names the amount, which is what the plan's own replay test expects; `unassessed` is kept for a missing schedule.
- **Publication record (Q3).** The summary is not written into the publication record. It is recomputed from the retained manager answer and replayed cases, both already in the evidence snapshot.
- **Decisions made before this contract** carry no `scenario_contract` marker and are not judged for omitting a scenario view.
- **Two existing expectations changed** because the fixture manager does not address the priced case and is asked once more: `test_native_resume_after_trader_does_not_repeat_completed_roles` and the Build 2 continuation drill now expect a second Portfolio Manager call.
- **Build 2 continuation drill** (`docs/reviews/valuation-build2-proof-tools/continue_cli.py`) compares saved and final scenario records without the newly derived `funding`, `reference_position` and `reference_history` fields and the funding warning. Everything else is still compared exactly.

## Known limits

- In every final live run the weights were 0.7 and 0.3. They are the model's subjective weights and may be a default; nothing calibrates them.
- After the rejection standard the manager accepted cases even with funding `partial`. Rejection is now rare by design; whether that is too permissive needs more runs.
- Not proven: that the analyst states the funding split and scenario roles under the new instruction. That needs a full run. The live sets with funding stated used hand-edited cash entries on the saved cases.
- Rent on leases that have not commenced is not modelled; every case says so.
- Scheduled payments are prorated by days within the final year.
- Whether decisions become more accurate is not shown by this build.
- Re-exporting an older run shows the new funding and reference lines on its cases; its decision card is unchanged because the decision predates the contract.
