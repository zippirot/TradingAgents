# DOCN review: assessment and gap-closing implementation plan

Date: November 4, 2026. Incorporates the user-supplied Claude assessment and one post-plan audit. **Historical audit verdict: revised and ready. Current execution amendment: the user approved Builds A, B and C together on the isolated `codex/docn-abc-gap-closure` branch; release actions remain separately authorized.**

## Branch and release boundary for approved A/B/C execution

- **Development baseline:** use the existing isolated `/Users/zipp/Documents/ChatGPT/Tauric/worktrees/docn-abc-gap-closure` worktree and `codex/docn-abc-gap-closure` branch, based on `f1e846d67bd9d02446956df882650f4eedac3a1b`. The older `b075166` SHA below describes the original review and launcher staging context; it is not a request to reset or rebase this approved branch. Do not alter the launcher or develop directly on `main`, `staging` or `production`.
- **Approved execution:** finish A, B and C sequentially in this one branch. Commit focused implementation, tests and evidence locally; no intermediate staging integration or new worktree between builds. Completion authorizes no merge, push, PR, deployment, installation, stable-app replacement or worktree removal.
- **Development proofs:** run from this worktree with its own verified virtual environment and isolated results, cache, memory, checkpoints and preferences. Use existing private credential access without copying a whole dotenv file. Keep paid work within the user-approved USD 100 combined ceiling: up to USD 70 for at most seven total Shallow live-proof attempts including retries, and USD 30 for the final independent audit/rechecks. Codex credits are separate. Stop earlier when evidence suffices or a recurring failure needs diagnosis.
- **Later integration and release:** require separate explicit authorization for staging integration, each push, production promotion, installation and cleanup. Preserve applicable CI checks on an authorized pushed commit. Machine 1 acceptance is not required for this local research-pipeline build.

The original November 4 audit and predecessor records below remain historical evidence. This amendment controls execution where their earlier machine, branch, approval or build-by-build integration language conflicts.

## Recommendation

The review is directionally right: better accounting checks have not yet produced a consistently well-supported investment decision. The main defects are incomplete promotion of retrieved evidence into usable records, an unfinished investing-cash-flow reconciliation, missing forward per-share economics, and weak continuity between a thesis, its decision horizon and its measured outcome.

The remedy is to extend the existing evidence, valuation, memory and publication paths. A new agent framework, more debate rounds, a model upgrade, or a second parallel evidence database would not resolve these defects. Deliver Build A first; it has value independently of the larger decision and evaluation work.

There are three important corrections to the review:

- A shared financial context already exists. The failed run loses useful disclosures during extraction/validation, before they can enter that context. Narrative retrieval is not the same as a validated fact.
- A deterministic EV/revenue and P/E calculator, decision memory, and backtest runner already exist. The report failed to use a supported valuation; the evaluation machinery has a horizon and auditability gap.
- The report already labels the cash-flow comparison incomplete and the $74.50 stop unvalidated. These are incomplete analysis and presentation problems, not evidence that the program executed an unsafe order. No order-execution work is proposed.

## Baseline and investigation evidence

Repository inspected: `/Users/zipp/Documents/ChatGPT/Tauric/TradingAgents`, branch `staging`, commit `b075166df6f1738ef691cee23d1473e5085e05a1`.

**Historical post-plan audit baseline (before the approved `f1e846d` base):** read-only `git ls-remote --heads origin refs/heads/staging refs/heads/production` confirmed GitHub `zippirot/TradingAgents` staging at that exact SHA. No `production` head was advertised. Production establishment/selection is a later explicitly approved release prerequisite, not a development blocker or permission to substitute `main`. Recheck refs only at a later authorized integration/release; the approved development baseline is the existing `f1e846d` worktree.

