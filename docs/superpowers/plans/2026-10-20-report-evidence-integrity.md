# TradingAgents report evidence and calculation integrity

## Execution authority and current checkpoint — 2026-11-04

This execution record supersedes the historical machine assignment and not-started status below. The user activated implementation and approved publishing staging at `3411158f91eb267aab8760fc90afbf43556eb0bb`. GitHub staging, remote origin/staging and local staging were verified equal before feature creation. Only that bootstrap push is authorized; feature integration/push and release remain separate decisions.

Development compute: Machine 1, `zipp@100.89.132.10`, M1 Pro/16 GB. Coordinating Mac: M2 Pro/32 GB at `100.96.201.122`. Remote feature worktree: `/Users/zipp/Developer/tradingagents-integrity/feature`; branch `codex/report-evidence-integrity`. Repository control checkout: sibling `repository`. Raw verification logs: sibling `evidence`. Existing installed runtime is untouched. The finalized plan and assessment were transferred explicitly; secrets and historical runtime data were not copied wholesale.

Milestone 1 offline containment implemented; live proof deferred by user approval. Milestone 2 offline implementation verified; milestones 3–5 offline implementation checkpointed; milestone 6 verification and recovery pending. Offline checkpoint: 120 focused tests passed, touched-area lint and dependency checks passed; see `../../reviews/2026-11-04-milestone-1-evidence.json`. On 2026-11-04 the user approved moving live SEC verification to final acceptance and continuing offline implementation now. The earlier live-SEC gate no longer blocks milestones 2–5. The final real source-complete and failure/recovery proofs remain required; offline results do not replace them. Dependency installation succeeded in the remote `.venv`. Eight new rendered-prompt contracts failed before the containment change; live model compliance is still unproven. A separate preferences-path regression reproduced home-scoped writes; the narrow `TRADINGAGENTS_PREFS_PATH` override is necessary to meet runtime isolation without changing HOME or the existing account's preferences.

Live-proof prerequisites updated by explicit user direction on 2026-11-04: use the supplied existing OpenRouter key despite its $250 weekly provider limit; the earlier requirement for a separate $10 non-resetting key is superseded. The goal retains its $10 aggregate verification budget, tracked using pre/post-run provider usage and bounded application tool/output/retry settings. Do not represent the provider limit as a $10 guarantee. Credentials were transferred only to the private sibling directory, outside Git, over verified SSH. The original deepseek/deepseek-v4.1-flash-1017 model is available in the current OpenRouter catalog; no substitution is needed. The user supplied the SEC contact email on 2026-11-04; it is configured in the private verification file outside Git. Free live SEC retrieval succeeded. Spend so far: $0. Keep the original October 19 case as historical fixtures; real proof uses the execution date. No milestone may be declared passed on prompt tests alone.

Date: 2026-10-20. Status: finalized and frozen after post-plan audit revision 1; implementation has not started and is not authorized by this finalization.

Audited repository commit: `75b4db62f4fdbed576f1d17f63e9746ac64a280f`. Application/predecessor baseline: `3411158f91eb267aab8760fc90afbf43556eb0bb` (0.7.0 plus local setup); the intervening commit changes only the assessment and this plan. These are review baselines, not authorization to branch from them for implementation. Repository: `/Users/zipp/Documents/ChatGPT/Tauric/TradingAgents`.

Read [the evidence assessment](../../reviews/2026-10-20-docn-audit-assessment.md) first. It maps all twelve audit findings to code and original run evidence, confirms primary accounting disclosures, and records verification limits.

## Branch and Release Boundary

- **Machine 2 / development:** GitHub `origin/staging` is the canonical development/integration branch. Before implementation, in a separately authorized execution task, fetch remote refs and compare the intended local `staging` SHA with the canonical GitHub `staging` SHA. Missing branches or differing SHAs require reporting and resolution; never silently choose `main`, `production`, a stale tracking ref, or this audit branch, and never rewrite history. Create a **new isolated feature branch and worktree from that exact current staging commit** only after the comparison succeeds. Recheck the plan's affected assumptions if that source differs from the reviewed application baseline.
- **Feature completion:** Commit implementation and proof freely in that isolated branch. Passing checks authorizes no merge, fast-forward, push, release, installed-app replacement or worktree removal. Machine 1 acceptance is not a prerequisite to starting development.
- **Development integration:** Only explicit user approval authorizing integration and push permits the verified feature commit to be integrated into `staging` and pushed to GitHub `staging`. It remains unreleased development work.
- **Stable release:** Only separate explicit stable-release approval authorizing integration and push permits the exact verified staging state to be integrated into `production` and pushed to GitHub `production`. Neither feature nor staging verification implies that approval.
- **Machine 1 / stable runtime:** Only after intentional production advancement may Machine 1 retrieve the exact resulting `production` commit, build/install, launch and verify it. Stable installation/acceptance is a conditional release step, not part of this feature's development-runtime proof. Machine 2 runs that proof in its isolated worktree with separate development data.
- **Audit-only boundary:** This revision uses read-only Git inspection and edits this plan only. No fetch, commit, branch/worktree operation, integration, push, database mutation, paid run or application change is authorized in this audit.

Read-only `git ls-remote origin refs/heads/staging refs/heads/production refs/heads/main` on 2026-10-20 returned only `main` at `e8f5503e9b86d5c2710b0c76b1f686703968c9df`; local branches likewise contain no staging/production. The canonical staging branch is **not yet established**. On 2026-10-20 the user selected `3411158f91eb267aab8760fc90afbf43556eb0bb` as the staging bootstrap baseline (retaining the verified launcher) and confirmed this computer is **Machine 2**. These planning decisions are resolved. Actual staging setup/push remains a later separately authorized operation, followed by exact canonical staging verification before implementation. Production remains a separate deliberate-release decision. This finalization neither creates nor advances either branch.

