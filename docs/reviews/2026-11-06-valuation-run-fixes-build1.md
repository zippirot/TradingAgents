# Valuation run fixes: Build 1 checkpoint

Authority: user Goal on 2026-11-06 plus Amendment 1 and explicit third-proof approval. **Current status: Build 1-specific acceptance met by the third run; case generation and Build 2 are unproved and held.** Earlier chronological checkpoints below retain their original outcomes; the latest outcome and scope rationale are at the end. Publication, comparison and installation remain held.

## Isolation and governing inputs

- Verified Machine 1: Apple M1 Pro, 17,179,869,184 bytes RAM.
- Base and fetched GitHub staging: `89aae4965ecbeb6f1a0efeaf73371922a16789c1`; no drift.
- Worktree: `/Users/zipp/Developer/tradingagents-valuation-range-20261106/build1`.
- Branch: `codex/valuation-run-fixes-build1`.
- Governing plan: `/Users/zipp/Claude/2026-11-06-valuation-range-and-run-fixes-plan.md`. Exact plan/four retained DOCN states and manifest are outside Git in task `private/inputs`; transferred hashes verified.
- Amendment: `2026-11-06-valuation-range-and-run-fixes-plan-amendment-1.md`, SHA256 `d49615e27c6c173c5ad42a07f9d738f4ed5f450ae12ecfe819e3dc6c5cbe50ee`.
- Agent setting verified from current task metadata: GPT-6.1 Sol, medium. Development/testing stayed on Machine 1. The launcher at `e482070`, model pins, credentials, preferences, original reports/history and prior worktrees were not modified.
- The environment is an APFS clone of the preserved prior verification environment, with task-local editable paths. All 90 noneditable dependency pins match; the original environment was not modified.

## Delivered scope

1. New Portfolio Manager decisions have a required horizon field/contract. Missing or invalid horizons remain explicitly incomplete, with valuation unsupported and the PM rating preserved. Legacy states remain readable; no horizon is inferred from a forecast.
2. Audit records safe failure categories, bounded request character/UTF8 byte sizes and finish status. A dedicated deep client has actual SDK retry count zero; at most one application retry. Authentication/invalid-request/budget-stop errors do not retry. Exact quote/source validation and advisory authority remain intact.
3. Accepted filing-linked financing authorizations retain amount, type, agreement/filing dates, complete quote, source hash and locator. Authorization does not establish issuance or remaining capacity. A dollar symbol alone does not verify currency: the DOCN record retains source `$` and unknown denomination unless an explicit local statement establishes it.
4. Unsupported peer share classes now identify the bounded offending QName and missing class/economic-rights evidence. CRWV is not guessed into acceptance. The baseline already has eligible-period filtering; no new foreign-filer parser was added for NBIS.
5. Model and deterministic disclosure extractions/counts are separate; duplicate accepted claims need not add to the merged total. Full rejected details stay in evidence; a summary replaces per-record quality-warning noise without weakening critical checks. The model block remains because retained replay demonstrates a unique model-supplied cash disclosure.
6. Sell levels are advisory thesis invalidations, not execution stops or short instructions. Buy stops and legacy entry compatibility remain.
7. Run metrics retain observed input/output usage and complete/partial/unavailable coverage across missing responses/retries/resume. Provider-internal retry usage remains explicitly potentially unreported; counts are not billing totals. Markdown/HTML footers expose the record.
8. Retained news failure says Yahoo had no tagged news response. It does not retain a transport-error diagnosis. Existing quote/search fallback and bounded rate-limit retry tests pass; no speculative additional retry was added.

### Amendment application

A1 and A2 were added before the first commit, after provisional source review. Their own diffs received focused independent review.
- A1: the pre-analyst brief replays only the retained acquisition-time deterministic RPO packages, bound to issuer/cutoff. All four analyst factories receive the exact canonical comparison and cause/demand caveat; no graph reorder, model output or extra call.
- A2: stable content/scope finding IDs link optional PM accepted/rejected responses and reasons. Unknown/malformed/duplicate replies are rejected diagnostically; missing replies are unanswered. Tolerant advisory input cannot invalidate the core PM decision, trigger a retry or create a publication gate. The report discloses same-model review of RM/PM and absence of an audit of PM's own text.
- A3 belongs to unstarted Build 2. It is recorded for that separate approval; no dated short-term value/link or Build 2 pricing/card range was implemented.

