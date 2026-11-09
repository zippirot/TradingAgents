# TradingAgents report defect closure (post workflow gap closure)

Date: 2026-11-09 (revised the same day after source re-check of V1, E1, E4, F2). Author: Claude.
Status: **approved for execution on 2026-11-09 (Claude Code goal issued the same day).** Decisions resolved in the goal unless the user edits it: no paid calls (X3 deferred), S1 default 12,000, S4 no post-PM audit, one worktree with sequential builds. Execution authorizes no integration, push, install or release.

**Goal:** close the nine defects observed in the DOCN report of 2026-11-09 (decision `520623df`, run attempt `~/.tradingagents/logs/DOCN/2026-11-09/080944-6b051473`), so that a case that double-counts an instrument is rejected by code, every number the Portfolio Manager cites resolves, conditions print once with their metric, peers are not excluded for periods nobody reads, follow-ups say honestly what they cannot answer, the Trader keeps the Research Manager's triggers when structured output fails, and the page renders cleanly.

**Baseline:** the run was produced on the installed launcher checkout at `55edfd7e` (checked out 2026-11-09 07:52, run started 08:09). Local `staging`, `origin/staging` and the launcher HEAD all resolve to `55edfd7e` (verified read-only 2026-11-09). Every defect below was re-checked against that source. The earlier workflow gap-closure plan and Amendment 1 are complete and integrated; this plan starts from their result.

**Spec:** the defect list and verified facts in `~/Claude/2026-11-09-tradingagents-session-handoff.md`; evidence paths in this file. Offline replay uses `~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-09_520623df.json` and the attempt directory above; no paid calls for Builds V, T, E, P, F.

**Branch and release boundary:** identical to the base plan (`docs/superpowers/plans/2026-11-07-tradingagents-workflow-gap-closure-plan.md`, section "Branch and Release Boundary"). Each build is a new isolated worktree from the exact confirmed `staging` commit. Completion authorizes no merge, push, install or worktree removal.

Independent audit: required

Build size: **medium**. Recommended implementer: Claude Opus 5.5 (`claude-opus-5-5`), medium effort.

## Execution status (2026-11-09)

Done on `claude/report-defect-closure-20261109`: V1-V3, T1-T3, E1-E4, P1, F1-F2, X1-X2, S1-S3. Deferred: X3 (no paid calls), S4 (decision: not added). Adjustments, commits and proofs: `docs/reviews/2026-11-09-report-defect-closure.md`. This plan has no checkboxes; this section is its status record.

## Finding coverage

| # | Defect observed in `520623df` | Root cause confirmed in source | Task |
|---|---|---|---|
| 1 | Fundamentals analyst counted the 2030 notes as borrowings (~$150M) and as ~3.9M conversion shares; third run in a row. Audit caught it, case disputed, card shows no range. Also: ATM cash with no ATM shares. | `valuation_cases.price_case` validates each capital value in isolation; nothing links a share estimate to the obligation it converts, or cash proceeds to the shares they create. | V1, V2 |
| 2 | PM citation check reports false mismatches on F46/F44, which are inputs to the matched growth calculation C15. | `citation_check._canonical_values` tests each label against its own value only; a sentence citing a derived figure and its inputs fails on the inputs. | E1 |
| 3 | Conditions printed twice (four kept + four content-identical "new proposals"), proposals carry one pasted generic reason, two price-level conditions have no metric label, one is "Unspecified thesis role". | `memory/thesis.py` merge keys on `condition_id` only; the PM re-proposed the same four conditions under new IDs. `decision_context.py:296-298` labels price levels `'condition'` and pastes `thesis.rationale` as every proposal's reason. `ThesisCondition.thesis_role` defaults to `unspecified`. | T1, T2, T3 |
| 4 | Nebius excluded: "Revenues ambiguous at 2023-12-31". | `sec_edgar._as_of_records` raises for the whole peer on one ambiguous period; the three-year `period_floor` (2023-11-09) admits FY2023, which peer statistics never consume. | P1 |
| 5 | All four follow-ups `no_relevant_passage`, yet the RM marked bear-2 "partially answered". Two questions ask about post-filing events (ATM sales, 2026-note settlement) no filing can answer. | RM judgment is free; nothing ties it to retrieval. Questions carry no scope. | F1, F2 |
| 6 | Bull and bear cite F63/F64 (current assets, current liabilities); the published brief ends at F55. | `prompt_reference_map` assigns F56–F68 to facts that appear only in the shared source brief; they are stored in `prompt_evidence_references` (evidence.json) but never rendered, and the citation check lists them as unresolved. | E2 |
| 7 | Trader dropped the RM's bearish triggers and checkpoints; footer shows a Trader fallback. | `invoke_structured_or_freetext` accepts any free text on fallback. Cause was `OpenAIInvalidRequestError` (also hit the Sentiment Analyst); the error body is not retained anywhere. | X1, X2, X3 |
| 8 | `&#x27;` on the card; "unavailable USD/shares"; disputed case undecorated in the scenario summary row; executive summary credits the case to the RM. | `thesis._display` and `shared_valuation._cell` HTML-escape text that markdown-it (html=False) escapes again. Summary table row ignores `disputed_by`. Unit built from a missing currency. Summary template attributes adoption generically. | E3, E4, V3 |
| 9 | Every SEC document hits the text limit; 7 of 7 model disclosure submissions rejected ("numeric quote drops part of the source subject or qualifier"); audit reads 6,000 chars per role and never audits the PM. | Per-document ceiling 40,000 chars and package ceiling 120,000 in `sec_documents.py` while the cache holds the full 10-Q text (1.55M chars). `audit_pass._ROLE_LIMIT = 6000` is a constant. Audit node precedes the PM in the graph. | S1, S2, S3 (S4 is a decision) |

