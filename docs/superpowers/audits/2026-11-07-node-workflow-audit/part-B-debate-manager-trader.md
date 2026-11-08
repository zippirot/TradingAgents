# Node audit Part B: Bull/Bear, Document Followup, Research Manager, Trader

Run: DOCN, 2026-11-07, attempt `162527-34fe1c55`, run id `cfae95e9`, repo commit `8920ffac` (clean apart from untracked docs).

## How this was checked
- **Raw text the nodes actually saw.** The saved final state holds placeholders, not the debate. Every string in `investment_debate_state` reads "Unvalidated debate narrative retained in evidence.json diagnostics." The cause is `enforce_publication` in `output_validation.py:153-163`, which runs after the Portfolio Manager (PM). The real text that downstream nodes consumed is in `unvalidated_outputs.*`. I used it for every check below (`ran`).
- **Turn files.** The six turn files in `partB/turn1..6.txt` were checked against `unvalidated_outputs.investment_debate_state.history`. All six match exactly, and each one also appears in `bull_history` or `bear_history` (`ran`). `current_response` equals `investment_plan`, as `research_manager.py:85` intends.
- **Prompts are reconstructed, not captured.** I rebuilt each node's injected context by calling `get_instrument_context_from_state` from the repo `.venv`, with sockets blocked, on the final state with `unvalidated_outputs` restored. Debater context leaves out `document_followups`, which did not exist yet when they ran. Output files are `partB/recon_ctx_bullbear.txt` (82.5k chars), `recon_ctx_rm.txt` (95.9k) and `recon_ctx_trader.txt` (88.5k).
- **Limits of the rebuild.** `shared_valuation_scenarios` and `event_comparison` come from the final state, which re-runs them on replay. The Research Manager (RM) did not revise any cases, so they should match what the nodes saw. The market, sentiment and news reports in the final state carry a publication banner that the runtime copies did not.
- **No nodes in message_tool.log.** `message_tool.log` contains no Bull, Bear or RM entries. The only node output from this part is the Trader's, at 16:34:21 (line 48). Debate timing cannot be recovered from the logs.

---

## Bull Researcher / Bear Researcher (6 turns; `final_question_turn`, setup.py:226-234)

**Reads:**
- `investment_debate_state.{history, bull_history|bear_history, current_response, count}`
- `market_report`, `sentiment_report`, `news_report` (in full)
- `fundamentals_report`, replaced by "See the accepted evidence brief…" because canonical context exists (context.py:492-497)
- `instrument_context` with `include_mechanical=True` (context.py:386-475). This adds:
  - the shared source brief, including `filing_terms_evidence` (convert terms and uncommenced leases, context.py:242)
  - the valuation reference brief
  - the mechanical valuation context
  - the canonical evidence brief
  - the fundamentals analyst prose: 3,542 chars, under the 6,000 cap, so not truncated
  - event comparison, `thesis_context`, shared valuation scenarios
- `decision_context` is **not** an input, and could not be. It is created only at publication (output_validation.py:228).

**Instruction summary:**
- Advocate for one side, accept or dispute the shared valuation cases, and engage the opponent's last argument.
- Follow `EVIDENCE_DISCIPLINE`, including "address unresolved assumptions … instead of repeating accepted facts".
- On the final turn only (count ≥ 4 for bull, ≥ 5 for bear), append a `document_questions` fence.

**Do the six turns differ?** Yes, substantively (`ran`).
- 8-word-gram overlap with all earlier turns is 0.0%, 0.1%, 0.1%, 1.0%, 1.0% and 4.1%.
- Turns shrink from about 1,900 words to about 1,400–1,600.
- Distinct figures cited per turn fall from 127 to 58–66. Later turns narrow onto the disputes still open (the 5.0× multiple, lease perimeter, margin trigger, ATM) instead of restating round 1.
- **Answered well (turn 6, bear, on bull turn 5).** Turn 6 §3, "You moved your margin trigger", quotes the bull's change of position: "holding at 50.15% now counts as 'evidence of absorption'". It then restores the jointly set ≥55.5% / <50.15% triggers.
- **Point left unanswered (bull turn 5, on bear turn 4).** Bear turn 4 §6, "The risk was known at 16.31×", argues the vendor $67.27–77.36 sensitivity only brackets the close. Bull turn 5 has no reply. Neither "16.31" nor "known" appears in turn 5.

