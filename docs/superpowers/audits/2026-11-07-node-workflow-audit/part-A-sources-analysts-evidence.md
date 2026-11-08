# Node workflow audit, Part A: Source Acquisition through Evidence Check

Run: DOCN, analysis date 2026-11-07 (a Saturday; last completed session 2026-11-06). Attempt `162527-34fe1c55`, repo at 8920ffac.
Abbreviations: MTL = `message_tool.log` (line numbers), STATE = `full_states_log_2026-11-07_cfae95e9.json`, EV = `tradingagents/agents/evidence_validation.py`, CTX = `tradingagents/agents/context.py`.
Prompts were not captured. Every Q2 conclusion rests on reconstructing the prompt from source plus the state values it formats in. The analyst outputs themselves were captured (MTL 44–47).

Type tags: **[code]** = goes in the existing gap-closure plan. **[node]** = prompt, instruction or hand-off issue for a new node-workflow plan.

## Tool-call ledger (ran)

There were 24 calls: Market 8, News 9, Fundamentals 7. Sentiment makes no tool calls; it pre-fetches 3 sources. All 24 returns reached their models: the `audit_*_tool_evidence` records show `status: success` for each one, and `all_tools_failed=False`.

Only 13 returns appear as `[Data]` lines in MTL. The 11 missing are:
- all 9 News returns (MTL 18–23, 26–28);
- 2 Fundamentals `search_documents` returns (MTL 24–25).

Root cause, reproduced (see the Cross-node section): any tool round that includes `search_documents` writes to `messages` more than once. `search_documents` returns a `Command`, and LangGraph's task stream folds multiple writes into `{"$writes": [...]}`. `stream_run` (`trading_graph.py:790-795`) then iterates that dict as if it were a message list, so nothing is logged. A round with only one `search_documents` call (MTL 42→43) logs normally. The earlier pre-Build-D run today has the same defect (24 calls, 14 Data).

---

## Source Acquisition
**Reads:** `company_of_interest`, `trade_date`, `asset_type`, `evidence_acquisition` (resume guard), config. **Writes:** `evidence_acquisition`, `issuer_identity`, `filing_evidence`, `financial_evidence`, `document_sources`, `filing_terms_evidence`, `transcript_sources`, `valuation_reference(_brief)`, `price_observation`, `shared_source_brief` (EV:303-412).
**Instruction:** No model. It fetches one SEC/price vintage, runs source-only checks, and builds an 18k-character brief for every analyst (CTX:210).

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| SA1 | 1/5 | Medium [node] | ran | The brief leaves out the $1.0B ATM, even though its source (8-K `docn-20261103.htm` block-31, item 8.01) is already in `filing_evidence` before the analysts run (STATE `filing_evidence.documents[2]` contains "equity distribution"). The financing record is only built later, at Evidence Check (`issuer_event_evidence.financing_records`). Result: Sentiment, which has no search tool, calls the offering "not in the retained filing brief … not verified here" (sentiment_report §1), although it is a filed fact. | Run `issuer_supplement`'s financing extraction during acquisition and render `financing_text` into `build_shared_source_brief`. |
| SA2 | 1 | Medium [code] | ran | Document text limits removed press-release outlook blocks 42, 43, 47 and 49, keeping 41/44/45/46/48/50 (STATE `filing_evidence`, doc `50c5…`; gap "Document text limit reached" on all 3 accessions). The contiguity validator then rejects the outlook rows that sit between the gaps: deterministic rejects at block-24/44/48/50, "missing or reordered source blocks in period scope". Lost from accepted evidence: FY2026 adjusted FCF margin of 20–22%, Q4 and FY diluted share guidance (128–129M; 122–123M), and RPO $800M / $345M recognised over the next 12 months. The brief's own priority rule wants that share guidance (CTX `disclosure_priority`=2), but none is present. | Keep every block within a retained outlook heading's span intact when trimming documents (trim whole sections, not lines inside a section). |
| SA3 | 4 | Low [code] | read | Brief line: "Canonical completed price: 72.4800033569336 USD" (float noise in a prompt). | Format the price to source precision. |

**Sound:** One pinned vintage feeds every analyst. Filing terms (2026 notes: $312.3M principal, $178.51 conversion price, 12-01 maturity; $2.955B uncommenced leases) and the RPO comparison are in the brief. Every source has an ID and filing date.

