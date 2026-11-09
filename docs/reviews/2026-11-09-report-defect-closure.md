# Report defect closure: build evidence (2026-11-09)

Plan: `docs/superpowers/plans/2026-11-09-tradingagents-report-defect-closure-plan.md`. Base `55edfd7e`.
Decisions recorded with the plan: no paid calls, X3 deferred, S1 12,000 characters, no post-PM audit, one worktree.
The goal text itself was not available to the builder; these decisions come from the plan header and the operator's saved note.

## Verification (builder-run, not independently rerun)

- Full local suite at the last implementation commit `043e2d93`: 4035 passed, 10 skipped, 1 deselected.
- The 10 skips are `langchain_aws` missing and private DOCN inputs unavailable.
- No paid model or vendor call was made. No remote CI exists for this unpushed branch.
- Offline replays read `full_states_log_2026-11-09_520623df.json` and the cached NBIS companyfacts.

## Replay of run 520623df

| Build | Result |
|---|---|
| V | Recorded case rejected: "share_changes must sum to the 10079269 difference". With a stated bridge (153.2M conversion, 312.3M debt repaid): "Converted principal 153200000 still counted in borrowings". |
| T | 7 conditions: 4 metric (each with 1 alias), 1 price level "Completed close (USD)", 2 events; no duplicates, no unspecified role. |
| E | Citation check 7 of 7, no mismatches or unresolved labels; F56+ listed; 0 `&#x27;` in HTML and Markdown; no "unavailable USD". |
| P | NBIS no longer fails on the 2023-12-31 ambiguity, which is disclosed; it remains without a multiple because it has no quarterly revenue facts. |
| F | bear-2 coerced to unanswered with the override note; other three unchanged. |
| X | RM Strategic Actions carried verbatim when the recorded Trader text is run through the fallback finisher. |
| S | Seven rejected submissions: records 0, 2, 3, 4 and the previously accepted record now accepted (5 of 8 records); 5, 6, 7 remain rejected. |

Retained proof: `docs/reviews/report-defect-closure-proof-tools/replay.py` reruns all seven against the recorded state.

| Build | Commit |
|---|---|
| V | `9a4e4262` |
| T | `1937a1d3` |
| E | `894ecede` |
| P | `338ceec3` |
| F and X | `a2110a82` (one commit, not separate groups) |
| S | `56cb6490` |

### Rendered-report comparison

`complete_report.md` rendered from the recorded state at `55edfd7e` and at this branch differs on about 90 of 3,323 lines. Excluding the export timestamp, every line falls in one of these groups:

- HTML entities removed from text and comparators (E3).
- Price-level metric and each proposal's own reason (T2).
- Citation-check count, now 7 of 7 (E1), and the new prompt-only list (E2).
- A rejected-row reason line (V1).
- The executive summary shows as stale and "Rating inputs" as "summary unavailable". This is a re-export effect: the saved summary's digest covers the rendered text, which changed. A new run writes a new summary.

The recorded thesis is re-rendered as saved, so the duplicate rows only disappear when `prepare_thesis` runs, which the T replay shows.

## Plan adjustments

0. **Worktree.** One worktree with sequential builds replaces the base plan's one worktree per build; technically equivalent, per the goal.


1. **V1 formula.** The plan's test `sum(borrowings) - estimate >= converted` passes the real case (461.6M - 150M = 311.6M >= 153.2M) because the 2026 notes repaid with cash already explain the fall. The check now requires `min(converted + debt repaid with cash, snapshot)`.
2. **T proof.** The plan expected two price levels. The 87.34 level was recorded as `unspecified`, so T3 rejects it with a visible warning; replay shows one.
3. **E3 scope.** The plan named two escape helpers. Its proof needs no entities anywhere, so every Markdown-path helper stopped HTML-escaping and the `reporting.py` decode workaround was removed. HTML export escapes once through markdown-it with html=False.
4. **E4 site.** "unavailable USD/shares" actually came from `render_case_summary`, not the listed sites; fixed there too.
5. **P1 guard.** Plain `exclude` would silently move a statistic to an older window. Exclusion applies only to consumed metrics and to periods more than 24 months before the newest quarter; an annual-only filer has no consumed period. The plan's expected NBIS multiple is not achievable from its facts.
6. **X2.** `required_sections` became a `finish_freetext` callback. The Action check is skipped for non-English runs, where the label may be translated.
7. **S2.** The premise was stale: filing terms, follow-up search, audit lookup and deterministic discovery already read the full `document_sources` corpus. The change is the gap wording plus tests proving the boundary.
8. **S3.** Root cause was a copied list bullet in the model quote. It is stripped at the model-submission parser only.
9. **Fixtures.** Historical Build2 drill freezes the capital bridge and `audit_role_chars`, following its existing frozen-contract precedent.

## Scope added after the plan

Commit `043e2d93` adds M2 and M1 from the 2026-11-09 audit of staging `55edfd7e`, requested through another session: a repeated corrected claim keeps the review warning, and the reassessment PM sees labelled originals plus its prior decision. E1 from that audit was already closed by Build E; an apostrophe regression was added.

## Process departures

- The goal text reached the builder only after the builds were committed. Named tests were therefore written with each build, not always first.
- Commit `56cb6490` (S) carried one failing fixture test (`test_model_package_limit_unchanged`), corrected in `043e2d93`. Every other build's final commit had a passing full suite.
- Commit `043e2d93` is outside the goal's nine defects; another session relayed it as requested by the user. It is a separate commit and can be reverted alone.

## Deferred

- **X3.** Cause of the provider 400 is unknown and needs one paid call, excluded by the goal. X1 now captures the error class and message. Exact later diagnostic, after adding a one-off script that sends `unvalidated_outputs` Trader messages through `bind_structured(llm, TraderProposal, "Trader")`:

```bash
PYTHONPATH=. python docs/reviews/report-defect-closure-proof-tools/replay.py
```

  The replay above is offline and proves the fallback. The paid step is one `structured_llm.invoke(messages)` on the configured deep slot, reading `error_message` from the `fallback_recovered` observation. `test_trader_schema_is_strict_mode_compatible` waits on that message.
- **S4.** No post-PM audit, per the goal.
- **M3** from the staging audit (replay status saved before post-graph misses), deferred by that audit.
- **Confirming paid DOCN run**, recommended and not done.
- **Annual-only peers** such as NBIS have no trailing revenue from companyfacts; supporting them is a new feature.

## Known limits

- A pre-upgrade checkpoint holding a case without the capital bridge is rejected on resume, and new settings change run signatures.
- Re-exporting an old run can show its executive summary as stale, because rendered text changed.
- X3 (cause of the provider 400) remains deferred. One confirming paid DOCN run is recommended, not done.
