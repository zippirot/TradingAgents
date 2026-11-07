# Document access Build B — vendor calls and existing macro

Local implementation candidate. Paid proof was subsequently approved for three attempts on 93a1ae5; two attempts are consumed. Required acceptance remains incomplete.
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

The original frozen-candidate approval and all old ledgers remain intact. The older $6.587296 unknown reservations remain separate; old attempt authority is exhausted and is not stacked with this task’s allowance.

The user subsequently approved $72 aggregate, $24 each, for at most three Medium-depth CLI attempts on 93a1ae5, one each DOCN/MSFT/CAT, using anthropic/claude-opus-5.5 quick and openai/gpt-6.1-terra-pro deep, all four analysts, three research/risk rounds, four tool rounds and 16,384 maximum output tokens. DOCN must observe a positive dated transcript and successful dated macro output; MSFT/CAT may prove explicit unavailable continuation without claiming positive transcript coverage. Missing observations remain explicit and do not become successful positive proof.

Vendor transcript revisions/publication vintage cannot be verified retrospectively from this endpoint. Its wording stays unverified, never accepted financial evidence. The data cannot supply undisclosed operating facts or establish predictive ratings.

Valuation Build 2/A3, the comparison, publication and installation remain held. No push, PR, merge, production change, worktree removal, scheduler or broker action is authorized. Exact-head GitHub CI awaits separate publication approval.

## Post-approval observations and correction checkpoint

Two attempts on exact 93a1ae582c1ebf1b50761c7dff92b243bcd25074 are consumed; neither may be rerun under this authority. CAT has not started. No release action is approved.

- DOCN ran after the actual November 6 NYSE close, all four analysts, three research/risk rounds, 33 wire calls. Its CLI completed with an Underweight research rating and six-month model-stated horizon. The original proof job failed because its inherited Build 1 check required a same-analysis-date close. Actual canonical data explicitly used the November 5 completed close, $70.70, because the November 6 bar had no Close. That fallback is shown on the rendered card; November 6 close/indicators were not observed by this CLI. A separate preflight close is not substituted.
- Original report evidence retains eight full documents, six searches, four debate questions with returned passages, a dated November 3 vendor transcript (47 turns), and four dated macro outputs. Read-only recovery from those exact saved artifacts validated the new source/journal fields. The main state-log projection omitted those fields and nested debate questions; original job/log files are preserved as failing evidence rather than rewritten.
- The original rendered DOCN report was visually inspected using isolated M1 Chrome CDP captures after simple screenshot capture produced blank images. Search counts, unverified transcript labels, dated fallback and all four unresolved follow-up labels are readable. All four questions remain unresolved because the published final decision did not cite a returned source reference. These are actual missing citations, not a claim that a source was absent.
- MSFT’s single attempt ended in REVIEW before research/risk debate. Its 29 submitted financial claims passed, but critical reconciliations lacked large primary filings rejected by the old bounded reader’s 2.5 MB transport limit. The new full-search reader had acquired them. A subsequent offline replay with the corrected transport reads both large primaries while preserving 40,000 extracted characters each; some accounting reconciliations remain unavailable within those existing brief limits. Two other selected source files are absent from the retained replay cache, so its disclosure-coverage result also has a fixture limitation. Increasing transport is necessary but is not evidence that all MSFT REVIEW causes are resolved. This attempt does not establish late-role delivery or a complete unavailable-transcript continuation.
- Two runs have $11.46117315 known settled usage and $5.450528 retained unknown reservations, $16.91170115 committed exposure. Three HTTP400 structured-call responses lacked usage; their holds are not cleared by observed account deltas. No extra attempt or top-up is authorized.

The correction batch repairs bounded primary transport without changing the accepted brief’s filing selection or character caps, retains new source fields/questions in standard logs, supplies bounded labeled transcript/follow-up material to the existing advisory audit call, and corrects the document-only price verifier. Build 1’s stricter proof remains unchanged. New audit input has not been observed in either consumed live attempt.

A replacement committed candidate must pass affected offline checks and independent review before requesting a CAT-only rebind to that exact SHA. The original allowance, two consumed claims, unknown holds, model/depth/configuration and three-attempt ceiling remain intact. No CAT call is authorized on changed code until that rebind is approved. The original job failures remain recorded; recovered source evidence and offline corrections do not become a single full live run on the replacement revision.

### Correction verification

The stable correction batch passed a fresh full offline suite: 2,851 tests plus 100 subtests, one optional AWS dependency skip and one configured live-integration deselection (31.01 seconds). Full Ruff, pip dependency check and diff check passed. This broader rerun is justified by changes across source acquisition, advisory audit inputs, standard state logging and paid proof authorization boundaries. Actual DOCN and MSFT retained report evidence passed the corrected standard log round-trip offline; MSFT correctly lacks post-debate fields because it entered REVIEW. Original paid outputs and failure records remain unchanged. Fresh source/log hashes are in evidence/build-b-correction-verification.json outside Git.

### CAT source qualification: final paid slot preserved

Seven fresh free SEC GETs acquired the two missing selected 8-Ks, their three selected exhibits, the prior 10-Q and CompanyFacts into new immutable private wrappers; no retries, original-cache substitution or model calls. The offline existing pipeline parsed 615 canonical facts / 470 sources and seven bounded filing documents. Disclosure coverage, source integrity and balance-sheet checks pass. Critical core statements (compatible Net Income at 2026-09-30), dated equity movement, obligation-category coverage and equipment/lease principal cash-flow coverage remain unavailable. Qualification SHA256: aa894a2a5828b5cd9a42517691dfaecbf5c8f9c1dee57f8167e626290dbdc39d, private/inputs/cat-qualification/qualification.json. These are pre-analyst source preconditions; model prose cannot make their absence a verified value. No complete non-REVIEW CAT outcome is qualified.

The last CAT attempt remains unclaimed. The recommendation is to preserve it and obtain a separate scope decision for the existing accounting-source coverage before spending it. The document-access correction candidate is locally verified; cross-company full-run acceptance remains incomplete. Accounting source/tag/period changes are not silently added to the approved search/transcript build, and no REVIEW gate is weakened. The draft-only CAT rebind helper remains unused as authority. A later CAT attempt still needs an exact repaired-candidate approval and fresh usage/rate receipt; no extra attempt or top-up is implied.

### Deferred accounting-source scope decision

CAT CompanyFacts has no eligible us-gaap/NetIncomeLoss row ending 2026-09-30, the sole current Net Income mapping. It has distinct ProfitLoss ($3.286B Q3 / $9.427B YTD) and NetIncomeLossAvailableToCommonStockholdersBasic ($3.287B / $9.429B), filed November 4 in accession 0000018230-26-000057. They must not be blindly aliased. The full retained 10-Q has 962 blocks: equity statement heading block-92, table block-95, cash-flow table block-118. The bounded selection retains the equity table but omits its heading; current verification does not establish complete dated movement/principal bridges. Required obligation categories or explicit sourced zeros remain unverified.

The proposed separate local scope is definition-aware income mapping plus preservation of statement/table date context and source-supported equity/obligation/principal extraction, tested against retained DOCN, MSFT and CAT sources. Unknown amounts remain unavailable; no gate downgrade, invented zero, new reasoning call, new service, paid attempt or release action is implied. This is broader accounting extraction than the approved search/transcript change and needs a scope decision before implementation. The last CAT slot remains preserved.
