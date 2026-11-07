# Document access Build B — vendor calls and existing macro

Local implementation candidate. Required paid CLI observations are not authorized and remain incomplete.
No publication, release or installation acceptance is claimed.

## Baseline and isolation

- Accepted staging: b67f1c8444075048cb12921d9b758c53cfc9e886, identical accepted PR #8 source a066b6f874eca5c102f3e8a089dbcce599d86daa.
- Build A parent: 0376d61036e3b944bff40482deb918a579749d09 on codex/document-access-a. Initial e49260e9f13161a4e83d168450761ffd48240f72 remains an ancestor.
- Active branch: codex/document-access-b; worktree /Users/zipp/Developer/tradingagents-document-access-20261106/build-a, Machine 1 M1 Pro/16 GB.
- Plan SHA256: 724bf45c6326de8bb48e56fb662a5d825a7e93813efaae1efae753a32a2e09fe.
- Full private source wrappers, authorized credentials, proof ledgers, generated reports and runtime remain outside Git under the task root. Existing worktrees, staging, launcher, model pins, preferences, history, reports and other projects are preserved.

## Shipped behavior

An eligible SEC earnings source must explicitly identify its fiscal quarter/year and actual call date. Calendar quarter-end never substitutes for call date. Fiscal-quarter ambiguity, future calls or missing date evidence produce a reasoned unavailable result and research continues. An exact intraday historical cutoff with no reliable transcript publication/end timestamp conservatively withholds the full call until the end of its Eastern call day; call start does not establish complete Q&A availability.

Alpha Vantage transcript wording is unverified. Prepared remarks are bounded to 4,000 source characters with partial excerpts labeled. Fundamentals and News receive that context and use the same search_documents tool with an explicit transcript: query prefix for Q&A. Unprefixed searches remain SEC filing searches. Both share three calls per analyst, three whole passages / 12,000 source characters per call and a 200-character query limit. Final bull/bear questions can request either source; returned vendor passages stay labeled for RM/risk/PM and report as cited or unresolved.

The exact vendor body hash, normalized turns, date-source pin, scope, corpus and wrapper hashes are retained for replay. Resume does not replace source text from cache. Optional provider failures do not stop research. Quota notices, entitlement denial, key failures and transport failures are distinguished safely, without automatic provider retries.

All transcript figures remain unlinked vendor wording. Independent review rejected an unused helper that trusted caller-supplied acceptance/semantic fields and did not compare values. It and its misleading positive test were removed. Full verified company/metric/period/unit/basis/qualification comparability is unavailable in the current canonical claim schema; no positive numeric-link proof is claimed. SEC filing claims retain their separate quote/metric/period/unit/qualification validator and authority.

Existing FRED functionality is reused. The News prompt requests a short dated macro section or the actual unavailable reason. No macro feature, paid data service, article-body fetch, dependency, valuation case revision, pricing or range was added.

## Source observations and cross-company qualification

- Exactly one authorized free Alpha Vantage preflight: HTTP200, 56,967 bytes, 47 DOCN turns, no provider notice. Provider body SHA256 6629854cad9b0fc46741d887140210dbdd6da9acb36c837de3212bb2802da55a. SEC ex99.1 block-54 pins the November 3 call. No second availability probe was made.
- Official Alpha Vantage documentation lists the endpoint without a premium badge; general support describes the standard free allowance as 25 requests/day for most datasets. No endpoint-specific transcript quota guarantee was found. A later free response may be unavailable or limited; no paid entitlement is enabled.
- Six free FRED reads (series plus observations for FEDFUNDS, DGS10, CPIAUCSL) pinned observation_end and realtime_start/end to 2026-11-06. Latest observation dates were 2026-10-01, 2026-11-05 and 2026-09-01 respectively; no future dates were rendered. No-key behavior explicitly names FRED_API_KEY. Full model-run macro delivery is still unobserved.
- DOCN's retained response/date source is positive offline evidence. JPM's actual earnings release also supports an explicit dated call. Its bank Revenue tag is outside the existing canonical Revenue mapping; this is a deferred pre-existing scope finding, not new financial behavior.
- The proposed live pair is MSFT (software SIC7372) and CAT (machinery SIC3531). Their full filings fit the corrected finite 16 MB reader. MSFT has the existing accepted Revenue tag. Retained MSFT/CAT earnings sources do not establish the necessary explicit fiscal year/call date, so the transcript source is unavailable. Their offline tests verify that no vendor request is made from those ambiguous sources. No positive transcript coverage is claimed for them.
- Minimal public SEC excerpts are in tests/fixtures/document_access; full wrappers, hashes and publication references are private/inputs/non-docn*, evidence/document-transcript-cross-company.*, and evidence/document-transcript-msft-addendum.*.

