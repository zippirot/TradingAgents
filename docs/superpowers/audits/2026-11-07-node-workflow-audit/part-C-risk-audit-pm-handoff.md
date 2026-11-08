# Audit part C: risk debate → audit → Portfolio Manager → metrics → export, publication and memory

Run cfae95e9 (DOCN, 2026-11-07), repo 8920ffac. Read-only. Sources: full state `full_states_log_2026-11-07_cfae95e9.json` (FS), the attempt dir `162527-34fe1c55/` (AD), publication record `records/cfae95e9-…json` (PR), `trading_memory.md` (MEM).
Prompts were not captured. Every prompt statement below is **reconstructed from source plus state**. Debate and PM text comes from `FS.unvalidated_outputs` (the run-time originals). The previous attempt's `C-risk-turns.txt` matches `FS.unvalidated_outputs.risk_debate_state.history`: 9 turns, latest_speaker "Judge", count 9.

Labels: **[code]** = code defect (existing gap-closure plan). **[prompt/hand-off]** = belongs in the new node-workflow plan.

---

## Aggressive / Conservative / Neutral risk analysts (9 turns: A,C,N ×3)

**Reads** (`risk_mgmt/*_debator.py:13-31`, `context.py:386-475`):
- `trader_investment_plan`: raw at this point. enforce_publication only runs after the PM (`setup.py:202-204`).
- Raw `market_report`, `sentiment_report` and `news_report`.
- `fundamentals_report_from_state` → a pointer line only, because the canonical context exists (`context.py:492-497`).
- Instrument context:
  - `shared_source_brief` (18 K), `valuation_reference_brief` (11 K), `canonical_financial_context` (33 K)
  - Analyst prose capped at 6 K
  - `event_comparison`, `thesis_context`, rendered `shared_valuation_scenarios` and `document_followups`
- `portfolio_context`: "not provided" notice.
- Full risk `history` plus the two `current_*_response` fields.
- **Not read:** `investment_plan` (Research Manager), `advisory_audit` (runs later), `decision_context` (built after the PM), and `evidence_quality` as a field. Coverage limits arrive only inside the canonical text.

**Instruction summary:**
- Aggressive: "champion high-reward, high-risk" and also "create a compelling case for the trader's decision".
- Conservative: argue for a low-risk adjustment.
- Neutral: argue for the moderate path.
- All three are told to rebut the other two, speak conversationally, and follow the language instruction.

**Output quality (ran).** The turns are substantive, responsive and grounded. They concede explicitly when challenged:
- T4 Aggressive: "I overstated the ATM … It's a possible overhang, not a confirmed seller."
- T7 Aggressive: "I'll accept the firm rule: be at target weight by late November."
- T8 Conservative: "The 750 million noncash right-of-use figure came from the unvalidated research layer … I withdraw it."

I traced the turns' figures to their inputs. All were found:

