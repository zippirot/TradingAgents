# DOCN audit assessment

Date: 2026-10-20. Reviewed source: `3411158f91eb267aab8760fc90afbf43556eb0bb`, TradingAgents 0.7.0. This is an assessment and proposed correction plan, not implementation or a new investment recommendation.

## Conclusion

All twelve audit topics identify real weaknesses in this run, but their severity labels and proposed remedies should not be adopted wholesale. The strongest findings concern missing primary evidence, unsupported accounting interpretations, untraceable valuation assumptions, and propagation of those interpretations. Neither the original Underweight recommendation nor the auditor's numerical quality scores are validated by this review.

The direct correction is to extend the existing data path, preserve definitions and provenance, calculate important bridges in code, and prevent materially unsupported conclusions from becoming final decisions. More debate agents or a replacement research platform are not prerequisites.

## Evidence inspected

- Original seven Markdown reports and `message_tool.log` under `/Users/zipp/.tradingagents/logs/DOCN/2026-10-19/`.
- Full saved state: `/Users/zipp/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-10-19.json`.
- Original cached SEC companyfacts, inspected read-only by the financial-data reviewer.
- Audit supplied in `/Users/zipp/.codex/attachments/9b75917a-ad28-47af-8f3d-7e66228acceb/Pasted text.txt`.
- Current acquisition, analyst, graph, structured-output, reporting, rating, memory and backtest source; focused offline tests.
- Primary disclosures below, retrieved on October 20. No paid model rerun or broker operation was performed.

The saved run used `deepseek/deepseek-v4.1-flash-1017` through OpenRouter for both model tiers, with five research rounds and five risk rounds. This establishes configuration, not that this model caused the defects or that another model would fix them.

Code Review Graph was checked: only `/Users/zipp/Libertas` was indexed. Its results were not used for this checkout; direct source tracing was used instead.

## Primary-source cross-check