## Delivery estimate

| | V valuation integrity | T thesis & conditions | E references & rendering | P peers | F follow-ups | X Trader fallback | S persistent limits |
|---|---|---|---|---|---|---|---|
| Build size | small | small | small | small | small | small | medium |
| Recommended model (Codex) | GPT-6 Sol (`gpt-6-sol`) | Sol | Sol | GPT-6 Astra (`gpt-6-astra`) | Sol | Sol | Sol |
| Reasoning effort | medium | medium | medium | medium | medium | medium | medium |
| Active implementation and verification | 4–6 h | 3–5 h | 4–6 h | 3–5 h | 3–4 h | 3–5 h | 8–12 h |

- Independent audits and gap closure: 3–5 h across the seven builds. **Total 31–48 active hours.** Overall build size: medium.
- Astra for P because choosing which ambiguous periods may be dropped is a source-of-truth rule where a plausible wrong answer passes local tests and silently changes a peer range (the same reason R1 used Astra). Sol elsewhere: each task has a clear contract, a replayable fixture and a deterministic test. Engineering judgment, not a measured comparison.
- Paid calls: none for V, T, E, P, F, S. X3 needs one Trader call against the recorded prompt to capture the provider's 400 body (well under $1); it is a decision below. One confirming DOCN run after integration is recommended, not required for build acceptance.
- Codex credits: no usage measurements exist for this repository; I cannot estimate them credibly.

## Global constraints

- No change to rating eligibility, publication gating or evidence-gate pass/fail rules, except V1/V2, which add rejection reasons for a case.
- Proofs replay the recorded 2026-11-09 state; no paid model or vendor calls except X3 if authorized.
- Escape HTML only at HTML export, never in prompt text or markdown (restated from the base plan; E3 enforces it).
- Existing publication records are never rewritten.
- Prompt-contract changes (V1/V2, F2) each get a test asserting the rendered prompt contains the new field text.
- Each build is proven by its named tests plus a replay of `520623df` showing the defect gone and nothing else changed in the rendered report.

---

## Build V — Valuation integrity (defects 1, 8-attribution)