## Milestone 2 checkpoint — 2026-11-04

Exact statement display, metadata-preserving selection, dimension/invalid-value exclusion, unit/period ambiguity rejection and expanded accounting rows are implemented. The saved DOCN companyfacts fixture retains original filing records and a cache-content hash; it is not live retrieval evidence. 182 affected tests passed, including existing SEC vintage/unit/YTD, tool cutoff and graph checks. Immutable typed source/fact packages, bounded model views, and compatible quarter/TTM derivations are implemented. Independent review corrections preserve gross-flow reconciliation gaps, reported annual precedence and warning-linked evidence in partial tool views. See ../../reviews/2026-11-04-milestone-2-evidence.json. Issuer-specific narrative coverage is milestone 3; canonical accounting gates and final live proof remain outstanding.

## Milestone 3 checkpoint — 2026-11-04

Bounded SEC filing/subsequent-event discovery, safe exhibit retrieval, source hashes and dated section/table excerpts are implemented. Fundamentals exposes the retrieval tool, emits bounded structured disclosures, validates literal source spans/numbers/units and preserves the result through its private subgraph. Coverage gaps and rejected extractions are explicit; these checks do not certify semantic or accounting completeness. Independent review corrections reserve earnings/financing documents under the cap, preserve table context, and reject years mistaken for amounts and forward-looking statements classified as historical. 251 focused tests passed including analyst graph and checkpoint compatibility; dependency and lint checks passed. See ../../reviews/2026-11-04-milestone-3-evidence.json.

Synthetic fixtures are not recorded DOCN disclosure proof. Actual primary-document fixtures and live verification remain outstanding under the user-approved deferral; ambiguous multi-column KPI extraction remains visibly unavailable. The next implementation is the milestone-4 deterministic accounting/claim gate, while final acceptance must still close these source-proof gaps.

## Milestone 4 checkpoint — 2026-11-04

The pre-debate graph now acquires canonical evidence independently of model tool choices, verifies dated filing cells and their coverage, computes supported accounting bridges, and produces complete readable REVIEW state for critical gaps. Material claims render from source records; original model prose is retained separately in state. Canonical inputs/calculations and source-grounded disclosure excerpts reach downstream context. Optional KPI, definition and earnings-precision gaps remain warnings; actual reconciled contradictions remain critical. No source quantum, missing zero, residual transaction or disjoint obligation definition is invented.

369 affected tests passed, including a successful synthetic-source run through real graph nodes and a saved unavailable-source Python run. These are offline integration proofs, not live application acceptance. Touched-area Ruff, dependency and diff checks passed. Bounded independent review findings were closed with regressions; final whole-change audit remains milestone 6. See ../../reviews/2026-11-04-milestone-4-evidence.json. Milestone 5 must still enforce targets/output and exclude REVIEW from trading memory, settlement and performance scoring before feature completion. Actual primary-document layouts and final real CLI/recovery proofs remain required.

## Milestone 5 offline checkpoint — 2026-11-04

Typed EV/revenue and basis-matched P/E requests now produce deterministic conditional targets or explicit omissions. Publication replays requests against canonical facts and independently revalidated management outlooks, preserving source IDs, periods, assumptions and guidance/ambition distinctions. Latest-filed comparable outlooks supersede earlier ranges; contradictory same-vintage outlooks remain unavailable. Unsupported legacy numeric targets remain diagnostic inputs only.

Final decision, research/trader and debate output uses the canonical evidence/valuation projection when free prose cannot be reconciled. Original model narratives remain in evidence JSON diagnostics; other analyst narratives are explicitly unvalidated. Streamed intermediate AI/report text is labeled provisional without mutating graph state or tool arguments. Numeric sizing is omitted without validated portfolio/loss-budget/execution assumptions. REVIEW overrides stale ratings and targets, persists readable evidence, and is excluded from trading memory, settlement/reflection and scoring. Legacy REVIEW entries remain readable and do not prevent a corrected rerun. Backtests expose incomplete cells and retry only on explicit launch/resume.

Markdown/HTML exports retain report order and include evidence/quality JSON plus deterministic coverage and calculation tables. Required artifact replacement is atomic and write errors propagate. 413 affected checks passed together; all changed/new Python files passed Ruff, dependency and diff checks passed. See ../../reviews/2026-11-04-milestone-5-evidence.json. This is an offline implementation checkpoint, not overall acceptance. Final whole-change audit, full offline suite, checkpoint-version/recovery proof, rendered inspection and real CLI source-complete/unavailable-source runs remain outstanding. Paid verification spend remains $0.

## Milestone 6 verification in progress — 2026-11-04

The full offline suite on the recovery candidate passed 1,704 tests (one optional Bedrock dependency skipped; one integration test deselected by existing configuration). The earlier three macOS failures were Windows errno fixture setup; the portable simulation retains the same assertions. Checkpoint signatures now distinguish evidence/publication versions, preserve older saved threads, and do not resume them past the new gate. Full-state persistence uses strict atomic replacement; injected replacement failure preserves the prior snapshot and a retry succeeds. These are offline recovery checks, not the required real CLI recovery proof.

Independent whole-change review found incorrect period/metric binding in disclosure quotes and exact-equality false conflicts for rounded filing tables. Regressions and bounded corrections are implemented; independent re-review closed the reproduced guidance and rounding findings. Additional real-layout work is still in progress. No final full-suite or final audit claim applies to subsequent changes until they are rerun/reviewed.