The [Q2 2026 Form 10-Q](https://www.sec.gov/Archives/edgar/data/1582961/000162828026052556/docn-20260630.htm) confirms the financing and lease omissions. In USD thousands, the equity roll-forward is:

`-28,690 - 37,335 + 2,494 + 887,888 + 55,962 - 796 + 51,208 = 930,731`.

The statement-of-equity compensation figure differs from the cash-flow adjustment; they must not be interchanged. June 30 borrowings are 921,053; finance leases/equipment obligations 577,720; operating leases 479,087; cash 767,026. Net obligations are therefore 154,027, 731,747 or 1,210,834 depending on perimeter. The original estimate resembles the broadest perimeter, not conventional debt. Noncash finance/operating lease asset additions are 414,902/273,823; uncommenced colocation commitments are approximately $2.759B. The filing also describes July financing events: June balances cannot silently represent October debt. These facts support classification and freshness fixes, not an automatic bullish conclusion.

The [August 4 earnings release](https://investors.digitalocean.com/news/news-details/2026/DigitalOcean-Announces-Second-Quarter-2026-Financial-Results/default.aspx) confirms AI Customer ARR of $234M, $1M+ Customer ARR of $259M, RPO of $894M and incremental ARR of $93M. AI Customer ARR includes conventional cloud spending by AI-using customers; it is not pure AI-product revenue. RPO is not a recognition schedule or guaranteed incremental growth. FY2026 revenue guidance was $1.170–1.180B; exceeding 50% growth in 2027 was management's ambition. Applying 50% to the midpoint gives $1.7625B, not a guaranteed forecast. Q3 revenue guidance was $304–307M: the report's $290M bull-condition threshold also needs reconciliation. Reported Q2 diluted EPS was $0.29 versus adjusted $0.45; adjusted FCF was $61M. These definitions must remain separate.

## Finding-by-finding verdict

Paths below are repository-relative unless identified as original reports. Line anchors refer to the reviewed commit.

| # | Assessment | Code/run evidence and correction |
|---|---|---|
| 1 | Confirmed material omission; not every missing KPI is necessarily disclosed | `agents/analysts/fundamentals_analyst.py:14-20` offers five narrow tools, no release/filing-text tool. `dataflows/vendors/sec_edgar.py:46-73` omits operating KPIs. The original fundamentals report explicitly says these were unavailable. Add official disclosure retrieval; record absent, unavailable and not-applicable separately. Do not invent NRR or counts. |
| 2 | Confirmed erroneous interpretation | Original `fundamentals_report.md:111` treats net financing cash flow as if it explains equity changes and speculates about a conversion. The statement tool supplies only financing totals. Add a real equity bridge; never infer an undocumented transaction from residuals. |
| 3 | Confirmed classification/provenance failure; “wrong arithmetic” overstates it | Original `fundamentals_report.md:115` reconstructs debt from a vendor ratio. `vendors/yahoo/fundamentals.py:88-89` displays the ratio correctly as percent and multiple, but gives no components. Use explicit obligation categories and a matched EBITDA/EV convention; do not substitute an unlabeled net-debt number. |
| 4 | Confirmed unjustified causal inference and incomplete investment measure | Original `fundamentals_report.md:138-151` concludes lower cash capex means buying/renting growth instead of building capacity. SEC tool exposes one capex line and no noncash investment. Separate cash spending, financed additions and future commitments. A universal revenue-per-MW/payback model is unnecessary for this fix. |
| 5 | Confirmed unsupported forecast assumptions, not proof a forecast must match management | Original `fundamentals_report.md:205-213` gives three revenue scenarios without a bridge to management. Capture guidance and ambitions separately; explain deviations. Do not require paid consensus data or three fully independent forecasting systems. |
| 6 | Confirmed unsupported target | Original `final_trade_decision.md:23` gives 96.0. `agents/schemas.py:253-265` accepts an optional float without inputs or method. A local reproduction accepted 96 with no valuation evidence. Require a reproducible method, not necessarily probability weighting; omit an unsupported target. |
| 7 | Confirmed unsupported dismissal of discrepancy | Original `fundamentals_report.md:134-136` calls vendor FCF a definition artifact without tracing it. `sec_edgar.py:65-71` exposes only four cash-flow lines. Compare definitions and periods; leave an unresolved discrepancy unresolved. Preserve conventional FCF and financing-payment variants separately. |
| 8 | Confirmed comparability gap | `sec_edgar.py:56-63` omits interest, tax, share counts and compensation. `vendors/yahoo/fundamentals.py:72-73` emits forward EPS without its accounting basis or forecast period. Do not compare that field to a hand-normalized GAAP result as though equivalent. A full owner-earnings modeling product is not required. |
| 9 | Confirmed unsupported inference; individual transactions remain unverified | Original report's remaining supply and conviction claims exceed the Yahoo transaction table. `vendors/yahoo/fundamentals.py:148-168` does not establish motives or remaining ownership. Report observed sales with scope and limitations; require actual filing evidence before stronger claims. Exhaustive ownership-service construction can wait. |
| 10 | Confirmed false precision, partly overstated by auditor | Technical probabilities have no cited calibration. The final decision itself criticizes half-size as halving an unknown loss, so the audit misses some downstream correction. Quantified allocation still lacks a portfolio risk budget. Label scenarios subjective or omit percentages; distinguish price/indicator observations from trading edges. A new statistical service is a separate project. |
| 11 | Confirmed overinterpretation; some safeguards already exist | Yahoo news emits title/summary/link (`vendors/yahoo/news.py:75-84`), not assured full articles. Original sentiment/news reports interpret the same Zacks question in opposite directions. Zero Reddit matches become broad silence; prediction prices become macro certainty. The sentiment report already states medium confidence and small sample, so the defect is enforcement and wording, not complete absence of caveats. |
| 12 | Confirmed shared-evidence failure | `graph/setup.py:157-166` joins analyst prose directly into debate. Researchers consume those strings; `agents/structured.py:36-39` expressly denies downstream external tools. Repeated debate is not independent source verification. Add a bounded evidence check using actual source records and deterministic calculations; a second LLM's approval alone is insufficient. |

## Additional findings and scope corrections

1. **Precision is discarded before reasoning.** `sec_edgar.py:235` formats USD in whole millions. This changes the locally reproduced revenue-growth calculation from 28.5706% using exact source values to 28.3105% using 281/219. Preserve exact numeric values for arithmetic and round only for display. This matters more for reconciliation than the small growth-rate difference itself.
2. **Derived periods lack a calculation trail.** The SEC tool intentionally labels YTD columns and does not derive Q4 (`sec_edgar.py:75-89,201-237,245-257`). The report nevertheless presents derived quarterly and TTM figures. Add safe derived-flow arithmetic with explicit source periods; never subtract EPS or share-weighted ratios as if additive.
3. **A forecast is not an observation.** Distinguish management ambition, analyst assumption, historical result and vendor consensus. Bounds and units alone do not validate meaning.
4. **Existing protections are worth keeping.** Filing-date filtering, restatement vintage handling, YTD labels, market snapshots, typed ratings, checkpoint handling, backtests and decision memory already exist. Passing unit tests prove their tested contracts, not the quality of this financial narrative.
5. **Existing REVIEW is useful but not a ready-made financial gate.** `agents/rating.py:106-112` prefers `final_rating` and otherwise parses prose; the typed portfolio enum has only five actionable ratings. Any new evidence status must override every output path, including fallback prose, CLI, memory and backtests. Do not call inadequate evidence Hold. Existing memory pending/context selectors do not exclude REVIEW, so the proposed gate must also avoid creating a pending trading-memory entry and prevent invalid reflections from contaminating later research.
6. **No score calibration was supplied.** The audit's 6.5/10 and 4/10 are opinions. This review did not evaluate autonomous trading readiness, forecast accuracy, or profitability. No broker execution path was exercised.

## Verification and limits

Two independent read-only reviewers inspected financial extraction and downstream reasoning. Their source claims were checked against the files and primary disclosures; one approximate equity bridge was replaced with the exact statement-of-equity bridge above.

Executed from the repository using the existing Python 3.12 environment:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_sec_edgar.py tests/test_statement_knowledge_time.py \
  tests/test_backtest.py tests/test_rating_integrity.py \
  tests/test_structured_agent_prompts.py tests/test_news_analyst_prompt.py \
  tests/test_graph_end_to_end.py
# 142 passed in 3.45s

.venv/bin/python -m pytest tests/test_fundamentals_units.py tests/test_fundamentals_lookahead.py -q
# 16 passed
```

158 distinct focused tests passed across these two invocations on the same unchanged application source. A separate 24-test SEC run duplicates part of the first command and is not added to that count. These are existing tests, not regressions for proposed corrections. No full-suite run was required for this read-only assessment.

Not verified: every insider filing, historical indicator, prediction contract, source article, vendor FCF definition, latest October capital structure, or consensus forecast. The audit's factual additions should not be pasted into the old report as a complete corrected valuation. No API credentials were read or printed.

Next: [implementation plan](../superpowers/plans/2026-10-20-report-evidence-integrity.md).
