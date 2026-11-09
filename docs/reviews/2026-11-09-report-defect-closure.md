# Report defect closure: build evidence (2026-11-09)

Plan: `docs/superpowers/plans/2026-11-09-tradingagents-report-defect-closure-plan.md`. Base `55edfd7e`.
Decisions recorded with the plan: no paid calls, X3 deferred, S1 12,000 characters, no post-PM audit, one worktree.
The goal text itself was not available to the builder; these decisions come from the plan header and the operator's saved note.

## Verification (builder-run, not independently rerun)

- Full local suite on the final branch head: 4047 passed, 10 skipped, 1 deselected.
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

### Per-commit proof

Each build commit was exported on its own, then its full suite and its replay were run. These runs came after the commits, so they are retrospective. Output: `report-defect-closure-proof-tools/per-commit-results.txt`.

| Build | Commit | Full suite at that commit | Replay |
|---|---|---|---|
| V | `9a4e4262` | 3981 passed | Defect gone |
| T | `1937a1d3` | 3986 passed | Defect gone |
| E | `894ecede` | 3997 passed | Defect gone |
| P | `338ceec3` | 4002 passed | Exclusion disclosed |
| F, X | `a2110a82` | 4016 passed | Defect gone |
| S | `56cb6490` | 4028 passed, 1 failed | Five accepted, three correctly rejected |

The S failure is a test fixture only, corrected in `043e2d93`.

### Rendered-report comparison

`complete_report.md` rendered from the recorded state at `55edfd7e` and at this branch differs on about 90 of 3,323 lines. Excluding the export timestamp, every line falls in one of these groups:

- HTML entities removed from text and comparators (E3).
- Price-level metric and each proposal's own reason (T2).
- Citation-check count, now 7 of 7 (E1), and the new prompt-only list (E2).
- A rejected-row reason line (V1).
- The executive summary shows as stale and "Rating inputs" as "summary unavailable". This is a re-export effect: the saved summary's digest covers the rendered text, which changed. A new run writes a new summary.

The recorded thesis is re-rendered as saved, so the duplicate rows only disappear when `prepare_thesis` runs, which the T replay shows.

## Build W: regressions from run 2a2e47dd

Fix commits `210a039c`, `3fb83b78`, `6acbe527` and `8c230492` on top of `0236255d`. No paid report run was made.

Verification (builder-run): full `pytest -q` 4079 passed, 10 skipped, 1 deselected on `8c230492`. `ruff check` reports one finding, an import-order issue in `tests/test_action_aware_trader.py` that is already present at `0236255d` and was left alone.

Replay of `2a2e47dd` (`report-defect-closure-proof-tools/replay_w.py`, output in `replay-w-results.txt`):

| Target | Result |
|---|---|
| Two supported cases | Base $74.86 and Downside $44.86, both supported, no rejection reasons |
| bear-1 keeps the RM's judgment | `answered`; bull-1 keeps `partially_answered`; the two post-filing questions stay `unanswered` |
| Operational audit | 4/5 Good, run identity matched, no malformed records. The 4 reflects the recorded Trader and Sentiment fallbacks in that run. |
| One row per event condition | Three event rows; both paraphrases aliased; no "omitted from proposal" warnings |
| No ".." on the card | 0; citation mismatches 0 |

Unverified: W4's live effect. Nothing offline can show that OpenRouter's Anthropic route now returns structured output. Acceptance is zero `fallback_recovered` records for the Trader and Sentiment Analyst on the next paid DOCN run, deferred by user decision.

Independent audit of `8bf4f690` (GPT-6 Astra, $1.04, 32 turns): no Critical or High, two Medium, both confirmed and closed in `3fb83b78` and `6acbe527`:

- A negated event ("does not cut guidance") could alias to its affirmative form. Differing negation now keeps them separate. `test_negated_event_is_new` failed before the fix and passes after.
- A condition kept by ID alone still raised "omitted from proposal", contradicting the new PM instruction. The warning is removed; the condition is still preserved. `test_keep_by_id_alone_is_not_an_omission` failed before and passes after. Two older tests that required this warning now require its absence.

Re-audit of `24376a3c` ($1.02, 32 turns): no Critical or High, two Medium, both in W5 matching, both confirmed and closed in `8c230492`:

- "notes" stemmed to "not", so "refinances the notes" and "will not refinance the notes" got one key.
- Decimals split into digits, so "$1.5 billion" and "$5.1 billion" got one key.

Exact keys are the full description again. Quantities, scale and negation are read before stemming and must match for any fuzzy alias. `test_opposite_or_different_amount_events_stay_separate` failed before and passes after.

The audits also noted lint is not green; that is the one finding at the base recorded above.

Plan adjustments:

- W5: Jaccard 0.6 on plain tokens scored the real "settled or refinanced" pair at 0.56, so it missed. Added light suffix stemming. The same threshold would also have merged "2026 notes" with "2030 notes" and "cuts guidance" with "raises guidance", so differing numbers, direction words or negation now keep events separate.
- W2: also applied to saved records whose status is `no_relevant_passage` but which hold passages, so the retained `2a2e47dd` record and resumed checkpoints behave the same way.
- W4: pinning and the no-forced-tool-choice flag ship together as the plan says, so forced tool choice is not sent for `anthropic/` models on OpenRouter even though the pinned host accepts it. A reply without the tool call falls to the free-text path and would show as a fallback.
- W6: `comparison` is a structured record, so its `value` and `unit` are read rather than parsing text.
- `document-access-proof-tools/live_cli.py` now counts the new status. The historical Build2 continuation fixture freezes the provider pin, because that proof's budget guard refuses route overrides. Future paid runs through that proof adapter would need the guard revisited; normal app runs do not use it.

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

## Independent audit

GPT-6 Astra through the frozen executor on `524fe352`: 32 turns, $1.75, 18 minutes, one High and two Medium. All three were reproduced by running them, and all are closed on this branch.

| Finding | Disposition | Closure |
|---|---|---|
| High: quoted request-body keys kept in provider error text (X1) | confirmed | Text after any serialized request key is dropped; quoted JSON, Python dictionaries and pydantic input values tested against the log and the helper. |
| Medium: trigger and checkpoint section bodies dropped (X2) | confirmed | Heading-delimited sections are copied whole; tested through `create_trader`. |
| Medium: empty FINAL TRANSACTION PROPOSAL accepted (X2) | confirmed | Both labels need Buy, Hold or Sell; empty, invalid and valid forms tested through `create_trader`. |

Commits after the audited head changed the Trader fallback, error redaction, the prompt-only list filter, and lint-only imports. No second audit was run; the skill directs bounded review over repeated audits. Audit record: `~/Claude/audits/docs/superpowers/audits/2026-11-09-report-defect-closure-final/`.

## Process departures

- The goal text reached the builder only after the builds were committed. Named tests were therefore written with each build, not always first.
- Build P was committed after focused tests only; its full suite was first run on that exact commit retrospectively and passed.
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
