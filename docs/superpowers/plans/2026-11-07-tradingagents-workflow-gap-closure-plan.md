# TradingAgents workflow gap closure (post A–D)

**Status:** decisions D1–D4 approved by the user on 2026-11-07. R5 is integrated and pushed to staging at `730bbe04ce7ba382367463dccca57bc39b7e0e92` under explicit approval; all seven exact-staging CI jobs passed. R1 is integrated and pushed at `78e3611ffb3fd6d8672acc2c15f54489cc258ae6`; all seven exact-SHA CI jobs passed. Its 3448-pass local suite/native proofs and completed independent Claude Fable review (zero Critical/High/Medium, three Low observations retained) are recorded in the R1 report. R2 has started in separate `document-followup` worktree from that exact confirmed staging, with 32 baseline tests passed and the four original wrong rankings reproduced before implementation. R4/R3/Na/Nb have not started. User24-hour advance authority covers necessary stage integrations/pushes and audit retries within existing caps until2026-11-09T05:20:03Z. Post-plan audit on 2026-11-07: **revised and ready**, frozen after the affected-area recheck recorded below. This is plan readiness, not implementation, integration, spend or release authorization. This document supersedes `2026-11-07-tradingagents-rearchitecture-followup-plan.md` and `2026-11-07-tradingagents-node-workflow-plan.md`, which are kept for history.

**Goal:** Close every gap found by the 2026-11-07 node-by-node workflow audit, so that:
1. evidence the system already retrieved reaches every agent that needs it;
2. document follow-ups return relevant passages, and say honestly when they don't;
3. the decision you read leads with the decision, and the publication record keeps the Portfolio Manager's reasoning;
4. the next run inherits what this run decided;
5. every node's inputs and outputs can be inspected;
6. each agent does its job well on that evidence: the Research Manager uses what it looked up, the risk debate tests direction against the full research plan, the valuation shows the lease-inclusive view, and lessons reach the roles that size the decision.

**Spec:** `~/Claude/audits/2026-11-07-node-workflow-audit/` (README; parts A, B and C, with exact file:line evidence per finding). Executors read the matching part alongside each task.

**Baseline:** local HEAD, local `staging`, tracking `origin/staging`, and GitHub `staging` all resolve to `8920ffac07d1063001291799e99963403955582a`, confirmed read-only by `git ls-remote` on 2026-11-07. GitHub `production` remains `9ade69bf155d1b25699d3aecfff3c1b07752aff0`. Builds A–D are integrated; their completed acceptance/closure records and the exact-staging CI receipt are retained in `docs/reviews/2026-11-07-*-acceptance.md` and `release-records/2026-11-07-gap-closure-8920ffac/release-result.md` (all seven CI jobs reported passed). These are predecessor receipts, not tests rerun by this plan audit. Reference run: DOCN analysis date 2026-11-07, attempt `~/.tradingagents/logs/DOCN/2026-11-07/162527-34fe1c55`, publication `cfae95e9`, full state `~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-07_cfae95e9.json`. R5 bootstraps disposable recorded inputs for the first CLI proof; R1 owns the reusable `tests/fixtures/docn_2026_11_07/` fixture, including retained corpus and source bytes needed to rerun changed extraction. No secrets or private memory are committed. Offline proofs use these recorded inputs.

## Branch and Release Boundary

- Machine 2 owns development. Before implementation, fetch remote refs and confirm local `staging` equals canonical GitHub `staging`; report any discrepancy without silently choosing a baseline or rewriting history. This plan-only audit used read-only inspection and did not fetch or mutate refs.
- Each build starts in a new isolated feature branch/worktree from the exact current, confirmed `staging` commit containing its required predecessors. Do not develop directly on `main`, `staging`, or `production`, or branch ordinary development from `production`. Commit implementation and evidence on the feature branch. Existing launcher checkouts are not implementation worktrees.
- Feature completion means the exact local commit, applicable checks, runtime evidence and independent closure are complete. It authorizes no merge, fast-forward, push, deployment, installation, or worktree removal. Dependent builds wait for required predecessor evidence and separately approved integration.
- Only explicit development-integration approval naming the verified feature state permits integration into `staging`; pushing GitHub `staging` additionally requires that approval to authorize the push. Staging remains unreleased development. If integration changes the tested source or dependencies, verify the affected integrated behavior before using it as a successor baseline.
- Only separate explicit stable-release approval permits intentional integration of the exact verified staging state into `production` and an explicitly authorized GitHub `production` push. Passing feature/staging checks never supplies this authority.
- Machine 1 may pull the exact resulting `production` commit and build, install, launch and verify the stable application only after that release is approved and production intentionally updated. Machine 1 acceptance is not required to start development. All plan runtime proofs occur on Machine 2 in isolated worktrees and disposable stores; stable installation/acceptance is a separate conditional release stage.

**Shape:** seven builds in two phases.
- **Phase 1, code (R5, R1, R2, R4, R3):** proven offline against the fixture; no paid calls.
- **Phase 2, prompts and hand-offs (Na lower-risk, then Nb judgment changes):** each proven by paid DOCN and MSFT comparison runs, with a rating comparison at every step.

Phase 2 waits for Phase 1, because several prompt findings are partly caused by the evidence gaps that Phase 1 fixes.

Independent audit: required

## Finding coverage

Every audit finding maps to exactly one task. ID prefixes follow the audit parts. To avoid clashing with build names, the audit's risk findings R1–R5 are written **RK1–RK5** here, and its Advisory Audit findings A1–A3 are written **AA1–AA3**.

| Audit finding | Task | | Audit finding | Task |
|---|---|---|---|---|
| SA1 ATM missing from brief | R1.1 | | DF1 search ranks wrong blocks | R2.1 |
| SA2 text limit drops outlook | R1.2 | | DF2 "found" ≠ answered | R2.2 |
| SA3 float price in brief | R1.6 | | DF3 repeated follow-up passages | R2.3 |
| SE1 Sentiment calls ATM unverified | R1.1 (fixed by SA1) | | BB1 RPO history missing | R1.4 |
| SE2 undated fallback news | R1.5 | | BB2 duplicate questions / phrase form | R2.3 + N4.2 |
| SE3 "not supported" vs uncheckable | N2.3 | | BB3 hash IDs inflate prompts | N4.3 |
| SE4 run log hides stage | R5.2 | | BB4 unanswered opponent points | N4.1 |
| NE1 News returns not logged | R5.1 (via CN1) | | RM1 RM ignores follow-up passages | N1.1 |
| NE2 off-topic news, coverage "available" | R1.5 | | RM2 rationale cut at 300 chars | R4.2 |
| FA1 duplicate-document rejections | R1.3 | | TR1 risk roles lack RM plan | N1.2 |
| FA2 no lease-inclusive valuation | R1.7 | | TR2 Trader fallback cause hidden | R5.2 |
| FA3 disclosure rules too long | N2.2 | | TR3 merged levels / misattribution | N1.4 |
| ML1 lessons reach PM only | Nb.2 | | EX1 "evidence.json" wording | R3.1 |
| ML2 past_context not persisted | R5.3 | | EX2 manager export buries plan | R3.1 |
| ML3 HTML-escaped prompt context | R4.3 | | RK1 risk roles don't test direction | Nb.1 |
| EC1 duplicate/merged warnings | R1.6 | | RK2 duplicate turns in risk prompts | N4.3 |
| EC2 "limited" has no meaning | R1.6 + N1.4 | | RK3 escaped thesis_context | R4.3 |
| EC3 "$" denomination unknown | R1.6 | | RK4 risk roles lack RM plan/audit | N1.2 |
| CN1 multi-write tool returns unlogged | R5.1 | | RK5 risk export by role | R3.6 |
| CN2 brief + canonical context duplicated | N4.4 | | AA1 audit reads first 6k chars | R3.5 |
| P1 decision page buried (High) | R3.1 | | AA2 independence by slot | R3.7 |
| P2 "Changed since" noise | R3.2 | | AA3 audit result not on card | R3.1 |
| P3 conditions duplicated / capped | R3.3 | | M1 partial token observation | R5.4 |
| P4 no_case_reason truncated | R3.3 | | M2 exec-summary call not counted | R5.4 |
| P5 PM not told evidence status | N1.4 | | H1 same-day rerun not logged | R4.1 |
| H2 non-metric conditions lost | R4.2 | | H3 record drops PM reasoning | R3.4 |
| H5 operational headline incomplete | R3.6 | | H6 transcript stops after Trader | R5.3 |
| D11 trace switch (excluded from D) | R5.5 | | CN3, H4, H7 | checked sound; no task |

## Delivery estimate

Build size: large

This standalone metadata restates the existing overall plan size for the audit-policy parser; it does not change the per-build estimates or the claimed build stage.

| | R1 evidence | R2 doc follow-up | R3 decision page | R4 memory | R5 observability | Na lower-risk prompts | Nb judgment changes |
|---|---|---|---|---|---|---|
| Build size | medium | small | medium | small | small to medium | small to medium | small |
| Recommended model | GPT-6 Astra (`gpt-6-astra`), medium | GPT-6 Sol (`gpt-6-sol`), medium | GPT-6 Sol (`gpt-6-sol`), medium | GPT-6 Sol (`gpt-6-sol`), medium | GPT-6 Sol (`gpt-6-sol`), medium | GPT-6 Sol (`gpt-6-sol`), medium | GPT-6 Sol (`gpt-6-sol`), medium |
| Active implementation and verification | 10–15 h | 4–6 h | 8–11 h | 5–8 h | 8–12 h | 8–12 h | 5–8 h |