## Diagnosis adjustments and retained replay

Historical Opus invocation-versus-parsing cause cannot be recovered: the exception/raw response/finish metadata was not saved. The reconstructed bounded prompt size is an observation, not proof of a size-related failure.

Current validation of original model submissions gives Terra 0 accepted/8 rejected, Opus 0/20, DeepSeek 1/17 (the accepted item duplicates deterministic discovery), split 1/24 (a unique cash disclosure). The plan's inferred zero count for DeepSeek was inaccurate. All four single-source deterministic extractions accept 15 records. Original input bytes remain unchanged.

Four complete Markdown/HTML reports, CLI redisplays, source briefs and diagnostic sidecars are retained privately under `private/evidence/build1-retained-review`. They are labeled offline current projections, preserve original canonical ratings/targets, and do not verify historical publication-store identity. Legacy audit unanswered counts are 0/0/10/1; synthetic ten-answered and four-answered/six-unanswered cases are separately labeled. Original snapshots lack token usage; the footer reports unavailable. Root and independent review inspected the supplement; all four HTMLs fit the 1440px viewport with no cell-text overflow, and wide tables retain scrolling.

## Verification and evidence reuse

A stable-source full offline run produced **2,719 passing tests, three failures, one optional Bedrock skip, one paid integration deselection and 100 passing subtests**. The three failures were the shared scripted PM fixture dispatching only the old schema, causing fallback. The fixture was updated to answer the new required-horizon schema with an explicit fixture horizon; assertions were retained.

All four modules using that fixture were rerun: **65 passed**. This completes the failed/affected graph, thesis, evidence-gate and real-CLI offline adapter paths. The other passing full-run results are reused: only those two fixture files changed, runtime/dependencies/configuration are unchanged, and direct fixture importers were inventoried. This is combined evidence, not one full passing run on one revision.

Full Ruff, pip check, staging-relative diff check and full inventory passed. Focused red/green and recovery evidence is recorded in task `evidence/`; independent review separately passed the amendment/source/retry/metrics boundaries. Ordinary tests block network; no paid integration test was run. An unverified or unavailable audit remains distinct from zero findings.

## Paid proof authority and preflight gate

Fresh allowance: **$24 aggregate / at most two CLI attempts / $12 per build**. It replaces unused old Part B authority; no stacking. This Goal may consume only Build 1's one attempt. Prior ledgers stay unchanged, linked by hash. No extra CLI attempt, report, top-up or other paid API call is authorized.

The proof guard binds the clean committed candidate, Machine 1/worktree/module origins, exact user authorization, existing ledger hashes, actual after-close session metadata and refreshed served-route prices/usage. Models are `anthropic/claude-opus-5.5` quick and `openai/gpt-6.1-terra-pro` deep, all four analysts, depth 1, 16,384 output tokens, four tool rounds, normal clocks, no pinned peers or frozen sources. All SDK retries are disabled for the proof; the bounded audit retry is inside the same attempt/cost cap.

Requests reserve conservative served-route input/output/cache costs before transmission, serialize reservation/read/settlement, and retain unknown-cost reservations. A sticky budget stop forbids further sends. Durable exclusive job/runtime/ledger paths prevent duplicate launches. Private request observation retains approved body bytes/hash/ticket only, never authentication headers; fixtures qualify that observer but are not live proof.

Proof, final candidate hashes/cost review and live observations remain pending in this checkpoint. No release acceptance or exact-head GitHub CI is claimed; those require authorized publication.

Pre-live setup correction: query1 returned HTTP429; the standard query2 endpoint returned actual current metadata. Independent review caught the guard allowing only query1. It now accepts exactly the two official DOCN chart URLs with the same path/query, preserving the true receipt URL and every hash/time/close check. Regression: query2 failed before correction; both exact endpoints pass and wrong host/ticker remain rejected. This affects proof receipt validation only, not application runtime/source inputs; B3/Build1/CLI guard checks were rerun. No attempt had started. The original frozen commit remains in branch history; a new candidate includes this correction.


## Actual proof outcome — incomplete, review required