### V1 One instrument, one role
**Files:** `tradingagents/agents/valuation_cases.py` (`CapitalValue`, `CaseCapital`, `price_case`), `tradingagents/agents/analysts/fundamentals_analyst.py` (`SHARED_VALUATION_INPUTS`), `tests/test_shared_valuation.py`.
- Constraint found in source: `valuation._borrowings_complete` (valuation.py:269) requires the borrowings category to cite the reported Total Borrowings fact (or its complete components), so a converted note cannot be dropped from the fact list. The double count therefore has to be caught on the **estimated value**: the analyst's `obligations.borrowings.value` must fall by the converted principal.
- Add `share_changes: tuple[ShareChange, ...] = ()` to `CaseCapital`, where `ShareChange` has `source: Literal["conversion", "atm", "sbc", "buyback", "other"]`, `shares: Decimal`, `converted_principal: Decimal | None = None` (required for `conversion`), `instrument: str` (free text, e.g. "2030 convertible notes"), `reason: str`.
- In `price_case`: when `closing_shares.assumption == "estimated"` and its value differs from the snapshot shares fact, `share_changes` must be present and sum to the difference (exact Decimal). Then `sum(borrowings fact values) − obligations.borrowings.value` must be **at least** `sum(converted_principal)` across conversion entries; otherwise raise `ValueError("Converted principal <amount> still counted in borrowings")`. The case then shows as rejected with that reason, as other validation failures do today.
- Update `SHARED_VALUATION_INPUTS` with the `share_changes` shape and one sentence: a note you convert into shares must also be removed from the borrowings estimate.
- Alternative rejected: a text heuristic on `closing_shares.reason`; it cannot tell which instrument was converted or by how much.
- Tests: `test_conversion_shares_with_principal_still_in_borrowings_is_rejected` (the 2030-notes case replayed from `520623df`), `test_conversion_shares_with_borrowings_reduced_is_supported`, `test_estimated_shares_without_share_changes_is_rejected`, `test_prompt_contract_names_share_changes`.

### V2 Cash and shares from the same financing move together
**Files:** as V1.
- Add `cash_changes: tuple[CashChange, ...] = ()` to `CaseCapital` with `source: Literal["atm", "operations", "debt", "other"]`, `amount: Decimal`, `reason: str`. When `cash.assumption == "estimated"` and the value differs from the snapshot cash fact, `cash_changes` must sum to the difference. An `atm` cash change without an `atm` share change, or the reverse, raises `ValueError("ATM proceeds and ATM shares must both be stated")`.
- Tests: `test_atm_cash_without_atm_shares_is_rejected`, `test_atm_cash_and_shares_together_is_supported`.

### V3 Executive summary names the case author
**Files:** `tradingagents/report_summary.py` (`_ADOPTED_CASE` templates, ~:191, :447-456).
- Where the summary says the portfolio manager adopted a validated case, add whose case it was: "proposed by the fundamentals analyst" or "revised by the Research Manager" from `shared_valuation_scenarios.revision_status` and the adopted version (1 = analyst, 2 = RM revision).
- Test: `tests/test_report_summary.py::test_adopted_case_attribution_follows_version`.

### V proof
Replay `520623df`: the 2030-notes case is rejected with the V1 reason before audit; the card shows a range from the remaining supported case or an explicit "no supported case". Full `pytest tests/test_shared_valuation.py tests/test_report_summary.py`.

## Build T — Thesis conditions print once, with their metric (defect 3)

### T1 Content-identical re-proposals are the kept condition
**Files:** `tradingagents/memory/thesis.py` (merge block ~:385-414), `tests/test_thesis.py`.
- Define a content key per kind: metric → (metric, period_start, period_end, comparator, threshold, unit, basis); price_level → (comparator, threshold, currency); event → (description). After the existing ID merge, any new proposal whose key equals a preserved prior condition's key is dropped and its ID recorded in the prior's `condition_aliases`; the "Kept condition … omitted from proposal" warning is not raised when a content match exists.
- Tests: `test_reproposed_identical_condition_is_aliased_not_duplicated` (four prior + four identical new → four conditions, four aliases, zero omission warnings, exact IDs from the 2026-11-09 state), `test_different_threshold_is_a_new_condition`.

### T2 Price-level rows carry a metric and each proposal carries its own reason
**Files:** `tradingagents/agents/decision_context.py` (~:283, :296-298), `tests/test_decision_page.py`.
- Row metric for `kind == "price_level"`: `"Completed close (<currency>)"`; for `event`: the description. Never the literal `'condition'`.
- New-proposal `reason` is the condition's own `rationale` (required on `ThesisCondition`), not `thesis.rationale`.
- Tests: `test_price_level_row_shows_completed_close_and_currency`, `test_new_proposal_reason_is_its_own_rationale`.

### T3 Every new proposal states its role
**Files:** `tradingagents/memory/thesis.py` (`ThesisCondition.thesis_role`), PM structured schema in `tradingagents/agents/schemas.py`, `tests/test_thesis_condition_kinds.py`.
- New proposals must give `supports_thesis` or `reconsideration_trigger`; `unspecified` remains only for legacy rows loaded from prior publications. Validation error names the condition.
- Test: `test_new_proposal_without_role_is_rejected_legacy_rows_still_load`.