## Verification and independent review

- Full Build B offline inventory: 2,836 passed, one optional langchain_aws skip, one configured deselection, 100 subtests; log build-b-offline-boundary.log.
- Full Ruff and pip check passed; no dependencies changed. Diff checks passed.
- Final collection: 2,838 selected / 2,839 collected (one DeepSeek live integration deselected by repository policy). The added candidate-branch boundary test was covered by 18 fresh proof-guard passes after the full run. The optional AWS-provider test remains skipped because its optional dependency is absent. This is complete combined offline inventory coverage, not one full run on the final source revision.
- Focused B/FRED source checks passed (64 tests plus 8 subtests). Actual Fundamentals/News node prompts receive labeled prepared remarks or unavailable reasons; their actual private analyst subgraphs execute prefixed Q&A searches. Vendor passages cannot become quoteable SEC packages.
- Actual checkpoint interruption after transcript fetch/cache and before source persistence resumes without a duplicate request; exact wrapper data is preserved. Search-call interruption, tamper rejection, legacy/report/publication recovery and canonical memory/scoring exclusions are covered with the retained A evidence and fresh affected checks.
- DOCN saved-state replay captures actual RM/risk/PM prompts with deterministic model responses. Markdown/HTML/CLI display citation-or-unresolved outcomes. Ready and unavailable transcript reports were rendered in isolated headless Chrome on M1 and visually inspected on the coordinator.
- Independent code/artifact review is in evidence/document-build-b-independent-audit.md. Confirmed call-start and unsafe linkage findings were closed. Proof-tool independent review is in evidence/document-proof-independent-review.md; confirmed false-success, account-receipt, failure-observability, credential and candidate-branch findings are addressed before live authorization.
- The public proof runner and its guard tests are versioned under docs/reviews/document-access-proof-tools and tests. Default/qualification performs local reads only. A fresh hash-bound approval, exact clean candidate, per-attempt fresh usage/endpoint receipt, authorized source credentials and conservative reservations are required to send a paid request.
- One advisory audit pass permits at most two model-call attempts (one application retry); SDK retries are disabled. Unknown-cost reservations remain held. A CLI failure consumes its single ticker attempt; there is no automatic rerun or top-up.
- Passing evidence is reused only for unchanged source/dependencies/configuration/impact. Final affected harness checks account for changes after the full suite; combined evidence is not a full suite on one final revision.

## Pending acceptance and authority

No new paid model calls have been made. All old ledgers remain intact, with $6.587296 unknown reservations held separately; old attempt authority is exhausted and is not stacked with a new budget.

A separate fresh allowance will be requested for at most three Medium-depth CLI attempts, one each DOCN/MSFT/CAT, using anthropic/claude-opus-5.5 quick and openai/gpt-6.1-terra-pro deep, all four analysts, three research/risk rounds, four tool rounds and 16,384 maximum output tokens. DOCN must observe a positive dated transcript and successful dated macro output; MSFT/CAT may prove explicit unavailable continuation without claiming positive transcript coverage. Missing observations remain explicit and do not become successful positive proof.

Vendor transcript revisions/publication vintage cannot be verified retrospectively from this endpoint. Its wording stays unverified, never accepted financial evidence. The data cannot supply undisclosed operating facts or establish predictive ratings.

Valuation Build 2/A3, the comparison, publication and installation remain held. No push, PR, merge, production change, worktree removal, scheduler or broker action is authorized. Exact-head GitHub CI awaits separate publication approval.