Frozen paid source candidate: `493083c71c4f2c7d64c888955f962d9237f4d0fa` (core implementation `0db69f881161b74f36ea669f581db9c96199d704`). The candidate remained clean and unchanged throughout the attempt. A subsequent documentation-only checkpoint does not establish a new live proof.

Exactly one authorized CLI attempt ran after the actual November 6 US close: start `2026-11-06T21:55:15.523997+00:00`, finish `2026-11-06T22:01:30.308350+00:00`, close `21:00 UTC`. All four analysts ran at depth 1 with the approved Opus quick/Terra Pro deep configuration; preferences and launcher were not changed. Its report is `private/run-fixes-build1-live-proof/results/reports/DOCN_20261106_150129`. The completed canonical close is `72.4800033569336 USD`, session `2026-11-06`, retrieved after close. This is a live observation, not a fixture.

The run correctly ended in **REVIEW**. Fundamentals Claim 0 labeled TTM revenue `reported`; the canonical source fact is `derived` through `four_quarter_sum_v1`. All four quarters sum to `1,102,671,000 USD`; value and dates matched but origin did not. Independent review confirmed the rejection: 29 claims were accepted; correcting that label only in an explicitly diagnostic in-memory copy yielded 30 accepted. No saved live output was changed, and no validator relaxation or speculative prompt change was made. Audit and Portfolio Manager were correctly bypassed. Therefore live audit, horizon, Sell, PM dispositions and downstream publication observations remain missing. Offline checks do not replace them. The required positive proof is incomplete.

The CLI saved the REVIEW/no-action report; the proof wrapper recorded failed status and wrote no success receipt. Ten requests were reserved; nine have settled charges totaling **$1.895472**. One HTTP 400 has an unknown reservation of **$1.486000**, retained unchanged: committed exposure **$3.381472**. One free post-run key-usage read matched the settled total exactly but is aggregate evidence, not an individual billing receipt. No cost was assumed zero. See `evidence/run-fixes-build1-cost-reconciliation.json`.

The Build 1 attempt is consumed. Remaining dollar headroom does not authorize a rerun. The second attempt is reserved for separately authorized Build 2, which remains held. No additional paid call or CLI attempt will run without explicit new/reallocated authority. Build 2, comparison, publication, installation and all release actions remain held. Exact-head GitHub CI is pending authorized publication.

Verification after the original offline inventory: the exact endpoint receipt guard regression failed before correction, then 95 focused guard/CLI/audit checks passed; full Ruff and diff checks passed. Other full-run results and the 65-case fixture correction are reused with the source/dependency/configuration/impact reasoning in `evidence/combined-verification.json`. This remains combined evidence, not one full passing run on this revision. Final live diagnosis/review/artifact records are private sidecars; source inputs and old ledgers remain preserved.


## Reallocated final attempt and corrective checkpoint

The user explicitly approved “Reallocate the remaining slot to Build 1” in response to the recorded $12-within-$24 question. This superseded the reserved Build 2 slot, not the dollar ceiling. The exact question/answer and immutable first-attempt linkage are private records. Independent review and 12 network-blocked private guard tests verified the fixed second-attempt paths, legitimate Build 1 binding, original unknown reservation, no duplicate/third launch, $12 attempt cap and unchanged $24 aggregate. No historical ledger was rewritten.

Attempt 2 used clean documentation checkpoint `12b37d3412aafc293ee8261309e03915b51a0bcd`; application source was identical to `493083c`. It ran from `2026-11-06T22:17:03.391369+00:00` to `2026-11-06T22:23:15.550798+00:00`, at the same approved depth/models after the actual close, with fresh free usage/rates/session receipts. Rates were unchanged. Its actual report is `private/run-fixes-build1-attempt2-live-proof/results/reports/DOCN_20261106_152315`.

It again ended in REVIEW at Claim 0, explicitly emitted as `kind=reported` for a canonical derived TTM revenue fact. No schema default injected that value. Thirty other claims were accepted; a diagnostic-only in-memory kind correction gives 31 accepted. Original live artifacts remain unchanged. Both reports correctly exclude actionable decisions, decision memory/thesis and all five eligible publication/scoring endpoints. The canonical November 6 completed close and sourced A1 comparison were consistent in both runs. The second run made 11 calls, with 10 observed usage receipts; Markdown/HTML correctly mark partial usage (319,710 input / 35,324 output). Live CLI token-footer display was not observed; token recording itself was observed. Both actual HTMLs were inspected, 218 cells each without text overflow. Audit/PM/risk and their downstream horizon/Sell/A2 behavior were not observed live.