- Independent audits and gap closure: Phase 1 4–6 h, Phase 2 5–7 h. **Total 57–85 active hours**, summing the build and audit ranges. Overall build size: large. Approval waits and unavailable external systems are excluded.
- Astra for R1, because a plausible but wrong selection or dedupe rule passes local tests and silently changes which facts reach every agent (the reason Build A used Astra). Sol elsewhere: clear contracts, replayable, and quality in N is judged by the rubric and the independent audit, not by a stronger implementer. This is engineering judgment, not a measured comparison.
- Paid runs: six to ten traced runs planned. Required: Phase 1 baseline DOCN and MSFT, Na candidate pair, Nb candidate pair. Plus one retained-combination pair for Na and/or Nb if anything is dropped. The reference DOCN run used about 2.3M input tokens; this is a planning reference, not a measured forecast for every ticker. Comparison runs still make paid model calls. D4 and the recorded additions govern existing authorization; this plan audit grants no additional spend or retries. Obtain explicit authorization before any supplemental pair beyond the previously approved allowance. If a retained-combination pair fails, stop that build as incomplete rather than automatically buying another pair.
- Codex credits: no usage measurements exist for this repository, so I can't estimate them credibly.
- Assumes the DOCN fixture replays offline. If `document_sources` can't be rehydrated without the network, add 2–3 h to R1 for a fixture loader.

## Global constraints

- No change to rating eligibility, publication gating, evidence-gate pass/fail rules, or numeric validation, except where a task says so.
- Phase 1 build proofs use recorded inputs with no paid model or vendor calls. The two paid Phase 1 baseline runs in Sequence steps 6–7 occur after code-build acceptance, under the existing paid-run authorization. Phase 2 uses the candidate and, if needed and authorized, retained-combination pairs above; no implicit retries.
- Every new or changed input given to a model keeps source IDs, so claims stay traceable.
- Escape HTML only at HTML export, never in prompt text.
- Existing publication records are never rewritten; new fields apply to new records only.
- Prompt changes keep every existing safety and labelling instruction: unvalidated-reasoning labels, no guaranteed-fill language, qualitative sizing only.
- Each prompt change gets a unit test asserting the rendered prompt contains, or no longer contains, the specific text or input. Quality is judged by the comparison runs.
- Keep one primary owner per outcome: R5 owns trace/replay and comparison isolation; R1 owns evidence assembly and the reusable DOCN fixture; R2 owns retrieval status; N1.1 owns RM answer judgments and their delivery to the card; R4 owns condition continuity; R3 owns decision-page layout and publication narrative fields. Secondary tasks consume those contracts without creating another authority.

# Phase 1 — Code

## Build R1 — Evidence assembly (findings SA1, SA2, FA1, FA2, BB1, SE2, NE2, EC1, EC2, EC3, SA3)

**Worktree slug:** `evidence-assembly`.

### R1.1 Financing events in the shared brief (SA1)
**Files:** `tradingagents/agents/context.py::build_shared_source_brief`, `tradingagents/agents/evidence_validation.py` (~:407).
- When `filing_evidence` contains an 8-K Item 8.01 or 1.01 financing disclosure (ATM, notes, credit agreement) dated within the brief window, render one line per event: form, filed date, stated amount and currency, source ID. Build it from the same deterministic matcher that later builds `issuer_event_evidence.financing_records`, moved earlier and reused, not duplicated.
- [x] `test_brief_includes_retained_atm_8k` (DOCN fixture: "$1.0 billion" ATM line present with source ID), `test_brief_omits_financing_outside_window`.

### R1.2 Text limits never cut inside a guidance run (SA2)
**Files:** `tradingagents/dataflows/vendors/sec_documents.py` (block selection under the text limit), the contiguity validator named in part A SA2.
- When a document hits its text limit, keep or drop contiguous runs of blocks under the same outlook or guidance heading **as a unit**. If a run is dropped, record one gap naming the heading, rather than leaving holes the contiguity check rejects.
- [x] `test_outlook_run_survives_text_limit` (DOCN press release: blocks 41–50 kept together, FY2026 adjusted FCF margin 20–22 % and diluted shares 128–129M accepted), `test_dropped_run_records_named_gap`.

### R1.3 One document, one package (FA1)
**Files:** `tradingagents/agents/evidence_validation.py` (~:481), `tradingagents/dataflows/disclosure_context.py` (~:161).
- Deduplicate `quote_packages` by **document identity plus content**: issuer CIK, accession, primary-document URL or `source_id`, and `content_hash`. Identical identity and hash → collapse to one package. The same hash with conflicting identity metadata, or the same identity with a different hash → reject with an explicit "conflicting document metadata" reason. Never silently pick one. Issuer binding and known-at cutoff checks run on the collapsed package exactly as today.
- Bounded and full versions of one document: combine their blocks by locator. A block present in both must have identical text, otherwise reject as conflicting. A block present only in the full version is added. The combined package keeps the full version's block order, so contiguity checks see the real sequence.
- [x] `test_same_document_from_two_paths_is_one_source` (DOCN fixture: the 6 previously rejected records are accepted, and the 3 genuinely bad ones are still rejected with their original reasons), `test_same_hash_conflicting_accession_rejected`, `test_same_identity_different_hash_rejected`, `test_bounded_and_full_blocks_merge_by_locator`, `test_conflicting_block_text_rejected`, `test_cutoff_and_issuer_checks_unchanged_after_dedupe`.

### R1.4 Metric history, not just the latest change (BB1)
**Files:** the canonical context builder in `tradingagents/agents/context.py`, which renders the "RPO 893,828,000 → 799,707,000 −10.53 %" line.
- For each period-comparison KPI (RPO first; the mechanism is generic over the existing KPI comparisons in `kpi_comparisons.py`), also render the same quarter a year earlier and the latest fiscal year-end when they are in the retained corpus, each with its source ID. Label any recast ("prior periods recast to include all contracts") when the source says so.
- [x] `test_rpo_context_includes_year_ago_and_fiscal_year_end` (DOCN: $61M Q3 2025, $134.1M FY2025, $893.8M Q2, $799.7M Q3, with $345.1M due within 12 months).

### R1.5 Dated news and an honest coverage status (SE2, NE2)
**Files:** `tradingagents/dataflows/vendors/yahoo/news.py::_format_articles` (~:83), the news coverage builder.
- Print each article's publish date (UTC, ISO) and publisher. When the quote feed failed and the search fallback supplied the items, set coverage to `degraded: search_fallback, headlines_only` instead of `available`.
- [x] `test_formatted_articles_show_publish_date`, `test_search_fallback_marks_coverage_degraded`.

### R1.6 Small evidence corrections (EC1, EC3, SA3)
- Deduplicate warning messages; split "model submission rejected" from "source coverage gap" in the evidence-quality message. State in the evidence-quality message which optional evidence is missing, so "limited" carries an actionable meaning (EC2; the PM receives this line via N1.4). Map a `$` source unit to USD only when the same filing binds the reporting currency (an XBRL `USD` unit or a stated "U.S. dollars" reporting currency for that filing). Otherwise leave the currency unresolved, as today. Format the brief's price to source precision.
- [x] One test each, plus `test_dollar_sign_without_currency_binding_stays_unresolved`.

### R1.7 Lease-inclusive sensitivities: find where they are lost, then fix there (FA2)
**Files:** `tradingagents/agents/valuation_cases.py::price_case` (~:67–124), `tradingagents/agents/shared_valuation.py` (~:80–157).
- `price_case` already computes `finance_equipment` and `all_leases` sensitivities when the obligation inputs exist, and `shared_valuation.py` retains them separately from `scenario_results`. In the DOCN run both cases have `sensitivities: {}`. **First step:** replay the DOCN fixture through `price_case` and record which branch empties them: missing obligation categories, an exception path, the currency/basis guard (~:71), or delivery to the card. Write the finding into the build's review file before changing code.
- Fix at that point only. No second calculation path. If the cause is a missing input, supply it from the canonical obligations already retained. If it is delivery, render the existing sensitivities on the card.
- Every rendered sensitivity states its assumption explicitly: obligations as of their balance-sheet date (2026-09-30) held constant against the case's future period (for example FY2027), with no growth or repayment assumed. No change to which case is the base.
- Preserve the analyst's original submitted request, base-case capital assumptions and base target. Reuse `price_case` with a separately labelled source-bound sensitivity request when missing categories need to be supplied; do not silently rewrite the accepted base case. Missing/incompatible canonical categories remain unavailable, never zero or guessed. Verify original request/base target unchanged alongside the sensitivity result.
- [x] A regression test named for the root cause found, plus `test_docn_case_renders_finance_equipment_and_all_leases_sensitivities` (lower per-share figures than the $77.73 borrowings-only base) and `test_sensitivity_states_obligation_date_assumption`.

### Approved Amendment 1 tasks activated for R1

### G2 Prior trading inside a price band, computed by code

**Files:** `tradingagents/agents/tools.py::get_verified_market_snapshot` and the builder it calls (`build_verified_market_snapshot`); its tests.

- Append a "Prior closes by price band" table to the snapshot: from the latest completed close down to the lowest close of the last 252 completed sessions, in bands of 5% of the latest close. Each band lists the number of closes in it, the most recent date and the lowest and highest close. Bands with no closes say "no closes in the last 252 sessions". Point-in-time: only sessions on or before the analysis cutoff.
- No new vendor call: reuse the OHLCV the snapshot already loads, extending its window if it is shorter than 252 sessions.
- [x] `test_band_table_lists_march_closes_below_lower_band` (DOCN fixture, close 72.48 on 2026-11-06: the 65.2–68.9 band reports closes including 66.22 and 68.63/68.69 dated March 2026, and the 61.6–65.2 band reports 62.01), `test_band_table_respects_cutoff`, `test_empty_band_says_no_closes`.

### G4 Guidance grounding is stable on the same corpus

This is an acceptance check on R1.2 and R1.3, not new code unless it fails.