## Memory Log
**Reads:** `analysis_clock`/`trade_date`, `company_of_interest`, the memory log, publications (`trading_graph.py:545-628`). It runs in parallel with the analysts (`setup.py:279-287`). **Writes:** `past_context`, `memory_note`, `outcome_summary`, `prior_thesis`, `thesis_context` (legacy only).
**Instruction:** No model in the read path; settlement reflections may call one. It loads past decisions, outcome horizons and the latest prior thesis.

Produced in this run:
- `prior_thesis` is version c808427e, from the 16:10 same-day pre-Build-D run (Underweight), with 4 conditions. All 4 are for the Q4 2026 period (2026-10-01..12-31).
- `outcome_summary`: D1–D3 Underweight, all horizons pending.
- `thesis_context` was rendered at Evidence Check, not by the memory node (`setup.py:294-298`). Every condition is "unknown", which is correct because Q4 has not been reported.

**Where it goes:** It never reaches the analysts, because it runs in parallel. `thesis_context` reaches Bull and Bear onward through `get_instrument_context_from_state` (CTX:441). `past_context` reaches only the Portfolio Manager (`portfolio_manager.py:72`, `state.py:129`).

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| ML1 | 5 | Medium [node] | read | Lessons such as the 10-19 reflection "weigh oversold rebound risk more explicitly when sizing an underweight after a steep decline" (`trading_memory.md:31`) go only to the PM. That lesson bears directly on today's Market report (RSI 27, riding the lower band) and on the Bull/Bear and risk debate, which never see it. | Give a short lessons digest to Research Manager and the risk debaters, or state explicitly that lessons are PM-only by design. |
| ML2 | 5 | Low [code] | ran | `past_context` and `memory_note` are not saved in the full-state log (field list at `trading_graph.py:835`), so what the PM was shown cannot be audited. | Add both to `_log_state`. |
| ML3 | 4 | Low [code] | ran | `thesis_context` is HTML-escaped inside an LLM prompt ("&lt; 348000000", "&gt;= 55.5"; `memory/thesis.py:405`), and the memory log stores "&#x27;". For the gross-margin conditions the observation reason reads "Gross Margin inputs missing or competing" (`thesis.py:170`), when the real reason is that Q4 has not been reported. | Escape only for HTML export. Report "period not yet reported" when the period end is after the cutoff. |

**Sound:** The cutoff is respected (end of day 2026-11-07 Denver). Observations are correctly "unknown" for an unreported quarter. The prior is labelled advisory and non-binding.

## Market Analyst
**Reads:** `trade_date`, `instrument_context` + `shared_source_brief` + `valuation_reference_brief` (CTX:401-412), `messages` (private). **Writes:** `market_report`, `audit_market_tool_evidence`.
**Instruction:** Pick up to 8 non-redundant indicators. Call `get_stock_data`, then `get_indicators`, then the verified snapshot, and treat the snapshot as the source of truth. Name the completed session. Write a detailed report ending with a table.
**Tools (8):** `get_stock_data` 2026-03-01→11-07 (175 rows, completed session 11-06); snapshot (30-day look-back); `get_indicators` rsi/macdh (40 days), vwma/200sma/atr (30 days), boll_lb (20 days). All windows end at 11-07, and the vendor dropped the Saturday row correctly. All 8 returns were logged (MTL 16–17, 36–41).

Claim checks against tool returns (ran), all match:
- close 72.48, open 78.40, low 69.78 (snapshot);
- 10-14 close 109.29 on 4.57M shares;
- 05-05 move 108.81→152.77 on 14.95M shares; 06-15 close 181.29; 06-17 high 187.50;
- macdh 10-06 −0.458, 10-19 −4.42, 10-29 −0.77, 10-23 −3.85 ("most negative since 10-23" is correct);
- RSI 10-22 29.6, 10-27 43.4, 11-05 25.5;
- VWMA 10-08 138.40; boll_lb 10-19 101.30, 11-05 70.22.

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| — | — | — | — | No defects found. | — |

**Sound:** Fully grounded. It flags Saturday as having no bar, cites brief facts (RPO −10.53%, guidance) without assigning cause, and avoids claiming a death cross it cannot see.

## Sentiment Analyst
**Reads:** `company_of_interest`, `trade_date`, instrument context + brief + valuation brief. It pre-fetches `get_news.func` (10-31..11-07), StockTwits (30), and Reddit (3 subreddits). **Writes:** `sentiment_report`, `audit_social_tool_evidence`.
**Instruction:** Produce a structured SentimentReport (band, score, confidence, narrative) from the three blocks, with no tools. Social numbers match a retained fact only when metric, period and unit all agree.