**Findings**

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| BB1 | 1 | Medium | ran | The debaters saw only the June→September RPO change: "893,828,000 → 799,707,000 … -10.53%" (recon_ctx_bullbear.txt:462). None of the RPO history was in their context: $134.1M at 2025-12-31 (10-K block-1084), the Q2 jump to $893.8M, and $61M in Q3 2025 (8-K block-24). The corpus has all three (`document_sources.corpus.documents[0,1,6]`). As a result, "RPO fell 10.53%" became a bear point (turn 2:42, turn 6:27) and then a reconsideration trigger in every later node, without the base effect of a large Q2 contract being recognised. **This is an evidence-assembly (upstream) defect.** | Evidence gate / shared brief: when an RPO change is emitted, include the prior-year and year-end RPO values and the next-12-months portion (Q3 10-Q block-148: $345.1M). |
| BB2 | 2 | Low | ran | The document-question instruction gives a keyword example ("lease commitments not yet commenced") but asks for "questions". Both sides wrote full natural-language questions, and bull-1 and bear-1 ask nearly the same RPO question. There is no dedupe across roles (document_questions.py:68-89 dedupes within a role only), so one of the four lookup slots was spent twice. | Ask for "short filing search phrases (3–6 key words)" and dedupe across roles before lookup. |
| BB3 | 1 | Low | ran | 14,820 of the 82,298 context chars (18%) are 40–64-char hex source and fact hashes, repeated in all six debate calls and again in the RM, Trader, 9 risk turns and PM. | Drop the hashes from the prompt view and keep short IDs (F12, S54), which the agents already cite. |
| BB4 | 4 | Low | ran | Engagement gaps: (a) bull turn 5 never answers bear turn 4 §6; (b) bull turn 5 §4 quietly redefines its own margin trigger. The bear caught (b); nothing caught (a). | Add to the prompt: "List the opponent's numbered points from the last turn and answer each or concede it." |

**Spot-checked claims (all grounded, `ran`):**

| Claim | Source in context |
|---|---|
| $73.22 history-median sensitivity | recon_ctx:164,184 |
| $1.9328B floor | `1932800000.00` |
| C12 $149.0M | 149022000 at line 309 |
| $2.955B uncommenced leases | 2955158 thousand in filing terms |
| 117.92M / 91.95M shares | present in context |
| ≤5.14× / ≤4.32× | present in context |
| Polymarket 2% contract | news report |

**Sound:** a real debate. Each turn engages the previous one, concessions are explicit, accepted vs disputed scenario inputs are tabulated, and the figures trace to the canonical or mechanical context.

---

## Document Followup (`lookup_document_questions`, document_questions.py:201-253)

**Reads:**
- `investment_debate_state.document_questions` (bull and bear: 2 questions each, status `ready`, none rejected)
- `document_sources` (validated corpus with 8 filings), `transcript_sources.record_hash`

**Instruction summary:** No model call. One deterministic `search_filing_evidence` pass per question, at most 3 passages and 12k chars each. The result is sealed with a hash and written to `document_followups`.

**What the lookup returned (`ran`, `partB/document_followups.json`):**

| Q | Query (short) | Returned | Answers it? |
|---|---|---|---|
| bull-1 | cause of RPO decline | 3 finance-lease maturity / weighted-term tables (Q3 10-Q block-226, Q2 block-221, Q3 block-223) | **No.** Irrelevant |
| bull-2 | undrawn revolver / equipment capacity | the same lease table twice plus block-200: "available borrowing capacity under the Revolving Facility was $396,916" | Partly (revolver yes, equipment financing no) |
| bear-1 | RPO decline reason and next-12-month portion | 8-K block-24 ("$800 million, of which $345 million … next 12 months. RPO was $61 million in the third quarter of 2025"), Q2 10-Q block-149, FY25 10-K block-1084 | Partly: wrong period. The Q3 10-Q RPO note (block-148: $799,707k; $345,111k in 12 months) exists but was not returned |
| bear-2 | year-by-year schedule for finance leases and uncommenced leases | finance-lease maturities (block-226), weighted terms (block-223, Q2 block-218) | Half. The uncommenced-lease block (Q3 block-218: $2,955,158k) was not returned |