Free live SEC retrieval on Machine 1 obtained 979 financial facts and four selected DOCN documents for 2026-11-04. Hidden inline XBRL previously consumed the visible excerpt allowance; the parser now excludes it and preserves source-backed table context. The real annual filing is 2,210,338 decoded bytes, supporting a bounded transport-cap adjustment from 2.0 to 2.5 MB without changing request/time/document caps. The real 8-K press-release link is recognized within the same accession. Text-limit warnings remain visible; this does not establish full-document coverage.

All eight critical checks now pass on the complete retained recorded-source package (1,019 facts, four selected filings). Borrowings use the sourced carrying-value inventory and facility disclosures; financed acquisitions/proceeds reconcile separately from principal. The primary cash period is the reported nine-month period, not derived TTM. Conventional cash generation is USD 193.713 million and the principal variant is USD 153.818 million. Optional warnings remain visible. This is a recorded-source gate proof with a constructed factual claim, not a real model/CLI proof. Synthetic HTML headers and evidence tables were inspected with headless Chrome on Machine 1; real saved-report inspection remains required. The live CLI runner is prepared with isolated results/cache/memory/preferences, zero SDK retries, three analyst tool rounds, one debate/risk round, bounded output and a conservative pre-run cost reservation. No paid model run has started; provider key usage is still $0. The final offline candidate suite passed 1,762 tests (one optional Bedrock skip and one integration deselection); touched Python lint, dependencies and diff checks passed. Independent whole-change and affected-source re-review closed all reproduced material findings. Real source-complete, unavailable-source REVIEW/no-memory and CLI restart/recovery proofs, actual saved-report inspection and final evidence review remain required.

## Outcome and delivery estimate

Produce stock research whose material financial facts trace to dated evidence, whose accounting and valuation arithmetic is reproducible, and whose final report does not disguise incomplete evidence as an actionable recommendation. Preserve the current local CLI workflow and report sequence.

- **Build size:** large.
- **Recommended model:** GPT-6 Astra, `gpt-6-astra`.
- **Reasoning effort:** medium.
- **Active implementation and verification:** approximately **24–40 hours** for all milestones. The first vertical containment/proof milestone is approximately 3–5 hours and does not constitute the whole correction. This estimate assumes the runtime prerequisites below are available; external waiting time is excluded.
- **Codex credit estimate:** not credible from current evidence. There is no measured credit baseline for this accounting/retrieval workload; API prices cannot be converted reliably into Codex credits. Paid application evaluation calls are a separate cost with a user-approved **$10 aggregate verification ceiling**.
- **Assumptions:** one isolated branch/worktree; US SEC-filing common stocks are the initial enhanced-coverage path; existing Python/provider infrastructure; free SEC sources and official releases; no new paid data service; focused offline checks followed by early and final real development-runtime proof. Time excludes approval waits, unavailable external services and expanded asset coverage.