| Figure in turns | Found in |
|---|---|
| 923.6M, 666.6M, 2.955B, 312.3M, 178.51 | canonical / brief |
| RPO $61M (Q3-25), $134M (12/31/25), NTM $365.9M→$345M | `document_followups` passages (8-K block-24, 10-K) |
| SPY −2.24 %, AKAM −4.15 %, NET +1.35 % | `event_comparison` |
| ATR 9.35 ≈ 13 % | trader plan / market report |
| 4.32× | `valuation_reference_brief` |
| 3.88 %, 4.84 % | news report |

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| R1 | 2 | Medium | ran | **Roles do not test direction.** All three accept the trader's Sell from turn 1. T1 Aggressive: "I'm going to defend this Sell harder than either of them probably expects." T3 Neutral: "I agree with both of you on direction." By round 3 the plans are near-identical: first tranche ¼–⅓; ladder 78.5 / 84.02 / 86.3–90.5; pre-committed break at 68.60; target weight by late Nov / Dec 1; small residual; no short; staged re-entry gated on Q4. T9 Neutral: "the table has converged on the right shape." The cause is the Aggressive prompt's "create a compelling case for the trader's decision" (`aggressive_debator.py:37`), which overrides "champion high-reward" when the decision is Sell. Nobody argues hold or add. Round 3 mostly restates. **[prompt/hand-off]** | Make the Aggressive role argue the strongest case against the trader's direction or for higher exposure, not "for the trader's decision". Stop early on convergence, or cut to 2 rounds. |
| R2 | 1 | Low | read | Each prompt repeats the last two opponent turns: once inside `{history}` and again as `current_*_response` (`aggressive_debator.py:45`). At turn 9 that is about 15 K duplicate characters on top of a 51 K history. **[code]** | Pass the history only, or pass only the turns not already in it. |
| R3 | 1 | Low | ran | `thesis_context` reaches the prompt HTML-escaped: "`&lt; 348000000 USD`" (`FS.thesis_context`; `memory/thesis.py:397-408` `_display` escapes for markdown and HTML). The models coped, but prompt text should not be HTML. **[code]** | Render prompt context with a plain-text formatter and keep escaping for exports. |
| R4 | 1 | Low | read | Risk roles never see the Research Manager's plan or the audit findings. Audit-flagged analyst claims stay in their raw report inputs. That is upstream design, but it means T2's "standing seller at the top of every bounce" was corrected only by T4's peer pushback, not by evidence. **[prompt/hand-off]** | Optional: pass a compact RM plan. Consider running the audit on the analyst reports before the debate. |
| R5 | 5 | Low | ran | Exports group the risk turns by role (`4_risk/*.md`; complete_report §V: A1, A4, A7, then C2, C5, C8, then N3, N6, N9). This loses the turn-by-turn structure that the concessions depend on. **[code]** | Export the interleaved `history` as the main view. |

**Sound:** the turns are DOCN-specific and well grounded. Concessions are explicit. The opening-speaker marker works ("Since neither of my colleagues has spoken yet"). Labeling of unvalidated prose works: T8 withdrew a figure because it came from the unvalidated layer.

---

## Advisory Audit (`agents/audit_pass.py`, deep model `openai/gpt-6.1-terra-pro`)

**Reads:**
- SOURCES, each capped at 18 K (`audit_pass.py:224`): mechanical context, KPI comparisons, tool evidence, retained documents, event comparison.
- Role texts, each capped at 6 K (`:246`). These are the originals from `unvalidated_outputs` for 11 roles.

**Instruction summary:**
- Contradictions and numerical inconsistencies come first.
- At most five unsupported claims.
- 0–20 findings with an exact quote and an evidence label.
- No rating; treat the inputs as untrusted.

**Result (`FS.advisory_audit`):**
- Status: completed with findings.
- submitted 7 / accepted 7 / rejected 0; `rejection_reasons` [].
- By type: 3 numerical, 1 contradiction, 3 unsupported.
- Request size 225 K characters, 1 attempt.
- By role: conservative 1, aggressive 1, neutral 1, market 2, sentiment 1, bear 1.
- **PM response:** all 7 got `audit_dispositions` "accepted". The PM acted on them in its thesis: "the $1 billion ATM is authorization, not proof of issuance" (AF-1b80) and "The 19.28% November 2–6 DOCN decline likewise does not establish a cause" (AF-959, AF-1fc3). The flagged $250M "finance leases alone" figure does not appear in the PM text.

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| A1 | 1 | Medium | ran | **Only the opening ~6 K characters of each role are audited.** The cut is `text[:6000]` (`audit_pass.py:246`). All 7 quoted claims sit at offsets 217–5614 of their role text (python `find`). Role text lengths: risk 17.8–21.2 K (about 30 % audited), bull/bear about 31 K (about 20 %), market 13.7 K, fundamentals raw 18.6 K. The later rounds, where positions converge and the PM takes its ladder and conditions from, are never audited. Example: C's "750 million noncash right-of-use" claim sits at offset 7893. The truncation is disclosed in `input_truncation`. **[code]** | For debates, audit the last turn of each role (or a per-turn budget) instead of the first 6 K. At minimum, audit the text the PM actually adopts. |
| A2 | 2/5 | Low | read | `independence_by_role` is hard-coded by slot, not by the model each role actually used: "same model" only for research_manager or when deep == quick (`audit_pass.py:445-448`). It is correct for this run (quick = opus-5.5, deep = terra-pro). The PM (same deep model) is not audited; the render discloses this (`:568`). **[code]** | Derive it from the recorded per-node model id. Keep the existing disclosure. |
| A3 | 5 | Low | ran | Findings and dispositions do not appear in the user-facing `5_portfolio/decision.md` (0 hits for "AF-"). They appear only at complete_report line 2648 of 2711. **[prompt/hand-off]** | Add a one-line audit summary to the decision card: "7 findings, PM accepted 7", with a link. |