**Findings**

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| DF1 | 3 | Medium | ran | **Retrieval ranks the wrong blocks for question-shaped queries. Reproduced offline:** replaying `search_filing_evidence` on the retained corpus returns exactly the recorded passages. Root cause: bag-of-words scoring (filing_search.py:122-131) counts date and filler tokens. bull-1's 15 terms include `june, 30, september, 30, 2026, does, say, from`; the lease table's section heading hits 5 of them, while the RPO note scores 0 heading hits and 7 of 15 in the body. The keyword query "remaining performance obligations next 12 months" ranks Q3 block-148 first. "leases not yet commenced" ranks Q3 block-218 first. **Code defect.** | Before scoring, remove question and date filler (does, say, what, cause, from, month names, years). Prefer the latest-period filing when the phrase appears. Weight full-phrase body matches above heading hits. Keep BB2 (keyword phrasing) as a complement. |
| DF2 | 4/5 | Medium | ran | `status: "found"` means "at least one passage scored", not "answered". All four results say `found`. The user-facing `5_portfolio/decision.md:351-354` prints "3 passage(s): source passages retrieved" for each, including bull-1, whose three passages are unrelated lease tables. **Code/report defect.** | Add a relevance gate (all phrase words present in the body), or label results "passages returned; relevance not checked". Count a block repeated across results once (block-226 appears in 3 of the 4 results). |
| DF3 | 5 | Low | ran | The follow-up context appended to every later prompt is 13.4k chars (recon_ctx_rm.txt, from "UNTRUSTED RETRIEVED" on). It goes to the RM, Trader, 9 risk turns and PM, and about half of it is the same irrelevant lease table repeated. | Dedupe passages across questions. Drop passages that fail the DF2 relevance check. |

**Sound:** deterministic, sealed and replay-verified, and it carries an explicit untrusted-source label. The revolver passage reached the Trader ("Undrawn revolver capacity was $396.9M"), and that figure exists nowhere else upstream (`ran`: only in `document_followups`).

---

## Research Manager (research_manager.py; deep model; structured `ResearchPlan` succeeded, no fallback)

**Reads:**
- `investment_debate_state.history`: the full 62k-char interleaved debate, not a summary
- `instrument_context` with mechanical context: everything the debaters had, **plus** `document_followup_context`
- `shared_valuation_scenarios` via `replay_cases`
- **Not read:** market, sentiment or news reports. These arrive only through the debate (by design).

**Instruction summary:**
- Judge which side is stronger. Hold only if the case is balanced or thin.
- Optionally revise the cases in `revised_cases`, and do not promote a scenario into a target.
- Output Recommendation, Rationale, and Strategic Actions (no numeric sizing).
- **There is no instruction to address the document follow-up results.**

**Output:** "**Recommendation**: Underweight". Rationale: the "bear case wins narrowly on the per-share cost and execution risks". No case revision.

**Balance:** The plan states the bull's strongest facts (39.87% growth, 60%+ 2027 guidance, cash and securities, $149.0M enumerated cash flow). It also adopts the bull's turn-5 method point verbatim in substance: "it is not valid to assert a specific lower valuation merely by deducting leases while holding the multiple fixed". On the bear side it takes the gross margin, the 6% adjusted operating income, obligations, the ATM and RPO. The framing ("per-share cost") is the bear's, but both sides are represented. It omits the bull's −$204.5M net-borrowings point (C3).

**Numbers checked (`ran`):** all present upstream:
- 39.87%, 50.15%, 6%, $149.0M, $923.6M, $666.6M, $2.955B, $72.48 (Nov 6), $73.22, $1.9328B, $312.3M (Dec 1), 10.53%
- both SEC URLs (seven and two occurrences in the RM context)
- the AI Customer ARR definition (recon_ctx_rm:475)

No invented figures.

**Findings**

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| RM1 | 2/5 | Medium | ran | **The follow-up passages were in the RM's context and went unused.** The RM wrote: "RPO fell 10.53% quarter over quarter, but its cause is unavailable in the retained evidence and the decline alone does not establish weak demand." It never mentions the bear-1 passage: $345M due in 12 months, and RPO of $61M in Q3 2025, i.e. roughly a 13× rise year on year. It also never mentions the bull-2 revolver capacity of $396.9M. It does reflect the gaps: "complete equipment-financing capacity schedule … unavailable" and "Seek a sourced schedule … for uncommenced leases". So it read the follow-up but kept only the absences. The debate's one-sided RPO framing passed into the plan and then to the PM, whose final text repeats "RPO fell 10.53% sequentially, but its cause … unestablished". **Prompt defect.** | Add a required RM section, "Document follow-up: for each question, what the returned source text establishes, contradicts, or leaves open". Do the same in the PM prompt. |
| RM2 | 1 | Low | read | The prior thesis (rating Underweight) is in the RM's context through `thesis_context`, and the RM again chose Underweight. Anchoring cannot be shown from one run (see Open questions). The rationale field shown is cut at 300 chars (thesis.py:459, `_display` limit 300; the stored rationale is 365 chars), losing "…are not yet available; advisory conditions do not enforce trades." | Raise the `_display` limit for the rationale to about 600, or render it whole (365 chars). |