Independent prompt/caller diagnosis found a narrow ambiguity: the extraction instructions said to copy `kind` from the financial-evidence tool, but the canonical attribute is `origin`, and the derived TTM fact appeared in the shared source brief rather than that tool's bounded raw-fact subset. The correct origin was available in the prompt. This is not proof that ambiguity caused the model error. The corrective source diff explicitly maps claim `kind` to canonical fact `origin`, permits the canonical shared-brief records as well as the tool, and says a derived four-quarter sum stays derived even when quarter inputs are reported. Claim validation remains unchanged. A prompt-version checkpoint tag prevents silently resuming under the old instruction. No additional call, retry, invented evidence or forced output was added.

The prompt contract regression failed before correction. After correction, **109 affected tests passed**, followed by **25 caller/checkpoint tests** after adding actual-factory delivery and old-thread separation assertions. Full Ruff, pip dependency and diff checks passed. Existing passing calculation, source, schema and renderer results are reused because those paths/dependencies/configurations are unchanged; full evidence reasoning is in `evidence/combined-verification.json`. The correction has **no live proof**, and its effectiveness with the model is unknown. This record does not claim that offline fixtures establish it.

Final spending for this fresh allowance: **$3.880792 settled**, **$2.972000 unknown reservations retained**, **$6.852792 committed exposure**. Each one-free-GET post-run account delta exactly matched its settled charges, but neither provided per-ticket proof to release the two HTTP 400 reservations. There were **two CLI attempts, two starts, 21 reservations; zero attempts remain**. Unspent dollars are not attempt authority. Build 2 now needs fresh proof authority as well as its separately required implementation approval.

**Build 1 remains incomplete:** required positive live audit/PM/horizon/Sell/A2 observations and proof of the prompt correction are missing. No third attempt, publication, comparison, installation, merge, push, cleanup, scheduler or broker action is authorized. The corrected source and synchronized review checkpoint are ready for the user's review; exact-head GitHub CI still awaits separately authorized publication.


## Third proof — Build 1-specific acceptance met

The user separately approved one third Build 1 attempt capped at $12 within the unchanged $24 aggregate, on corrected source `433fc966c2c432716c3779e7339086cf0482b954`. This increased attempt authority to three; it did not stack a budget or authorize a fourth, Build 2, comparison or release. The inherited adapter's `attempts=2` marker is the original per-ledger schema, explicitly distinguished from current total-three authority in the third link/job. Fourteen network-blocked private guard tests, Ruff/compile and independent binding review passed. Both original ledgers/runtimes/jobs were immutable; all previous unknown exposure was retained.

The third actual CLI application ran `2026-11-06T22:40:26.491545+00:00`–`2026-11-06T22:52:25.806151+00:00`, after the actual November 6 close at `21:00 UTC`, with all four analysts, depth 1, Opus 5.5 quick/Terra Pro deep, no peer pins or saved-preference changes. Fresh free usage/rates/session receipts were retained; rates were unchanged. The report is `private/run-fixes-build1-attempt3-live-proof/results/reports/DOCN_20261106_155224`, with an actual `cli-receipt.json`.

Observed Build 1 outcomes:

