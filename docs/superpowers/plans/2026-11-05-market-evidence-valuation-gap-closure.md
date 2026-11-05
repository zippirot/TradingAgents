# Market evidence and valuation gap closure

Date: 2026-11-05. Revision 2: independent Build 1 release, live session proof, explicit suitability and remote handoff. Status: revision 2 approved for autonomous implementation by the user on 2026-11-05. The user separately authorized a new $10 aggregate budget for at most three paid CLI attempts, with no retry reserve. Publication and installation remain unauthorized. The original approved input is frozen by hash outside Git.

## Outcome and evidence

A run during market hours must consistently distinguish completed-session analysis from intraday observations. News outages must use the available fallback. Every eligible report must explain the multiples represented by its observed price, independently of model-generated target requests. All selected analysts must receive the same available primary-source facts before reasoning. Preserve research usefulness without presenting assumptions as facts or recommendations as executable orders.

Reviewed installed baseline: `6340c9df6cd557195ea13ae994d19bd874b00746`. Inputs:

- `/Users/zipp/Claude/tradingagents-docn-nov5-gap-assessment-2026-11-05.md`.
- User-supplied November 5 review and report in attachments `644fe88d-0614-4861-b87a-8629bd49e4cd` and `73046366-73e9-4cac-8837-6ed48d3e48db`.
- Saved run `/Users/zipp/.tradingagents/logs/reports/DOCN_20261105_100518`, including `evidence.json`, `diagnostics.json`, `quality.json` and complete report.
- Canonical price in that evidence: November 4 completed close approximately $84.02; narrative technical snapshot: November 5 unfinished bar at $74.24. The distinction is established by retained evidence, not a new market-price lookup.

This is a new follow-up plan. Do not overwrite or reopen `2026-11-05-docn-remaining-gap-closure.md`, its accepted proof deferrals, or the unrelated Kairo branding draft. The earlier implementation's completed checks do not prove these new behaviors.

## Delivery estimate

- Build size: **extra medium** overall; Build 1 small-to-medium, Build 2 medium, Build 3 medium.
- Recommended primary model: **GPT-6 Astra (`gpt-6-astra`), medium reasoning**. Moving acquisition across graph/checkpoint boundaries while preserving immutable publications and reconciling share, time and obligation bases requires cross-system data-lineage judgment. This recommendation follows the user's routing policy; it is not a claim about the current model or measured speed/cost superiority.
- Bounded supporting work: GPT-6 Sol (`gpt-6-sol`), medium, for the news fallback, action-aware fields and focused tests. Delegate only independently owned work; never concurrent edits to shared graph/state/valuation files.
- Active implementation and verification: **18–29 hours**: Build 1 4–6, Build 2 5–8, Build 3 4–7, boundary/final verification and audit 5–8. Build 1 is independently releasable after its own acceptance; market-open scheduling and release-decision waits are excluded. Excludes external waits and future outcome maturation; assumes existing providers and dependencies suffice.
- Codex credits: not credibly estimable without workload usage measurements. API verification costs are separate.

## Execution and release boundaries

After approval, inspect applicable instructions and current Git state. Use Machine 1 for development and sustained verification: `zipp@100.89.132.10`, SSH key `/Users/zipp/.ssh/tradingagents_machine1`, `IdentitiesOnly=yes`, `BatchMode=yes`, `StrictHostKeyChecking=yes`. Verify M1 Pro/16 GB before mutations. This M2 Mac coordinates and retains its installed launcher unchanged until separately authorized installation. Machine 1 remains the standing compute choice; the reviewer’s suggestion to move development here is not treated as a user-approved machine change.

Fetch canonical GitHub `staging`, record its exact SHA, and compare it to the reviewed baseline. Inspect intervening changes and reassess affected assumptions; do not substitute another branch or discard work. Establish a new isolated `codex/` feature branch/worktree from verified staging, record its paths, and explicitly transfer this plan. Do not assume an old retired feature worktree exists. Keep long jobs logged and recoverable after SSH interruption; check for existing jobs before restarting.

### Remote evidence and credentials handoff

