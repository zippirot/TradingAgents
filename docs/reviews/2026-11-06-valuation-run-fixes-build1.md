# Valuation run fixes: Build 1 checkpoint

Authority: user Goal on 2026-11-06 plus Amendment 1. Build 1 only; Build 2, the comparison, publication and installation remain held. No paid attempt has started at this checkpoint.

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