- The original TTM revenue claim now explicitly has `kind=derived`, matching its canonical fact. All **31 structured financial claims passed** the unchanged validator; lineage revalidation had no errors. This one run demonstrates correct labeling, not a guarantee of future model compliance or proof of causality.
- Every initial analyst request contains the exact sourced deterministic RPO comparison and caveat; no A1 model call was added. The canonical completed November 6 close is `72.4800033569336 USD`, consistently sourced and retrieved after close.
- Source coverage remains **limited: 20 checks passed, zero failed, six unavailable**, including source-precision limitations; passing structured claims do not validate every narrative judgment.
- The advisory audit completed in one call with **seven findings**: two contradictions, four numerical inconsistencies, one unsupported claim; all seven passed quote/source-label validation, none were rejected. These remain advisory model judgments. Request size: **193,954 characters / 194,507 UTF8 bytes**; finish `tool_calls`, no error, no retry. The report honestly states the auditor differs from analyst models, shares the Research/Portfolio Manager model, and does not audit the PM's own text.
- The PM answered **all seven findings**, accepting each with a reason; zero unanswered or invalid responses. The canonical rating remains the PM's **Underweight**, with an explicit **six-month** horizon and risk-assessment basis. A2 added no model call or gate.
- The natural Trader action was Sell. Its 88.00 level is labeled advisory thesis invalidation/reassessment, explicitly not an execution stop or short instruction. No supported final target or allocation is promoted to trading authority.
- One research round and one risk round completed. Token coverage is honestly partial: **1,081,421 observed input / 68,257 output tokens, 18 usage receipts for 20 calls**. Sentiment and Trader used their existing free-text fallbacks after HTTP 400; those unreceipted costs remain reserved. The live CLI token footer was not observed, while saved Markdown/HTML retain the metrics.

The normal application completed without an exception and saved its receipt. The outer proof wrapper nevertheless marks `failed` solely because it conservatively flags **two unknown-cost reservations**. That safety flag is preserved, not relabeled as a passing wrapper. It does not erase the independently inspected positive application evidence; retaining unknown reservations is an explicit Goal requirement, not an instruction to infer zero cost. No rerun follows that flag.

### Scope and remaining observations

Fundamentals hit the fixed **16,384-token output cap** and ended during its disclosure JSON, before the `valuation_scenarios` fence. Thus **no structured case proposal was observed** in this run; the card correctly publishes no supported valuation. This is truncation, not a reasoned empty-case choice. Existing `analyst_prose` strips even a truncated recognized structured block, so it does not swallow later report sections. No fourth run or output-cap increase is authorized.

The mixed plan's general actual-case-proposal observation remains unproved. It is not claimed satisfied merely by choosing Opus. For this **Build 1-only Goal**, the explicit independently releasable Build 1 boundary and instruction not to hold it for Build 2 control: all eight fixes and A1/A2 now have their applicable offline and live evidence. Case creation, capital assumptions, pricing/ranges, A3 and their case-feature proof remain with unstarted Build 2. Independent completion review records this scope interpretation while preserving the literal general-proof limitation. Natural Sell/nonzero findings happened here; they were not invented additional live gates. Forced retry, missing/malformed dispositions and legacy edge cases retain their offline evidence rather than being claimed observed live.

Final fresh-allowance totals across **three attempts**: **$7.87506405 settled**, **$6.587296 unknown reservations retained**, **$14.46236005 committed exposure**, below $24. The third alone settled $3.99427205 and retains $3.615296 unknown exposure, totaling $7.60956805 below its $12 cap. Each one-GET account reconciliation matches settled charges, but does not establish individual HTTP 400 billing. All ledgers remain unchanged; zero paid attempts remain. The app, launcher `e482070`, pins, credentials, original inputs/reports/history and other worktrees were preserved.

Source is unchanged from `433fc966` except this final documentation checkpoint. Existing passing full inventory, 65-case fixture correction, 95-case receipt checks, 109 affected prompt/recovery checks and 25 final caller/checkpoint checks are reused with recorded source/dependency/configuration/impact justification. Full Ruff, dependency and diff checks passed. This remains **combined verification evidence, not one complete full-suite run on the final revision**. Independent code/actual-artifact review found no unresolved material Build 1 defect. Live audit retry, provider-internal usage and case generation retain their stated limits.

**Delivery boundary:** Build 1 is ready for review. No push, PR, merge, installation, production change, worktree removal, scheduler or broker action occurred. Exact-head GitHub CI and release acceptance await separately authorized publication. Build 2 and the comparison remain held.

Final actual-artifact inspection passed 26 checks. Full HTML had 733 cells without overflow; downstream headings and all seven audit responses remained outside code blocks despite the truncated original disclosure block. Root visually inspected the hash-verified actual audit/PM excerpt; source quotes retain minor literal HTML-entity artifacts, a cosmetic deferred limitation. Final code-and-artifact reviews found no unresolved material Build 1 issue.