Before remote work, create a manifest of exact inputs: this plan, the assessment, the saved November 5 report tree, its associated retained full state/tool logs if needed, and only the publication records plus referenced immutable snapshots needed to prove prior-thesis linkage. Resolve references using the existing publication loader; do not copy a directory merely because its name looks related. Freeze a read-only input copy outside the installed checkout. Record relative paths, sizes and SHA-256 values; recheck originals for concurrent change. Transfer the explicit manifest members over the verified SSH connection into a private task-specific directory outside Git on Machine 1. Verify every destination hash and publication reference before replay. Write replay outputs to a different directory. Never copy the whole runtime/cache/history or import these inputs into Machine 1’s normal runtime.

Inspect the existing Machine 1 private verification configuration for required key names and validity without printing values. Prefer an already authorized usable key there. If necessary, securely transfer only the existing OpenRouter key and authorized SEC contact from this Mac to a task-private mode-0600 file under a mode-0700 directory over SSH, never through command arguments, chat, logs, Git or an environment dump. This is same-project verification on the already authorized development machine, not permission to expose credentials elsewhere. Preserve existing private files; do not overwrite another task’s configuration. Check retained provider/model settings and refresh usage against the same key before calls. No new key or FRED key is required for offline work. Record nonsecret paths and whether configuration was reused or securely provisioned.

Preserve installed applications, keys, preferences, user reports, memory, publication stores, old checkpoints and other branches. Use isolated results/cache/memory/preferences for tests and live proofs. Retained historical artifacts are inputs, never edit targets. Keep schema/API/report compatibility or provide a narrow explicit read adapter for legacy records. No automatic rewrite of existing publications.

No new paid data service, scheduler, broker functionality, mandatory portfolio-input step, full DCF/forward cash-flow engine, generalized calendar service or unrelated branding/refactor. Do not add another valuation engine or persistence system when existing modules suffice.

## Build 1 — consistent market data, resilient news, unambiguous proposals

### 1A. Completed-session market tools

**Files:** `tradingagents/dataflows/vendors/yahoo/{ohlcv,snapshot,price_observation,fundamentals}.py`, existing stock/indicator callers and `agents/analysts/market_analyst.py`; relevant state/configuration only where necessary.

Reuse the existing session-finality and price-provenance mechanisms. Apply one resolved observation cutoff and instrument/session interpretation to stock-data, deterministic snapshot and indicator inputs. Completed-session indicators must exclude the unfinished daily row before calculation, including cached data. Do not merely relabel indicators already calculated with that row.

Retain session date, exchange timezone, retrieval time, finality status and source identity. A supported, actually observed intraday quote may appear separately with its timestamp and explicit provisional status; do not manufacture a last-trade timestamp from a daily-row date or retrieval time. Intraday availability is optional and cannot block completed-session research. A provisional high/low must not silently become a finalized execution reference.

Respect explicit historical cutoffs, exchange-local session clocks, DST and available session-end metadata. Unknown completion metadata must not promote today's row to final. Preserve existing crypto/non-US applicability and unavailable/stale-data behavior. Do not assume a universal US 4 p.m. close. Keep the existing cache and its 15-minute same-day TTL; filter unfinished rows after loading, before every completed-session calculation. No cache redesign, new cache store or broad invalidation policy is in scope. The TTL still permits a pre-close cached row to be read immediately after close: narrowly require a post-session retrieval for promotion of that row, refresh it through the existing fetch mechanism, or retain the prior completed session until refresh. Test that boundary; elapsed clock time alone is not evidence the stored bar became final.

Vendor fundamentals snapshots must also label price-dependent market cap, trailing P/E and forward P/E with retrieval time, available quote timestamp/session status, and vendor-defined share/earnings basis. Retrieval time is not proof all constituent values share that timestamp. Unknown source timing remains unknown. Do not label these vendor ratios as completed-close canonical calculations or rescale them by a price ratio. During Build 1 distinguish them from canonical completed-session evidence; after Build 2, link readers to its qualified table for authoritative deterministic comparisons. Preserve the independent limitations of vendor forward earnings and do not imply $9.91B is an unqualified current market cap: it is a dated completed-close/share-basis calculation.

