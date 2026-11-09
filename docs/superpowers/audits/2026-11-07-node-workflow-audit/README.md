# TradingAgents node-by-node workflow audit — 2026-11-07

**Subject:** staging `8920ffac` (builds A–D merged, CI green). One fresh DOCN run, analysis date 2026-11-07, 16:25–16:41 MST, quick `anthropic/claude-opus-5.5`, deep `openai/gpt-6.1-terra-pro`, 3 debate / 3 risk rounds, 2.31M in / 106k out tokens. Attempt dir `~/.tradingagents/logs/DOCN/2026-11-07/162527-34fe1c55/`, publication `cfae95e9`.

**Method:** 18 nodes, five questions each (input, instruction, tools, output, hand-off). Three Opus reviewers in parallel (parts A, B, C here), read-only, every Medium+ labelled `ran` or `read`. The one High (P1) was reproduced by me. Per-node prompts were **reconstructed** from source plus saved state: D11 (the trace switch) was excluded from Build D, so prompt bytes were not captured. The run log also misses 11 of 24 tool returns (CN1).

## Verdict

The pipeline is sound where it counts most: every number checked in analyst reports, debate, Research Manager, Trader and Portfolio Manager traces to tool returns or canonical evidence. The debate turns are substantive and responsive (0–4 % wording overlap with earlier turns). The PM answered all 7 audit findings. Build B records reached all four analysts.

The weaknesses are in **what each node is given** and **what reaches you and the next run**:

1. **Evidence the system already retrieved does not reach the agents that need it.** The $1B ATM is missing from the shared brief, and the RPO history (from $61M to $800M year on year, $345M due within 12 months) never reached the debate. Truncation drops the FY2026 outlook lines, and duplicate-document checks reject 6 valid disclosures. Net effect this run: "RPO fell 10.53 %" became a bear point and a reconsideration trigger in every later node, without the context that explains it.
2. **The follow-up document search returns the wrong passages and calls them "found".**
3. **The decision you read is buried and noisy (High).** The decision file is 45 KB, its Executive Summary line is a placeholder, and the PM's real summary sits at line 336 of 353. The first lines are 21 raw "Changed since" diffs and condition rows without thresholds.
4. **The next run inherits less than the PM decided.** A same-day rerun is never written to memory, non-metric conditions are dropped, and the publication record keeps the first 12 KB of tables rather than the PM's reasoning.
5. **The risk debate never tests direction.** All three roles defend the Trader's Sell from turn 1. They never see the Research Manager's plan.

## Findings index (High / Medium; Lows are in the parts)

| ID | Node | Sev | Kind | One line | Plan |
|---|---|---|---|---|---|
| P1 | Portfolio Manager / export | High | code | Decision file is 45 KB, placeholder Executive Summary, the PM's summary is at line 336/353 | R3 |
| SA1 | Source Acquisition | Med | code | ATM 8-K retained but left out of the shared brief, so Sentiment calls a filed fact unverified | R1 |
| SA2 | Source Acquisition | Med | code | Text limits drop outlook blocks; contiguity check then rejects FY2026 FCF margin and share guidance | R1 |
| FA1 | Fundamentals | Med | code | Same press release passed twice, so 6 valid disclosures are rejected as "needs one unique source document" | R1 |
| BB1 | Bull/Bear | Med | code | Debate sees only the June→Sept RPO change, not the year-on-year history in the corpus | R1 |
| SE2 | Sentiment/News | Med | code | Fallback news has no dates; `_format_articles` never prints `pub_date`; coverage says "available" | R1 |
| DF1 | Document Followup | Med | code | Bag-of-words search: dates and filler win; wrong passages for 3 of 4 questions (replayed offline) | R2 |
| DF2 | Document Followup | Med | code | "found" means passages came back, not answered; decision card says "3 passages retrieved" for unrelated tables | R2 |
| P2 | PM card | Med | code | 21 "Changed since 2026-11-07" lines: cases diffed by free-text name, so real changes (base revenue 1.93B→1.90B, 7× case dropped) stay hidden | R3 |
| P3 | PM card | Med | code | Conditions printed twice without thresholds; the card keeps only 3, dropping Operating Margin | R3 |
| H3 | Publication record | Med | code | Record keeps `decision[:12000]`: tables and diffs, not the PM's summary or thesis | R3 |
| A1 | Advisory Audit | Med | code | Audits only the first 6,000 chars per role (20–30 %); converged later turns never audited | R3 |
| H1 | Memory | Med | code + decision | A same-day rerun is silently not logged; memory and thesis continuity disagree | R4 |
| H2 | Memory/thesis | Med | code | Non-metric PM conditions are lost; prior rationale cut to 300 chars | R4 |
| CN1 | Run log | Med | code | Tool rounds with `search_documents` log zero returns (11/24 missing) | R5 |
| FA2 | Fundamentals | Med | prompt | Valuation uses borrowings only; the requested lease sensitivity was never produced and nothing checks it | N2 |
| ML1 | Memory → roles | Med | hand-off | Lessons reach only the PM, not the Research Manager or risk roles | N3 |
| RM1 | Research Manager | Med | prompt | Had the correct RPO passages, kept only the gaps; the PM repeated the framing | N1 |
| TR1 | Trader → Risk | Med | hand-off | Risk roles get only the Trader's Sell, never the RM plan and its conditions | N1 |
| R1 | Risk roles | Med | prompt + decision | No role tests direction; plans converge by round 2, round 3 restates | N1 |

## Two plans, not one

- **[Re-architecture follow-up](../../2026-11-07-tradingagents-rearchitecture-followup-plan.md)** (R1–R5): code. Evidence assembly, document search, the decision page and record, memory continuity, observability. Verified offline against the retained DOCN corpus; no paid run.
- **[Node workflow plan](../../2026-11-07-tradingagents-node-workflow-plan.md)** (N1–N4): prompts and hand-offs. Verified only by paid comparison runs against this run as the baseline.

**Why split:** different verification (offline replay vs paid output comparison), different risk, and an order dependency. Several prompt findings (RM1, SE1) are partly caused by missing evidence, so prompt changes judged on unfixed plumbing would be mis-scored. Re-architecture goes first. Each finding belongs to exactly one plan.

## Open questions (not resolvable read-only)

- Why the Opus structured-output calls failed for Sentiment and Trader: the run log redacts the agent name and exception class (fixed by R5).
- What `past_context` the PM saw: it is not persisted (R5).
- Whether the prior Underweight anchors the Research Manager: needs an A/B run with `thesis_context` withheld (optional, N-plan).
- Whether `post_screen` ran: depends on `TYPESAFE_API_KEY`.