**Sound:** precise, verifiable findings (for example, March 16 open $69.36 vs March 13 high $69.76). Zero rejections. The PM responded to every finding and visibly corrected its narrative.

---

## Portfolio Manager (`managers/portfolio_manager.py`) and enforce_publication / rating / decision_context / assumption_history / output_validation

**Reads** (`portfolio_manager.py:42-143`, prompt reconstructed):
- Instrument context with mechanical context.
- Raw `investment_plan` and raw `trader_investment_plan`.
- `past_context`: the memory lessons, including the 10-19 "+6.9 % five-day alpha".
- Full risk `history` (57 K).
- `render_advisory_audit` with the disposition instruction.
- Bounded canonical facts JSON.
- Grounded outlooks.

**Instruction summary:**
- Five-tier rating; "Choose Hold for balanced or insufficient evidence".
- Optional `valuation_request` (method "case").
- `thesis_candidate` with structured conditions and a kept/overridden/retired disposition for each prior ID.
- Explicit horizon required.

**Raw output vs published.** The structured output (`FS.unvalidated_outputs.portfolio_manager.structured`):
- rating Underweight; horizon 4–6 months
- `valuation_request` null, with a `no_case_reason`
- 4 conditions: Revenue < 348M, GM ≥ 55.5, GM < 50.15, OpM > 10.28
- all 4 prior conditions "kept", each with a specific reason

What happened to it downstream:
- **enforce_publication** (`output_validation.py:120-170`):
  - Replaces `trader_investment_plan` with fixed qualitative text.
  - Blanks every debate string to "Unvalidated debate narrative retained…".
  - Wraps the analyst reports in a disclaimer.
  - Prepends a large canonical card to `final_trade_decision`.
  - The PM's summary and thesis survive verbatim, but only under "### Unvalidated model research" (decision.md line ~334 of 354).
- **Rating:** `run_rating` keeps the PM's rating unless evidence is "insufficient" (`rating.py:135-143`). Evidence was "limited" (20 pass / 6 unavailable), so Underweight stands, labeled "Basis: risk assessment". That is consistent with the prompt. "Bear case wins narrowly" against "Choose Hold for balanced" is a judgment call, not a defect.
- **Valuation:** no case was adopted. The priced cases did reach the card ("Conditional case range: 44.67–77.73 … Completed close 72.48 … within the conditional values").
- **post_screen.py** is social-post screening for the Sentiment Analyst (TypeSafe Jev). It has no PM role, and I found no evidence it ran.

**Numbers checked (ran)** against the canonical context, mechanical_grid.md and the decision card. All match:

