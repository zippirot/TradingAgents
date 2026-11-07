# Document access Build A — retained filings

Local implementation candidate; required live model proof remains unapproved and incomplete.
No release acceptance is claimed.

## Baseline and isolation

- Accepted PR #8 source: a066b6f874eca5c102f3e8a089dbcce599d86daa.
- Verified GitHub/local staging base: b67f1c8444075048cb12921d9b758c53cfc9e886; identical tree to the approved source. No baseline drift.
- Development/verification: Apple M1 Pro, 16 GB, Machine 1 only.
- Worktree: /Users/zipp/Developer/tradingagents-document-access-20261106/build-a.
- Isolated branch: codex/document-access-a. This record belongs to the source commit that contains it.
- Approved plan SHA256: 724bf45c6326de8bb48e56fb662a5d825a7e93813efaae1efae753a32a2e09fe.
- Input and publication references: task-root evidence/setup.json, document-retained-inputs.json, retained-filing-inputs.json.
- All saved states, full source wrappers, credentials, runtime and generated reports remain outside Git under the task root's private/ and evidence/ directories. Originals and launcher/model preferences were preserved.

## Delivered behavior

The existing bounded accounting brief remains unchanged. A separate full-source corpus includes latest periodic filings, prior-quarter 10-Q, intervening 8-K exhibits and 424B supplements. Limits are 24 filings, 32 documents, four exhibits per 8-K, 33 requests and 240 seconds; omissions are retained and reported.

Fundamentals and News each receive three deterministic search calls, at most three complete passages and 12,000 source characters per call, with queries at most 200 characters. Full tables are either returned intact or explicitly omitted. The run pins exact corpus/block hashes and returned text. Only returned SEC passages enter the existing quote/metric/period/unit/qualification validator; retrieval alone grants no accepted-evidence authority. Source metadata is registered even if the bounded brief was unavailable.

Bull and bear use their existing final turns for up to two structured questions each. One deterministic lookup node precedes Research Manager; passages reach existing RM, risk and PM context. No additional reasoning call or RM fallback was needed. Reports and CLI distinguish valid returned citations, unresolved questions and not-found-in-retained-filings; they never infer non-disclosure from no match. Market-only and non-stock scopes do not acquire extra SEC sources; later lookup reports unavailable when no filing-using analyst acquired a corpus.

An explicit intraday cutoff cannot establish a same-day filing's publication time from SEC filingDate alone. Such documents are omitted from the new searchable corpus with a reason. Ordinary date-only end-of-day behavior and the legacy bounded package are preserved.

## Verification and evidence reuse

- Complete Build A offline inventory before review corrections: 2,771 passed, one optional langchain_aws skip, one configured deselection, 100 subtests (build-a-offline-boundary.log).
- Initial 12 failures were diagnosed: an extra graph step exceeded the existing turn budget, and strict new-source IDs rejected baseline-supported synthetic bounded IDs. Corrections preserve graph turn count and bounded-input compatibility. The affected 12 tests passed.
- Independent review found and closed resumed-journal budget bypass, absent search-only canonical source registration, discarded question state, raw-only citation mislabeling and exact-intraday ambiguity. The stronger saved-state replay also found and closed raw-report overlay loss and CLI omission.
- Focused checks cover canonical exact quote acceptance/paraphrase rejection, source/period/units/qualification validation, future sources, intact/oversized tables, call limits including parallel execution, malformed and forged recovery records, actual ToolNode interruption/resume without cache fetch or duplicate journal, legacy reporting, real later-role prompt capture, and report publication paths.
- DOCN retained replay finds current/prior omitted RPO passages, uncommenced leases, equity agreement and prospectus. Actual RM/neutral-risk/PM prompts were captured with deterministic model responses; Markdown/HTML/CLI show one cited follow-up and three unresolved follow-ups. No live decision is inferred.
- Public SEC excerpt fixtures cover JPM (banking SIC6021) and CAT (machinery SIC3531). Full wrappers remain private.
- A headless isolated Chrome profile on M1 rendered the HTML report; its screenshot was visually inspected on the coordinator. Text wraps without overflow, citations and unresolved labels are visible.
- Full Ruff, dependency and diff evidence plus final affected-test results are recorded in task-root evidence. Passing broad results are reused only for source and dependencies unchanged after the review. Affected source/search/report/recovery tests were rerun; no dependency/configuration changes were made. Combined evidence is not a full suite on one revision.
- Final affected checks: 115 passed after source/search/report/recovery corrections; the new actual-node saved-state replay and JPM/CAT checks also passed 4/4. Full Ruff and pip check passed.
- Private evidence: document-build-a-independent-audit.md, document-retained-replay.json, document-replay-output/, document-replay-nodes-output/, build-a-final-affected.log, build-a-final-render-recovery.log, build-a-search-recovery.log and build-a-audit-fix-checks.log.

## Limits and held authority

Fresh acquisition and real model source-use decisions remain unproved. Deterministic offline model responses are fixtures. No new paid model calls were made; old ledgers and unknown-cost holds remain preserved and do not grant attempt authority. A fresh proof allowance will be proposed separately for DOCN/JPM/CAT.

Document-access Build B may continue independently from this frozen source. Valuation Build 2/A3, the comparison, installation, publication and all release actions remain held. No valuation cases, pricing or ranges changed. Required exact-head GitHub CI awaits authorized publication.