**Sound:** grounded, hedged correctly (dated close, intent vs completion, authorization vs issuance), and it keeps the debate's agreed triggers (55.5% / 50.15% / $348M) as non-binding conditions.

---

## Trader (trader.py; quick model; structured `TraderProposal` failed, free-text fallback used)

**Reads:**
- `investment_plan` (raw 4.3k chars, in full)
- `market_report` (in full)
- `portfolio_context` ("not provided")
- `instrument_context` **without** mechanical context, so the $73.22 sensitivity appears only through the RM plan. It does include canonical evidence, the valuation reference, event comparison, the prior thesis, scenarios and the document follow-up.

**Instruction summary:**
- Output Buy, Hold or Sell. Underweight maps to Sell.
- Ground levels in the market report.
- For Sell: a reference sale level and an advisory invalidation level, but no stop and no short.
- Give sizing only when it can be supported.

**What it adds beyond the RM plan (`ran`):**
- **Technical levels:** reference sale level 84.02, the 11-04 close (market_report:37,108); invalidation level 98.59, the 20 SMA (market_report:52); breakdown 68.60 and 69.78–69.85, the lower band and lows (market_report:89,161); next references 62–58 and 52.26.
- **Execution pacing:** spread the reduction over several trades into strength, because ATR is about 13% of price.
- **Revolver figure:** $396.9M, from the document follow-up only.

**Valuation check:** 7.75× equity/trailing revenue against a 4.47× own-history median matches `valuation_reference_brief:26,28`. Shares 117.92M vs 91.95M and the $130.5M year-end finance-lease figure are both in context. "Down about 60% from 181.29": 72.48 / 181.29 = 0.40, so correct. Everything is consistent with the evidence.

**Effect of the structured-output fallback (`ran`):**
- `invoke_structured_or_freetext` (structured.py:99-114) re-sent the same prompt as free text. That cost one extra quick-model call (16:34:00 failure → 16:34:21 output).
- The free-text output is *richer* than the schema would have produced: the schema caps reasoning at 2–4 sentences.
- **Lost:** the `FINAL TRANSACTION PROPOSAL: **SELL**` line, and the schema-rendered disclaimer sentence (schemas.py:261-265). The free text carries its own wording instead: "advisory reference only … not an order, a quote, or a share quantity".
- **Not lost:** the only machine consumer, `decision_context._trader` (decision_context.py:202-209), parsed `**Action**: Sell`. The state records `decision_context.trader_provisional = "Sell"`. No downstream code reads the typed `reference_sale_level` or `advisory_invalidation_level`.
- **Cause unknown.** `cli/run_logging.py:29` redacts every log argument, including the agent name and the exception class name. run.log shows only "%s: structured-output invocation failed (%s)". The quick model also failed the same way for the Sentiment Analyst at 16:25:42.

**Findings**

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| TR1 | 5 | Medium | read+ran | **The risk debaters never receive `investment_plan`.** aggressive, conservative and neutral `_debator.py:28-31` read only `trader_investment_plan`, and the aggressive analyst is told to "create a compelling case for the trader's decision" ("Sell"). Several RM conditions are absent from the trader text, so the 9 risk turns never saw them: "A margin between 50.15% and 55.5% is inconclusive", "improving adjusted operating-income growth", and "Seek a sourced schedule and appropriate present-value treatment for uncommenced leases". The 5-tier meaning ("Underweight, not exit") survived only because the Trader wrote "not a full exit". The risk histories never say "full exit" (`ran`), so there was no harm this run. **Hand-off defect.** | Pass `investment_plan` (or its Recommendation and conditions block) to the risk debaters alongside the trader proposal, and show the RM rating next to the mapped Buy/Hold/Sell. |
| TR2 | 3 | Low | ran | The structured failure cause is unobservable (see above). **Code defect** (logging). | Allow agent name and exception class through the run-log redaction. Both are non-sensitive. |
| TR3 | 4 | Low | ran | The Trader merged the separate 84.02 level and the 86.3–90.5 zone (market_report:162) into an "84–90.5 resistance band". Downstream, the PM attributes "$78.50 and $84.02–$90.50 sale areas" to the trader. The 78.4–78.5 rung came from the risk debaters (unv_rds_history:67,77,94), not the Trader. | PM prompt: attribute levels to their source role. Trader: keep level lists exactly as the market report gives them. |