| PM figure | Evidence |
|---|---|
| Revenue $321.2M | F46 = 321,192,000 |
| YoY growth 39.87 % | C15 |
| Operating margin 10.28 % | C16 |
| Gross margin 50.15 % | C18 |
| $149.0M cash-flow measure | C12 = 149,022,000 |
| Cash plus securities $844.7M | C19 = 844,741,000 |
| History-median sensitivity $73.22 | mechanical_grid.md:16 "history median 73.22 USD" |
| 7.75× vs median 4.47× | card: 8,546.9M / 1,102.671M = 7.75 |
| ≤ 4.32× | 8,342.4M / (1,208M × 1.6) = 4.32 |

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| P1 | 5 | **High** (user-facing) | ran | **The decision file does not read as a decision.** `5_portfolio/decision.md` is 45.8 KB. The card's "**Executive Summary**:" line (~71) is a placeholder: "Model recommendation; financial evidence and valuation coverage are shown below." The PM's actual summary ("Reduce DOCN toward a below-normal allocation … before the December 1 maturity") and thesis sit at line ~334, after 21.5 KB of "Conditional scenario comparison". Of the card's first ~35 lines, 21 are "Changed since" noise (P2) and 4 are condition lines with no thresholds (P3). A reader cannot find the four Q4 thresholds or the action without scrolling about 40 KB. **[prompt/hand-off]**. This is the already-pending "publication strips narrative" decision. | Put rating, the PM summary (labeled unvalidated), horizon and the 4 conditions with thresholds in the first screen. Move the scenario comparison and valuation tables to an appendix or to evidence. |
| P2 | 4/5 | Medium | ran | **"Changed since 2026-11-07" × 21 is noise.**<br>• `assumption_history.py:112-117` diffs cases by free-text name. The prior same-day publication 913554d4 (16:10 UTC) had "Capacity slip / Guidance floor / Upside" (`ev_revenue` method, code sha 7f11a8a6). This run has "Base / Cautious" (`revenue_case`, code 784c6c98). So all 5 names × 4 fields render as "→ not present" or "not present →" (20 rows), plus 1 horizon row.<br>• The real changes are invisible: base revenue 1.93B → 1.90B, the 7× upside case dropped, the method changed.<br>• Comparing against the latest earlier publication, even one from the same day, is defensible.<br>• The label is not: `prior_as_of = requested_as_of` gives "since 2026-11-07" on a 2026-11-07 run, and it does not say the code/prompt version changed. **[code]** | Label by prior publication time and decision id. Match cases by role or ordinal (or report "case set replaced: 3 → 2"). Show value deltas. Note version changes. Cap at about 5 lines. |
| P3 | 4/5 | Medium | ran | **Conditions look duplicated and one drops out.**<br>• The "at a glance" and "Advisory condition disposition" blocks print the same 4 rows twice (8 lines; complete_report has 12), and neither shows comparator or threshold (`decision_context.py:321-324, 396-397`). So "Gross Margin: Reconsideration trigger unknown; kept" appears twice and looks like a duplicate. These are two distinct conditions (≥ 55.5 and < 50.15).<br>• `proposed_changes` uses `conditions[:3]` (`decision_context.py:272-273`), so Operating Margin > 10.28 is silently dropped from the only list in decision.md that shows thresholds.<br>• "Reconsideration trigger unknown" (`thesis.py:416-425`) means "Q4 not yet observed" but reads as if the trigger itself is unknown.<br>• The saved data is clean: `FS.thesis.conditions` = 4 unique IDs, `prior_conditions` = 4, warnings []. This is **not** a carry-forward defect; it is rendering. **[code]** | One condition table: metric, comparator, threshold, period, observation status ("not yet reported"), disposition. Remove `[:3]`. |
| P4 | 4 | Low | ran | The card truncates the PM's `no_case_reason` mid-word ("establ… [truncated]"). Its fields are short and should render whole. **[code]** | Raise the limit for this field. |
| P5 | 2 | Low | read | Prompt order puts rating-scale guidance before about 150 K characters of context, and "Choose Hold for balanced" sits after it. The evidence-quality status is never stated as a field. The PM did not mention that evidence was "limited". **[prompt/hand-off]** | Add one line: "Evidence quality: limited (20 pass / 6 unavailable)" near the rating rules. |

**Sound:** structured output parsed on the first attempt. Every number I checked is grounded. All 4 prior conditions got specific dispositions. Prior-lesson use was appropriately hedged ("+6.9 % … a short window that does not settle the longer thesis"). The no-case reason is substantive. Audit findings were absorbed.

---