- Add a fixture for the `16416b7e` retained corpus next to R1's `tests/fixtures/docn_2026_11_07/` (same privacy rules: retained source bytes only, no memory or secrets).
- [x] `test_16416b7e_corpus_accepts_guided_shares_and_margin_guides`: deterministic discovery accepts Q4 2026 diluted weighted shares 128–129M, FY2026 diluted weighted shares 122–123M, Q4 and FY2026 adjusted EBITDA margin guides, and the FY2026 adjusted FCF margin guide.
- [x] `test_discovery_is_order_independent`: the same corpus with documents and blocks in shuffled order yields an identical accepted set and identical record IDs.
- [x] R1 proof records accepted counts for both the `913554d4` and `16416b7e` corpora, before and after. If the two corpora themselves differ (different blocks retained), record which blocks differ and why; a difference in retention is an R1.2 defect, not an acceptable run-to-run variation.

### G5 Peer exclusion only for facts the peer statistics read

**Files:** `tradingagents/dataflows/vendors/sec_edgar.py` (`_select_facts`, ambiguity raise ~:271), `tradingagents/agents/valuation_reference_flow.py::_fetch_peer` (~:242).

- At build start, list the metrics `calculate_peer_statistics` and the peer render actually read (expected: Revenue, Gross Profit, Common Shares Outstanding; verify). For peer packages only, an ambiguity in any other metric drops that metric from the package with a recorded gap ("Assets ambiguous at 2023-12-31; not used for peer statistics") instead of raising. An ambiguity in a metric the statistics read still excludes the peer with today's reason.
- Subject-issuer packages are unchanged: ambiguity still raises.
- [x] `test_peer_ambiguity_in_unused_metric_keeps_peer` (synthetic companyfacts: conflicting `Assets` at 2023-12-31, clean revenue and shares: peer status `available`, gap recorded), `test_peer_ambiguity_in_revenue_still_excludes`, `test_subject_ambiguity_still_raises`.
- [x] R1 proof: NBIS from the `16416b7e` recorded inputs is either accepted or excluded for a reason that names a metric the statistics read.

### G7 Maturity totals labelled as undiscounted, with present value beside them

**Files:** the canonical context builder in `tradingagents/agents/context.py`; the filing-cell extraction that already reads the lease table (`block-226` in DOCN).

- When the retained finance-lease and equipment maturity table yields both a per-year undiscounted schedule and its present-value total, render one line: "Finance lease and equipment maturities (undiscounted, include imputed interest): 2027 $250.0M; total $X; less imputed interest $Y; present value $923.6M (F25). Scheduled payments are not principal." Values come only from the retained table with source IDs; if any piece is missing, render nothing for that piece.
- [x] `test_maturity_line_labels_undiscounted_and_present_value` (DOCN fixture), `test_partial_table_renders_only_present_pieces`.

### R1 proof
Full `pytest -q` and `ruff check` green at one commit. A DOCN fixture replay of Source Acquisition through Evidence Check shows: ATM in brief; 0 false disclosure rejections; FY2026 outlook accepted; RPO history in context; dated news; lease-inclusive sensitivities on both DOCN cases. Record before and after counts in `docs/reviews/<date>-evidence-assembly.md`.

## Build R2 — Document follow-up that finds the right passage (DF1, DF2, DF3, BB2 dedupe)

**Worktree slug:** `document-followup`.