### T proof
Replay: the thesis section lists four metric conditions, two price levels labelled "Completed close (USD)", two events; no duplicates; no "Unspecified thesis role". `pytest tests/test_thesis*.py tests/test_decision_page.py`.

## Build E — Evidence references and rendering (defects 2, 6, 8)

### E1 A cited input of a matched derived figure is not a mismatch
**Files:** `tradingagents/agents/citation_check.py` (`_canonical_values`, `check_pm_citations`), `tests/test_citation_check.py`.
- Every C row in the canonical brief already ends with `inputs F46, F44` (confirmed in the `520623df` brief: `- [C15] revenue yoy growth: pass; 39.87 … percent; …; inputs F46, F44`). Parse that suffix in `_canonical_values` into a `C → {F}` map. In `check_pm_citations`, evaluate a sentence's labels together: if any C label in the sentence matches a stated number, F labels that are inputs of that C are counted matched. F labels not tied to a matched C keep today's rule.
- Also resolve labels from `state["prompt_evidence_references"]` (F56+ and S labels) to their fact values via `financial_evidence`, so they are checked instead of listed as unresolved.
- Tests: `test_inputs_of_matched_calculation_are_not_mismatches` (F44/F46 with C15 from the 2026-11-09 brief), `test_prompt_only_label_resolves_to_fact_value`, `test_unrelated_fact_label_still_mismatches`.

### E2 Prompt-only references appear on the page
**Files:** `tradingagents/report_html.py`, `tradingagents/reporting.py` (markdown export), `tests/test_report_html.py`.
- Render a "Prompt-only references" list after the canonical evidence appendix: label → metric, period, value, unit, fact_id, for every `prompt_evidence_references` entry whose label is not in the canonical appendix and whose fact exists in `financial_evidence`. Same list in the markdown report.
- Test: `test_prompt_only_fact_labels_render_with_values` (F63 → Current assets 1,071… from the replayed state).

### E3 Escape once, at export
**Files:** `tradingagents/memory/thesis.py` (`_display`), `tradingagents/agents/shared_valuation.py` (`_cell`), `tests/test_report_html.py`, `tests/test_thesis.py`.
- Remove `html.escape` from both helpers; keep pipe and markdown-marker escaping. `report_html._markdown()` already escapes with `html=False`.
- Tests: `test_apostrophe_in_condition_renders_literally` (no `&#x27;` or `&amp;` in the rendered HTML), `test_pipe_in_cell_still_escaped_for_tables`, `test_markdown_export_has_no_html_entities`.

### E4 Disputed case marked in the summary row; unit never "unavailable"
**Files:** `tradingagents/agents/shared_valuation.py` (summary row ~:312, :348), `tradingagents/agents/decision_context.py` (~:415), `tradingagents/agents/schemas.py` (~:536, :559), `tradingagents/reporting.py` (~:576).
- Summary row value for a `disputed_by` row: "<value> <unit> — disputed (<finding ids>), excluded from range".
- "unavailable USD/shares" is `display_number(None)` ("unavailable", valuation_comparison.py:144) followed by the unit at the five sites above. Add one helper `display_value(value, unit)` in `valuation_comparison.py` that returns "unavailable" alone when the value is None and use it at all five sites.
- Tests: `test_disputed_row_marked_in_summary_table`, `test_missing_value_renders_unavailable_without_unit`.

### E proof
Replay: citation check shows 0 false mismatches on F44/F46; F63/F64 resolve; no `&#x27;` anywhere in `complete_report.html`. `pytest tests/test_citation_check.py tests/test_report_html.py tests/test_shared_valuation.py`.

## Build P — Peer exclusion by period actually read (defect 4)

### P1 Ambiguity excludes the period, not the peer
**Files:** `tradingagents/dataflows/vendors/sec_edgar.py` (`_as_of_records` ~:288-312, `get_financial_evidence`), `tradingagents/agents/valuation_reference_flow.py` (`_fetch_peer` ~:235-245), `tests/test_peer_period_scope.py`, `tests/test_sec_edgar.py`.
- Add `ambiguity: Literal["raise", "exclude"] = "raise"` to `_as_of_records` and thread it from `get_financial_evidence(peer_revenue_definitions=True)` as `"exclude"`. In exclude mode an ambiguous (end, span) is skipped and recorded in `package.warnings` as "Revenues ambiguous at 2023-12-31; period excluded". Subject-issuer behaviour is unchanged (still raises).
- `_fetch_peer` then fails only if `_latest_ttm`/`_ttm_at` cannot form the quarters the statistics use; the exclusion text reaches the existing `result["excluded"]` list so the brief says which period was dropped and why.
- Tests: `test_peer_ambiguous_old_period_is_excluded_not_fatal` (NBIS companyfacts fixture with the 2023-12-31 conflict; TTM at 2025 quarters still computed), `test_subject_issuer_ambiguity_still_raises`, `test_excluded_period_is_disclosed_in_peer_brief`.