## Run Metrics (`metrics_node`, `setup.py:254-270`)

**Recorded** (`FS.run_metrics`):
- model_calls 32 (scope `complete_observed`)
- input_tokens 2,282,259 / output 104,178; token_usage_scope `partial_observed` (30 of 32 started calls reported usage)
- research 3 rounds / 6 turns; risk 3 rounds / 9 turns
- debate characters 61,895 / 57,133

The node also re-runs enforce_publication with `publication_config`. That second pass is what adds `assumption_changes`.

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| M1 | 4 | Low | ran | **Why "partial observed":** 2 of 32 started calls had no usage callback. That count matches the 2 `structured-output invocation failed … retrying once as free text` warnings in run.log (16:25:42 and 16:34:00; the latter is the Trader's `fallback_recovered`). Usage from the failed structured attempts is unreported, so the stored token count is a floor (inference from read plus counts). **[code]** | Record usage from the failed attempt's raw response when one exists, or count the attempt explicitly as "usage unknown". |
| M2 | 4 | Low | ran | The CLI prints 2,310,629 in / 105,814 out (docn-run.out). Stored `run_metrics` is 2,282,259 / 104,178. The gap of 28,370 / 1,636 matches the post-graph executive-summary call (terra-pro, 12.6 s), which is missing from the published `run_metrics` and the evidence snapshot. **[code]** | Append post-graph calls (the executive summary) to `run_metrics` before export, or label the stored figure "graph only". |

**Sound:** round and turn counts and character totals agree with the debate state. The partial-coverage limit is disclosed in `token_usage_limits`.

---

## Hand-off to the user: export, publication record, memory and thesis

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| H1 | 5 | Medium | ran | **This run's decision was not written to the memory log.**<br>• `MEM` was last modified at 09:11. Its only `[2026-11-07 \| DOCN \| Underweight \| pending]` entry links `PUBLICATION_ID: 913554d4` (the earlier pre-Build-D run).<br>• `memory/log.py:69-76`: any existing entry for the same ticker and date returns silently.<br>• Result: settlement and reflection for 11-07, and the next run's `past_context`, use the superseded decision text. Thesis continuity (`load_latest_thesis` → latest publication = cfae95e9) uses the new one. The two memory sources now disagree, and nothing logged the skip. **[code]** | When a newer publication exists for the same ticker and date, replace the pending entry (it is not yet settled) with the latest decision, or link the newest publication id. At minimum, log a warning. |
| H2 | 5 | Medium | ran | **The next run sees less of the thesis than the PM wrote.**<br>• The saved thesis keeps the 4 metric conditions exactly as the PM stated them (thresholds verified; IDs preserved).<br>• The PM's other stated conditions are lost from structured memory: settlement confirmation, ATM issuance, RPO stabilization, reduced 2027 guidance, close below 68.60 / above 98.59.<br>• `render_prior_thesis` cuts the prior rationale at 300 characters; this run's `thesis_context` shows "Q4 observations  [truncated]" (`thesis.py:397, 457`).<br>• `prepare_thesis` keeps the prior condition's rationale text over the PM's new one (`combined` / `setdefault`, `thesis.py:318-327`). Minor. **[code]** + **[prompt/hand-off]** | Allow non-metric "watch items" (event or filing type plus text) in `thesis_candidate`. Render the full rationale (≤ 3000 characters) in `thesis_context`. Update the rationale on kept conditions. |
| H3 | 5 | Medium | ran | **The publication record does not preserve the PM's reasoning.**<br>• `PR.canonical_decision` = `decision[:12000]` (`memory/publication.py:214`); `decision_truncated: true`. It ends mid-table ("Excluded 2024-06-30: exact quarter-end sh"). Most of those 12 K are the 21 diff lines, the card and valuation tables.<br>• The PM summary and thesis are absent from the record and from the evidence snapshot (grep "bear case wins narrowly" = 0). The snapshot keeps only `thesis.rationale` (a 2-sentence candidate).<br>• Retrospective scoring therefore depends on the per-run folder. **[code]** | Store the PM structured output (summary, thesis, horizon, dispositions) as its own field in the record or snapshot, independent of the 12 K rendered cut. |
| H4 | 4 | Low | ran | `executive_summary.json` (terra-pro): `truncation: true` for all 6 sections. Its 12 sentences agree with state: Underweight, 4–6 months, 39.87 % / 50.15 % / 6 %, 923.6 / 666.6 / 2.955B, $77.73 base excludes leases, risk analysts agree on reduction, "Evidence quality is limited". It drops the audit result, the no-case reason and the condition thresholds, and adds no new caveats. Acceptable. | Optional: add one sentence with the four thresholds. |
| H5 | 4 | Low | ran | **operational_audit.md vs run.log.**<br>• Its headline names only "Sentiment Analyst" fallback; the body lists Sentiment and Trader (both `fallback_recovered` in `operational_observations`).<br>• run.log has 4 WARNINGs: 2 Yahoo news fallbacks (16:25:39, 16:25:44) and 2 structured-output retries (16:25:42, 16:34:00). The 16:25:42 retry is not clearly attributed to any stage.<br>• Every run.log line prints unformatted `%s` with "[arg types: …]", so you cannot tell from the log which stage or ticker failed. **[code]** | List all material findings in the headline. Log a stage name (not a secret) in the redacted format. |
| H6 | 5 | Low | ran | `message_tool.log` has 7 `[Agent]` lines, all analysts plus the Trader (16:34:21). No Bull, Bear, RM, risk, audit or PM output is logged, even though the brief describes it as the chronological transcript. **[code]** | Emit the observed-node outputs, or a pointer, to `message_tool.log`. |
| H7 | 4 | — | ran | Checked and correct: `final_trade_decision.md` equals `FS.final_trade_decision` apart from two "diagnostics.json" wording swaps and the appended document follow-up in decision.md. The complete report includes full per-role risk histories (`4_risk/*.md` ≈ history lengths). The PM thesis paragraphs are complete in both files. | — |

**Sound:** the thesis IDs carry forward correctly with no duplication. The evidence snapshot and thesis are hash-linked from the record. Exports reproduce the state faithfully; nothing was silently altered.

---

## Cross-node

1. **The noise is all rendering; the decision is good.** The risk debate and the PM produced grounded, specific and self-correcting reasoning. Every High/Medium issue here is about what reaches the user and the next run: P1–P3, H1–H3.
2. **Coverage stops partway through the text.** The audit sees the first 6 K of each role (A1), the publication record keeps the first 12 K (H3), and the next run's thesis view keeps the first 300 characters of the rationale (H2). Each cut keeps the head and drops the tail, which is where the converged, final material is.
3. **Earlier same-day runs leak in:**
   - the memory log keeps the pre-Build-D decision (H1)
   - `assumption_changes` diffs against it across a code/prompt version change (P2)
   - `prior_thesis` is the same-day parent c808427e

   Re-runs on the same date need one consistent "latest publication wins" rule.
4. **Risk stage value.** 9 quick-model calls with roughly 100–170 K-character prompts (estimate from component lengths) converged by round 2 (R1). The audit finds the most errors in turn 1. A third round adds little.

## Open questions

- Which stage owns the 16:25:42 structured-output retry? `operational_observations` lists `fallback_recovered` only for Sentiment and Trader, and the redacted run.log has no stage. Is the Sentiment record for the Yahoo news fallback or for the structured retry? Did the News Analyst's Yahoo failure (16:25:44?) go unrecorded?
- Did `post_screen` (TypeSafe Jev) run? Nothing in the artifacts shows it. That depends on whether `TYPESAFE_API_KEY` was set, which I could not check read-only.
- Are the 2 calls missing usage exactly the 2 failed structured attempts? The counts match, but there is no per-call usage record to confirm it.
- Exact risk-prompt sizes: I did not execute `get_instrument_context_from_state`, to stay read-only and avoid replay helpers that might touch vendors. Sizes are estimates from component lengths.