**Historical completed predecessor at the review baseline:** report-integrity/narrative closure at `26f23dcd994351aacb66ab2475c911ca11cb1ad7`, with runtime source `d675a0b146e4a5bf559c0bd57fac769377e14aa1`; current `b075166` adds only the staging-integration record. Reviewed `docs/reviews/2026-11-04-narrative-audit-closure-evidence.json`, `2026-11-04-integrity-independent-audit.md` and `2026-11-04-staging-integration.md`. All 216 recorded source hashes match current files; runtime/application/dependency paths are unchanged from the tested source. The manifest records 1,826 passing offline tests and three live CLI proofs, with explicit missing live disclosure/valuation coverage. Its archived Machine 1 logs/screenshots were not reopened during this audit. GitHub [CI run 41929000999](https://github.com/zippirot/TradingAgents/actions/runs/41929000999) was independently read as completed/success on exact `b075166`. These predecessor results support the baseline; they do not prove the proposed changes or Machine 2's future runtime setup.

Inputs:

- [User-supplied run transcript](</Users/zipp/.codex/attachments/2d8ee1c5-5b5a-4150-b1fb-e5c37751cf6b/Pasted text.txt>).
- [User-supplied critical review](</Users/zipp/.codex/attachments/99cf739c-9e25-44a0-92c8-c22214298f37/Pasted text.txt>).
- [User-supplied Claude assessment](</Users/zipp/.codex/attachments/241a7b3c-9686-4e37-be1f-c777e4c9304e/Pasted text.txt>). The pasted assessment, rather than the separately named but unprovided full Claude plan, is the source incorporated here.
- Existing draft [shared valuation scenarios plan](2026-11-04-shared-valuation-scenarios.md), present as an untracked file when this investigation began. At the time of that audit its technical scope, sequence and tests were preserved while machine, branch and release wording was aligned. It covered a useful subset of Build B and is already implemented on the approved base `f1e846d67bd9d02446956df882650f4eedac3a1b`; verify its relevant contracts and reuse recorded evidence rather than rebuilding it. See `docs/reviews/2026-11-04-shared-valuation-evidence.json` and `2026-11-04-shared-valuation-staging-integration.md`.

**Reproduced locally:** replaying the transcript's four disclosure records against the existing recorded Q3 release fixture accepts only cash and cash equivalents and reproduces the three rejection messages printed in the report. No guidance record was submitted. Transcript lines 954–956 explicitly say guidance was omitted because its period appears in separate outlook headings. The AI Customer ARR proposal also uses `block-94–block-95` where the current contract requires one exact definition locator. Existing tests demonstrate that a correctly formed record can pass.

**Claude's additional root cause confirmed:** a controlled in-memory replay changes only the leading bullet on the Revenue value block. The exact submitted claim fails with the bullet and passes without it: `validate_context` strips the bullet for the subject check but treats the same bullet as unsupported preceding prose later. No source fixture or application code was changed. The other rejected records need separate treatment: AI Customer ARR has the invalid locator above, while the EBITDA quote omits a further margin clause. Removing its bullet alone does not make it pass. Do not treat all three failures as interchangeable or accept incomplete quotations indiscriminately.

Code confirms the relevant path:

1. `agents/analysts/fundamentals_analyst.py` proposes financial and disclosure records.
2. `dataflows/disclosure_context.py` supports narrowly scoped historical Financial Highlights context; it explicitly rejects use of that context for guidance.
3. `agents/evidence_validation.py:assess_financial_package` replaces the raw fundamentals report with accepted facts and canonical accounting context, adding only accepted disclosures.
4. `agents/context.py:get_instrument_context_from_state` gives downstream agents that canonical context. Passing original prose as verified input would bypass the protections rather than fix extraction; A1 instead proposes a separate labeled interpretation section alongside the repaired evidence.
5. `agents/valuation_outlooks.py:grounded_outlooks` additionally accepts only precisely dated annual absolute Revenue/EPS outlooks. A percentage growth expectation needs its own validated representation and explicit baseline derivation.

Two further source checks qualify Claude's diagnosis. `valuation.py:_forecast` permits an explicit analyst forecast without management guidance, with a warning; this run's target result says no supported structured request was provided. Evidence starvation is a plausible contributor to that omission, not a demonstrated sole cause. Also, memory stores the whole canonical decision text, not only a rating and hashes. Publication replaces the original thesis with an evidence summary before that memory write; the original prose survives separately in diagnostics but is not the thesis context supplied on the next run.

Focused existing checks run during investigation, with no application changes:

```sh
.venv/bin/python -m pytest -q tests/test_disclosure_context.py tests/test_valuation_outlooks.py tests/test_valuation.py tests/test_evidence_gate.py tests/test_accounting_checks.py
# 176 passed in 1.60s
```

A read-only supporting audit ran:

```sh
.venv/bin/python -m pytest -q tests/test_memory_pointintime.py tests/test_review_memory_backtest.py tests/test_backtest.py tests/test_portfolio_context.py tests/test_review_authority.py tests/test_output_publication.py
# 80 passed in 1.11s
```

These are two focused passing runs on the inspected baseline, not a full-suite result or proof the proposed fixes work. Code Review Graph had zero indexed files for this repository; no graph conclusions were used. No paid TradingAgents run, remote mutation, implementation, deployment or commit was performed for this assessment.

## How Claude's recommendations are incorporated

Keep three verifiable build boundaries within the one approved branch. Claude's two-build grouping mixes evidence repair, rule authority and performance measurement; the mapping below retains those boundaries while adopting the useful changes.

| Claude recommendation | Incorporated treatment |
|---|---|
| Fix the leading-bullet bug and guidance headings | A1: explicit reproductions and regression cases; retain qualifier/source checks. |
| Give agents readable evidence plus labeled narrative | A1: compact canonical brief and separate bounded analyst research context; narrative never becomes a verified input merely by being passed downstream. |
| Remove repeated hash dumps | A1: concise prompts/report, one provenance appendix and intact machine-readable IDs. |
| Preserve thesis and exit conditions | B1: retain thesis rationale, active conditions and change history independently of settled outcomes. |
| Show a recorded override prominently | B1: advisory disposition for prior conditions, with status and reason visible. Automatic hard-rule enforcement and a rule-authorization UI are deferred. |
| Use SEC releases when the news feed fails | A3: reuse the existing filing package as issuer-event context; show independent news/consensus and optional macro gaps separately. B3 adds expectations analysis. |
| Add cash-flow reconciliation and prior-quarter KPIs | A1/A2: retained in the first build. |
| Compare scenarios with price and show implied expectations | B2: required calculated price comparison and reverse sensitivity; explicit extension to the earlier shared-scenarios draft. |
| Score 5, 21 and 63 days; favor forward evaluation | C2: those trading-session diagnostics plus the stated three-/six-calendar-month endpoints, with prospective publication records as the primary performance evidence. |
| Add keys or lower research depth | Optional operating choices only: no account creation, required new keys, model switch or saved depth change. Measure repetition and cost before changing defaults. |

Claude's claim that the stock fell about 16% after the earlier call, the exact prior alpha, and the original authority of the 53% condition remain unverified here. They are not plan acceptance facts. Historical replay remains useful for engineering comparisons; LLM contamination prevents treating it as clean proof of investment skill. Prospective observation also needs predeclared selection and scoring to avoid its own biases.

## What the review establishes

| Review concern | Assessment against report and source | Planned closure |
|---|---|---|
| Agents disagree about guidance | Confirmed inconsistent coverage. Original narrative cites guidance, structured extraction omits it, later agents correctly lack an accepted record but describe the wider source situation poorly. | A1: extract supported context and communicate precise verification status. |
| Earlier 53% gross-margin exit gate overridden | Report acknowledges the breach, but the original 53% text exists in the October 19 record, while its authority and classification remain unavailable. Original thesis prose also fails to survive into subsequent memory context. | B1: preserve thesis and advisory conditions, observations and dispositions; preserve legacy ambiguity. |
| Investing outflow treated too broadly | Report cautions that the comparison is incomplete. Existing code already separates cash capex, principal and financed-equipment gross flows, but does not explain every investing component. | A2: complete and publish the bridge. |
| RPO decline left as a social claim | Confirmed missed source verification. The comparable quarterly filings contain the balances. The cause of the change remains a separate question. | A1: current/prior comparable KPI observations and deterministic delta. |
| No valuation | No supported final target in this run; an existing calculator supports two methods. Missing forecasts, provenance and justified assumptions cannot be replaced by arbitrary multiples. | B2: reuse shared-scenario plan, then add funding and horizon treatment. |
| Dilution/funding not modeled | Confirmed. Current EV/revenue request explicitly assumes unchanged capital structure. Outstanding shares and non-GAAP weighted-average diluted guidance have different meanings. | B2: explicit share and funding bridges. |
| Expectations and market reaction weak | Company-news retrieval failed in the supplied run. The FRED key was also reported missing, a separate macro gap. No dependable same-period consensus table or comparative event-return analysis was produced. | A3: issuer-event fallback and coverage. B3: expectations and reaction analysis. |
| Debate agreement treated as validation | Role repetition is not independent evidence. Existing prompts say this, but lengthy repeated arguments still dominate the presentation. | A1/B3: shared facts, focused assumption disputes and concise synthesis. |
| Performance evidence inadequate | Tracking and backtesting exist. Default settlement is five trading days; report horizon is 3–6 months. Published time, evaluation assumptions and immutable decision identity need strengthening. | C1/C2: auditable records and horizon-aligned evaluation. |
| Stop/sizing more precise than evidence | Report and publication code already label stops unvalidated and suppress authoritative numerical sizing. The quoted stop's investment value has not been demonstrated. | B3: make research versus execution authority unmistakable. |
| Source fallbacks/validation warnings | Truncation and extraction rejection are observed. EPS precision warnings do not themselves prove a faulty tolerance. | A1/A2: diagnose each loss; preserve source-specific precision and missing-data distinctions. |

### External checks and limits

DigitalOcean's [November 3 earnings release](https://investors.digitalocean.com/news/news-details/2026/DigitalOcean-Announces-Third-Quarter-2026-Financial-Results/default.aspx) supports the review's broad guidance, cash-flow and share-basis distinctions. It confirms reported Q3 growth and management's forward growth expectation; a verified management statement is not a verified future outcome. Its cash-flow statement separates marketable-security purchases from operating investment and equipment financing.

The [Q2 10-Q](https://www.sec.gov/Archives/edgar/data/1582961/000162828026052556/docn-20260630.htm) and [Q3 10-Q](https://www.sec.gov/Archives/edgar/data/1582961/000162828026069141/docn-20260930.htm) support RPO of $893.828 million and $799.707 million, respectively: a $94.121 million, approximately 10.53%, decline. This establishes the change, not deteriorating demand as its cause. The supporting audit accessed both filings; the primary agent's separate Q3 open failed, so the cash-flow cross-check also used the accessible issuer release and local recorded filing fixture.

The claimed final $84.12 close, Stifel target change and exact prior +6.9% alpha were not independently verified. Preserve the run's $84.02 observation as a dated snapshot; do not silently replace historical evidence with a later corrected close. The review's employment/trading-restriction assertion is not established by this workspace; do not infer the user's employment status or add a compliance workflow from it.

## Scope, estimates and decisions

**Outcome:** a research report whose material facts survive validation and reach every decision role, whose calculations reconcile, whose recommendation explains its valuation/risk/rule basis, and whose later results can be audited against the stated horizon.

**Scope:** existing SEC-stock research path first, including DOCN regression cases and at least one different issuer. Preserve existing crypto/non-SEC behavior and explicitly label unsupported scopes. Reuse current providers, report formats, checkpointing and memory. Add no broker execution, portfolio optimizer, general DCF platform, paid data subscription, automatic trading or mandatory new approval step per research run.

| Deliverable | Build size | Recommended implementation model / effort | Active implementation and verification |
|---|---|---|---|
| A: reliable evidence, cash-flow explanation and issuer-event fallback | medium | GPT-6 Astra, `gpt-6-astra`, medium | 16–26 hours |
| B: advisory thesis continuity and valuation/decision context after the completed shared table | medium | GPT-6 Astra, `gpt-6-astra`, medium | 12–22 hours |
| C: recommendation audit and evaluation | medium | GPT-6 Sol, `gpt-6-sol`, medium | 8–14 hours |
| Remaining approved A/B/C program | extra medium | GPT-6 Astra, `gpt-6-astra`, medium for integration; GPT-6 Sol, `gpt-6-sol`, medium for bounded slices | 36–62 hours |

The shared-scenarios task is complete on the approved base; its former 4–7-hour estimate is historical and excluded from remaining work. The remaining ranges are engineering planning estimates, not measured benchmarks, throughput or spending limits. A includes roughly 2–4 hours for the first slice; cross-issuer extraction, source-scope boundaries and live-proof iteration drive the wider 16–26-hour range. Astra is recommended for the broader work because source-period interpretation, cash/funding treatment and thesis lineage interact in ways that plausible but wrong local calculations could miss. This is task-specific engineering judgment, not measured speed or credit evidence. Official documentation confirms the [Astra ID and medium support](https://developers.openai.com/api/docs/models/gpt-6-astra) and [Sol ID and medium support](https://developers.openai.com/api/docs/models/gpt-6-sol). These are implementation recommendations, not changes to the running model or TradingAgents runtime settings.

Estimates assume the current environment and fixtures remain usable, existing provider access, and bounded live verification. They exclude waiting for user input, unavailable sources and future 3–6-month outcomes. No credible Codex credit range is available without measured workload usage for this integrated work; API token prices are not Codex credit rates. The user approved a USD 100 combined ceiling: USD 70 for at most seven total Shallow live proofs including retries, and USD 30 for the final independent audit/rechecks; Codex credits are separate. No new source fees or provider accounts are authorized.

The first A slice covers the bullet fix, readable evidence, bounded analyst narrative and compact prior-decision presentation; its roughly 2–4 hours are included in A, not added to the total. Thesis continuity, price comparison and multi-horizon scoring remain in their respective builds. Claude's Sol-medium recommendation is reasonable for the isolated parser and presentation changes; the broader A/B source-lineage, financial and authority integration retains the Astra-medium recommendation above. This model recommendation does not change TradingAgents runtime model settings.

**Approved product choices for A/B/C:**

1. Preserve a clearly labeled research opinion when valuation is unavailable; do not force an invented target or automatically add a new REVIEW gate just because a target is missing. Show the decision's basis and unresolved material evidence explicitly.
2. Preserve prior thesis conditions as advisory research context and show any breach, unknown observation or discretionary departure with a recorded reason. The October 19 report contains the original 53% threshold text, but its authority is unknown; do not make it an automatic Sell. Defer automatic hard-rule enforcement and a rule-authorization UI to separately decided scope.
3. Treat scenario weights as subjective assumptions until calibration is demonstrated. A correctly calculated weighted return is not a validated probability distribution.
4. Include the analyst's bounded original narrative in downstream research context, explicitly separate from accepted evidence. This approved change preserves canonical calculations/publication authority and does not relax validators.

The user approved the entire A/B/C outcome. Sequence work in one branch: the first A slice, early C publication and 5/21/63-session settlement, the remainder of A, advisory B continuity and remaining valuation/decision work, then C thesis linkage, calendar-month endpoints, recovery and evaluation. Preserve all required checks, reviews and live proofs at applicable boundaries.

## Build A — make the retrieved evidence usable, reconcile cash flow and retain company events

### A1. Repair disclosure extraction and share the accepted evidence consistently

**Files:** `tradingagents/dataflows/{disclosure_context,disclosure_evidence,financial_evidence}.py`; `dataflows/vendors/sec_documents.py`; `agents/analysts/fundamentals_analyst.py`; `agents/{evidence_validation,valuation_outlooks,context,state}.py`; `graph/setup.py`; `reporting.py`, `report_html.py` and CLI display where needed; existing disclosure/evidence tests and fixtures.

**First implementation milestone, within A1:** carry the single Revenue bullet correction, a readable accepted-evidence brief, a separately labeled bounded analyst narrative, and compact prior-decision presentation through the actual worktree launcher/CLI, Evidence Check, first bull/bear turns, canonical publication and saved Markdown/HTML/evidence outputs. Inspect a rejected/unknown counterexample in the focused replay. Run and record one bounded real CLI proof described below before expanding disclosure patterns or starting A2/A3; resolve runtime/configuration/data-flow blockers first. Next implement the early C immutable publication and 5/21/63-trading-session outcome slice, then finish A1/A2/A3. Reuse proof runs across applicable first/final assertions when source and behavior make that valid.

**Implementation:**

- Capture the supplied run as a small regression fixture: exact submitted records, source identifiers/locators, rejected reasons, and expected valid facts. Reuse the recorded release/filing fixtures; do not fabricate missing source text.
- Fix list-marker handling before testing preceding semantic prose. A leading supported bullet/whitespace alone must not invalidate an otherwise exact claim; real preceding qualifications must still be checked. Keep original source spans/locators intact. Test Revenue, AI Customer ARR and EBITDA separately: correcting one parser defect must not excuse an invalid locator or an omitted material clause. Improve bounded rejection reasons so these causes are distinguishable.
- Support a bounded, explicitly linked outlook heading plus metric row, with same-document identity, contiguous scope, period, currency, unit, accounting/share basis and qualifiers. Keep historical highlights and forward guidance distinct. Add explicit comparator support for lower-bound growth language such as `60%+`; never convert it to an exact 60% forecast or a finite range with an invented upper bound.
- Correct the analyst's extraction instructions/examples for exact locators and complete source qualifications. Add deterministic discovery for the supported release/table patterns so core coverage does not depend solely on the model remembering a JSON row. Unsupported formats remain visible gaps; no unlimited repair agent or permissive quote matcher.
- Keep one accepted evidence representation in the existing state/package path. Include stable IDs, source URL/hash/locator, known-at time, observed period, metric definition, units, status and rejection reason. Reuse existing types where possible; add only fields needed for these failures. Distinguish `verified historical`, `verified management statement`, `derived`, `analyst assumption`, `retrieved but unvalidated`, `not retrieved`, and `conflicting` in the rendered context.
- Derive revenue growth and margins from comparable exact facts already in the full canonical package before considering a new retrieval. For year-over-year growth require the same quarter of the prior year, not the previous quarter or annualized current revenue; compute `(current / prior - 1)` only with a valid nonzero comparator. Preserve the source's reported comparison separately where appropriate; do not merge rounded headline amounts with exact statements without retaining their precision. Promote guidance only after checking the source, not because another agent says it is verified.
- Fetch the immediately preceding comparable quarterly disclosure when necessary for a material KPI comparison. Current filing selection normally chooses the latest 10-Q; the same-document current/prior relationship must not be assumed. Keep requests bounded, cached and cutoff-aware. For RPO, require compatible definitions/currency/periods, calculate absolute/percentage change, and distinguish documented causes from hypotheses.
- Give researchers, research manager, trader, risk agents and portfolio manager the same plain-language accepted evidence brief before their decision turns: growth, margins, cash generation, obligations, guidance, material KPI changes and precise coverage status. Analysts execute with private histories; do not force new serial analyst calls merely to share later evidence. Reconcile the earlier news/social claims in the existing post-analyst stage, then retain their original prose as diagnostics.
- Add a separate, bounded **Analyst research — unvalidated interpretation** section from `financial_claim_validation.raw_report`, with structured extraction fences removed from this prose view and truncation disclosed. Keep the full original in existing diagnostics. Use this context for hypotheses, source leads and interpretation; explicitly marked rejected/unverified claims cannot supply canonical numbers, target inputs, verified guidance or rule observations. Accepted evidence wins on conflict; the model must surface unresolved differences rather than silently promote the narrative. Add no summary-model call. This restores useful reasoning without substituting analyst prose for evidence.
- Remove repeated full hash/source dumps from ordinary reading and repeated prompt sections. Render the brief once per consumer, using readable source labels and one provenance appendix in the report; preserve exact IDs in a single reference block where structured valuation requests require them, and retain full source/hash/lineage records in `evidence.json`. Do not change validation to accept ambiguous shortened IDs. Check saved/re-exported reports and actual prompts for duplication and broken provenance links.
- Publish a compact coverage summary. The explanation should say “retrieved but not validated because …” when that is what happened. Required structured decision references must resolve to accepted IDs. Do not pretend deterministic checks can certify every sentence of arbitrary prose; conflicting prose remains labeled and is covered by live report acceptance.
- Diagnose truncation at the needed source spans. Prefer retrieving the missing bounded section over globally enlarging every prompt. Preserve malformed-source rejection, unavailable-data semantics and point-in-time filtering.

**Verification:** reproduce the current failure before correction; bullet-present and bullet-absent valid revenue claims agree; valid Q3 growth, outlook and AI KPI records accepted; malformed/range locators rejected; absent/ambiguous headings, stale filings, wrong issuer/year/unit, omitted qualifiers and source injections rejected. Test lower-bound expectations without inventing a ceiling; zero/missing/mismatched growth comparators; comparable RPO delta and unavailable comparison when either period is missing. A mocked full graph must give identical accepted facts/statuses and separately labeled narrative to all downstream roles before their first turn, with no unplanned model calls. False figures and instructions injected into supplemental narrative must not change calculations, validated inputs, canonical rule observations or publication policy. Compare prompt/report lengths against baseline while preserving required evidence; cover at least one non-DOCN source shape.

### A2. Complete the cash-flow bridge and use it in the report

**Files:** `tradingagents/dataflows/{filing_facts,financial_evidence}.py`; `agents/{accounting_checks,evidence_validation}.py`; `reporting.py`; existing cash/evidence/report tests.

**Implementation:** extend the existing calculations with source-linked signed investing components, classified financial-investment purchases/sales, acquisitions/intangibles, paired financed-equipment gross flows, principal and cash-balance reconciliation. Preserve unresolved components as unresolved; never plug a residual into capex or assume a missing item is zero. Show cash plus restricted cash on the statement's basis separately from unrestricted valuation cash.

DOCN fixture arithmetic, in USD millions, gives concrete acceptance examples:

```text
Investing outflow = 105.124 PP&E + 19.279 software
                 + 75.143 financed equipment + 0.754 intangibles
                 + 4.042 business acquisition + 177.632 securities
                 = 381.974

OCF less PP&E, software and lease/equipment principal
  = 318.116 - 105.124 - 19.279 - 39.895 = 153.818

Same measure after the disclosed intangibles and business acquisition
  = 153.818 - 0.754 - 4.042 = 149.022

Change in cash and restricted cash
  = 318.116 - 381.974 + 475.796 - 0.319 FX = 411.619
Closing cash and restricted cash = 254.633 + 411.619 = 666.252
```

These are labeled reconciliations with explicit exclusions, not a new universal definition of shareholder free cash flow. Retain the $75.143 million equipment acquisition and matching financing proceeds gross in the cash bridge. Do not erase the asset investment or future obligation by netting the two. Avoid deducting operating-lease payments again when already included in operating cash flow. Noncash lease additions remain separate from current cash outflows. The cash-plus-restricted-cash closing balance is not the $666.096 million unrestricted cash input.

**Verification:** exact signed arithmetic, period/unit/source compatibility, sum-to-statement total, restricted cash, acquisitions, securities, financing pairs, noncash exclusions, principal overlap and missing components. Preserve current source-specific rounding tolerances; do not widen them to make EPS warnings disappear. Render one compact bridge that both sides of the debate and the final decision receive. A downstream claim of operating cash burn based only on OCF minus total investing must be challenged by this context, not repeated as a conclusion.

### A3. Reuse issuer disclosures when company news is unavailable

**Files:** existing `agents/analysts/news_analyst.py`, `agents/{evidence_validation,context,state}.py`, `dataflows/router.py` only where required, and report/coverage tests. Reuse `filing_evidence`; do not create another news store.

**Implementation:** expose the already retrieved eligible 8-K and earnings-release events to downstream agents and the report as a dated **Issuer disclosures** supplement when independent company news is unavailable. Build it at the existing post-analyst evidence boundary, so parallel analysts need not be rerun or serialized. Preserve the original News Analyst report and clearly distinguish the later supplement. Use accepted facts plus source-linked release/event descriptions; do not label a whole document verified because it was retrieved. If no eligible package exists, keep the fallback unavailable rather than expanding retrieval silently.

Show separate coverage states for independent news, issuer-event evidence, consensus and optional macro data. A degraded banner should identify what failed and what substitute is available; the issuer release must not be represented as independent reporting or analyst consensus. Diagnose the failed configured news call. The router already supports ordered vendors and intentionally respects the configured chain; use a second provider only when explicitly configured with suitable access. Do not add Alpha Vantage, require a FRED key or create accounts as part of this build. Report the missing FRED key as an optional macro limitation, separate from company news.

**Verification:** failed company feed plus available release; available feed; absent/stale/future/wrong-issuer release; truncated or rejected release claims; missing optional FRED configuration; and explicit two-vendor fallback versus single-vendor configuration. Confirm that issuer disclosures reach the first debate turn without extra model calls or unconfigured vendor requests and that the degraded status remains visible.

**Build A exit:** the DOCN reproduction and another issuer work through the actual evidence gate; source-valid guidance and KPI comparisons reach decision roles in a readable brief; supplemental narrative remains labeled; the investing bridge reconciles or names the exact unresolved component; and existing issuer-event evidence survives a news outage. Inspect one authorized live report for actual use of the evidence and concise presentation. Optional unavailable fields must not become zero, invented certainty or new blanket decision gates.

## Build B — connect evidence to a defensible research decision

### B1. Persist thesis continuity and make advisory dispositions visible

**Files:** `tradingagents/agents/{schemas,state,output_validation}.py`; `agents/managers/portfolio_manager.py`; `memory/log.py`; `graph/trading_graph.py`; `reporting.py`; a small thesis module only if the existing path needs one.

**First milestone:** publish a thesis with an advisory condition through the actual CLI, restart, and show that the next run reads the same version and reports observed status and disposition. Use isolated memory and recorded evidence for breach/unknown counterexamples. This is a research record, not a trading instruction or a new approval workflow.

**Implementation:** preserve a compact versioned thesis record with published rationale, material assumptions, evidence references, candidate conditions, known-at time, metric definition/period/comparator/threshold/unit, observation status, disposition and change history. Capture the candidate before canonical publication replaces model prose; store the finalized record after publication. Retrieve the active same-ticker thesis independently of settled performance lessons so it remains available while outcomes are pending. Keep original wording as labeled diagnostics, without promoting unchecked narrative to a fact or authoritative rule.

Compute `met/breached/unknown` from compatible canonical facts when possible. Display the prior condition, observed value/date, retained or changed recommendation, and the model's reason for any departure near the canonical decision. Unknown evidence stays unknown. This is advisory continuity: it does not automatically force a rating, create a hard-rule classification, or let a positive five-day result declare a longer thesis successful. The October 19 record contains the 53% text, but its original authority is unknown; retain that ambiguity without an invented automatic Sell. Defer automatic hard-rule enforcement, authorization UI and retroactive migration. Existing publication authority and REVIEW behavior remain intact.

**Verification:** threshold boundaries, rounded values, wrong period/basis, missing evidence, explicit departure, expiry/supersession, pending same-ticker visibility, checkpoint resume, historical known-at cutoff and round-trip through publication, memory and next-run context. The 53% legacy example must remain advisory/unclassified unless authority is established. An advisory breach must be visible with disposition, without overriding canonical publication by itself.

### B2. Reuse shared valuation, then add funding and horizon treatment

**Files:** reuse the completed shared-scenarios implementation; extend `agents/{valuation,valuation_outlooks,schemas}.py`, relevant fact extraction and tests; add a small funding-calculation module only if it simplifies the existing calculator.

**Implementation sequence:**

1. Reuse the completed shared-scenario table on base `f1e846d67bd9d02446956df882650f4eedac3a1b`, preserving independent final target validation and omission on unsupported inputs. Verify its current contracts and recorded evidence rather than reimplementing it. This Build B adds dated price/return comparison and reverse valuation. Diagnose missing final requests separately from rejected requests or missing guidance; optional analyst forecasts can be supported without a management outlook, with their existing limitations.
2. Add explicit forward capital/funding assumptions to the existing `unchanged_from_snapshot` contract as a versioned extension. Keep snapshot-only requests valid and clearly labeled. Each scenario links current capital facts, future operating cash/capacity spending, debt/lease principal, funding proceeds, issuance price/fees and projected shares; scenario funding shortfalls remain visible. No fabricated debt capacity or cash plug.
3. Calculate closing cash, obligations and end shares with signed bridges. Equity issuance increases cash and share count; debt proceeds increase cash and obligations; debt repayment reduces both; conversions remove the relevant debt and add shares once. New leases create obligations/assets and their later payments, not free cash. Separate existing noncash additions from future cash commitments. Keep dilution from actual outstanding shares separate from weighted-average basic/diluted EPS denominators and management's non-GAAP share guidance.
4. Use one suitable supported valuation method per comparable bear/base/bull table. Forecast revenue/margins and the related cash-conversion assumptions explicitly; do not equate EBITDA or adjusted FCF to funding capacity. EV/revenue still needs a justified, dated multiple and compatible obligation/lease perimeter. P/E must use compatible earnings and share basis and remain unsupported where inappropriate. Unrestricted securities may enter an equity bridge only with sourced value/liquidity treatment, not by silently treating purchases as cash equivalents.
5. Distinguish the valuation date, future financial period and 3-/6-month decision endpoints. A future annual revenue multiple does not itself establish a near-term target. State the rerating/catalyst assumptions linking it to the decision date; otherwise publish only a conditional sensitivity. If discounting is used, expose its assumption and calculate it explicitly. Do not silently relabel year-end 2027 value as six-month value.
6. Show scenario price, percentage return `100 × (scenario price / observed price - 1)` percent, forecast/share/funding assumptions, supporting facts, catalysts and invalidation conditions; require a positive, sourced dated price with currency/session status. Include a required **What the price implies** table using the same capital/perimeter assumptions: for EV/revenue, implied multiple is `(price × scenario shares + scenario net obligations) / forecast revenue`, or implied revenue is that enterprise value divided by an explicit positive assumed multiple. Identify both the price observation date and scenario capital date. Missing inputs produce a specific unavailable reason, not a guessed table. This helps readers see what must be true without claiming those assumptions are likely.
7. Keep early scenarios unweighted, as in the existing draft. If the final request supplies weights, require nonnegative weights summing to one and rationale; display the resulting expectation as subjective and conditional. Do not use “validated expected-return distribution” until an empirical calibration protocol supports that claim. Do not force probabilities when no credible basis exists.

**Verification:** arithmetic independent of model prose; funding shortfall; no-issuance, equity-funded and debt/lease-funded paths; share-basis mismatch; conversion and principal double-counting; negative equity value handled explicitly; missing assumptions; dated price freshness/session status; target date versus financial period; tampered saved outputs recalculated. Price sensitivities and reverse calculations must agree algebraically. A valid early scenario cannot bypass an invalid final request. Full publication paths must preserve subjective-assumption labels and existing qualitative sizing.

### B3. Explain expectations, disagreement and decision authority concisely

**Files:** existing news tools/vendor routing and `agents/analysts/news_analyst.py`; `agents/researchers/{bull,bear}_researcher.py`; research/trader/risk/portfolio prompts; `schemas.py`, `reporting.py`, `report_html.py`, CLI display where necessary.

**Implementation:**

- Build an event comparison using actual results, prior same-period management guidance and timestamped same-period consensus when a verifiable source is available. Keep GAAP/adjusted EPS distinct. Store source/date and compute surprise only from compatible values known before the event.
- Reuse A3's issuer-event supplement and coverage states; do not rebuild its fallback or treat it as consensus. Use the existing configured news-vendor chain for independent coverage and preserve failure evidence. If reliable consensus requires a new paid/licensed source, present that concrete dependency for approval. Unavailable consensus is a disclosed coverage limit, not zero, an inferred beat, or a hidden completed requirement.
- Calculate stock, broad-benchmark and a small disclosed relevant peer comparison over the same event window using existing price tools. Select peers before examining the event returns and explain comparability. Market reaction is observed; attribution to margins, capital efficiency or other causes stays sourced reporting or a hypothesis.
- Give the final report a concise canonical decision card: rating, basis (`valuation`, `thesis rule`, `risk assessment`, or `insufficient evidence`), horizon, evidence coverage, scenario/target availability and rule disposition. An Underweight opinion may be risk-based without a target, but must not claim a demonstrated negative expected return.
- Keep original analyst/debate narratives inspectable. Lead with facts, assumptions still disputed and what would change the decision; instruct later debate rounds to address unresolved assumptions rather than restate facts. Do not add agents or change the user's model/debate-depth defaults as a supposed fix. Measure repetition and call/token counts before proposing a new early-stopping policy.
- Use Shallow 1 for the approved bounded live proofs; do not change saved depth preferences. Claude's “Medium research depth” suggestion is deferred operating advice, not an active proof setting or evidence of quality. Report each proof's actual rounds/tokens and whether later turns add evidence or resolve an assumption. No new API key is a prerequisite for the evidence/valuation fix; optional FRED or second-news-provider setup is separate and user-controlled.
- Keep the Trader's provisional SELL distinct from the Portfolio Manager's canonical rating. Technical levels remain dated observations or unvalidated research proposals; no validated stop or numeric allocation is published without its required evidence. Do not collect tax/employment/MNPI data or add compliance gates for this research-only task.

**Verification:** earnings beats with a negative reaction, unavailable/stale consensus, mismatched periods/bases, provider failure and fallback, benchmark date alignment, unchanged model call policy, conflicting trader/PM prose and invalid technical stops. Inspect CLI, Markdown, HTML and saved evidence for one unmistakable final rating and accessible supporting research.

## Build C — measure recommendations on the horizon they actually claim

### C1. Preserve a stable publication record

**Files:** `tradingagents/graph/trading_graph.py`; `memory/{log,settlement}.py`; `reporting.py`; state/schema and existing persistence tests.

**Early C milestone, immediately after the first A slice:** publish one new decision via the worktree CLI into the versioned record, restart the process, and exercise the existing settlement entry point `TradingAgentsGraph.settle_all_pending()` against an isolated previously published record whose shortest window has actually elapsed. Inspect the persisted outcome, its immutable decision/thesis linkage and the still-pending longer horizons. Early thesis linkage may be absent until B1 adds versioned thesis records. The first new decision is correctly pending until its dates arrive. An actually mature legacy settlement record may establish the runtime path if its recorded dates and provenance are adequate; never invent a publication timestamp. If no eligible prior record or provider can be used, keep this runtime proof incomplete; replay can test arithmetic but cannot substitute for that proof. Implement immutable publication and 5/21/63-trading-session outcomes here; complete thesis-version linkage, three-/six-calendar-month endpoints, recovery and evaluation after A and B, then repeat the full publication/settlement path at C acceptance. No scheduler, new worker or immediate claim of future performance is needed.

Extend the current saved decision/evidence records with stable run/decision IDs, immutable first-publication time with timezone, requested as-of cutoff, source hashes and references to existing evidence snapshots, code/prompt/model versions, a minimal sanitized configuration fingerprint, canonical rating/basis, target/scenario/rule versions, and explicit evaluation endpoints. Do not serialize credentials, duplicate raw portfolio details or retain extra licensed feed content for this feature. Separate rendering/export time from publication time. Re-export and checkpoint resume must preserve identity; a material rerun creates a new version linked to the previous decision without overwriting its history.

In the early C slice, retain an optional thesis reference; after B1, link each outcome to the immutable published thesis/condition version, not whichever thesis exists when scoring runs. Track eligibility, pending status and resolution time per endpoint so a five-day result neither completes nor overwrites the longer-horizon observation.

Define scoring eligibility before outcomes: retain all publications, but keep the existing first eligible ticker/date recommendation as the primary daily observation by default; label later revisions separately so repeated runs cannot inflate sample size. Keep incomplete/REVIEW records in the audit trail and coverage denominator while excluding them from directional trade scoring. Preserve existing legacy log readability. A mature, actually recorded legacy settlement may prove the runtime path, but old records with unknown publication time cannot acquire invented historical precision. Memory rotation must not erase the permanent recommendation/outcome evidence.

**Verification:** duplicate invocation, re-export, checkpoint resume, two same-day different recommendations, revised data, missing legacy timestamps, crashes and ordinary concurrent writes using existing locking. Outcomes and reflections cannot be visible before their resolution dates; active thesis rules use their own known-at dates.

### C2. Extend settlement early, then establish an honest evaluation protocol

**Files:** `tradingagents/memory/{settlement,reflection}.py`; `tradingagents/backtest.py`; `default_config.py`; CLI backtest options/reporting and focused tests.

- In the early C slice, add the requested 5-, 21- and 63-trading-session diagnostics using the existing settlement price path. After B1 thesis linkage, also evaluate both three- and six-calendar-month endpoints, mapped to disclosed eligible trading sessions. Sixty-three sessions is not defined as three calendar months. Reuse price retrieval and identical-date computations while preserving endpoint labels; do not count coincident endpoints as independent samples or choose whichever result later looks best.
- Resolve each eligible endpoint once, retaining longer endpoints as pending. Show a horizon-by-horizon table with matured results and unresolved observations. Apply the corresponding horizon label when injecting a lesson into later research; short-term results cannot be reported as the outcome of the longer investment thesis. Score and summarize additional endpoints deterministically, without new model calls. Preserve the existing configured single model reflection per decision with its actual horizon label; later matured measurements are supplied separately and do not trigger extra paid reflections. A different reflection frequency is outside this build.
- For daily-close research, retain the conservative first eligible close strictly after the publication/as-of session; record actual entry/exit prices and times, benchmark, corporate-action adjustment, missing bars and window. Historical simulations must use the information cutoff; live records must also respect actual publication time. A date alone cannot prove that a price was executable.
- Report gross security/benchmark return and excess return separately from any hypothetical strategy result. Store transparent commission/slippage assumptions for an explicitly defined strategy calculation; do not subtract guessed costs from a relative opinion and call it realized P&L. Without holdings or sizing, Underweight is a relative research call, not an executable portfolio trade.
- Make prospective paper tracking the primary evidence of recommendation quality: timestamp and freeze each eligible decision before its scored outcomes occur, predeclare selection/horizons/baselines/costs/metrics, retain all attempts and coverage/failure rates, and avoid hindsight revisions or selective reporting. Forward collection does not by itself eliminate selection bias or establish a profitable strategy. No recurring run/automation is created without separate authorization.
- Use offline historical replay and disjoint development/holdout periods to test engineering consistency and compare pipeline behavior on frozen inputs. Point-in-time provider guards do not eliminate an LLM's possible knowledge of historical outcomes; describe this contamination explicitly. A historical holdout is not clean evidence of investment skill merely because its dates were not used to tune prompts. Do not require historical profitability or a claimed calibrated expected-return distribution to complete the software build.
- Compare the prior baseline against the changed pipeline on the same frozen inputs. Report return/alpha distributions, directional accuracy under a declared rating mapping, coverage, and drawdown only for a fully specified strategy. Report forecast error/interval coverage where actual forecasts exist. Assess probability calibration only when there are defined mutually exclusive outcome events and enough observations; scenario weights alone are not calibration data.
- Define minimum evaluation samples and improvement criteria before scoring, based on the chosen universe, usable data and declared comparison; keep engineering replay criteria separate from prospective performance criteria. Report small samples and uncertainty; do not promise profitability. A successful engineering build can be complete while investment-performance evidence remains unproven. Collecting prospective 3–6-month evidence takes elapsed calendar time beyond the implementation estimate. No scheduled monitor or recurring paid backtest is authorized by this plan.

**Verification:** holidays/weekends, after-close publication, mismatched calendars, splits/dividends, missing prices, independently pending/matured endpoints, coincident 63-session/three-month endpoints, cost arithmetic, benchmark selection, thesis-version linkage, append-only revisions, isolated backtest memory and future-information exclusion. Repeated settlement must not duplicate an outcome or reflection; a short endpoint must not suppress a later one. A frozen small offline comparison proves reproducibility and metric calculation; it does not prove an investment edge. Record any provider-dependent or prospective acceptance still pending.

## Integration, acceptance and handoff

Execute approved A/B/C in the existing isolated branch and worktree identified above. Do not integrate A or B into staging between slices. Reuse the completed shared-scenarios implementation and passing evidence whose source and assumptions remain valid. The first A slice precedes early C publication/settlement; remaining A evidence work precedes B continuity, funding and decision work; final C linkage and evaluation follow B. Version changed state/request contracts and run signatures so incompatible old checkpoints cannot bypass new evidence preparation; keep legacy exports readable and labeled.

### Real runtime proof and primary owners

The real trigger is `Start TradingAgents.command`, which runs `.venv/bin/python -m cli.main`; the Typer callback is not an `analyze` subcommand. All runtime proof below runs from the isolated feature worktree, using its own verified interpreter/import paths and existing private provider access. Required components are the Python CLI/LangGraph pipeline, configured data/LLM providers, local files and optional existing SQLite checkpoints. No deployed service, broker, external database or worker is involved.

Before invoking the CLI, create/verify this worktree's own `.venv` and set the existing `TRADINGAGENTS_RESULTS_DIR`, `TRADINGAGENTS_CACHE_DIR`, `TRADINGAGENTS_MEMORY_LOG_PATH` and `TRADINGAGENTS_PREFS_PATH` overrides to distinct disposable paths inside the proof workspace. Provider/model/language/depth choices must also be explicitly set or supplied through the existing prompts; do not change global preferences, use the default shared memory, copy secrets wholesale or run `--clear-checkpoints` against shared data. Example for the recorded DOCN as-of case, under the approved bounded live budget:

```sh
.venv/bin/python -m cli.main --ticker DOCN --date 2026-11-04 --analysts market,social,news,fundamentals --save --html --show --checkpoint
```

Use a currently retrievable, eligible as-of date for a fresh live source proof if the historical source cannot be served, retaining the frozen November 4 case as offline regression evidence. Record the actual date/provider/model/source status; neither a mocked provider nor a historical replay is a live run. A failed provider, missing credential or unsupported disclosure leaves the affected proof pending rather than proving fallback as success. First-slice and final proofs are required; reuse a single run across multiple applicable assertions instead of launching per-section jobs. Stay within the approved USD 70 live-proof subceiling and seven-total-Shallow-attempt ceiling, including retries; reserve the USD 30 audit/recheck subceiling for its stated purpose. Diagnose failures before retrying.

| Primary task / proof | Concrete evidence and destination |
|---|---|
| A1 owns first and final A runtime acceptance | CLI trace at `<results>/DOCN/<analysis-date>/message_tool.log`; canonical state at `<results>/DOCN/TradingAgentsStrategy_logs/full_states_log_<analysis-date>.json`; report path announced by CLI under `<results>/reports/DOCN_<save-time>/`. Inspect `complete_report.md`, `complete_report.html`, `quality.json`, `evidence.json`, accepted disclosure/brief and first bull/bear use. Final A proof includes A2 cash bridge and A3 issuer-event coverage. |
| B1 owns advisory continuity runtime acceptance | Above outputs plus the isolated memory/thesis record and the second process's prior-thesis context. Final B proof includes B2's supported scenario/current-price comparison and B3's decision/coverage card; target omission alone does not prove valuation success. |
| C1 owns early and final C runtime acceptance | Versioned published record, restart readback, existing settlement summary, endpoint outcome with actual price/window/benchmark provenance and unresolved longer endpoints. C2 owns calculation/calibration tests and the explicitly pending prospective performance results. |

Match canonical rating, evidence status, target availability and applicable rule/decision IDs across state, memory and saved reports; model narrative remains separately labeled. `record_decision` precedes optional report saving, and the CLI can report a save error after analysis succeeds: inspect artifact existence/content and the save result, not just process exit or a final rating. One controlled save/persistence failure in the isolated fixture must remain visible and retryable without inventing a successful publication. Record source SHA, environment/configuration fingerprint, commands, actual artifact paths and limitations in the existing `docs/reviews/` evidence location; no new tracking system.

### Applicable operational boundaries

| Concern / primary owner | Required behavior and focused evidence |
|---|---|
| Source/decision authority — A1, B1 | Existing canonical evidence package and `enforce_publication` remain authoritative. Narrative is research context; B1 owns rule/thesis versions. No second fact registry or authority hidden in report rendering. |
| Durable identity and partial writes — B1, C1 | Reuse existing locks and atomic file replacement. C1 establishes the versioned publication record early; B1 adds its minimal advisory thesis/version and C later links outcomes to it. Current per-date snapshots overwrite on rerun, so they cannot alone serve as immutable history: retain versioned canonical records in the existing results tree and treat the legacy per-date view and prompt memory as projections. Recovery after a failure between state write, memory write and report save must reconcile from the canonical record without duplicate decisions or lost active conditions. Missing/corrupt records are visibly unavailable, never silently “no prior thesis.” Test the actual interrupted write/restart path in isolated files/checkpoints. |
| Growth/rotation — B1, C1 | One bounded versioned record per actual publication/revision, finite condition/scenario payloads and at most five named endpoint outcomes per decision; reuse source snapshots by reference. Prompt history remains bounded by the existing context selection. Existing optional memory rotation may prune prompt lessons but cannot delete the sole active thesis or audit record. Audit history grows with user-requested runs, has no new automatic deletion policy and remains available for explicitly requested archive/cleanup; no retention daemon or new database is required. Test rotation and rerun behavior. |
| Provider/restart behavior — A1/A3, C2 | Reuse current vendor routing, configured retry bounds and per-ticker checkpoints. Show unavailable/slow-provider errors; leave unresolved endpoints pending and do not duplicate paid reflection. A1 owns updated run signatures and a real isolated interruption/resume check where state/prompt compatibility changed. Do not repeat completed analyst calls on a compatible resume. |
| Stable install, broker, deployed worker/service | **Not applicable to feature acceptance:** this changes the local research CLI, not an installer, trading execution or deployed service. Machine 1 installation/acceptance is conditional on a later explicit production release/install approval and exact resulting production commit, per the branch boundary. |

These clarify existing persistence and recovery requirements, not a new orchestration or storage product. The current dependencies and local locks/files/SQLite capabilities suffice; no new dependency or data migration service is justified. The approved order is first A slice → early C publication/session outcomes → remaining A → B → final C.

Use focused tests for each milestone. Select from the existing suites above plus affected structured-agent, date/cutoff, checkpoint, graph, publication, stream, CLI and rendering tests. Add new tests for observable failures, not mirrors of implementation. At the meaningful A, B and final C boundaries, run:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m pip check
git diff --check
```

The full offline suite is justified at these boundaries by changes to shared state, financial calculations, publication or memory. Preserve the repository's external-service test exclusions and report them. Do not repeat a passing expensive check unless later source/dependency changes affect it. If a proof fails, distinguish application, fixture/setup and external failures, fix the smallest cause, and rerun affected checks before the failed proof.

For A/B, perform the first-slice and final worktree runtime proofs owned above and inspect actual evidence/scenario use. All-scenarios-omitted proves fallback only. Do not loosen validators or keep paying for blind retries to get a good-looking run. Offline replay covers date-sensitive source contracts; current live data cannot substitute for historical as-of proof. For C, require the real isolated publication/restart/settlement proof plus a frozen offline evaluation example, with prospective performance explicitly pending until its horizons mature. No Machine 1 run or stable installed-app change is required for these development proofs.

Obtain focused independent engineering review at each build's financial, authority or evaluation boundary, plus a final independent audit of the completed A/B/C build; no per-file review bureaucracy or requirement for every runtime research report to use another model. Review is not a substitute for tests. Close material in-scope findings from the final audit in this same worktree, inspect the complete diff and generated reports, and update the existing `docs/reviews/` records at meaningful completion milestones.

Completion of the approved A/B/C program requires committed implementation and evidence on this isolated branch, exact checks/results, material adjustments and deferred findings. Missing required real-path proof means implementation acceptance remains incomplete. Report the exact feature commit; it does not advance staging or production. Development integration, each GitHub push, stable production release and Machine 1 installation/acceptance are the separate transitions defined above; preserve CI on each authorized published state. PR creation, new paid services and worktree removal also need their applicable authorization. No previously saved report, rule or outcome is rewritten to make the new version appear correct.

## Post-plan audit disposition

One audit against the baseline above; the existing plan was revised in place once and only affected sections were rechecked. No application code, Git refs, databases, installed product or prior acceptance records changed. The shared-valuation draft received workflow-only alignment because B2 incorporates it by reference.

| Material finding | Initial classification / location | Disposition |
|---|---|---|
| Referenced draft directs new development to Machine 1; primary plan does not specify exact remote baseline or release stages | **FAIL** — shared draft “Verified baseline and execution boundary”; this plan “Integration, acceptance and handoff” | Removed Machine 1 implementation/SSH instructions; added the Machine 2 exact-staging boundary and separately authorized integration, production and installation stages in both active plans. |
| First real vertical path, saved destination and final runtime proof are insufficiently explicit | **PARTIAL** — A1/B1/C1 and final acceptance | Added thin first milestones within existing tasks, exact CLI/output evidence, early and final Machine 2 proof, and primary ownership. No task reordering or new runtime service. |
| Immutable history/active rules need an explicit answer for per-date overwrites, partial writes and lesson rotation | **PARTIAL** — B1/C1/C2 | Clarified one authoritative versioned saved record, projections, bounded per-decision growth and recovery using existing locks/atomic writes; no second ledger/database or broad migration. |

**Historical audit verdict: revised and ready at that time.** Subsequent user approval changed the active sequencing and branch boundary above while preserving the required technical checks and safety criteria. Build authorization was subsequently granted for all A/B/C, with a USD 100 combined paid-work ceiling (USD 70 live proofs, USD 30 independent audit/rechecks). New A/B/C runtime proofs are future work relative to this plan review. The missing GitHub production head requires an explicit release-stage decision later; it does not prevent feature development. Historical installed-state details were not inspected and no Machine 1 acceptance is claimed.

## Deferred rather than silently added

General DCF/Monte Carlo modeling; portfolio optimization and tax-aware execution; broker integration; individualized company-trading compliance; automatic data subscriptions; more model roles; automatic multi-model voting; parameter-search infrastructure; broad ticker coverage beyond supported source contracts; and profitability claims. Consider these only after the three builds produce trustworthy evidence about their actual value.
