# Report executive summary acceptance

Execution began November 7, 2026 on the isolated branch `codex/report-executive-summary`. The base is verified `origin/staging` commit `3d1b8f329f53b98daaecf05df4e522bc5491c87c`. Staging gained document-access and token-usage reporting after the planning inspection. The new layout retains both. Source imports were verified from this worktree, using the existing Python 3.12.13 environment, pytest 9.1.1 and Ruff 0.17.1.

## Acceptance specimen

The offline proof uses the retained November 6 DOCN state and a hand-reviewed editorial response supplied at the model boundary. The analysis has four contributing analysts, competing growth and funding interpretations, a provisional trader Sell, a final portfolio Underweight, limited evidence coverage and no supported final target. The real summary preparer, validator, writer and renderers process the fixture. It proves data flow, presentation and fidelity for this response. Live summarizer prose quality and provider usage are unverified.

Compared with a fresh export of the same state at the exact staging base. The installed launcher's prior export has different source code and was not used for parity. All 14 per-agent Markdown files (including mechanical sensitivity and evidence) were byte-identical. Their full text appears exactly once per file in the candidate's Markdown body. Both exports use the same summary. The old section targets resolve in the new display order: `s5, s1, s2, s3, s4, s6`; 21/21 HTML internal links resolve, no duplicate IDs, and Markdown contents links have explicit targets.

The locally retained specimen is at `/Users/zipp/Documents/ChatGPT/Tauric/output/report-executive-summary-proof/2026-11-07-docn-offline`. It is not part of this repository or the external audit payload. Its `manifest.sha256` identifies the report, fixture, images, PDF and proof metadata. HTML SHA-256: `8a570629506cf72060a36b5685bed957b728f1b7cb8e56c082daf21822e8df89`; PDF: `ab113a8e9afc9e1d35f4c6cefaccc6dff989a1972ba96fc653f749df4cc5e215`. The retained state SHA-256 is `c45825a614ea8cbd8a93ba44e9cb012d8c80914e02a3b5d9e983df72a5368d10` (decision `ddb3c455-244c-4332-a607-b6e0bc5e7917`).

**Reading proof.** Chrome 156: inspected desktop, emulated 390px mobile, and print. After wrapping long identifiers inside body paragraphs/list items, mobile viewport and document scroll width are both 390px; wide tables keep their local scrolling. The 98-page US Letter PDF starts with the summary on page 1 and the visible contents on page 2. Title/date precede two paragraphs; contents precede metadata, disclosures and the final decision. The process uses 68 words / 3 sentences; the decision uses 10 sentences. An in-flow contents replaces the hover rail; the back-to-top link remains.

**Source comparison.** All six groups were represented in the bounded model input. Each was truncated; the evidence and target constraints were supplied separately. We checked the fixture against the complete prepared sections as well as the excerpts:

| Source | What the summary retains |
|---|---|
| Portfolio | Underweight defined immediately; six-month horizon; funding, execution and per-share risk warrant a reduction with continued exposure. |
| Analysts | Broken trend and rebound risk; mixed, thin social evidence; issuer-reported growth and forward guidance; offering/dilution concerns. Growth and adjusted operating income are in the analyst excerpt; gross margin is also in portfolio/research excerpts and the full fundamentals report. |
| Research | Bull's cash-generation/growth case and the manager's greater weight on capacity funding, margins and valuation assumptions. |
| Trading | Provisional Sell means trimming toward a lower holding in this proposal. Its staging and levels did not become a portfolio target or binding instructions. |
| Risk | Agreement on a residual holding; disagreement over speed of reduction and evidence needed to rebuild. |
| Evidence | Only selected sources/calculations checked. Outstanding obligations and share/convertible reconciliation remain uncertain; scenarios are conditional and there is no supported final price target. |

The fixture shows that this response can survive the real pipeline accurately. Section tags, sentence counts and safe rendering do not prove other model responses factually correct. No live report summarizer or market-data call was made.

## Verification and audit

The focused publication, evidence, memory, checkpoint, state-log replay and streaming checks passed (101 tests before the extra timeout case). Real CLI and Python completion paths were exercised with offline model/vendor doubles. A timeout test observes the already-published decision and frozen evidence from inside the model call, then verifies that they, the memory rating and the usable exports survive the failure and that retry/re-export never repeats the call.

The first default run exposed an obsolete fixed `VI` expectation for a report with five sections, two offline wire-drill count mismatches, and nine pre-existing document-session fixture failures. The last group reproduced on exact staging: its relative UTC fixture could assign the wrong New York date to the close. The test fixture now binds its date to a completed New York weekday close; the production proof guard is unchanged (23/23 focused checks).

The two mapped/unmapped offline wire drills now check immutable research-call counts at the start of editorial generation and total physical calls at its end; every paid transport attempt still goes through the original wire budget. The adapter's 23 tests passed, including retries and rejecting stray calls outside that boundary. Production spend caps, approval records and trading authority were not changed. No live wire proof was run.

Narrow verification covered partial, legacy, failed, stale and REVIEW exports; section order and old links; injection and malformed input; rating definitions, coverage, sentence counts, source limits and locales. A separate three-case offline check verified that a supported target appears in the closing sentence only when `final_target_eligible` is true. An unsupported target and an ineligible “supported” target both use the no-target limitation. Normal customized languages can translate the fixed framing in the same request; offline fallback uses the known canonical English wording when no verified translation is retained. This keeps the rating meaning visible without introducing a translation service. Stale original records remain available in the companion for traceability; a failed/legacy re-export does not pretend to be a complete 5–12-sentence narrative.

**Candidate verification:** default `python -m pytest -q` completed in 66.94 s: **3,003 passed, 10 skipped, 1 deselected, 100 subtests passed**, with 24 warnings. The skips require an optional Bedrock dependency or separate private retained fixtures. Local Python 3.12 was exercised; hosted CI and other interpreter versions were not run. `python -m ruff check .` and `git diff --cached --check` passed. We inspected the full candidate change. The independent reviewer is asked to check this build against the governing plan, test changes and the above source/render evidence, including honest fallbacks and the publication and money boundaries.