**Proof:** fixed-clock tests during session, after a confirmed close with refreshed data, pre-open, weekend/holiday, early-close metadata, DST, missing metadata, stale cache, historical cutoff and crypto/non-US scope. Exercise actual stock/snapshot/indicator callers, not just a new helper. Reproduce the retained DOCN divergence and prove consistent completed-bar indicators. Preserve original fixture data and separately label corrected replay output. Include vendor snapshot tests for intraday, completed, missing/stale quote time and incompatible earnings/share bases; no unqualified intraday cap/P/E may appear as canonical completed-close evidence.

### 1B. Yahoo news fallback

**Files:** `tradingagents/dataflows/vendors/yahoo/news.py`, `common.py` only if needed; news/coverage tests.

Catch the existing expected `VendorUnavailableError` from the quote-feed request and try `_search_news`, as with an empty feed. Keep bounded retries, ticker tagging, publication cutoff filtering, deduplication where already applicable and honest sample-coverage reporting. Preserve the original failure as diagnostics when useful. If both sources fail, report unavailable; never claim there was no news. Do not broadly catch programming errors or introduce another provider.

**Proof:** quote success, empty feed, quote exception/search success, untagged/out-of-window search results, malformed expected vendor data, both unavailable and bounded call count. A later live probe is a time-specific availability observation, not proof Yahoo will remain reliable.

### 1C. Action-aware price fields and legacy context

**Files:** `tradingagents/agents/{schemas.py,trader/trader.py}`, report consumers and relevant schema/prompt tests; `memory/thesis.py` for the narrow context cleanup.

Distinguish an optional purchase entry from an optional reference sale level in new Trader proposals and renderers. A Sell recommendation cannot publish a purchase-entry field as its canonical meaning. Preserve legacy parsing through an explicit compatibility path; legacy ambiguous fields remain labeled ambiguous, not silently reinterpreted. Update prompts and serialized consumers together. A sale reference is advisory, not an order, executable quote or instruction to sell a specific number of shares. Holdings absence remains explicit and does not force a new user gate.

Skip legacy context entries only when their existing structure establishes they contain no thesis content (for example canonical fact-only output). Do not delete memory or use a speculative text classifier that could discard a real thesis.

**Proof:** Buy/Sell/Hold, structured and free-text fallback, missing price, legacy payloads, CLI/Markdown/HTML, canonical rating unchanged, preservation of genuine legacy thesis and omission of proven fact-only context. Validate without rewriting historical reports.

### 1D. Independent release candidate and integration decision

Freeze a clean committed Build 1 candidate before Build 2 changes enter its release branch. Run its full offline suite, full Ruff, dependency checks, focused boundary/recovery tests and rendered report inspection. Obtain a focused independent review of Build 1’s affected paths and close material findings. Then perform the first budgeted real CLI proof below and present the exact candidate, evidence and rollback reference for the user’s staging integration and launcher-installation decision. Required GitHub CI must pass on the exact published candidate under separate push/PR authorization before installation. Never ship unaccepted Build 2/3 changes with it.

**Market-open proof:** start the source-available all-analyst shallow CLI run during an actual NYSE regular session, using verified exchange session metadata/schedule for that date. Record both start and price-fetch times in UTC and exchange-local time, raw Yahoo response metadata and observed partial/completed rows. The price fetch must occur before the actual session end. Prove all completed-close/indicator paths use the prior completed session, intraday figures are distinctly labeled, vendor cap/P/E carry the correct limitations, and the Sell field is unambiguous if emitted. Retain real news/search results and in-window/ticker filtering evidence. Do not wait for the whole model run to finish before recording whether the source fetch was intraday. If Yahoo supplies no partial row, the real observation is limited; fixed-clock tests still prove rejection, but do not claim a live partial-row exclusion was witnessed. A required missing proof remains open.

If the market is closed or a release decision is pending, continue independent authorized Build 2/3 development in a separate isolated branch/worktree based on the frozen candidate; do not move its tested release head. No scheduler or automatic wakeup is authorized. Preserve proof/CI identity and reassess subsequent staging drift before integration. Build 1 need not wait for the rest of this plan, but this plan itself grants no release authority.

