# B1 mechanical sensitivity checkpoint

## Scope and branches

The user's 2026-11-05 follow-up authorizes B1 only after Part A publication. The approved-plan amendment records the exact boundary. B2, B3 decision adoption/prompt expansion, comparison and installation remain on hold.

Part A is frozen at 24172f6c05a332f4c74f8b9984e61564feae09d4 on codex/valuation-reference-part-a, in [staging PR #5](https://github.com/zippirot/TradingAgents/pull/5). All seven jobs in [run 42150548960](https://github.com/zippirot/TradingAgents/actions/runs/42150548960) passed, including exact-head full suites on Python 3.11–3.14 plus New York timezone, clean installation and full lint. No merge or installation occurred.

B1 is an isolated local branch, codex/valuation-reference-b1, at /Users/zipp/Developer/tradingagents-valuation-reference-20261105/part-b1 on verified M1 Pro/16 GB. The Part A worktree remains clean. The independent B1 environment retains the same 90 noneditable dependency pins. Initial editable setup failed because --no-build-isolation lacked the temporary setuptools build backend; a normal isolated editable build fixed setup without changing runtime pins.

## Delivered behavior

B1 recalculates price sensitivities from retained, revalidated price, financial, own-history/peer and source-only management disclosure records. Model targets, scenarios and free text do not supply its inputs. Every cell uses equity value / revenue: revenue × multiple ÷ shares, with no obligation deduction. No enterprise-value multiple is silently substituted.

History and peer reference groups have separate tables. Fewer than three accepted same-session peers produces individual ticker columns, not a pooled range. New references use schema 3; legacy schema 1/2 projections remain exactly replayable, including empty defaults. Earlier-session fallback peers remain dated diagnostics excluded from same-session grid references.

Management low/high values, a single guidance-floor outlook, and vendor annual estimates retain separate periods/horizons. The floor uses the source's base guidance low and stated growth floor, with held-fixed assumptions; it is not a share-price floor or three invented scenarios. Vendor next-fiscal-year values appear only in a separate unverified block. Missing fiscal dates stay explicitly unverified; unknown currency/unit prevents arithmetic and unknown accounting basis remains noncomparable. A bad vendor block does not hide available management rows.

Reported shares retain measurement date and source. Source-grounded guided diluted weighted-average shares retain their own period and appear as conditional sensitivities, never forecast year-end counts. Returns are price changes against the actual completed close, without discounting, annualization or dividends. No pooled decision range, forced target, model call or rating authority is added.

The grid is a separate Markdown/HTML/CLI pane and typed evidence record. It is omitted from the canonical final decision consumed by trading-memory reflection. Publication retry → memory → fixture settlement/reflection tests confirm that separation. Target/scenario scoring paths remain unchanged; REVIEW withholds the grid and retains no-action-memory behavior. No B3 prompts or decision-card adoption were added.

## Verification and evidence reuse

A stable B1 affected run produced 1,079 passes and two failures in old peer-cover expectations (schema 2 and one-peer range). Those expectations were corrected for schema 3, retaining all source/share/numeric guards and adding explicit legacy schema 2 conditional-range replay. The affected 63 checks then passed.

Actual retained-input replay subsequently exposed a production defect: the new minimum-peer reason affected older empty peer sets. The guard now applies only to minimum_range_peers > 1. The final 97 flow/cover/grid/publication/report/legacy-recovery checks passed after the correction. Independent replay of immutable original A/A2 and the prior corrected schema 2 reference succeeded without reassembly or changed expected values. A final 61 display/report/CLI/asset checks also pass after excluding empty nonstock panes. Full Ruff passes after these source corrections. Pip check passes, pins remain identical, and diff checks pass.

The complete offline inventory contains 2,599 selected tests (2,600 total; the existing paid DeepSeek integration test is deselected). New and affected tests ran locally; unchanged areas reuse Part A's exact-head full CI and earlier passing local coverage, with source/dependency/configuration/impact justification in evidence/b1-verification/verification.json and the final evidence record. Provider/funding/math paths outside the changed consumers and the dependency pins remain unchanged. Combined evidence is not one full-suite run on the final B1 revision. Required B1 exact-head GitHub CI awaits separate publication approval.

Commands, source hashes, initial failures and correction logs remain under /Users/zipp/Developer/tradingagents-valuation-reference-20261105/evidence. This includes b1-verification, b1-corrected-fixture-checks.log, b1-final-legacy-recovery.log, b1-final-ruff.log and b1-pip-check.log. The original broad results are preserved rather than overwritten.

## Retained replay and limits

Private inputs remain outside Git. Original A/A2 receipt/source hashes are preserved. Offline A2 replay retains its original temporary MSFT/ORCL pins; passing data checks does not establish business comparability or a new sensible model peer selection. Its 135 numeric sensitivities are independently recomputed and compactly displayed without dropping cells. A separate original-A derivative uses repaired AKAM and dated NET inputs, no vendor snapshot from a different cutoff. Missing A consensus remains unavailable. None of these derivatives rewrites original reports or represents a new live run.

Full current Markdown/HTML, CLI capture, compact grid supplement, source hashes and visual QA are retained under private/evidence/b1-integration-artifacts. The [independent code/artifact review](2026-11-05-mechanical-valuation-b1-independent-review.md) is complete with no open confirmed material findings. Review SHA256: 41833366b45e830502daba48738c26811c54619b913858ec3918887924fb5d85. Final artifact QA SHA256: da82c77c6d28283b11c25c404257e05a2604f0568a0ba1a3684c70e10a175eb9; PDF SHA256: 6a512616a1b07d39cf3e624533436500467c1525867da3ca8779fb8afa343f8b. The actual source grids reproduce 135 A2 and 36 separate repaired-A cells. All 341 nonempty supplement cells pass text/scroll bounds; all 803 product cells pass internal scroll bounds, and the four B1 tables fit the portrait container. Original inputs remain unchanged.

Deferred existing presentation issue: unrelated evidence/quality tables 14/15 exceed the portrait container width. Their contents/CSS were not changed by B1; no product print redesign is included. This does not invalidate the inspected B1 grid bounds, and is not a claim that every pre-existing table fits in print.

No new paid calls: this follow-up spend is $0. Earlier Part A proof spend remains $2.33108810 for 34 settled requests. B1 has no new paid/live proof; deterministic offline checks do not establish live model behavior or broader Part B acceptance. No retry or extra report budget is inferred.

## Pending authority

B1 publication/CI, Part A merge, installation, B2, B3 decision adoption, comparison, worktree removal, scheduler and broker actions remain unapproved. This is the requested local review checkpoint, not installation or production acceptance.