**Fallback (ran):** The 16:25:42 warning is Sentiment's structured call (the only structured analyst; the node ran 16:25:28–16:26:29). This matches `operational_observations.43593cfc…` (stage Sentiment Analyst, `fallback_recovered`). The 16:34:00 warning is the Trader (`01c6c70d…`; Trader output at 16:34:21), which belongs to Part B.

What was lost: the free-text header reads "**overall_band:** Mixed / **overall_score:** 4.5 / 10 / **confidence:** low" instead of `render_sentiment_report`'s "**Overall Sentiment:** **Mixed** (Score: 4.5/10)". All three values are present and valid, and nothing downstream parses the header (grep shows no consumer), so there is no decision impact.

Claim checks (ran): StockTwits 8 Bullish / 3 Bearish / 19 unlabelled of 30, which matches. Reddit: one r/stocks post dated 11-04, which matches. "19 headlines, no bodies" matches. RPO 893.8→799.7 (−10.53%) matches the brief.

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| SE1 | 1/4 | Medium [node] | ran | It treats the filed $1B ATM as unverified media talk, because the brief omits it (see SA1). | Fixed by SA1. |
| SE2 | 3 | Medium [code] | ran | The news block is 19 bare headlines with no dates and no summaries. The Yahoo quote feed failed (run.log 16:25:39), the search fallback returns flat articles with no summary, and `_format_articles` (`yahoo/news.py:83`) never prints `pub_date`, even though it filters on that date. Pre-earnings items ("What to expect…") cannot be dated by the model. The same block is fed to News. | Print `pub_date` (and the publisher timestamp) in `_format_articles`. Mark search-fallback output as headline-only in coverage. |
| SE3 | 4 | Low [node] | read | "Got out above $150 … not supported by the retained price data". Closes above $150 did occur (05-05 to June). Sentiment simply has no price history. | Have Sentiment say "not checkable with my inputs" rather than "not supported". |
| SE4 | 3 | Low [code] | ran | run.log hides which node failed and why: `_SafeRunFormatter` (`cli/run_logging.py:25-29`) strips every argument, including the app-owned agent name and exception class (`structured.py:92-95`). | Put agent name and exception class into the template text, or allowlist those arguments. |

**Sound:** Honest about thin data (confidence low). Checks social numbers against facts with correct unit and period discipline. Notes that all bearish tags come from a single account.

## News Analyst
**Reads:** `trade_date`, `asset_type`, instrument context + brief + valuation brief + `transcript_analyst_context`, `messages`. **Writes:** `news_report`, `news_coverage`, `audit_news_tool_evidence`, `document_search_trace`.
**Instruction:** Past-week company news and macro news, with a dated FRED macro section. The brief counts as issuer disclosure, not independent news. Use `search_documents` for retained filings. End with a table.
**Tools (9):**
- `get_news` 10-31..11-07;
- `get_global_news` (7 days, 10 items);
- FRED 10y (90 days), fed funds (180 days), CPI (200 days);
- Polymarket;
- `search_documents` ×3 (the cap).

Windows are correct for 11-07. None of the 9 returns is in MTL (ledger above), but all are in `audit_news_tool_evidence`.

Claim checks (ran, against the audit excerpts), all match:
- 10y 4.84% on 11-05, peak 5.31% on 10-05, 4.72% on 08-10;
- fed funds 3.63→3.75→3.88;
- CPI 336.298 vs 334.131 (+0.65%);
- Polymarket December cut 2% on $459K volume.

ATM and notes facts match the filing terms and the search hits.

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| NE1 | 3 | Medium [code] | ran | All 9 tool returns are missing from MTL (ledger root cause). The user-facing log cannot show what News read. | See CN1. |
| NE2 | 3 | Low [code] | ran | `get_global_news` returned off-topic items (an IBM inheritance tax article, mining earnings calls). `news_coverage.independent_news` says "available, 0 failed" even though the quote feed failed and the result was headline-only. | Add a `degraded: search_fallback, headlines_only` status to coverage. |

**Sound:** Separates issuer statements from independent coverage, states its headline-only limits, uses dated macro data, finds the ATM on its own, and handles the vendor transcript as unverified.