## Build 2 — useful price-implied valuation without invented certainty

**Files:** `tradingagents/agents/{valuation_comparison,shared_valuation,valuation,valuation_outlooks}.py`, `analysts/fundamentals_analyst.py`, `decision_context.py`, reporting and existing valuation fixtures/tests.

### 2A. Independent deterministic comparison

Decouple the existing “What the price implies” section from successful model scenario/final-target generation. Build it from validated issuer-bound price, compatible shares, obligation categories, cash and revenue records. Keep replayable input IDs, dates, definitions, units, formulas and unavailable reasons in existing evidence records.

For a declared basis, calculate equity value = observed price × compatible shares; enterprise/obligation-adjusted value = equity value + explicitly enumerated obligations − cash; divide by the identified revenue amount. Calculate trailing revenue only from compatible additive periods without overlap; do not subtract or sum EPS or weighted share counts.

Always render the section in eligible stock reports, but publish numbers only when evidence permits. Nonapplicable assets receive a scoped explanation. Missing shares, inconsistent currency/split basis, stale or incompatible price, absent revenue or unsupported obligation coverage yields unavailable for affected rows, not guessed inputs or failure of every independent row.

Presentation requirements:

- State the observed completed-session date; do not call yesterday's close a current executable price.
- Separate conventional borrowings-net-of-cash EV/revenue from finance/equipment-inclusive and all-classified-obligation-adjusted ratios. Do not present operating leases as interchangeable with borrowings.
- Reported shares are a dated snapshot; disclose temporal differences and unresolved subsequent capital changes. No claim of a fully current capital structure without support.
- Guided diluted weighted-average shares are a **conditional share-count sensitivity**, not current shares outstanding. Keep their period/definition distinct; omit that row if not source-grounded.
- Guidance is management's forward-looking statement. Preserve ranges: for positive numerator N and revenue range [L,U], ratio range is [N/U,N/L]. Do not silently select a midpoint.
- A 2027 growth-floor scenario requires an explicit 2026 base choice/range and fixed-capital assumption. Any conditional upper ratio is labeled “if management guidance is achieved and stated capital assumptions hold,” not an empirical bound. Unsupported or nonpositive-input cases remain unavailable rather than misapplying the inequality.
- These ratios do not establish fair value, expected return, bargain status or a target. Keep final target omission and canonical rating authority unchanged.

**Proof:** hand-reconciled DOCN rows from retained source records; guidance range and growth-floor arithmetic; weighted-average versus outstanding shares; all obligation perimeters; missing/negative inputs; split/currency/issuer mismatches; independent unavailable rows. Demonstrate the table remains available when model scenarios are absent or rejected. Do not turn Claude's rounded example table into a fixture's unquestioned expected truth.

### 2B. Scenario suitability

Separate three concepts in existing result metadata: source/arithmetic validity, decision-use suitability, and explicit assumptions. Preserve old records' meaning; do not retroactively change an old `supported` flag into proof of suitability.

Use this explicit source-only rule for P/E scenarios; no new unusual-item extraction or earnings-normalization engine:

1. A scenario using reported earnings for an already ended period, without an explicit forward earnings forecast, is always labeled **historical diagnostic**, regardless of ticker or growth rate. Historical arithmetic remains available for inspection.
2. Exclude that historical scenario from decision-use comparisons and final-target eligibility when existing verified facts establish a positive share issuance or debt-to-equity conversion after the earnings period and on/before the decision cutoff. Require matching issuer, definition, units, source filing availability and an event date or reporting interval wholly after the earnings-period end. Do not infer conversion from financing totals, net equity movement or a model statement. A cumulative interval overlapping the earnings period cannot establish a later event; mark comparability unestablished rather than inventing event timing.
3. Record the event fact/source IDs, dates and a reason such as `historical_earnings_precedes_verified_capital_change`. This is an explicit conservative decision-use policy for any verified positive qualifying event, not a claim that every issuance is financially material. No arbitrary materiality percentage is introduced. Absence of a returned event is not proof of no event: if coverage/share comparability cannot be established, retain a historical diagnostic with `comparability_unestablished`, not an endorsed fair-value estimate.
4. A comparable historical case is not rejected solely for being historical; retain its diagnostic label and existing validation limits. No historical diagnostic is promoted automatically to a forward target. Forward forecasts remain subject to explicit periods, accounting/share bases, assumptions and existing funding/dilution validation. EV/revenue is not automatically preferred or considered suitable.