Astra is recommended because this crosses source vintage, accounting definitions, derived periods, model output, checkpoint and decision-consumer contracts: plausible wrong interpretations can pass ordinary unit tests. This is engineering judgment, not a measured speed or cost advantage. Official [model documentation](https://developers.openai.com/api/docs/models/gpt-6-astra) supports its complex reasoning/coding use and medium effort. No running model or app model preference is changed by this recommendation. Sol medium is appropriate for bounded implementation/test support under the user's delegation policy.

## Scope and important choices

Extend the current SEC adapter and graph; reject a wholesale pipeline rewrite. Add reproducible evidence and arithmetic before adding another debating or approving agent.

Included:

- Precise, dated financial facts; debt/lease/equity/cash-flow/earnings bridges.
- Bounded retrieval of filed narrative and earnings-release evidence, including operating KPIs, guidance and subsequent material financing disclosures.
- Evidence quality status before debate and final validation before publishing a decision.
- Reproducible numeric targets; explicit assumptions and omission where unsupported.
- Source discipline for insider, news, sentiment and technical claims.
- Compatibility of CLI, Python API, Markdown/HTML reports, checkpoints, memory and backtests.

Excluded:

- Broker integration, execution authority, automated trade deployment, portfolio optimization or a correlation engine.
- A new performance database, empirical technical-signal service, universal accounting taxonomy engine, or guaranteed discovery of every KPI for every issuer.
- Mandatory paid consensus, universal transcripts/PDF crawling, new external services, or a stronger application model as the presumed fix.
- Rewriting the original DOCN report, its saved memory, or its historical rating. Corrected runs are new artifacts.

Only analyst-selected paths are assessed: a technical-only or non-SEC run is not silently represented as fully validated fundamental research. It receives an explicit coverage scope. Unsupported US-filing-specific checks are `not_applicable` for other assets, not fake failures or successes. General limits on ungrounded targets and claimed probabilities apply everywhere.

## Finalized user-visible behavior

For a selected US-stock fundamentals analysis, missing core evidence or a failed material reconciliation produces a saved **research-incomplete / REVIEW** report with specific reasons instead of a final Buy/Hold/Sell-family recommendation. Other completed research remains readable. The software does not add a confirmation dialog or require manual approvals during ordinary runs.

Missing optional information, such as consensus or an undisclosed KPI, is a visible warning and does not automatically suppress the whole report. A standalone unsupported target is omitted rather than blocking otherwise supportable qualitative research. REVIEW is distinct from Hold and must never be scored as a trading call.

This policy is part of the finalized plan. The user explicitly requested finalization without starting implementation; a later instruction to begin is still required.

## Evidence and calculation contracts

Use small versioned records in the existing run state and saved report directory, not a new service/database:

- `SourceRecord`: stable source ID, issuer/CIK, URL, accession when applicable, form, publication/filing date, retrieval timestamp, content hash and section locator. A retrieved page alone is not proof it was available on the analysis date.
- `FinancialFact`: metric, exact value, unit/currency, instant or start/end period, accounting basis, source ID, tag/context or exact table/paragraph locator, and reported-versus-derived status. Missing values are null with reasons, never zero.
- `EvidencePackage`: selected scope, facts, KPI/guidance records, definitions, source references and coverage results. It is immutable after validation for a run; analysts consume the same version.
- `Calculation`: named supported method, input fact IDs, explicit assumptions, period/units, formula ID, result, and validation status. No evaluation of arbitrary LLM-written Python or expression strings.
- `EvidenceStatus`: `sufficient`, `limited`, or `insufficient`, with check-level `pass`, `fail`, `unavailable`, `not_applicable` and stable reason codes. “Sufficient” means the declared checks passed, not that every narrative claim is true or the trade profitable.

Reuse existing config, routing, date guards, cache writes and Pydantic patterns. Narrative extraction can use the existing fundamentals model/tool budget, but candidate numbers are accepted only with matching source spans and correct issuer, period, unit and definition. An LLM's self-assigned confidence is not verification. Treat document instructions as untrusted content.

Preserve public tool signatures through adapters where needed. Store raw values for calculations; retain familiar text tables for readability. Classify company facts, vendor snapshots, management forecasts and analyst assumptions separately. Source-document availability after the run's cutoff must not leak into a historical run, even if it describes an earlier period.

## Milestone 1 — Prove the containment change through the real CLI

**Outcome:** A real Machine 2 CLI invocation acquires data, runs the changed analyst instructions through the selected provider, and saves a readable report that distinguishes unavailable evidence from undisclosed facts and avoids asserting an unsupported financing explanation. Known DOCN failure patterns become reproducible offline cases. This is the smallest end-to-end containment result, not the later accounting validator.

**Files:** Existing `agents/analysts/{fundamentals,market,news,sentiment}_analyst.py`, `agents/researchers/{bull,bear}_researcher.py`, `agents/managers/{research,portfolio}_manager.py`; `tests/fixtures/docn_2026q2/` (new); focused prompt/fixture tests.

**Implementation:** Preserve selected original tool outputs and primary-source excerpts with source dates/hashes in sanitized fixtures. Include missing fields, inconsistent definitions, rounded inputs, headline ambiguity and unsupported $96 target examples. Do not copy credentials, personal paths, or the whole runtime cache into fixtures. Add a fixture manifest identifying original evidence versus hand-authored expected results.

Change instructions to distinguish unavailable-to-tools from undisclosed-by-company, refuse motive/causal claims without evidence, scope empty search results to the queried feed/window, and describe prediction quotes as contract-specific market prices. Do not state empirical setup probabilities or moving-average crossover dates without a model; subjective scenario weights must say subjective. Do not infer holder cost bases from VWMA or remaining ownership from executed sales. Without portfolio/risk inputs, retain qualitative exposure guidance rather than presenting a numeric allocation as risk controlled.

**Verification and primary proof owner:** First run focused prompt/fixture checks, then exercise the actual CLI path below before broadening acquisition, schemas or validation in milestones 2–5. Inspect the saved report and original tool output to verify that the unsupported transaction inference is not presented as fact; a clean process exit alone is insufficient. If prompts do not achieve this bounded containment outcome, record the failed proof and resolve the affected behavior before declaring milestone 1 passed; do not claim reliable financial validation until the later deterministic work. Preserve the existing milestone order. Mocks support but do not replace this proof.

**Real entry point and dependencies:** Launch `Start TradingAgents.command` from the new feature worktree on Machine 2 (or its identical `.venv/bin/python -m cli.main` entry point if the agreed baseline lacks the launcher). Use that worktree's editable installation and Python environment. Required runtime dependencies are OpenRouter with the approved key/model, the existing market-data path, and SEC for the selected fundamentals tools; no broker, daemon, new database or Machine 1 installation is involved. Use DOCN with market and fundamentals analysts and one research/risk round, initially using the execution day's date to avoid mistaking historical Yahoo withholding for a retrieval defect. Keep the October 19 case as the deterministic historical fixture. Record the date/model/analyst selection explicitly; do not present the new date as a rerun of the original market conditions.

**Minimum controls and destination:** Before launching, set `TRADINGAGENTS_RESULTS_DIR`, `TRADINGAGENTS_CACHE_DIR`, and `TRADINGAGENTS_MEMORY_LOG_PATH` to a unique disposable development-run directory on Machine 2; confirm the resolved paths. Use an empty development memory log so the parallel Memory Log node cannot settle the user's historical calls or incur unrelated reflections. CLI preferences are home-scoped (`cli/prefs.py:28`), so use the designated Machine 2 development account/runtime and verify it is not sharing Machine 1's runtime home. Do not repurpose `HOME` or change global preferences to simulate isolation. Disable update notices for repeatability and use existing finite tool/retry/token limits. Select provider/model IDs available at execution; no silent substitution. The user approved a $10 aggregate verification budget. Before this path, configure and verify a dedicated provider-enforced key limit within that total and obtain the SEC contact identity; the current CLI has no proven dollar-budget limiter. Do not introduce a custom billing service. Budget configuration and paid calls are deferred to authorized execution.

**Evidence:** Use the CLI's save option (`--save --no-show` for the fully specified headless path), retain its resolved save-directory message, and inspect `results_dir/reports/DOCN_<timestamp>/complete_report.md`, `complete_report.html`, analyst sections and the full-state JSON under `results_dir/DOCN/TradingAgentsStrategy_logs/`. Record commit, source URLs/dates, run settings, exact command with secrets redacted, output paths, provider usage/cost if available, and observed report content. Verify the worktree's imported package path. Open the HTML report. Resolve dependency/authentication/network/configuration/runtime blockers before continuing the dependent build. If this real path cannot run, milestone 1 and overall completion remain explicitly incomplete; do not substitute mocked success.

## Milestone 2 — Preserve exact SEC facts and expose omitted accounting detail

**Depends on:** milestone 1 offline containment; its live SEC proof is deferred to final acceptance by explicit user approval on 2026-11-04.

**Files:** `dataflows/vendors/sec_edgar.py`, `dataflows/router.py`, `agents/tools.py`; new `dataflows/financial_evidence.py`; existing SEC, units and statement-timing tests plus new fixtures.

**Implementation:** Refactor the current fact selection to retain selected fact metadata rather than only `(end, span) -> value`. Maintain filing cutoff/restatement behavior. Expose selected rows for current/noncurrent borrowings, finance leases and equipment obligations, operating leases, cash/restricted cash, issuance/repurchases, equity components, compensation, software capex, financed equipment cash flows, financing repayments, noncash additions, tax, interest, and basic/diluted shares. Verify tag meaning and alternate coverage per period; never sum overlapping total/component tags. Where custom tags or narrative are required, report the gap for milestone 3.

Preserve numeric precision and currency/unit identity. Bound the history sent to models without discarding the periods needed for comparisons and TTM. Keep YTD periods explicit. Derived Q4 and TTM additive flows are allowed only with compatible fiscal dates, units and vintage, explicit formulas, and all source IDs. EPS and weighted share counts are not additive; use reported EPS or a complete numerator/denominator bridge, otherwise unavailable.

**Verification:** DOCN source values survive unchanged; revenue growth uses exact inputs. Fixtures cover alternate tags, duplicate tags, dimensions, missing versus zero, USD/share units, multi-currency mismatch, quarter versus YTD, non-calendar fiscal periods, restatements after cutoff, and incomplete period derivation. Existing point-in-time and vendor fallback tests stay meaningful. Do not fix sparse tagging by relabeling unverified vendor data as filed data.

## Milestone 3 — Retrieve dated filing narrative and earnings disclosures

**Depends on:** 2.

**Files:** `dataflows/vendors/sec_edgar.py`, new `dataflows/vendors/sec_documents.py`, `agents/tools.py`, `agents/analysts/fundamentals_analyst.py`, `agents/state.py`, `dataflows/router.py`; new disclosure tests.

**Implementation:** Discover official documents from SEC submission/filing metadata using the resolved issuer, including the latest eligible 10-Q/10-K and earnings-release 8-K exhibits. Select relevant subsequent financing disclosures up to the analysis cutoff. Prefer these stable official HTML/XML sources over an open-ended web crawler. Provide bounded, section-addressable text/tables for equity, financing, commitments, operating metrics, guidance and earnings reconciliation. Reuse request timeouts/cache handling and respect SEC request limits. Configure a real SEC contact User-Agent when live retrieval is used; do not invent user contact details.

Extract a bounded list of disclosed operating KPIs with definitions, period, comparisons and source spans. Distinguish AI customer spend from AI product revenue, backlog from recognized revenue, guidance from ambitions, and current disclosures from old ones. Coverage is established from sections retrieved and checks executed, not an LLM asserting “complete.” Missing documents or unsupported formats are visible coverage gaps. An optional official IR fallback must retain timestamp/provenance checks and restrict fetches to verified issuer domains; no arbitrary URLs or credential-bearing fetches from model output.

Do not blend June balances with later share issuance to manufacture current leverage. Present dated snapshots and subsequent events; produce a pro-forma figure only with a complete, explicitly labeled bridge. Consensus is optional; if no dated source/basis exists, say unavailable. No new vendor subscription.

**Verification:** Recorded DOCN filings/releases expose the omitted metrics and financing explanations with correct definitions. Negative fixtures include wrong issuer, post-cutoff release, revised page with unverifiable original vintage, missing exhibit, source timeout, malformed HTML, unit ambiguity and injected instructions. A second SEC issuer fixture prevents a DOCN-only implementation. Live read-only retrieval is a separate integration check and never replaces deterministic fixtures.

## Milestone 4 — Calculate financial bridges and check evidence before debate

**Depends on:** 2–3.

**Files:** new `agents/evidence_validation.py`, `dataflows/financial_evidence.py`, `agents/state.py`, `graph/{setup,propagation,trading_graph}.py`, `graph/analyst_execution.py`; new reconciliation and graph tests.

**Implementation:** Compute financial bridges deterministically: assets/liabilities/equity identity; opening-to-closing equity; classified obligations; operating cash less explicitly enumerated capital spending; separately labeled financing-principal cash generation; GAAP earnings/shares and management-adjusted reconciliation when available. Preserve unresolved definition differences. Reconciliation tolerance follows disclosed precision and component count; never invent a balancing plug. Missing a required component is `unavailable`, not a passing small residual.

Keep commitments, noncash asset additions and cash payments separate. Avoid counting financed equipment both at acquisition and principal repayment in the same measure without an explicit accounting definition. Do not deduct operating lease cash twice. Do not compare lease-inclusive EV with an incompatible EBITDA basis. Distinguish diluted EPS numerator adjustments for convertibles from simple net-income/share division.

Integrate a bounded check at the analyst-to-debate boundary. Critical checks for selected US-stock fundamentals: source period/unit/issuer validity; core statement coverage and accounting identity; equity movement coverage; material debt/lease/cash-flow perimeter; relevant operating/guidance disclosure retrieval status. An undisclosed optional metric is not itself critical. Materiality must be explicit in code/tests and tied to source precision and the calculation being used, not a hidden prompt judgment.

Insufficient core evidence returns an explanatory REVIEW result and saved research without actionable downstream trading instructions. Build a complete terminal state with empty skipped debate/plan fields expected by `_log_state`, and provide an evidence-specific CLI explanation rather than the existing unparseable-rating message. Limited evidence passes only the supported scope to debate. The validator can establish source and arithmetic consistency; it cannot guarantee all prose reasoning. Pass canonical facts/calculations directly to downstream agents as authoritative context, not only the analyst's summary. Require a bounded structured list of material financial claims with fact/calculation references and reported/derived/hypothesis classification; render the financial evidence summary from validated claims. Unsupported transaction explanations or debt reconstruction remain unverified hypotheses, not facts the debate can promote. If structured extraction fails, preserve the raw narrative as unvalidated research and do not treat it as a verified fundamentals package. Test a valid source package paired with contradictory analyst prose: the contradiction must be corrected or marked insufficient before it becomes the evidence for a decision. Do not add an unbounded repair loop or another paid verifier by default.

**Verification:** Good fixtures pass; an omitted offering, overlapping lease totals, unavailable source, incompatible periods and unexplained material equity residual cannot pass. A complete package with no NRR still passes with a warning. A package with valid bridges but a contradictory material analyst claim does not silently pass. Technical-only, crypto, non-US and fundamentals-disabled runs do not accidentally enter US accounting checks. Graph joins and parallel analyst state remain isolated by run.

## Milestone 5 — Make targets and final decisions traceable across all output paths

**Depends on:** 4.

**Files:** `agents/schemas.py`, `agents/structured.py`, `agents/managers/{research,portfolio}_manager.py`, `agents/trader/trader.py`, `agents/rating.py`, `graph/trading_graph.py`, `cli/run.py`, `reporting.py`, `report_html.py`, `memory/{log,settlement}.py`, `backtest.py`; valuation and output compatibility tests.

**Implementation:** Keep narrative analysis but require machine-readable inputs/method/basis for published financial targets. Initially support the methods already needed by the report: an EV/revenue scenario bridge to equity/share value and explicitly basis-matched earnings multiples. Clearly separate a technical price level from fundamental fair value. If scenarios are probability-weighted, validate weights, units and calculation; label subjective weights and do not call them calibrated. Other unsupported methods may be described qualitatively without a numeric target. A broken target alone becomes null with an explanation. This applies to material numeric targets in the research/trader plans, summary, thesis and free-text fallback as well as the typed field. Use a canonical validated target section and exclude or explicitly mark incompatible raw model claims as unvalidated; do not leave an unqualified $96 target in user-facing prose after nulling the field. If final prose cannot be reconciled safely with the structured target record, publish the deterministic evidence summary with the unvalidated narrative separated, rather than pretending the complete narrative passed.

Compare forecast assumptions with retrieved management outlook/ambitions for the same period; disclose material divergence and rationale. Absence of consensus must not cause invented consensus. Numerical position sizing requires actual portfolio/loss-budget and execution/gap assumptions; lacking those, output qualitative guidance. This does not introduce a new portfolio sizing engine.

Apply final evidence/target status outside the LLM so free-text fallback cannot bypass checks. For an insufficient research package, explicitly set `final_rating=REVIEW`; remove conflicting actionable summaries/targets and ensure `run_rating()` respects the authoritative status. Retain original intermediate evidence separately for diagnosis. New evidence-REVIEW outcomes are saved in reports, quality artifacts and the full-state log, but must not be inserted into trading decision memory. They must not enter performance scoring, automatic paid settlement/reflection or past trading lessons. Existing legacy REVIEW memory entries remain readable but are excluded from settlement and trading context without rewriting their history. A corrected rerun for the same ticker/date must remain able to store a valid decision. For backtests, explicitly retry evidence-REVIEW cells only when the user launches/resumes the backtest, since they have no completed decision-memory marker; show the prior quality outcome and do not add automatic background retries or a new completion database. Verify this resume policy and report unscored/incomplete cells accurately. Test typed responses, free-text fallback and providers lacking structured output. Missing optional fields remain backward-readable; old completed reports remain unchanged and marked legacy/unvalidated when necessary.

Publish concise evidence coverage, calculation tables and warnings in existing Markdown/HTML reports, plus `evidence.json` and `quality.json` beside them. Use deterministic rendering for canonical calculated values, rather than allowing the narrative to overwrite them. The display must not label all prose “verified.” Reuse the existing report writer; do not build a separate dashboard.

**Verification:** A model returning $96 without a valid bridge cannot publish it as a verified target. Incorrect weights, nonfinite/negative prices, wrong units, mixed EPS bases, nonpositive denominators and missing inputs are rejected appropriately. Test an unsupported target repeated in fallback prose, not just an invalid typed field. Critical REVIEW survives streamed and headless CLI/Python output, free-text fallback, report rendering, memory and backtest paths without turning into Hold or a tradeable call. Warning-only cases remain usable. No historical decisions are silently altered.

## Milestone 6 — Prove the complete path and preserve recovery

**Depends on:** 1–5.

**Files:** Existing checkpoint, graph, CLI/reporting, rating, memory and backtest tests; new `tests/test_report_evidence_integrity.py`; `graph/trading_graph.py` run signature; documentation and evidence records.

**Implementation:** Version the evidence schema and checkpoint run signature so a pre-validation checkpoint cannot resume past the new checks. Preserve old checkpoint files and explain incompatible-resume behavior. Use temporary data/memory paths for all evaluation. Save a reproducible test manifest with code revision, fixture hashes, source dates, configuration, commands and results; exclude secrets.

Run focused tests first, then the entire offline suite because graph/state/rating behavior crosses application boundaries. Obtain independent code review of period/definition math and REVIEW propagation; close material findings. Retain existing passing evidence only when its source/dependencies remain unchanged.

**Commands (initial focused baseline, then extend with new test files):**

```sh
.venv/bin/python -m pytest -q \
  tests/test_sec_edgar.py tests/test_statement_knowledge_time.py \
  tests/test_fundamentals_units.py tests/test_fundamentals_lookahead.py \
  tests/test_structured_agents.py tests/test_rating_integrity.py \
  tests/test_graph_end_to_end.py tests/test_checkpoint_resume.py \
  tests/test_reporting.py tests/test_report_html.py tests/test_backtest.py
.venv/bin/python -m pytest
.venv/bin/python -m pip check
```

The repository's default pytest configuration excludes integration tests. Inspect each failure and distinguish product, fixture and external failures; do not loosen assertions to make the suite pass. Any pre-existing failures require an explicit impact assessment and resolution or user decision before claiming full completion.

**Acceptance:** Replay corrected and incomplete DOCN fixtures end-to-end with fake model/tool responses; prove arithmetic/provenance and output behavior, not specific investment direction. Add a second issuer, non-SEC asset, technical-only selection, retrieval-failure, structured-fallback, concurrency-isolation and old-checkpoint case. Assert retained point-in-time restrictions. Open rendered HTML and verify coverage warnings, tables and citations visually.

**Required final real-path proof (primary owner: milestone 6):** After the offline suite and proportionate hardening, rerun the milestone-1 CLI-to-saved-report path on the final candidate commit in Machine 2's isolated environment. Inspect the actual dated sources, canonical financial bridges, evidence/quality artifacts, final target or explicit omission, HTML display and decision-memory outcome. A valid run may conclude REVIEW if live evidence is unavailable; that proves fail-safe handling but does not prove the successful evidence-complete path. Require at least one source-complete real run and a controlled unavailable-source run through the real application, verifying REVIEW and absence of a trading-memory entry for the latter. Limit the failure injection to the isolated runtime; do not disable or alter shared providers. Reuse recorded inputs for targeted failure fixtures, but distinguish them from live-source proof. Inspect a restart/checkpoint recovery on this development path when changed checkpoint behavior is exercised; the fake graph test alone is not runtime proof.

The user approved **$10 total** for the initial/final proofs and necessary bounded failure/recovery checks on 2026-10-20, not $10 per run. Configure and verify a dedicated OpenRouter key limit within that aggregate ceiling before the first paid call. The limit is a ceiling, not a prediction or permission to increase spend; any increase requires new approval. If it is exhausted, a provider is unavailable, or no source-complete run can be obtained, preserve passing offline evidence and report the missing real proof: **implementation completion remains incomplete**. Do not claim profitability or universal hallucination prevention. Finalizing the plan does not start paid execution; calls remain deferred until implementation is authorized.

## Runtime ownership and operational reliability

Only touched boundaries receive new checks. Primary ownership is:

| Concern | Owner and required evidence |
|---|---|
| Source selection, freshness and cache | Milestones 2–3: existing SEC adapter/date guards/cache are authoritative for source availability; source IDs refer to immutable evidence from that run. Apply finite document-count, response-byte and request-time limits to new narrative retrieval, with a visible incomplete-coverage reason on truncation. Cache reuse must still honor filing cutoff. No new refresh daemon or registry. |
| Financial values and decisions | Milestone 4 owns canonical facts/calculations and evidence status in run state. Milestone 5 owns final publication/rating enforcement. JSON and Markdown/HTML are snapshots of that state, not independently editable competing authorities. |
| New stored data and growth | Milestones 3 and 5: write selected evidence/quality artifacts once per saved run using the existing results directory; checkpoints use the existing cache location. Bound per-run acquisition and retain only referenced excerpts/metadata rather than copying entire caches or repeatedly appending the same evidence. Completed reports remain user-owned and grow with saved runs, with manual retention as today. No silent deletion or new retention service. Disposable proof directories are retained through acceptance, then removed only under cleanup authority. |
| Partial writes and unavailable dependencies | Milestone 5: use the existing atomic-file helper where appropriate for new JSON artifacts; inspect its cache-oriented failure semantics before reuse. Never announce saved/verified evidence when required files failed to persist. Milestone 3 uses existing finite network retries/timeouts and produces unavailable coverage; milestone 4 decides its effect. Milestone 6 proves interrupted/restarted writes and changed checkpoint paths without touching user data. |
| Memory and backtest | Milestone 5 owns REVIEW exclusions and same-date corrected retry behavior; milestone 6 verifies them. Existing decision memory remains the authority for actual trading calls, never failed evidence packages. |
| Runtime acceptance | Milestone 1 owns the early real CLI/report proof; milestone 6 owns final complete real proof and affected recovery. Evidence from each is required before its dependent milestone/handoff. |
| Broker/production worker/database migrations | **Not applicable:** this scope introduces no broker, server worker or database migration. Existing checkpoint SQLite is applicable only to schema/signature and restart compatibility already assigned above. |
| Machine 1 installed-product acceptance | **Not applicable to feature completion:** required only if a later stable release is explicitly approved and intentionally placed on production; then verify exact-commit launch/report behavior on Machine 1. |

## Release, rollback and completion

Apply the Branch and Release Boundary above. The plan, staging bootstrap choice and verification budget are finalized. Implementation starts only after a later user instruction to begin, authorized staging establishment, and successful canonical staging verification on Machine 2. Commit task changes and evidence on the new isolated feature branch. This audit's uncommitted plan revision must be preserved in the later authorized handoff; it is not already part of any GitHub baseline.

**Feature-branch completion** requires all offline acceptance checks, the early and final real Machine 2 proofs, independent review closure, and an exact verified feature commit with a clean task worktree. An offline-only handoff may report progress but is not completion. No Machine 1 acceptance is needed to begin or finish this development proof. Do not push, integrate, replace the stable application, delete worktrees or overwrite historical reports as a consequence of completion.

**Integration into staging** is a subsequent explicitly approved operation, including explicit push authority, targeting the verified feature commit; staging remains unreleased. **Stable release into production** is a different explicitly approved operation, including explicit push authority, targeting the exact verified staging state. **Machine 1 installation and acceptance** follows intentional production advancement only and uses the exact resulting production SHA. Never release automatically because feature or staging checks passed.

Feature rollback means reverting task commits in the development feature environment while retaining reports/evidence and ensuring an older consumer cannot treat REVIEW records as actionable. Rollback of integrated or released state, history changes, pushes, or Machine 1 replacement requires its own explicit authority; this paragraph is not standing release authorization.

## Deferred work and execution prerequisites

Deferred: empirical technical calibration, return distributions/transaction-cost modeling, comprehensive ownership filings, universal issuer KPI extraction, consensus subscriptions, correlation-based portfolio sizing, automatic earnings monitoring, and research-profitability evaluation. Each is a separate outcome with its own data/cost requirements. Existing backtests and decision memory are the starting point if those are later requested.

Planning decisions are resolved: the scoped outcome and research-incomplete/REVIEW policy are finalized, staging will be established from `3411158f91eb267aab8760fc90afbf43556eb0bb`, this host is Machine 2, and the aggregate paid verification ceiling is $10. Execution prerequisites remain: a later instruction to begin, separately authorized staging setup/push and exact canonical comparison, isolated development paths, and verified provider budget controls/SEC contact identity before paid proof. These are operational prerequisites, not requests to reapprove the resolved choices. Production branch establishment/release and Machine 1 acceptance can remain deferred until stable-release authorization. No additional architecture decision is needed for ordinary details within the approved scope.

## Post-plan audit record — single revision, 2026-10-20

**Overall verdict: revised and ready.** Technical/workflow corrections were written once in place. The user resolved the staging baseline, Machine 2 identity and $10 verification budget on 2026-10-20 and requested finalization without implementation. The plan is now frozen; execution and release remain deferred. This is decision closure following the single audit, not a second audit or a separate corrected plan.

**Reviewed baseline:** HEAD `75b4db62f4fdbed576f1d17f63e9746ac64a280f`; predecessor application `3411158f91eb267aab8760fc90afbf43556eb0bb`; upstream/fork main `e8f5503e9b86d5c2710b0c76b1f686703968c9df`. HEAD differs from the predecessor only in the two planning/review documents. The predecessor's 158 distinct focused passing tests are retained as baseline evidence, not rerun or represented as proof of proposed code. At audit time the baseline and budget decisions were unresolved. The subsequent user instruction finalized this plan and those choices but explicitly withheld implementation start; no release decision is implied.

| Original plan area | Finding | Disposition in this revision |
|---|---|---|
| Baseline; Release, rollback and completion | **FAIL:** an unspecified agreed baseline could bypass canonical staging; both required remote branches are absent. | Added exact Machine 2/staging preflight and explicit four-stage boundaries. User selected `3411158` for staging and confirmed this host as Machine 2. Actual branch setup and canonical verification remain deferred; no fetch or mutation during this audit/finalization. |
| Milestone 1 verification | **FAIL:** fake prompt capture alone is not the smallest proved user-visible path. | Same first containment milestone now ends in real CLI → provider/data → saved report inspection on Machine 2 before the existing milestones 2–5. No broader technical feature or new service added. |
| Milestone 6 and local handoff | **FAIL:** optional live evaluation allowed completion without exercising the real application. | Real final source-complete and failure/recovery proof is mandatory; inaccessible/unaffordable proof leaves completion incomplete. User approved $10 aggregate verification spend; budget controls and calls remain deferred to authorized execution. |
| Evidence contracts; milestones 3–6 | **PARTIAL:** new artifacts/cache limits and state ownership were insufficiently explicit. | Assigned single owners, bounded acquisition, specified manual report retention, existing persistence reuse and save-failure behavior. No new database, retention worker, service or registry. |
| Scope and milestones 2–5 | **PASS:** extends working SEC/rating/reporting mechanisms rather than replacing them. | Preserved accounting/valuation safety contracts, milestone order, tests and exclusions. Read-only inspection reconfirmed narrow SEC fields, free-text fallback, REVIEW/memory edge cases, and report/checkpoint destinations. |

**Affected-area recheck:** inspected launcher, CLI save/review flow, default path overrides, home-scoped preferences, SEC cache, report writer/tests, graph run signature/full-state persistence, memory/settlement and checkpoint tests; checked dependency/pytest configuration. No current runtime execution is needed or authorized for this plan-only audit. Verified the revised wording separates development proof from conditional Machine 1 acceptance and does not imply any automatic Git mutation/release. Decision closure updates only approvals, status and corresponding prerequisites; the technical milestones remain unchanged. The plan is frozen. Actual canonical staging establishment and verification remain required before implementation and have not been performed by this finalization.