### P proof
Replay with the cached NBIS companyfacts: NBIS appears in the peer table with its TTM multiple and a disclosed excluded period. `pytest tests/test_peer_period_scope.py tests/test_sec_edgar.py tests/test_peer_revenue_tags.py`.

## Build F — Follow-ups that say what they cannot answer (defect 5)

### F1 No passage, no answer
**Files:** `tradingagents/agents/managers/research_manager.py` (post-processing of `followup_judgments`), `tradingagents/agents/output_validation.py`, `tests/test_na_followup_judgments.py`.
- After the RM returns, any judgment whose question has retrieval status `no_relevant_passage`, `unavailable` or `invalid_query` is coerced to `unanswered` with explanation prefixed "No retrieved passage; model judgment '<original>' discarded." Record one operational observation `followup_judgment_overridden` per coercion. The RM prompt gains one sentence stating the rule.
- Tests: `test_partially_answered_without_passages_is_coerced_to_unanswered`, `test_answered_with_passages_is_kept`, `test_override_is_disclosed_on_card`.

### F2 Questions about events after the last filing are labelled, not searched
**Files:** `tradingagents/agents/document_questions.py` (`parse_document_questions`, question records, `_check_retained`), `tradingagents/agents/researchers/bull_researcher.py` and `bear_researcher.py` (prompt sentence), `tests/test_document_followup.py`.
- Questions are parsed from the debaters' fenced block by `parse_document_questions`; there is no pydantic schema. Add an optional `scope` field to that block (`retained_filings` | `post_filing_event`, default `retained_filings`), carried in `question_records` and covered by the existing record hash; legacy records without it validate unchanged. `post_filing_event` questions get status `not_answerable_from_filings` with zero passages and are not sent to retrieval; the card prints "Not answerable from filings retrieved before the event." The RM judgment for them is fixed `unanswered`. Debater prompts gain one sentence: mark a question `post_filing_event` when it asks what happened after the latest retained filing date, which is shown in the brief.
- Tests: `test_post_filing_event_question_skips_retrieval_and_renders_label`, `test_legacy_record_without_scope_validates`, `test_debater_prompt_names_scope_rule`.

### F proof
Replay: bear-2 shows `unanswered` with the override note; `pytest tests/test_document_followup.py tests/test_na_followup_*.py tests/test_ground_truth_followup_resume.py`.

## Build X — Trader fallback keeps the plan (defect 7)

### X1 The provider error is retained
**Files:** `tradingagents/agents/structured.py` (`invoke_structured`), `tradingagents/operational_capture.py`, `tests/test_structured_agents.py`.
- On structured failure, record the exception class and the first 500 characters of the provider message (API keys and request bodies stripped) in the `fallback_recovered` operational record and in the run log line. Today the record has only `code` and `stage`.
- Test: `test_fallback_record_carries_error_class_and_message`.

### X2 Free-text fallback must carry the plan
**Files:** `tradingagents/agents/trader/trader.py`, `tradingagents/agents/structured.py` (`invoke_structured_or_freetext` gains an optional `required_sections` check), `tests/test_action_aware_trader.py`.
- When the Trader falls back, verify the free text contains the Action line and a Reasoning section. Then, regardless, append a verbatim block "Carried from the Research Manager's plan (not restated by the Trader)" containing the RM's strategic actions and any trigger/checkpoint lines, extracted by their headings from `investment_plan`. If the Action line is missing, raise the existing stage failure rather than publishing a plan without an action.
- Tests: `test_fallback_appends_rm_triggers_verbatim`, `test_fallback_without_action_line_fails_stage`, `test_structured_success_does_not_append_block`.

### X3 Find the 400 (decision required; one paid call)
- Replay the recorded Trader prompt from `unvalidated_outputs` once against the configured deep slot with structured output on, capture the error body via X1. Both the Trader and the Sentiment Analyst hit `OpenAIInvalidRequestError` in this run and the deep model is the common factor; the likely cause is a schema feature (nullable floats with defaults, 19 optional fields across `schemas.py`) the provider's strict mode rejects. Fix per the captured message: either mark the schema fields required-with-null or switch those two agents' binding method. Record the body in the build report.
- Test after the fix: `test_trader_schema_is_strict_mode_compatible` (static check of the generated JSON schema against the constraints the message names).