### R2.1 Query terms that mean something (DF1)
**Files:** `tradingagents/dataflows/filing_search.py` (~:122–131), `tradingagents/agents/document_questions.py`.
- Before scoring, drop stop-words, question filler (does, say, from, what, how) and bare dates/years unless they are the only terms. Score phrase bigrams above single words, and weight body text above section headings.
- [ ] `test_question_shaped_rpo_query_returns_rpo_note` (DOCN: bear-1's question returns the Q3 RPO note containing $799.7M and $345.1M), `test_bull1_query_no_longer_returns_lease_tables`, `test_keyword_queries_unchanged` (existing keyword behaviour preserved).
- Preserve instrument-identifying years such as `2026 Convertible Notes` versus `2030 Convertible Notes`, the existing alias expansion, and multi-instrument passage reservation. Strip date filler only when it is not part of an identified instrument; prove the existing named-note cases still pass.

### R2.2 Retrieval says what it found, not whether the question was answered (DF2)
- Deterministic status only: `relevant_passages_found` when every non-stop content word of at least one query phrase appears in a passage body, otherwise `no_relevant_passage`. Retrieval never claims a question was **answered**. A passage can contain every search word without explaining, for example, why RPO declined.
- The card shows retrieval status and stops printing "N passages retrieved". N1.1 later owns the separate, unvalidated RM answer judgment and its card wiring; until that build is accepted, show "RM answer judgment unavailable" rather than inventing one. R2 does not depend on a future Phase 2 schema.
- [ ] `test_unrelated_passages_are_not_reported_as_relevant`, `test_retrieval_never_reports_answered`, `test_card_shows_retrieval_status_without_rm_judgment`.

### R2.3 Dedupe across questions and roles (DF3, BB2)
- Deduplicate near-identical questions across bull and bear before lookup (freeing the slot), and deduplicate passages across results before building the follow-up context.
- [ ] `test_duplicate_rpo_questions_use_one_slot`, `test_followup_context_has_no_repeated_passage`.

### R2 proof
Full suite and Ruff green. Replay the four logged DOCN questions through the new search: record each question, the top passage before and after, and the status in `docs/reviews/<date>-document-followup.md`.

## Build R3 — The decision page and the publication record (P1, P2, P3, P4, AA1, AA2, AA3, H3, EX1, EX2, RK5, H5)

**Worktree slug:** `decision-page`. Layout per approved decision D1.

### R3.1 Lead with the decision (P1, EX2)
**Files:** `tradingagents/agents/decision_context.py`, `tradingagents/reporting.py`, `tradingagents/report_html.py`, `tradingagents/agents/output_validation.py` (:147, :161).
- Order of `5_portfolio/decision.md` and the decision section of the complete report: (1) rating and horizon; (2) the PM's executive summary and thesis, labelled "model reasoning, not validated"; (3) audit summary line ("7 findings; PM responded to 7", AA3); (4) advisory conditions with comparator and threshold; (5) material changes since the prior publication; (6) what the price implies; (7) valuation tables and scenario comparison. Remove the placeholder "Executive Summary" line. `manager.md` likewise puts the plan before the evidence rows.
- Change "retained in evidence.json diagnostics" to "diagnostics.json" (EX1).
- [ ] `test_decision_page_starts_with_rating_then_pm_summary` (DOCN fixture: PM summary within the first 40 lines), `test_no_placeholder_executive_summary`, `test_manager_export_plan_first`.

### R3.2 Changes worth reading (P2)
**Files:** `tradingagents/agents/assumption_history.py` (~:112–117).
- Match cases by `(method, period, scenario role)`, not free-text name. If the method or code revision differs, print one line ("Prior publication used a different valuation method; field-level comparison not shown"), not per-field diffs. Show material changes only: revenue forecast, multiple, share basis, a case added or dropped. Label the prior by publication time, not just date, when it is from the same day.
- "Code revision" here means an incompatible valuation calculation/contract revision, not any change to the repository-wide source hash (`publication.runtime_versions` changes for unrelated edits). The current case schema has no scenario-role field: use a role only if explicitly supplied in retained data; never infer bear/base/bull from ordering or price. If matching is ambiguous, report additions/removals once instead of inventing identity. No new role registry or historical-record rewrite is needed.
- [ ] `test_same_day_method_change_prints_one_line` (DOCN: 21 lines → 1), `test_renamed_case_matched_by_role_shows_revenue_change` (1.93B → 1.90B shown), `test_dropped_case_listed_once`.

### R3.3 Conditions printed once, with thresholds, all of them (P3, P4)
**Files:** `tradingagents/agents/decision_context.py` (~:272, :321–324, :396–397).
- One conditions block with metric, comparator, threshold, status and reason. Remove the 3-item cap. Stop truncating `no_case_reason` mid-word.
- [ ] `test_two_gross_margin_conditions_render_distinct_thresholds`, `test_all_four_conditions_rendered`, `test_no_case_reason_not_truncated`.

### R3.4 The publication record keeps the reasoning (H3)
**Files:** `tradingagents/memory/publication.py` (~:214).
- Store the PM's executive summary, thesis and stated conditions as their own fields, in full (bounded at 20,000 chars each, with a `truncated` flag), separately from `canonical_decision`. `canonical_decision` keeps its cap but starts from the reordered page (R3.1), so its first 12 KB are the decision.
- [ ] `test_record_keeps_pm_summary_and_thesis_in_full`, `test_record_hash_stable_for_same_inputs`. Check the immutability and integrity checks still pass for existing records (they must not be rewritten).

### R3.5 Audit the whole argument (AA1)
**Files:** `tradingagents/agents/audit_pass.py` (~:246).
- Replace `text[:6000]` with the role's **final** turn plus a head-and-tail window of earlier turns, within the same total budget the audit has today. The final turn gets priority. If the final turn alone exceeds the role's budget, audit its head and tail within that budget and give earlier turns nothing. Disclose the coverage per role (characters audited of total, which turns) in the audit result. Never truncate silently.
- [ ] `test_audit_input_includes_final_turn_of_each_role`, `test_oversized_final_turn_gets_head_and_tail_within_budget`, `test_audit_coverage_disclosed`.

### R3.6 Export ordering and the operational headline (RK5, H5)
- Export risk turns in speaking order as the main view, with per-role files kept. The operational audit headline names every fallback, not just the first.
- [ ] `test_risk_export_in_speaking_order`, `test_operational_headline_lists_all_fallbacks`.

### R3.7 Audit independence from the models actually used (AA2)
**Files:** `tradingagents/agents/audit_pass.py` (~:445–448).
- Derive `independence_by_role` from the recorded per-node model ID instead of the hard-coded slot mapping. Keep the existing disclosure that the PM is not audited.
- R5's call metadata is the input contract: requested model plus provider-returned model identity when supplied, including fallback attempts. If actual identity is unavailable, report independence as unknown rather than inferring it from quick/deep slots. R3.7 owns this disclosure and its test.
- [ ] `test_independence_uses_recorded_model_ids` (same model for a quick role when quick == deep is marked "same model").

### R3 proof
Full suite and Ruff green. Re-render the DOCN reference run from the fixture: `decision.md` before and after (line number of PM summary, count of change lines, conditions rendered) recorded in `docs/reviews/<date>-decision-page.md`. Manual: open `complete_report.html` and confirm the Copy All button still works.

## Build R4 — Memory continuity (H1, H2, RM2, ML3, RK3)

**Worktree slug:** `memory-continuity`. Same-day behaviour per approved decision D2.

### R4.1 Same-day rerun (H1)
**Files:** `tradingagents/memory/log.py` (~:69–76).
- Per approved D2: a newer run **replaces** a still-pending entry for the same ticker and date, keeping one entry and linking the newest publication ID. A settled entry is never replaced (preserves the double-count guard).
- Perform the pending/settled check and replacement atomically under the existing store lock; reuse current partial-write quarantine and atomic replacement. Repeating the same publication is idempotent, and settlement/replacement ordering must not duplicate a settled outcome or lesson. Prove both orderings with the existing memory fixtures.
- [ ] `test_rerun_replaces_pending_same_day_entry`, `test_settled_entry_never_replaced`, `test_memory_and_thesis_reference_same_publication`.

### R4.2 Carry every stated condition forward: schema to next run (H2, RM2)
**Files:** `tradingagents/memory/thesis.py` (`ThesisCondition` ~:21–34, rendering ~:397–408, :459), `tradingagents/agents/schemas.py::ThesisProposal`, `tradingagents/agents/managers/portfolio_manager.py` (instructions), the thesis validation and publication code that persists conditions, the next-run `thesis_context` renderer.

Today `ThesisCondition` requires a metric, comparator, threshold, unit and period, and the PM is asked only for measurable conditions. Storage changes alone would not capture settlement confirmation, ATM issuance or price triggers. The complete path:
1. **Schema.** Add a `kind` field: `metric` (today's shape, unchanged), `price_level` (comparator and threshold on the completed close, currency, expiry), and `event` (a short description of the observable event, the evidence that would confirm it, such as "8-K reporting note settlement", and expiry; no comparator or threshold). Records without `kind` parse as `metric`, so every existing publication loads unchanged.
2. **PM output.** Extend the PM's structured output and instructions to emit all three kinds. A non-metric condition the PM states in prose but does not emit structurally is not invented by code.
3. **Validation.** `price_level` thresholds must be positive and in the instrument's currency. `event` needs a description, confirming-evidence text and an expiry. Invalid conditions are rejected with a reason and listed on the card as "stated but not retained".
4. **Persistence.** Saved in the thesis and the publication record alongside metric conditions, under the same immutability rules.
5. **Next run.** `price_level` is checked against the completed close. `event` is shown as an open question with its confirming evidence, status `unobserved` until a later run's evidence matches it; this plan adds no automatic event matching. Raise the rationale display from 300 to 1,000 chars.
- Compatibility includes measurement identity, not only successful parsing: adding a default `kind=metric` must preserve existing condition IDs, aliases, keeps/dispositions, and immutable publication/evidence hashes. Use the existing legacy metric identity representation for legacy-equivalent metric conditions. Do not rewrite old records. Compare price conditions only with a dated, currency-compatible completed close; missing/incompatible data stays unobserved. Events remain open unless explicitly disposed under existing advisory rules; no matcher is introduced.
- [ ] `test_existing_publications_without_kind_load_as_metric` (load every record in a copy of `~/.tradingagents/logs/publications/records/`), `test_pm_schema_accepts_three_condition_kinds`, `test_invalid_event_condition_rejected_with_reason`, `test_price_level_condition_carried_and_checked`, `test_event_condition_carried_as_open_question`, `test_prior_rationale_not_cut_at_300`.
- [ ] `test_legacy_metric_condition_ids_and_dispositions_unchanged`, `test_legacy_publication_hashes_unchanged`, `test_price_condition_missing_or_wrong_currency_close_stays_unobserved`. Portable tests use sanitized committed fixtures; scanning the private copied store is an additional local proof, not a CI prerequisite.

### R4.3 Plain-text prompt context (ML3, RK3)
- Render `thesis_context` as plain text for prompts; escape only at HTML export. Report "period not yet reported" instead of "inputs missing or competing" when the period's filing date is after the analysis date.
- [ ] `test_thesis_context_not_html_escaped_in_prompt`, `test_unreported_period_reason`.

### R4 proof
Full suite and Ruff green. Fixture sequence: write the 09:10 entry, then the 16:41 run: one entry linked to `cfae95e9`. A stub-model PM output containing all three condition kinds round-trips through validation, the publication record and the next-run `thesis_context`. Every existing publication record still loads.

## Build R5 — Observability and controlled comparisons (CN1, SE4, TR2, H6, M1, M2, ML2, plus the D11 trace switch and replay)

**Worktree slug:** `observability`.

### R5.1 Every tool return logged (CN1)
**Files:** `tradingagents/graph/trading_graph.py` (~:790–795).
- Handle the `$writes` multi-write form when extracting messages from stream updates.
- [x] `test_tool_round_with_search_documents_logs_every_return` (the reproduced case from part A CN1).

### R5.2 Run log names the stage and the error class (SE4, TR2)
**Files:** `cli/run_logging.py` (~:25–29), `tradingagents/agents/structured.py` (~:92–95).
- Put the agent name and exception class into the template text, or allowlist those two arguments. Exception messages stay redacted.
- [x] `test_structured_fallback_warning_names_agent_and_exception_class`.

### R5.3 All node outputs in the transcript; PM context persisted (H6, ML2)
- Emit each observed node's output (or a pointer to its state key) to `message_tool.log`. Add `past_context` and `memory_note` to `_log_state`.
- [x] `test_transcript_has_line_per_observed_node`, `test_state_log_includes_past_context`.

### R5.4 Token totals that add up (M1, M2)
- Count usage from failed structured attempts when the provider returns it. Append post-graph calls (the executive summary) to `run_metrics`, or label the stored figure "graph only".
- [x] `test_failed_structured_attempt_counts_usage_when_provider_returns_it` and `test_stored_metrics_explicitly_exclude_post_graph_editorial_calls` (the permitted graph-only labeling alternative; replaces the originally proposed executive-summary-inclusion test name).

### R5.5 Per-node trace (former D11)
- Adopt the optional D11 follow-up here; it was expressly excluded from completed Build D. Reuse the existing node/callback and attempt-directory mechanisms. `TRADINGAGENTS_TRACE=1` writes private, operator-removable `<attempt dir>/trace/<NN>-<stage>.jsonl` containing ordered run/stage/call-bound prompt, tool and response events. Keep traces outside report exports and off by default. Do not serialize credentials, request headers/configuration or raw provider diagnostics; redact known credential values from captured text. Partial/interrupted files are marked incomplete and are not silently treated as valid replay inputs. Reuse attempt isolation on restart; no retention service or new database.
- Retain requested and provider-returned model IDs (when supplied), stage and attempt identity in bounded run metadata available to R3.7 even when full tracing is off. Unknown actual identity remains unknown; this is call provenance, not a new model-selection mechanism.
- [x] `test_trace_default_off`, `test_trace_ordering_across_concurrent_stages`, `test_trace_restart_isolation_and_incomplete_write`, `test_trace_excludes_secrets_and_report_exports` (synthetic secrets in prompt/tool/response/error cases). Inspect private paths, sizes and cleanup instructions before a real traced run.

### R5.6 Controlled comparison runs
**Files:** the tool-execution path in `tradingagents/graph/setup.py::_analyst_graph` and `tradingagents/agents/tools.py`; `cli/run.py`.
- `TRADINGAGENTS_REPLAY_TRACE=<attempt dir>` reuses recorded external inputs at the existing execution boundaries, scoped by ticker, analysis cutoff, stage/tool, effective arguments and call occurrence where repeated calls differ. Rebind responses to the current tool-call IDs. Preserve tool state effects as well as messages: `search_documents` returns `Command(update=...)`; replaying text alone loses its retained search journal. Execute current candidate validation, extraction and calculation code against frozen source inputs; never substitute baseline derived outputs for the changed behavior being tested.
- Account for acquisitions outside model tools, including `create_source_acquisition`, verified quote inputs and memory/settlement reads. Reuse the retained corpus, source-byte/hash fixtures and existing offline HTTP boundary from predecessor proofs rather than adding a general replay platform. R5 owns a short boundary inventory in its review receipt and proves unchanged inputs still reach these paths.
- A call not in the trace may still run live under the existing known-at cutoff, marked `replay_miss` in trace and operational audit. Such a run is **mixed-input**, not controlled; record the returned input and its scope. Prefer answering a new query against the same frozen raw source when the current tool supports it. Material live input drift cannot satisfy the controlled-comparison gate; report the limitation and stop before claiming that proof complete. No automatic paid retry or new vendor behavior is authorized.
- Capture an immutable starting memory/publication/cache snapshot **before the baseline run**. Give baseline and candidate separate writable copies of that same snapshot using `TRADINGAGENTS_MEMORY_LOG_PATH`, `TRADINGAGENTS_RESULTS_DIR` and `TRADINGAGENTS_CACHE_DIR` (existing configuration keys). Never seed a candidate with baseline-created publications, settlements or lessons. Record hashes, analysis-clock settings, source vintages and resolved write paths. For Nb, use the pre-run snapshot associated with its accepted Na baseline; do not snapshot the Na run's post-run store. The live store is never touched.
- [x] `test_replay_serves_recorded_return_for_identical_call`, `test_replay_rebinds_call_ids_and_preserves_command_updates`, `test_replay_covers_source_acquisition_without_reusing_derived_results`, `test_replay_miss_is_live_and_marked_mixed_input`, `test_comparison_uses_prebaseline_snapshot_and_leaves_live_store_untouched`.

### R5 proof
First implementation milestone: on Machine 2, exercise the actual `cli.run.run_analysis` entry point through `TradingAgentsGraph` and its compiled graph, publication/memory finalization and report export into a disposable results tree. Bootstrap recorded DOCN inputs before this proof; R1 later owns the reusable fixture. Reuse `docs/reviews/operations-cli-proof.py` and the existing provider-boundary doubles with sockets denied; do not replace graph nodes or publication/report logic with test stand-ins. Inspect the persisted decision UUID, publication/evidence hashes, memory link, reopened state, exported report, transcript and per-stage trace. This proves the real local application path, not live-provider behavior.

Run that smallest path after wiring logging/tracing, before completing replay hardening. After R5 corrections, repeat the complete path: every tool return in `message_tool.log`, a line per observed node, trace files for every stage when enabled, and a second recorded-input run with zero `replay_miss`, preserved tool state updates and unchanged protected source files. Exercise a tool failure and an interrupted/restarted attempt using existing fixtures; verify visible diagnostics and attempt separation. Full suite and Ruff green at the final commit; retain the receipt in `docs/reviews/<date>-observability.md`. Live-provider proof remains Sequence steps 6–7, and overall runtime acceptance stays incomplete until those runs succeed.

**Local acceptance checkpoint (2026-11-07, Machine 2):** corrected source `0308e892bba5f7e8d31461637f3c98eb3b23e42e`; complete default suite 3358 passed / 10 skipped / 1 deselected / 100 subtests, Ruff clean, complete native CLI/replay/failure/restart proofs passed. Claude Fable closure on `7050666f62a32b6b19b451d4bc9684a3f10f677f` completed normally with no Critical/High/Medium findings; verified Low limitations retained. Exact source/input/output hashes, code-tree identities, review ledgers and dispositions: `docs/reviews/2026-11-07-observability.md` and its runtime/verification JSON receipts. This is local feature acceptance only. Staging integration/push, remote CI, Sequence 6–7 live-provider acceptance and later stages remain separately approved/unperformed. R1 has not started.

# Phase 2 — Prompts and hand-offs

Phase 2 is split by risk. **Build Na** holds the lower-risk changes: agents use what they already looked up, see the plan they are critiquing, attribute correctly, and get shorter, de-duplicated prompts. **Build Nb** holds the two judgment changes whose effect on the analysis is genuinely uncertain: risk roles arguing their own direction (D3) and the lessons digest. Nb ships only if its own comparison shows it helps. If it doesn't, Na still stands.

## Build Na — Lower-risk prompt and hand-off changes

**Worktree slug:** `node-workflow-a`. Starts from the staging commit that contains all of Phase 1. Its baseline is the Phase 1 traced DOCN run (see Sequence), plus a matching MSFT baseline run on the same commit.

### N1 — Research Manager, Trader and risk debate

#### N1.1 The Research Manager answers with what it looked up (RM1)
**Files:** `tradingagents/agents/managers/research_manager.py`.
- Add an instruction: for each document follow-up, classify it as **answered**, **partially answered** or **unanswered** by the retrieved passages (retrieval status from R2.2 is shown but is not the answer). For answered or partial: one line on what the passage establishes, with the figure and source ID, and whether it changes the bull or bear point it was raised for. For unanswered: say what is still unknown. Add the classification to the RM's structured output so the card can show it (R2.2), labelled unvalidated.
- [ ] `test_rm_prompt_requires_followup_classification`, `test_rm_output_schema_has_followup_classification`.
- N1.1 also owns `test_card_shows_retrieval_status_and_rm_judgment_separately`, proving the structured judgment survives state delivery and rendering. If N1.1 is dropped, the card keeps R2's honest unavailable-judgment display.

#### N1.2 Risk roles see the research plan (TR1, RK4)
**Files:** `tradingagents/agents/risk_mgmt/aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py` (~:28–31).
- Give each risk role the Research Manager's recommendation, rationale and stated conditions (`investment_plan`, compact form), in addition to the Trader's proposal. Instruct them to flag any Trader step that drops or contradicts a research condition.
- [ ] `test_risk_prompts_include_investment_plan_conditions` (DOCN baseline: "50.15 % and 55.5 %" condition present).

#### N1.4 The PM attributes levels to their source and sees the evidence status (TR3, P5)
**Files:** `tradingagents/agents/managers/portfolio_manager.py`, `tradingagents/agents/trader/trader.py`.
- PM: "Attribute every price level and condition to the role that proposed it." Add one line near the rating rules: "Evidence quality: <status> (<pass> pass / <unavailable> unavailable)", from `evidence_quality`.
- Trader: "Keep technical levels exactly as the market report states them; do not merge separate levels into bands."
- [ ] `test_pm_prompt_states_evidence_quality`, `test_trader_prompt_preserves_levels`.

### N2 — Analysts

#### N2.2 Disclosure rules the model can follow (FA3)
- Trim the disclosure-record rules to the subset the validator enforces, and add one worked example per record type (guidance range, unit-bearing amount, financing event).
- [ ] `test_disclosure_prompt_contains_one_example_per_record_type`. Measured in the comparison runs: model-caused disclosure rejections should fall (baseline: 3 of 9 on DOCN 11-07).

#### N2.3 Say "not checkable" instead of "not supported" (SE3)
- Sentiment prompt: a claim the analyst has no data to test (for example, a past price level without price history) is "not checkable with my inputs", not "not supported".
- [ ] `test_sentiment_prompt_distinguishes_uncheckable`.

### N4 — Debate hygiene and prompt size (BB4, BB2, BB3, RK2, CN2)

#### N4.1 Answer the opponent's points (BB4)
- Bull and Bear, rounds 2+: "List the opponent's numbered points from their last turn; answer or concede each. Do not change your own stated triggers without saying so."
- [ ] `test_debate_prompt_requires_point_by_point_answer`.

#### N4.2 Ask for search phrases, not questions (BB2)
- Document-question instruction: ask for "short filing search phrases (3–6 words)", matching the existing example.
- [ ] `test_document_question_instruction_asks_for_phrases`.

#### N4.3 Shorter prompts (BB3, RK2)
- Prompt view of evidence uses the short IDs the agents already cite (F12, S54), and keeps the hash-to-short-ID map in state for traceability. Risk prompts pass the history once, without repeating the last two turns separately.
- [ ] `test_prompt_view_uses_short_ids_and_map_round_trips`, `test_risk_prompt_has_no_duplicate_turns`. Expected: about 18 % fewer characters per debate call (measured in the comparison run).

#### N4.4 One evidence view for later roles (CN2)
**Files:** `tradingagents/agents/context.py` (~:401–417).
- After Evidence Check, roles from Bull/Bear onward receive the canonical context only; the pre-analyst brief is reduced to the items the canonical context does not carry (for example, Build B filing terms if not already canonical, and the R1.1 financing lines), labelled as such. Today both go in, about 95.7k chars per research call, with the same facts in two formats.
- [ ] `test_post_gate_roles_get_canonical_context_without_duplicate_brief`, `test_brief_only_items_still_reach_later_roles`.

### How comparison runs work (Na and Nb)

- **Controlled inputs.** Every Phase 2 comparison runs on the same ticker, analysis date, analysis clock and recorded model settings as its baseline, using the frozen external inputs and pre-baseline store snapshot in R5.6. A zero-material-drift comparison leaves model/provider variability uncontrolled; it shows **observed** differences, not causal proof. Any live replay misses are disclosed as mixed-input limitations, never described as removed input drift.
- **Observed vs inferred.** Each result is labelled in two columns. *Observed:* what the trace shows (a prompt contains the research plan; a role states its own direction; the rating moved from X to Y). *Inferred cause:* the auditor's best attribution, with the reasoning, marked as inference.
- **Keep or drop is decided on observed, per-change behaviour.** Each change's rubric item checks its associated visible behavior, for example "the RM prompt requires a follow-up disposition and the output gives one". Interactions are disclosed; the observation does not prove exclusive causation by that change. A change whose item fails is dropped. Rating movement is judged on the combination, not used to attribute blame to one change.
- **Proof is on the retained feature state.** If any change is dropped, the retained combination gets its own authorized controlled DOCN and MSFT pair before requesting integration, and the rubric and rating comparison are re-run on that pair. Name the exact tested feature commit. Integration requires separate approval; if it creates a different source/dependency state, verify affected behavior and record the integrated SHA rather than claiming an untested commit was exercised.
- **Rating and key-number comparison** (rating, base-case valuation, top three conditions) for the retained combination against its baseline. An unexplained rating change on a controlled pair is a finding for the auditor to investigate in the trace and report. It is not automatically a failure, because sampling alone can move a borderline rating.

### Build Na proof — comparison runs

1. Unit tests for every change above; full `pytest -q` and `ruff check` green at one commit.
2. **Two controlled traced runs** on the candidate commit (DOCN and MSFT, replayed against their baselines). MSFT is a profitable mega-cap with a different profile, to check that nothing regresses outside DOCN's situation.
3. **Scoring rubric**, applied by the independent auditor to baseline vs candidate trace files, each scored pass/fail with quotes:
   - RM classifies every follow-up as answered / partial / unanswered, and each answered or partial one quotes a figure that actually appears in the retrieved passage (N1.1).
   - Every risk role sees and cites at least one research condition (N1.2).
   - PM attributions match their source turns (N1.4).
   - Trader output preserves distinct market-report levels, and the PM prompt contains the actual evidence status (the other N1.4 behaviors).
   - Model-caused disclosure rejections are at or below baseline (N2.2).
   - No more than one unanswered opponent point per debate (N4.1).
   - Sentiment distinguishes unavailable evidence from contradicted claims when that situation occurs (N2.3); document requests use the required short phrases (N4.2). If a run contains no applicable N2.3 claim, mark that runtime item not exercised and use the focused rendered-prompt/behavior probe; do not invent a runtime pass or drop a change merely because no applicable event occurred.
   - Prompt characters per debate call reduced (N4.3), and no fact listed as brief-only is missing from later-role prompts (N4.4).
   - No regression: every number in the final decision still traces to evidence (spot-check 5 per run), and the rating stays within the existing eligibility rules.
   - Rating and key-number comparison per "How comparison runs work", with observed and inferred columns.
4. **Keep or drop per change.** Each Na change (N1.1, N1.2, N1.4, N2.2, N2.3, N4.1, N4.2, N4.3, N4.4) is kept only if its observed rubric item passes. A change that fails is reverted on the branch and recorded as not adopted, not fixed and retried. If a reverted change was needed by a kept one, the auditor says so and both are dropped. If anything was dropped, the retained combination gets its own controlled DOCN and MSFT pair, and the rubric and rating comparison are repeated on it before merge.
5. Record results, including the keep/drop table, in `docs/reviews/<date>-node-workflow-a.md` with all run IDs and the exact commit. The runs on the merged Na commit (the candidate pair, or the retained-combination pair if anything was dropped) become Nb's baseline.

## Build Nb — Judgment changes: risk-role direction and lessons

**Worktree slug:** `node-workflow-b`. Starts from the staging commit that contains Build Na. Its baseline is the DOCN and MSFT pair on the merged Na commit.

### Nb.1 Risk roles test direction before sizing (RK1) — approved D3
**Files:** the same three debators.
- Per approved D3: in round 1 each role states its **own** direction (add / hold / reduce / exit) from its risk lens, with the evidence that would change it, before critiquing the Trader. Replace "create a compelling case for the trader's decision" with "make the strongest case for the direction your risk lens supports, including if that differs from the Trader". Rounds 2–3: answer the other roles' numbered points (same rule as N4.1). The final round must name what remains unresolved rather than restate.
- [ ] `test_aggressive_prompt_no_longer_presumes_trader_direction`, `test_round_one_requires_own_direction`.

### Nb.2 Lessons reach the roles that use them (ML1)

**Files:** the memory context builder (`past_context`), `research_manager.py`, the three risk debators.
- Give the Research Manager and the risk roles a lessons digest: at most 5 lessons from the reflection log relevant to this ticker or setup, each one line, dated. The PM keeps its full past context. The Bull and Bear prompts stay unchanged (keeps the debate independent of past outcomes).
- [ ] `test_rm_and_risk_prompts_include_lessons_digest`, `test_bull_bear_prompts_exclude_lessons`.

### Build Nb proof — comparison runs and go/no-go

1. Unit tests for both changes; full `pytest -q` and `ruff check` green at one commit.
2. **Two controlled traced runs** on the candidate commit (DOCN and MSFT, replayed against the Na baselines).
3. **Scoring rubric**, applied by the independent auditor against the Na runs:
   - Round 1 contains each risk role's own direction; at least one role argues a direction other than the Trader's, or explicitly says why none does (Nb.1).
   - The risk debate's final round names what remains unresolved instead of restating (Nb.1).
   - The lessons digest is present in RM and risk prompts, absent from Bull and Bear (Nb.2), and every lesson the PM or RM cites is relevant to this ticker or setup, not a generic carry-over.
   - No regression: every number in the final decision still traces to evidence (spot-check 5 per run), and the rating stays within the existing eligibility rules.
   - Rating and key-number comparison per "How comparison runs work", with observed and inferred columns.
4. **Go/no-go per change.** Each of Nb.1 and Nb.2 is kept only if its observed rubric items pass and the auditor judges, in one paragraph with quotes, that the affected part of the argument is better reasoned, not merely different. That judgment is labelled as such. A change that fails is reverted and recorded as not adopted. If one is dropped, the retained change gets its own controlled DOCN and MSFT pair before merge.
5. Record results in `docs/reviews/<date>-node-workflow-b.md` with all run IDs and the exact commit.

# Sequence, acceptance and release

## Sequence

1. **R5** (observability and the trace switch), so every later proof and run is inspectable.
2. **R1** (evidence assembly; builds the DOCN fixture).
3. **R2** (document follow-up).
4. **R4** (memory continuity).
5. **R3** (decision page and record; renders R4's carried conditions).
6. **Phase 1 baseline run:** after separately approved R1–R5 staging integrations, run one traced DOCN analysis on Machine 2 from an isolated checkout of that exact confirmed staging commit, at your usual model settings. Capture the pre-run store snapshot and use its disposable baseline copy per R5.6. Confirm the Phase 1 effects on the real model/provider run (ATM in brief, RPO history, follow-up retrieval statuses, lease sensitivities with assumptions, decision page order, memory entry linked to the new publication, every tool return and node in the logs). Inspect the actual publication, reopened state, reports and trace; record their paths/hashes and exact source commit in the audit folder. If an effect is missing, it goes back to its owning build's gap closure before Phase 2 starts; no automatic paid rerun.
   **Diagnostic comparison with the 2026-11-07 run (`cfae95e9`):** rating, base-case valuation, and the top three conditions, each difference with an observed column and an inferred-cause column, for example "RPO year-on-year history now in context". This run is not controlled: news, prices since 11-07, memory and model sampling have all moved. So the comparison is evidence for the audit, not a pass/fail gate. The gate is that the Phase 1 effects listed above are present on the real run.
7. **MSFT baseline run** on the same exact source commit, using its own pre-run snapshot and disposable baseline store. Both baseline runs have the trace switch on, so Phase 2 can replay them. Verify the external-input boundary inventory and snapshots are complete before beginning a paid candidate pair.
8. **Na** (lower-risk prompt and hand-off changes), proven by DOCN and MSFT comparison runs.
9. **Nb** (risk-role direction and lessons), proven by DOCN and MSFT comparison runs, with a go/no-go per change.

R2 and R4 are technically independent and may run in parallel worktrees; each starts from exact confirmed staging containing R1. R3 waits for their accepted, explicitly authorized integrations. Nothing else runs concurrently, because R1, R3, Na and Nb touch shared context and rendering files.

## Integrated acceptance

Independent audit: required

- Each build: `pytest -q` fully green on its branch at a single commit, `ruff check` clean, proof recorded in `docs/reviews/<date>-<slug>.md` with the exact commit.
- Independent audit per build before any merge request (the existing `independent-build-audit` workflow), with every High reproduced by running, not reading. For Builds Na and Nb the audit includes the rubric scoring and the rating comparison.
- Gap closure per build: every confirmed in-scope finding from that audit is fixed on the same branch with a regression test, then the auditor re-checks the final commit. Repeat until no open in-scope Critical/High/Medium remains, or record "no gaps found". A build is complete only when its final commit is named, its checks pass on that commit, and the closure audit confirms every in-scope finding closed. For Na and Nb, a change that fails its rubric item is dropped and recorded as not adopted, not repaired inside this plan. Gap closure there covers code defects found by the audit (wiring, tests, rendering), not retrying failed prompt changes.
- **Feature-branch completion:** each build ends at its named verified local commit with required proof and independent closure; stop for explicit integration/push approval under the Branch and Release Boundary. A successor needing that integration waits; no automatic branch advancement is authorized.
- **Integrated plan acceptance:** after separately authorized integrations of all seven builds into staging in the sequence above, record all baseline/comparison runs and each finding's owning task, disposition and closing commit in `docs/reviews/<date>-workflow-gap-closure.md`. An Na/Nb change dropped at keep-or-drop is "not adopted", not "fixed"; it counts as a completed plan disposition while its original behavior gap remains disclosed. Proof must cover the final retained source state, and any required proof that could not run leaves that build/phase incomplete. Staging acceptance is an unreleased development outcome.
- **Stable release and Machine 1 acceptance:** neither is a plan-completion gate or an implied next action. Only after explicit stable-release/push approval, intentional production advancement and exact-commit readback may Machine 1 pull that production commit and perform build/install/launch acceptance. Record that result separately if authorized. Never install a staging commit as the stable Machine 1 release.

## Not in scope

- Rating eligibility and evidence-gate pass/fail rules.
- Changing the number of debate or risk rounds, or the model assigned to each role.
- Changing the publication immutability model.
- Prior-thesis anchoring A/B test (an open question in the audit): one extra paid run with `thesis_context` withheld, as a separate decision.
- Whether `post_screen` runs (depends on `TYPESAFE_API_KEY`). Verify and report it; don't change it.

## Decisions (approved 2026-11-07)

- **D1, decision page layout:** the PM's summary and thesis come first, labelled as unvalidated model reasoning, with validated evidence below (R3.1). This also resolves the 2026-11-04 "publication strips narrative" question for the decision page and the publication record (R3.4).
- **D2, same-day reruns:** the newest run replaces a still-pending same-day memory entry; a settled entry is never replaced (R4.1).
- **D3, risk roles:** each risk role states its own direction in round 1 before critiquing the Trader (Nb.1), subject to Nb's go/no-go.
- **D4, comparison runs:** DOCN plus MSFT at each Phase 2 step.
- **2026-11-07 additions:** a rating and key-number comparison after Phase 1 and in every Phase 2 proof; Phase 2 split into Na (lower risk) and Nb (judgment changes); every Phase 2 change, in Na and Nb, is kept or dropped on its own observed evidence, and the final retained combination is always the one tested.
- **2026-11-07 plan review (Codex) adopted:** controlled replay inputs (R5.6); observed vs inferred labelling; full condition path for R4.2; identity-aware dedupe (R1.3); retrieval status only, with the RM judging answered (R2.2, N1.1); lease sensitivities traced in existing code first and moved to Phase 1 (R1.7); currency only from a filing binding (R1.6); audit budget overflow rule (R3.5).

## Limits to state in the final report

- Prompt quality is judged on two tickers and one date; it is evidence of improvement, not proof across all companies. Real confidence in Nb's changes comes from reading several ordinary runs after release; watch the first five runs after installation for rating swings without a traced cause.
- The lease-inclusive sensitivities (R1.7) are sensitivities with stated assumptions, not a change to the base case.
- Controlled comparison runs remove input drift, not model sampling. One pair per step shows observed behaviour; causes are labelled as inference.
- Phase 1 replays use one retained DOCN corpus; behaviour on filers with different document structures is covered by existing tests only.

## Post-plan audit — 2026-11-07

**Verdict: revised and ready.** Audited once against exact local/GitHub staging `8920ffac07d1063001291799e99963403955582a` and the completed A–D handoffs recorded above; GitHub production was independently read as `9ade69bf155d1b25699d3aecfff3c1b07752aff0`. The checked-out branch is `codex/installed-evidence-settlement-ops`, not a new implementation worktree. Existing untracked draft plans/specs were left untouched. Read-only remote inspection used `git ls-remote`; no fetch, ref mutation, code change, database write or runtime/provider call was performed by this audit.

| Material finding | Original classification | Disposition in this revision |
|---|---|---|
| Sequence / Integrated acceptance allowed stable installation from staging and did not state the complete two-machine boundary | FAIL | PASS: added Branch and Release Boundary; separated local feature completion, explicitly approved staging integration/push, explicitly approved production release/push, and conditional exact-production Machine 1 installation. |
| R5.6 and comparison rules claimed controlled inputs despite live misses, post-baseline snapshots, text-only tool replay and acquisitions outside tools | FAIL | PASS: pre-baseline independent store copies; scoped external-input replay including `Command` effects/current call IDs and non-tool acquisition; candidate computations rerun; material live drift leaves controlled proof incomplete. No generic replay service added. |
| R5 proof lacked an explicit first vertical-path milestone; reusable fixture was owned by the later R1 build | PARTIAL | PASS: R5 bootstraps disposable inputs and exercises actual CLI → compiled graph → publication/memory → reopened state/report/trace early, then repeats after corrections; R1 still owns the reusable extraction fixture. Paid live-provider confirmation stays after Phase 1 under existing authority. |
| R2 card acceptance depended on N1.1's future schema; some Na keep/drop items had no explicit rubric observation | PARTIAL | PASS: R2 renders honest retrieval status without RM judgment; N1.1 owns judgment/schema/card delivery, with fallback when dropped. Added N2.3/N4.2 and remaining N1.4 observations; not-exercised cases are disclosed. |
| R4.2 default metric kind could change hash-derived condition IDs; R4.1 replacement must preserve settlement ordering | PARTIAL | PASS: preserve legacy metric IDs/dispositions and immutable hashes; prove missing/currency-incompatible price observations and atomic pending replacement using existing locks/fixtures. |
| R1.7 input supplementation could silently change the accepted base case; R2.1 generic year removal could break named-note lookup; R3.2 broad source-hash comparison would suppress legitimate changes | PARTIAL | PASS: separately labelled sensitivity using the existing calculator; preserve instrument years; compare valuation compatibility, with no invented scenario-role identity or registry. |
| R5.5 referred to four nonexistent named D11 tests; global paid-run wording contradicted Sequence and implied unverified extra spend authority; estimate total did not sum | PARTIAL | PASS: named bounded trace proofs from predecessor D11 requirements; clarified offline-build/live-baseline split, supplemental-run authorization and stop rule; corrected total to 57–85 active hours without changing per-build estimates. |

**Required runtime/operational evidence.** R5's early and final native application proofs use disposable Machine 2 stores, recorded external inputs and provider doubles, with sockets denied; they are explicitly not live-provider proof. R1–R4 retain their focused replay/render/continuity proofs. Sequence 6–7 owns paid real-model/provider confirmation before Na; Na/Nb own the accepted-combination comparison pairs. Each build retains full default pytest/Ruff and independent closure requirements. Record exact commits, input/snapshot hashes, resolved destinations, trace coverage/misses, failures and limitations. Preserve valid predecessor receipts without claiming they are a new run on changed code.

**Applicable operations:** existing local files/publications and caches remain the authorities; isolate all writes, preserve immutable old records, use existing locks/atomic writes, keep traces private/default-off and operator-removable, mark interrupted traces incomplete, and prove a failed tool plus restart through the existing harness. Compare stored/file sizes per attempt and document manual deletion of trace directories; no automatic retention subsystem is required. Network/provider failures use existing visible degraded/unavailable behavior; trace/replay must not hide them. **Not applicable:** broker/trading execution, deployed workers/queues/services, or a new database/migration; none is introduced. Stable installed-product proof is conditional on separate production release authority, not required for Machine 2 development.

**Remaining limits and freeze.** This is a plan-only audit: no new implementation checks, live paid runs, remote CI execution or Machine 1 acceptance occurred. Predecessor CI/audits are retained receipts. Two tickers/one date and model/provider variability limit inference; mixed live inputs are disclosed rather than claimed controlled. Required runtime or comparison evidence that cannot be obtained leaves completion incomplete. No material product decision is needed to freeze this plan; fetching/baseline confirmation, supplemental paid spend if needed, integrations, pushes and stable release remain explicit execution boundaries. Rechecked only affected contracts against `setup.py`, `tools.py`, `evidence_validation.py`, `operational_capture.py`, existing CLI proof, configuration paths, thesis/schema/identity, publication hashing and valuation/search implementations. The resulting single plan is frozen for implementation subject to those boundaries.

**Workflow wording changed:** new isolated feature work starts from fetched/confirmed GitHub staging on Machine 2; verified local feature completion does not integrate or push; staging integration/push needs explicit development approval and stays unreleased; production integration/push needs separate stable-release approval; Machine 1 installation/acceptance uses only the deliberately released exact production commit. No Git/release action was executed by this audit.

---

# Approved Amendment 1 — user-approved 2026-11-07

# Amendment 1 to "TradingAgents workflow gap closure (post A–D)"

Date: 2026-11-07. Author: Claude.
Status: **approved by the user on 2026-11-07 for appending to the base plan before R1 starts. Planning only.** It adds tasks to builds that have not started yet. It does not authorize implementation, paid runs, integration, push or release beyond what the base plan already states.

**Base plan:** `docs/superpowers/plans/2026-11-07-tradingagents-workflow-gap-closure-plan.md` in worktree `~/.codex/worktrees/workflow-gap-r5/TradingAgents` (branch `codex/workflow-gap-r5`, R5 in progress at `b3de0456`). Where this amendment and the base plan differ, the base plan's boundaries, constraints and acceptance rules govern; this amendment only adds tasks and acceptance checks.

**Why:** the DOCN run published 2026-11-08T00:26Z (decision `16416b7e`, Opus 5.5 quick / Terra Pro deep, built on post-A–D staging) and two independent reviews of it found seven gaps the base plan does not cover. Each was checked against the source at `b3de0456`.

## How to apply

- Nothing here touches R5, which is in progress. Every task attaches to **R1, R3 or Na**, none of which has started.
- Append each task under its host build when that build starts. Same worktree rules, same model recommendation as the host build, same independent audit and gap-closure loop. The host build's proof gains the checks listed under each task.
- The base plan's "Independent audit: required" marker covers these tasks; they are audited as part of their host build, not separately.

## Finding coverage (additions)

| Gap observed in run `16416b7e` | Task | Host build |
|---|---|---|
| G1 A case with an accepted audit finding against its inputs still prints on the card as a valid range ($65.89 used the $250M undiscounted 2027 payments as principal) | G1 | R3 |
| G2 "Little price history until $52–58" repeated by the market analyst and trader; March closes of $62.01–68.69 exist; the prior run's audit had already disproved it | G2 (code) + G2p (prompt) | R1 + Na |
| G3 The auditor flagged the $57.1M induced-conversion expense as unsupported and the PM accepted it; the figure is verbatim in the retained 10-Q | G3 | R3 |
| G4 Grounded disclosure excerpts fell from 15 (run `913554d4`) to 7 on the same filing, losing the Q4 and FY2026 guided share counts, both EBITDA-margin guides and the FCF-margin guide | G4 (acceptance) | R1 |
| G5 NBIS excluded for an ambiguous `Assets` fact at 2023-12-31; that date is inside R1's existing three-year peer window, so the shipped `period_floor` does not help | G5 | R1 |
| G6 Numbers the Portfolio Manager cites with evidence IDs are never checked against those IDs | G6 | R3 |
| G7 Agents see the 2027 finance-lease maturity total ($250.0M) without being told it is undiscounted and includes imputed interest | G7 | R1 |
| G8 Case multiples carry a rationale but no stated reference point, so the multiple drifts run to run (4.5×→5.0×, 6.0×→7.0×, 3.5×→3.0×) | G8p (prompt) | Na |
| G9 The decision horizon drifts on the same evidence (4, 4–6, then 6 months) | G9 (code) + G9p (prompt) | R3 + Na |

R3.2 (match changes by role, not name) already covers the "16 rows of not present" noise from the same run; no task added.

## Delivery estimate (additions)

| Host build | Tasks | Added active hours |
|---|---|---|
| R1 | G2, G4, G5, G7 | 6–9 h |
| R3 | G1, G3, G6, G9 | 8–12 h |
| Na | G2p, G8p, G9p | 1.5–2.5 h, judged inside Na's existing comparison runs |

Add 1–2 h to the host builds' audits. **Total 16–26 active hours** on top of the base plan's 57–85. No additional paid runs: G2p and G8p ride Na's existing DOCN and MSFT pairs. Model recommendations unchanged (Astra for R1, Sol for R3 and Na). Engineering estimate, not measured.

---

## R1 additions

### G2 Prior trading inside a price band, computed by code

**Files:** `tradingagents/agents/tools.py::get_verified_market_snapshot` and the builder it calls (`build_verified_market_snapshot`); its tests.

- Append a "Prior closes by price band" table to the snapshot: from the latest completed close down to the lowest close of the last 252 completed sessions, in bands of 5% of the latest close. Each band lists the number of closes in it, the most recent date and the lowest and highest close. Bands with no closes say "no closes in the last 252 sessions". Point-in-time: only sessions on or before the analysis cutoff.
- No new vendor call: reuse the OHLCV the snapshot already loads, extending its window if it is shorter than 252 sessions.
- [ ] `test_band_table_lists_march_closes_below_lower_band` (DOCN fixture, close 72.48 on 2026-11-06: the 65.2–68.9 band reports closes including 66.22 and 68.63/68.69 dated March 2026, and the 61.6–65.2 band reports 62.01), `test_band_table_respects_cutoff`, `test_empty_band_says_no_closes`.

### G4 Guidance grounding is stable on the same corpus

This is an acceptance check on R1.2 and R1.3, not new code unless it fails.

- Add a fixture for the `16416b7e` retained corpus next to R1's `tests/fixtures/docn_2026_11_07/` (same privacy rules: retained source bytes only, no memory or secrets).
- [ ] `test_16416b7e_corpus_accepts_guided_shares_and_margin_guides`: deterministic discovery accepts Q4 2026 diluted weighted shares 128–129M, FY2026 diluted weighted shares 122–123M, Q4 and FY2026 adjusted EBITDA margin guides, and the FY2026 adjusted FCF margin guide.
- [ ] `test_discovery_is_order_independent`: the same corpus with documents and blocks in shuffled order yields an identical accepted set and identical record IDs.
- [ ] R1 proof records accepted counts for both the `913554d4` and `16416b7e` corpora, before and after. If the two corpora themselves differ (different blocks retained), record which blocks differ and why; a difference in retention is an R1.2 defect, not an acceptable run-to-run variation.

### G5 Peer exclusion only for facts the peer statistics read

**Files:** `tradingagents/dataflows/vendors/sec_edgar.py` (`_select_facts`, ambiguity raise ~:271), `tradingagents/agents/valuation_reference_flow.py::_fetch_peer` (~:242).

- At build start, list the metrics `calculate_peer_statistics` and the peer render actually read (expected: Revenue, Gross Profit, Common Shares Outstanding; verify). For peer packages only, an ambiguity in any other metric drops that metric from the package with a recorded gap ("Assets ambiguous at 2023-12-31; not used for peer statistics") instead of raising. An ambiguity in a metric the statistics read still excludes the peer with today's reason.
- Subject-issuer packages are unchanged: ambiguity still raises.
- [ ] `test_peer_ambiguity_in_unused_metric_keeps_peer` (synthetic companyfacts: conflicting `Assets` at 2023-12-31, clean revenue and shares: peer status `available`, gap recorded), `test_peer_ambiguity_in_revenue_still_excludes`, `test_subject_ambiguity_still_raises`.
- [ ] R1 proof: NBIS from the `16416b7e` recorded inputs is either accepted or excluded for a reason that names a metric the statistics read.

### G7 Maturity totals labelled as undiscounted, with present value beside them

**Files:** the canonical context builder in `tradingagents/agents/context.py`; the filing-cell extraction that already reads the lease table (`block-226` in DOCN).

- When the retained finance-lease and equipment maturity table yields both a per-year undiscounted schedule and its present-value total, render one line: "Finance lease and equipment maturities (undiscounted, include imputed interest): 2027 $250.0M; total $X; less imputed interest $Y; present value $923.6M (F25). Scheduled payments are not principal." Values come only from the retained table with source IDs; if any piece is missing, render nothing for that piece.
- [ ] `test_maturity_line_labels_undiscounted_and_present_value` (DOCN fixture), `test_partial_table_renders_only_present_pieces`.

---

## R3 additions

### G1 A case disputed by an accepted audit finding leaves the range

**Files:** `tradingagents/agents/audit_pass.py` (finding schema and prompt), `tradingagents/agents/decision_context.py::render_condition_summary` (range assembly ~:341), the shared valuation record.

- Add an optional `case_id` field to audit findings. The audit prompt asks for it when a finding concerns a valuation case's inputs; the case IDs are already in the supplied material.
- A case is **disputed** when a finding that names its `case_id` has PM disposition `accepted`. Fallback with no `case_id`: the finding's `quoted_claim` is an exact substring of that case's rationale or assumption text. No other inference.
- Disputed cases stay in the record and the fundamentals section, marked "disputed by accepted audit finding AF-…; excluded from the conditional range". The card's range and count use undisputed cases only. If every case is disputed, the card says so instead of showing a range. Rejected or unanswered findings change nothing.
- No recalculation of the disputed case. Correcting inputs is the model's job on the next run; this task only stops a known-bad number from being displayed as valid.
- [ ] `test_accepted_finding_with_case_id_excludes_case_from_range` (`16416b7e` fixture: AF-44b5… against the base case's finance/equipment roll-forward → range shows 28.57 only, base marked disputed), `test_quoted_claim_substring_fallback`, `test_rejected_finding_keeps_case`, `test_all_cases_disputed_states_no_range`.

### G3 The auditor checks the full retained source before calling a number unsupported

**Files:** `tradingagents/agents/audit_pass.py` (after findings are parsed, before `prepare_audit_dispositions`), `tradingagents/dataflows/filing_search.py::search_filing_evidence`.

- For each `unsupported_claim` finding, extract the amounts in `quoted_claim` and search the run's retained full corpus (the same corpus `search_documents` uses, plus retained transcript text) for each amount in its displayed and filing forms (for example "$57.1M" → "57.1 million", "57,110" in a thousands table, "57,110,000"), requiring at least one non-numeric word from the quote in the same block.
- When located, keep the finding but relabel it "located in retained source <source_id, locator>; not in the evidence brief" and present it to the PM as a coverage note, not an unsupported claim. Record the original classification. Never delete a finding.
- Contradictions and numerical inconsistencies are untouched.
- [ ] `test_unsupported_finding_located_in_10q_is_relabelled` (`16416b7e` fixture: AF-80aa… and AF-9a28… on "$57.1M" locate "total induced conversion expense of $ 57,110" in the 10-Q), `test_truly_absent_amount_stays_unsupported`, `test_number_without_shared_word_is_not_a_match`, `test_contradiction_findings_untouched`.

### G6 Code check of the Portfolio Manager's cited numbers

**Files:** new `tradingagents/agents/citation_check.py`; `tradingagents/agents/decision_context.py` (card line).

- After the PM's structured output, scan its executive summary and thesis for sentences that cite evidence IDs inline (F, C, K, D labels from the canonical brief). For each cited ID with a numeric canonical value, check whether the sentence contains that value within display rounding (millions to one decimal, percent to two decimals). Report "PM citation check: n of m cited figures matched" and list mismatches with the sentence and the canonical value.
- Display only. No gate, no rewrite, no rating effect. Sentences without IDs are not checked and are counted as "uncited".
- [ ] `test_pm_cited_revenue_matches` ("$321.2 million … (F46)"), `test_pm_cited_value_mismatch_listed` (altered figure), `test_uncited_sentences_counted_not_checked`, `test_percent_and_millions_rounding`.

### G9 Six-month default decision horizon (user decision 2026-11-07)

**Files:** `tradingagents/default_config.py` (new `decision_horizon_months: 6`, env `TRADINGAGENTS_DECISION_HORIZON_MONTHS`), `tradingagents/agents/decision_context.py::decision_horizon`, the PM schema's horizon field and its `horizon_reason`, card rendering.

- The configured horizon (default six months) is the decision horizon unless the Portfolio Manager states a different one **and** a non-empty reason. A different horizon without a reason is replaced by the default and the card says so. The card shows "Horizon: 6 months (configured default)" or "Horizon: N months (PM override: <reason>)".
- Keep the existing "horizon required" behavior: a missing or invalid horizon still makes the decision incomplete. No change to rating eligibility.
- Valuation cases keep their own forecast periods; this task does not change case dates.
- [ ] `test_default_horizon_is_six_months`, `test_pm_override_with_reason_is_kept_and_labelled`, `test_override_without_reason_falls_back_to_default`, `test_env_override_of_default`.

---

## Na additions (prompt lines, judged by Na's existing comparison runs)

### G2p Price-history claims cite the band table

- Market analyst and trader prompts: any claim about where prior trading did or did not occur must cite the "Prior closes by price band" table from G2.
- [ ] Rendered-prompt unit test for both roles. Comparison-run rubric item: no claim of missing price history that contradicts the band table.

### G9p The PM is told the default horizon

- Portfolio Manager prompt: the decision horizon is the configured default (six months) unless the evidence gives a specific reason for another; state that reason in `horizon_reason`.
- [ ] Rendered-prompt unit test. Comparison-run rubric item: horizon equals the default, or differs with a stated evidence-based reason.

### G8p Each case multiple names a same-basis reference

- Fundamentals analyst case instructions: the multiple rationale names its reference point on the same basis and period convention (an own-history figure, a named peer, or the "what the price implies" ratio), or states "no same-basis reference available".
- No schema change.
- [ ] Rendered-prompt unit test. Comparison-run rubric item: every case rationale names a reference or states none; keep or drop per Na's rules.

---

## Considered and not included

- **Recalculating a disputed case automatically.** It would need the system to decide the corrected input. G1 removes the bad number from the card; the next run's model corrects it.
- **A second LLM pass auditing the PM.** G6 does the checkable part in code. A deep-model re-audit adds a call per run and shares the PM's model.
- **Caching evidence across same-day runs to cut tokens.** The repeat-run pattern is testing, not production use, and the measured cost is about $8–9 per run. Revisit if production runs one ticker more than once a day.
- **Calibrated scenario probabilities.** There is no track record to calibrate against yet. G8p limits multiple drift without claiming calibration.

## Decisions

**Made here (technical, reversible):** G1 uses explicit `case_id` with an exact-substring fallback only; G3 relabels rather than deletes; G6 is display-only.

**Approved by the user on 2026-11-07:**
1. Decision horizon: a configurable six-month default the Portfolio Manager must use unless it states a reason (G9, G9p).
2. Append this amendment to the base plan before R1 starts.
