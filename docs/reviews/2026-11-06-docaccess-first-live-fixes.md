# DOCN first document-access fixes — local verification

Date: 2026-11-06. Scope: the two fixes and diagnoses in `/Users/zipp/Claude/2026-11-06-docaccess-first-live-fixes-plan.md`. User authorization starts local implementation despite the plan's planning-only header. Valuation Build 2/A3, comparison, publication and installation remain held.

## Baseline and environment

Machine 2: Apple M2 Pro, 32 GB, Python 3.12.13. Dedicated clone and isolated `codex/docaccess-first-live-fixes-m2` worktree under `/Users/zipp/Developer/tradingagents-docaccess-fixes-m2-20261106`. Local staging was initialized from and confirmed equal to GitHub staging `a2e78acdde6ee6a4d7cd7066c4c8a5a5aba21ebd`; no existing staging branch was advanced. The installed `903a514` checkout/pins and old M1 worktree remain unchanged. GitHub has no production branch; none was created.

Retained decision `ddb3c455`, input `DOCN_2026-11-06_docaccess-first-live_state.json`, SHA-256 `c45825a614ea8cbd8a93ba44e9cb012d8c80914e02a3b5d9e983df72a5368d10`. The original and a private replay copy are outside Git. Plan SHA-256: `d705b8a4edc21a50d4367d858bbb88e7ccc788766fc4b4fdb8de6b48b24c4a39`.

## Changes and observed behavior

Guidance discovery no longer treats a consistent search excerpt of the same SEC source as an identity conflict. It compares identity and complete shared block metadata/content, permanently withholds a conflicting source for that calculation, validates deterministic discovery per document copy, and deduplicates identical validated claims before unique selection. Persisted/model-proposed values remain unauthoritative. No valuation formula changed.

The actual retained replay changed:
- FY2026 management revenue guidance: null → USD 1.208–1.211 billion, block-46.
- Q4 guided diluted weighted-average shares: null → 128–129 million, block-44; a period-weighted sensitivity.
- Conditional 2027 growth floor: null → 60%, block-4.
- Management grid: unavailable → available, guidance low/high plus exactly one floor outlook, with outstanding and guided share sensitivities. Accounting/fiscal comparability remains unverified; diagnostic rows remain noncomparable.
- Completed close remains USD 72.48 on 2026-11-06. Underweight and the original publication identity are unchanged.

Named-note search requires an explicit requested instrument/year match before ranking. Coordinated note queries reserve coverage for each requested identity. Wrong-instrument passages cannot qualify through generic cash/share/conversion words or incidental dates. Per-instrument no-match, size-limit, incomplete-block and passage-limit gaps are visible in both downstream context and reports, including partial results. Whole source blocks/hashes, issuer/date cutoffs, three-passage/12,000-character bounds and legacy sealed snapshots remain intact.

Actual `bear-2` changed from 2030-only blocks 187/185/195 to the latest quarterly filing's 2026-note blocks 205 (December 1, 2026 maturity and cash/share/combination election), 204 (USD 178.51 initial conversion price), and 126 (table also naming the 2026 notes). It returns 3 passages / 2,325 characters. This establishes the retained terms/election, not actual settlement or management's chosen settlement method.

## Verification

- Red regressions observed before fixes: consistent duplicate-source inputs lost guidance; 2030-only passages qualified for 2026; partial missing/omitted-instrument reasons were hidden. Development logs retained.
- Guidance/mechanical focused checks: 41 passed.
- Search/follow-up/reporting focused checks: 26 passed.
- Full offline suite on the stable seven-file implementation: **2,905 passed, 10 skipped, 1 deselected, 100 subtests passed**, 24 warnings. Full Ruff, pip check and diff check passed.
- Skips: optional `langchain_aws` absent (1); private M1-only document replay inputs (3), old price-implied inputs (5), and private transcript input (1). The external integration test was deliberately deselected. Skips are not passes. Portable regressions and this actual M2 replay cover the affected guidance/search/report/recovery behavior; unchanged transcript/provider paths are not claimed as newly observed live.
- Real development path: retained questions → actual lookup → report preparation/validation → independent price/table/grid → normal Markdown/HTML/evidence export and actual CLI renderer. Socket, requests, httpx, curl and model-invocation boundaries are denied; core calculations/search/renderers are not mocked.
- Hand-recomputed dated equity, guidance EV/revenue intervals and growth-floor ratios, and every management grid price, using Decimal precision matching the implementation.
- Both original and new sealed follow-ups reuse without re-search; changed passage/corpus is rejected. Repeated export preserves the in-memory input, rating/publication identity and report body. The first byte-comparison failed only on the intended per-export `Export generated` timestamp; the failed log is retained and the corrected check excludes only that header. No product code was changed for the expectation.
- Markdown/CLI and parsed HTML/evidence checked; headless Chrome rendering of the actual report was visually inspected. Direct deep-fragment screenshots were blank in the renderer; an ordinary page capture succeeded and shows the restored management comparisons. This is a renderer limitation, not a claimed successful fragment capture.
- Independent code/artifact audit: no confirmed material finding. Reviewer independently ran 16 conflicting-source cases and 2 partial-omission cases (18 passed).
- Post-review actual retained replay and runtime assertions passed again. No implementation source changed after the full suite or review; no duplicate full suite was run. Artifacts are private M2 exports, not new immutable publications, fresh analyst decisions or live API proof.

## Diagnosis: model submissions and follow-up citations

All 13 model submissions initially failed the same duplicate-source-context uniqueness check. A diagnostic using only the original source package still accepted 0/13: the original quoted spans did not meet the parser's supported qualification/context shape. No proposal was repaired or promoted. Twelve have matching deterministic source/locator/metric/amount/range/unit/period/kind/comparator fields; their quotation shapes differ. ARR added during the quarter (USD 160 million, block-14) has no accepted deterministic counterpart. The 15 accepted deterministic claims therefore do not establish complete model-submission coverage.

The per-record diagnosis and downstream reasons are recorded in the private evidence directory's `disclosure-diagnosis.md` and `private/disclosure-diagnosis.json`. No shared model-validator change, repair loop or extra call was added. Prompt/parser compatibility and duplicate handling in the shared submission validator are deferred, outside these two fixes.

All four original follow-ups returned passages but the final decision named no exact returned citation reference. “Unresolved” measures citation, not whether the model read or paraphrased the passage. The strict check is retained. Optional wording recommendation remains “source passages retrieved; final-decision citation not verified”; no semantic-usage inference, citation relaxation or optional label change was implemented.

## Adjustments, evidence and release limits

Bounded plan adjustment: named-note queries prioritize recent eligible filings before the existing within-date relevance/tie-break rules. Actual score-first replay chose older blocks 1171/200 and crowded out current conversion-price block-204. Recency-first returned current blocks 205/204 within the existing budget; a portable regression covers it. Generic search ordering is unchanged.

Machine 2 evidence root: `/Users/zipp/Developer/tradingagents-docaccess-fixes-m2-20261106/evidence`. Actual final exports: sibling `private/replay-final`; original proof, diagnostic files and first comparison failure are retained. Verification/source/dependency bindings and final commit are recorded in the synchronized private completion record. The audit and a per-record disclosure diagnosis accompany the handoff.

Paid API/proof spend: **USD 0**, no paid calls. Codex development usage is separate and not estimated. No credentials were copied into source, no models/preferences changed, no canonical store/database/broker/scheduler mutation, no push/PR/merge/fast-forward/staging or production advancement, no installation and no worktree removal. Exact-head GitHub CI remains pending authorized publication. Stable M1 installation can occur only after separate production release approval and exact-commit promotion.