For the retained DOCN run, trace the reported 2026 issuance and conversion facts against the 2025 EPS interval and prove exclusion with exact source identifiers. The reviewer cites approximately $887.9M issuance and $515.7M conversion; verify the saved records rather than treating these rounded figures as authority. Drop unusual-item detection from this build; model comments about one-off gains may remain labeled research, not inputs to this rule.

**Proof:** retained DOCN historical requests excluded from decision use with the verified capital-change reason while their arithmetic survives as diagnostics; comparable historical control; pre-period event; overlapping cumulative interval; zero/missing event; unknown coverage; wrong issuer/unit; filing after cutoff; forward forecast; prior EV/revenue request. Exercise both shared-scenario and final-target consumers so rejection cannot be bypassed by free-text fallback. Replay old records without rewriting them; current presentation must distinguish newly assessed suitability from original publication status. No acceptance requirement to make a live model emit a target.

## Build 3 — primary-source evidence before analyst reasoning

**Files:** `tradingagents/graph/{setup,analyst_execution,trading_graph}.py`, `agents/{state,context,evidence_validation}.py`, four analyst factories/prompts, existing disclosure modules and checkpoint tests.

Extract only model-independent acquisition/assessment from the existing evidence step into a pre-analyst node: issuer identity, applicable SEC facts/filings, deterministic disclosures/calculations and the retained price observation. Reuse that retained package after analysts finish; avoid duplicate fetches and changing evidence vintage within a run. Give each selected analyst a bounded brief of accepted facts, source references, dates, management-guidance labels and availability limits. Every selected analyst, including the Market Analyst, receives the same canonical completed-session price, session date, currency, adjustment basis and source ID (or the same explicit unavailable reason). Its market-tool responses must agree with this retained observation cutoff; independently timed intraday fields remain separate.

The later evidence step still validates model claims, parses model proposals, enforces critical coverage and prepares debate inputs. Acquisition success is not final evidence-gate success. Retain strict REVIEW and exclusion from actionable memory, settlement and performance scoring. Analyst branches remain parallel after acquisition; preserve the memory node's dependencies and prior-thesis cutoff. Keep selected-analyst/asset scopes: technical-only and non-SEC paths must not acquire mandatory SEC dependencies.

News must distinguish issuer disclosure from independent coverage; sentiment may identify a social numeric claim as matching a verified fact only when metric, period, unit and definition agree. Matching a number does not authenticate a social account, causation or its broader story. Do not claim facts are shared unless prompts actually consume the brief.

Version affected checkpoint signatures so old graph states cannot resume under a changed graph. Keep old checkpoints intact and provide the existing clear fresh-run/recovery behavior. Do not migrate or silently discard them.

**Proof:** actual graph/prompt integration with all four analysts; feed-down but filing-available news; partial disclosure coverage; misleading same-number social claim; missing SEC REVIEW; technical-only/non-SEC bypass; acquisition once; bounded context; unchanged model-call count for equivalent paths; interruption before/after acquisition and before publication; repeat export and publication identity. Reuse retained source packages on resume when compatible; never silently substitute a newer vintage.

## Integrated acceptance, audit and delivery

Work in Build 1 → Build 2 → Build 3 order, committing focused changes at verified milestones. Build 1 has its own acceptance/release boundary above; Builds 2 and 3 form the subsequent integrated candidate. No integration or installation is implied.