**Sound:** a correct, well-grounded conversion of the RM plan into dated, labelled technical references with no invented valuation. The fallback was harmless to the decision.

---

## Export comparison (2_research, 3_trading vs raw state)

`ran`. Each comparison checks that the raw string is contained in the exported file.

| Export | Raw contained? | Added | Stripped |
|---|---|---|---|
| `2_research/bull.md`, `bear.md` | yes, in full | a 277-char "Unvalidated model research" header | nothing. The raw ```` ```document_questions ```` fence is shown to the reader as-is |
| `2_research/manager.md` (20.1k) | yes (the 4.3k raw plan) | about 15.8k of canonical evidence before it (an F-list of facts); the recommendation sits at line 114 | nothing |
| `3_trading/trader.md` | yes, in full | the canonical sizing/levels disclaimer plus the header (587 chars) | nothing |

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| EX1 | 5 | Low | ran | The placeholder text in state and the canonical investment plan say narrative is "retained in evidence.json diagnostics" (output_validation.py:147,161). evidence.json has **0** occurrences of the debate text, while diagnostics.json has 2. The exports themselves correctly say "diagnostics.json". | Change the two strings to "diagnostics.json". |
| EX2 | 5 | Low | ran | manager.md puts the RM's recommendation and rationale after about 108 lines of fact rows. The interleaved debate (`history`) is not exported; only the per-side files are. | Put the model plan first (labelled unvalidated), then the evidence. Optionally export the interleaved history. Remove the question fence from the reader view. |

---

## Cross-node

1. **RPO framing came from incomplete evidence, and the one fix was ignored (BB1 → DF1 → RM1).**
   - The debaters saw only the quarter-on-quarter decline.
   - The follow-up search (DF1) returned the wrong-period RPO note.
   - It did return the 8-K line with the year-on-year base ($61M → $800M) and the $345M due in 12 months, but the RM and PM never used it.
   - Result: "RPO decline, cause unknown" is a reconsideration trigger in the RM, Trader and PM outputs. The bear-favourable framing reached the decision text without the base effect that was sitting in the retained corpus.
   - The risk debaters, who had the follow-up in context, did cite $345M (6 hits in unv_rds_history). The information was usable.
   - **Plan split.** DF1 and BB1 are code defects for the gap-closure plan. RM1 and DF2's prompt side go to the node-workflow plan.
2. **Context bloat repeats in every call.** About 82–96k chars of instrument context are re-sent in 6 debate calls, the RM, the Trader, 9 risk turns and the PM. Within that, 18% is hex hashes (BB3) and about 13k is follow-up text with roughly half duplicated (DF3). There is no evidence it hurt quality, but it is the largest token cost in this part (2.31M input tokens for the run).
3. **The 5-tier to 3-tier label mapping is lossy at the Trader → risk hand-off (TR1).** The PM receives both the RM plan and the trader proposal, so the final rating stays Underweight, consistent with the RM.
4. **Observability.** message_tool.log captures no debate or RM output. run.log redacts the agent name and exception class. Together they make per-node timing and failure diagnosis impossible from the logs alone.

**Plan split summary:**
- **Code defects (gap-closure plan):** DF1, DF2, TR2, EX1, BB1 (evidence assembly), RM2 (rationale display limit).
- **Prompt / instruction / hand-off (node-workflow plan):** RM1, TR1, BB2, BB4, TR3, DF3, BB3, EX2.

## Open questions
- **Why the Trader's structured call failed.** The reason is redacted. Possibilities include a provider tool-call refusal, a `parsing_error`, or `parsed=None`. It cannot be determined read-only, and the same quick model also failed for the Sentiment Analyst.
- **Prior-thesis anchoring.** Whether the prior Underweight in `thesis_context` anchors the RM's Underweight needs an A/B run with `thesis_context` withheld.
- **Shared-state assumptions in the rebuild.** The reconstructed contexts assume the final-state `shared_valuation_scenarios` and `event_comparison` equal what the nodes saw (no revision recorded). The exact runtime prompt bytes are not captured.
- **Whether the filings give a cause for the RPO decline at all.** `ran`: a regex over every RPO-mentioning block of the Q3 8-K and 10-Q finds no stated cause, so the RM's "cause unavailable" is accurate. Two caveats:
  - 8-K block-98 says RPO "is not necessarily indicative of future revenue growth".
  - 8-K block-36 says prior periods were recast to include all contracts.

  Both are context the debate never saw. A full MD&A read was not done.