## Fundamentals Analyst
**Reads:** `trade_date`, instrument context + brief + valuation brief + transcript context, `messages`. **Writes:** `fundamentals_report` (the model text), `disclosure_evidence` (from `_disclosures`), `audit_fundamentals_tool_evidence`, `document_search_trace`.
**Instruction:** Four named JSON fences (`valuation_scenarios`, `peers`, `financial_claims`, `disclosures`), then about 500 words of prose and a table. Roughly 60 detailed extraction rules apply (`fundamentals_analyst.py:90-217`).
**Tools (7):** `get_financial_evidence`, `get_filing_evidence`, `get_cashflow`, `get_insider_transactions`, and `search_documents` ×3. MTL logs 5 of the 7 returns (lines 24–25 missing). `get_balance_sheet`, `get_income_statement` and `get_fundamentals` were not called; this is acceptable because the evidence tool covers them.

**Output vs final (ran):**
- The model's [Agent] output (MTL 47, 18.6k characters) contains 2 valuation cases, 3 peers (AKAM, NET, CRWV), 24 financial claims, 9 disclosures and 3,542 characters of prose.
- The final `fundamentals_report` (15.4k) is entirely Evidence Check's `canonical_financial_context`, with the reference appendix removed (EV:805). None of the model's prose is in it.
- The prose survives in `financial_claim_validation.raw_report`. It reaches later roles as "Analyst research — unvalidated" (CTX:417-435) and reaches the user as "### Unvalidated model research" (`reporting.py:340`).
- The **6000-character prose passthrough is still present** (CTX:427/433). It did not truncate here (3,542 < 6,000, ran).
- What validation appended: evidence-coverage warnings, the RPO comparison, financing authorisation text, filing terms, source coverage.
- Outcomes: claims passed (24/24 fact IDs); both valuation cases are "supported" (targets $77.73 and $44.67); peers adopted; **model disclosures 0 of 9 accepted**.

Claim checks (ran), all match canonical facts: TTM revenue 1,102.7M; Q3 revenue 321.2M; operating income 33.0M; net loss 42.6M; finance lease + equipment 923.6M; cash 666.1M; shares 117.92M; follow-on 887.9M; RPO 799.7M.

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| FA1 | 3/5 | Medium [code] (would be High on a run where deterministic discovery misses) | ran | 6 of the 9 model disclosure records were rejected as "context needs one unique source document" (`dataflows/disclosure_context.py:161-162`). The cause: press-release doc `50c5…` appears both in `filing_evidence` and in a `search_documents` package, and both are passed as `quote_packages` (EV:481; STATE `disclosure_evidence.packages[0]` and `[1]` both contain it). Valid, locator-correct records were rejected, including FY2026 adjusted FCF margin of 20–22%, which nothing else captured (see SA2). This also inflates the "13 rejections" behind the "limited" status. | De-duplicate documents by `(source_id, content_hash)` before matching, and accept identical duplicates. The same applies in `_disclosures` (`fundamentals_analyst.py:108-133`). |
| FA2 | 2/4 | Medium [node] | ran | Both valuation cases use `multiple_basis: borrowings_only` with net cash of −$450M/−$300M. They ignore $923.6M of finance-lease/equipment obligations and $666.6M of operating leases, for a GPU lessee whose main funding is leases. The prompt asks for labelled sensitivities with finance_equipment and operating_leases, but `scenario_results` is empty, so that instruction was ignored and nothing checks it. The $77.73 base target therefore sits on the most favourable debt perimeter. | Require (or compute automatically) a finance_equipment sensitivity whenever finance-lease obligations exceed a threshold share of EV. |
| FA3 | 2 | Low [node] | read | Records 6–8 were rejected correctly: gross margin mislabelled as "Gross profit %"; revolver unit "thousand" not present in the quote; ATM association. The rule set is about 60 clauses long and the model still made 3 schema errors. | Trim the disclosure rules to the validated subset and give one worked example per record type. |

**Sound:** Strong source discipline. Every financial claim matched, the scenarios are well reasoned with stated dilution assumptions, the brief and filing terms were used, and guidance is kept apart from results.