Run focused regressions while developing. Run the full offline suite at the frozen Build 1 boundary and again on the stable final Build 2/3 candidate (valuation and graph changes provide the concrete coverage reason), plus full-repository Ruff, dependency checks and `git diff --check`. Use the existing environment/commands:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m pip check
git diff --check
```

Mirror current CI requirements; do not invent a historical matrix or weaken tests. Reuse prior passing results only with recorded source/dependency/configuration/interaction justification. After corrections rerun affected checks; repeat the full suite only when impact or an explicit gate requires it. Results across revisions are combined evidence, not one full run on one SHA.

Replay retained November 5 output into new artifacts. Inspect actual rendered HTML, Markdown and CLI: no conflicting final-close labels, clear reference sale level, qualified ratio table, supported/unavailable distinctions and authoritative REVIEW. Verify originals by hashes.

Under the user’s November 5 paid-proof approval, use the existing runner/ledger for **three planned shallow real CLI attempts total across all builds**, not two attempts plus an uncounted extra release run:

1. Build 1’s source-available market-open run at its frozen release boundary.
2. Final Build 2/3 source-available run with all four analysts; deliberately fail only the quote-news endpoint if needed to cover real search fallback while SEC sources remain available. Verify the deterministic table, shared prompt facts and completed price, actual proposed/rejected scenarios, and eligible prior-thesis parent. Prefer market hours, but Build 1 already owns the required live intraday proof; use affected timing regressions at final acceptance.
3. Final isolated SEC-unavailable CLI run proving readable REVIEW and no actionable memory/publication-scoring contamination after the graph reorder.

There is **no separate paid retry reserve** within this schedule. If one attempt covers multiple required outcomes, omit redundant calls and record coverage. A failed attempt counts against the cap; a retry needs both remaining attempt authority and a conservative cost reservation. If required coverage would need a fourth attempt or exceed the dollar ceiling, stop paid work and surface the exact decision while continuing independent offline work. Build 1’s live run cannot stand in for changed Build 3 behavior.

Fixtures prove exact timing/arithmetic cases, not live model behavior. Record scenario selection or abstention honestly. Exercise matured-outcome plumbing offline without fabricating elapsed market performance. There is no requirement to wait months for this software task to close.

Obtain one independent final code-and-artifact review, emphasizing session finality, financial definitions, shared evidence lineage and recovery. Close confirmed material findings in the same worktree and rerun affected checks. The reviewer must distinguish executed tests from source inspection. Prefer an available independent agent; external paid audit requires explicit budget authority.

Finish with all source/tests/plan updates and acceptance records committed, clean task worktree, exact SHA, machine paths, source/proof hashes, verification reuse, spend, deferred findings and risks. Record incomplete required checks as incomplete. Required GitHub CI must run on the exact published candidate when push/PR authority is subsequently granted; before then report local development acceptance separately from publication/CI acceptance.

## Decisions and deferred work

- **Plan approval:** approves the described behavior and ordinary reversible implementation; does not authorize release actions.
- **Paid proof:** user approved a new incremental **$10 aggregate ceiling**, at most three CLI attempts, allocated as above with no separate retry reserve, subject to preflight provider pricing/context bounds. The reviewer reports earlier shallow runs costing $2.34–$2.70 each (roughly $7.02–$8.10 for three); these observations are not a worst-case bound. Changed prompt sizes, model pricing and retries can exceed them. This approved limit is not a guarantee that all attempts fit. Reconcile actual usage and reserve worst-case bounded costs before calls; stop before exhausting the cap. Do not assume old proof budgets provide new spending authority. Respect a documented existing-key exception where it still applies, but never claim that a larger provider cap enforces this task budget. Missing paid authority blocks only paid proofs, not approved offline implementation.
- **FRED:** optional user configuration using a user-owned key. Never require it for the other fixes; retain readable missing-macro coverage. No account creation or secret collection in chat.
- **Deferred:** full cash-flow/DCF valuation, new peer/consensus service, recurring watchlist runs, automatic trading rules and broker execution. Scheduled watchlist collection requires its own cost/selection policy; it cannot accelerate each horizon's passage of time.
- **Release:** no push, PR, merge, staging/production promotion, app replacement, worktree deletion or remote branch deletion without separate authorization. On later authorized installation, pin the accepted SHA, preserve previous source/configuration and user data, and smoke-test the actual launcher. Rollback must not overwrite newer user reports, memory or immutable publications.