### X proof
`pytest tests/test_structured_agents.py tests/test_action_aware_trader.py tests/test_structured_agent_prompts.py`; a replay of `520623df` shows the carried block under the Trader section.

## Build S — Persistent limits (defect 9)

### S1 Audit budget is configuration and the final turn is never cut
**Files:** `tradingagents/agents/audit_pass.py` (`_ROLE_LIMIT` :39, `_role_windows`), `tradingagents/default_config.py`, `tests/test_audit_role_coverage.py`.
- `audit_role_chars` config key (env `TRADINGAGENTS_AUDIT_ROLE_CHARS`), default **12,000**; the final turn of a debate role is always audited in full, and earlier turns take what remains. Coverage disclosure unchanged. Rationale: at 3+3 rounds the current 6,000 covers under half of a debater's history; doubling it costs roughly 60k more audit input tokens per run (about 3% of the run's 2.1M).
- Tests: `test_role_limit_from_config`, `test_final_turn_always_complete_when_over_budget`.

### S2 Deterministic extractors read the full cached document
**Files:** `tradingagents/dataflows/vendors/sec_documents.py` (per-document 40,000 and package 120,000 ceilings ~:780-800), `tradingagents/agents/filing_terms.py`, `tradingagents/agents/document_questions.py`, `tests/test_sec_documents.py`.
- Separate two budgets that are one today: the **model package** (what agents read; keep 120,000) and the **extraction corpus** (what code reads). Filing-term extraction, guidance grounding, follow-up search and the auditor's full-source lookup (G3) read the complete cached text (the DOCN 10-Q cache holds 1.55M characters). The report's "Document text limit reached" gap then applies only to the model package and says so.
- Tests: `test_extractors_read_full_cached_text_beyond_package_limit`, `test_model_package_limit_unchanged`, `test_text_limit_gap_names_model_package_only`.

### S3 Why 7 of 7 model submissions were rejected
**Files:** `tradingagents/agents/evidence_validation.py` (rule "numeric quote drops part of the source subject or qualifier"), `tests/test_evidence_validation.py`.
- Replay the seven rejected submissions from `disclosure_evidence.model_extraction` offline and classify each: quote genuinely truncated the subject (keep rejecting) versus quote is a verbatim contiguous span containing the number and the metric phrase (accept). Relax the rule only for the second class; add the seven as fixture cases with the expected disposition. If all seven are genuinely truncated, change the fundamentals prompt's quoting instruction instead and record that no rule change was made.
- Tests: `test_verbatim_span_with_metric_phrase_is_accepted`, `test_quote_missing_subject_is_still_rejected`, plus the seven fixtures.

### S4 Audit the Portfolio Manager (decision, not a task)
- The audit node runs before the PM by design, so the PM's prose is checked only by the citation check (E1). A post-PM audit pass would add one model call per run (roughly 20–40k input tokens). Recommendation: do not add it now; re-evaluate after E1 has run for a week of reports.

### S proof
`pytest tests/test_audit_role_coverage.py tests/test_sec_documents.py tests/test_evidence_validation.py`; replay shows audit coverage per role at or near 100% of the final turn and guidance grounding unchanged at 15/15.

---

## Sequence

V → T → E → P → F → X → S. V first because it removes the recurring disputed case; T and E are the visible page defects; P, F, X are independent and may run in parallel worktrees if the user wants; S last because S2 changes shared retrieval behaviour and benefits from the others being settled. One confirming paid DOCN run after integration of V–X is recommended.

## Decisions for the user

1. Approve this plan and the executor (Codex, as for the previous plans).
2. X3: authorize one paid Trader structured-output call against the recorded prompt to capture the provider error (well under $1), or defer X3 and ship X1/X2 only.
3. S1: default audit budget 12,000 characters per role (recommended) or another value.
4. S4: accept the recommendation not to add a post-PM audit pass now.
5. Whether P, F and X may run as parallel worktrees to shorten wall-clock.

## Deferred, not in this plan

- Token cost per run (~2.1M input) beyond the S1 note; a separate measurement pass is needed before any budget change.
- Settlement and publication items from the 2026-11-07 plan are complete and not reopened here.