## Evidence Check
**Reads:** `evidence_acquisition`, `filing_evidence`, `issuer_identity`, `fundamentals_report` (model), `document_search_trace` packages, `news_coverage`, `prior_thesis`, `filing_terms_evidence`. **Writes:** `evidence_quality`, `financial_*`, `canonical_financial_context`, `fundamentals_report` (overwritten), `disclosure_evidence`, `issuer_event_evidence`, `prior_thesis.observations`, `thesis_context`, `valuation_reference`, `event_comparison`, `shared_valuation_scenarios` (EV:415-456, 458-807; `setup.py:290-306`).
**Instruction:** Deterministic. Validate the model's claims and disclosures against the pinned vintage, aggregate the checks, then build peers, event comparison and valuation.

**"limited", explained (ran):** Every required check passed. "limited" comes only from the 6 optional warnings (EV:207-240):
- EPS bridge ×2: "needs source precision";
- disclosure extraction: 13 rejections = 9 model + 4 deterministic;
- "Document text limit reached" ×3.

So the reason is partly right and partly an artefact. 6 of the 9 model rejections are the FA1 duplicate-package bug, and all 4 deterministic rejections are the SA2 trimming gaps.

**What "limited" changes downstream:** nothing in behaviour. Every consumer accepts `{"sufficient","limited"}` alike: `setup.py:296`, `shared_valuation.py:61`, `mechanical_context.py:16/25`, `event_comparison.py:357`, `output_validation.py:70`. Its only effects are the warning lines appended to `canonical_financial_context`, which every downstream prompt sees, and the label shown in the report.

| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| EC1 | 4 | Medium [code] | ran | The status is partly driven by false rejections (FA1, SA2). The warning list repeats the EPS line twice (STATE `evidence_quality.warnings[0..1]`). | Fix FA1 and SA2. De-duplicate warning messages. Split "model submission rejected" from "source coverage gap" in the message. |
| EC2 | 5 | Low [node] | read | "limited" carries no downstream meaning that a reader can act on. | Either document that it is informational only, or have downstream prompts name which optional evidence is missing (for example, guided diluted shares). |
| EC3 | 5 | Low [code] | ran | ATM financing record: "up to 1000000000.0 source $; denomination unknown" (`issuer_event_evidence.financing_text`), even though the quote states "$1.0 billion". | Map a "$" source unit to USD for US filers. |

**Sound:** No REVIEW false-positive. Required checks are sound (balance sheet, equity movement, cash-flow perimeter, RPO comparison). The thesis observations are correct for an unreported period. Valuation rows trace to fact IDs.

---

## Cross-node
| # | Q | Sev | ran/read | Evidence | Fix |
|---|---|---|---|---|---|
| CN1 | 3 | Medium [code] | ran | Missing `[Data]` lines. I reproduced the mechanism with `.venv` python. `map_task_result_writes([('messages',[a]),('document_search_trace',{}),('messages',[b])])` returns `messages={'$writes':[…]}`, and `provisional_messages` then yields the string `'$writes'`, so 0 ToolMessages are logged. The single-write case logs normally. Code path: `trading_graph.py:790-795` together with `ToolNode._combine_tool_outputs` when a round mixes in a `Command`. 11 of 24 returns are absent from MTL, in this run and the earlier one. | In `stream_run`, flatten `{"$writes": [...]}` lists (and nested lists) before yielding messages. |
| CN2 | 5 | Low [node] | ran | Later roles get both the pre-analyst brief (17k characters, labelled "not final evidence-gate approval") and the final canonical context: CTX:401-417 puts the brief first, then the canonical context. Total context per research call is 95.7k characters (ran on final state). Only 6 lines are verbatim duplicates, but the same facts appear twice in different formats. | After Evidence Check, drop `shared_source_brief` from `get_instrument_context_from_state`, or keep only its non-canonical lines (price, filing terms). |
| CN3 | 1 | Low [node] | read | Build B records (`shared_source_brief`, `filing_terms_evidence`) reached all four analyst prompts, and all four reports cite the $178.51 conversion price / $312.3M notes / $2.955B uncommenced leases (grep counts 1–2 in each). This is positive confirmation, not a defect. | — |

## Open questions
1. Why did Sentiment's structured call fail (Opus 5.5 via OpenRouter)? The exception class is not recoverable from run.log (SE4).
2. What exactly did `past_context` contain for the PM? It is not persisted (ML2).
3. Which selection rule in `sec_documents` dropped press-release blocks 42/43/47/49 (likely non-GAAP EPS / adjusted EBITDA lines)? I could not determine this read-only without re-fetching (SA2).
4. "Fifth straight quarter of acceleration" (fundamentals prose) was not checked. It needs the quarterly revenue series from the 63k `get_financial_evidence` return.
