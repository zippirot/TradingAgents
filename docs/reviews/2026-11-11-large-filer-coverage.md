# Large-filer coverage: build record

Plan: `docs/superpowers/plans/2026-11-08-large-filer-evidence-coverage-plan.md` with Amendment 1. Raw SEC material is private, outside the repository (`~/.tradingagents/private/large-filer-20261111/`).

## Frozen inputs (2026-11-11)

- Starting production code: staging `9942114fd69de7431513fc53b030a355385869c5`. Scorer and selection procedure: `2df2e033251cd65978097c3bbb6f06acfbb0fb40`, committed before selection ran.
- Analysis cutoff: 2026-11-11. Cohort manifest: `cohort/cohort.json` in the private store (order, decisions, hashes).
- Cohort, first 30 eligible issuers in SEC's published order. Development (10): MSFT, CAT, WMT, PANW, RTX, JNJ, LRCX, INTC, LLY, CSCO. Held out (20): AAPL, NVDA, AMZN, AVGO, TSLA, AMD, MU, ABBV, COST, KO, CVX, PG, ORCL, MRK, HD, GE, PM, AMAT, TXN, TMO. Control: DOCN.
- Skipped by rule, recorded with reasons: multi-class (GOOGL, META, V, MA, PLTR), financial SIC (BRK-B, JPM, UNH, BAC, HSBC, MS, RY), not a 10-K and 10-Q filer among recent forms (SKHY, XOM, ASML, NVS, AZN, SHEL, SAP). XOM is a domestic filer whose recent-forms window held no 10-K; the rule skips it as not established and no replacement is made.
- Replay faithfulness: live capture and offline replay gave identical statuses and reasons for all 10 development companies and DOCN.
- Held-out baseline: captured and scored with results sealed (`sealed/`), unopened.

## Development baseline at `9942114f` (pass / -- unavailable / FAIL)

| Check | MSFT | CAT | WMT | PANW | RTX | JNJ | LRCX | INTC | LLY | CSCO |
|---|---|---|---|---|---|---|---|---|---|---|
| source_integrity | pass | FAIL | pass | FAIL | pass | FAIL | FAIL | FAIL | pass | FAIL |
| core_statements | pass | pass | -- | pass | pass | pass | pass | -- | -- | pass |
| balance_sheet | pass | pass | -- | pass | -- | pass | pass | -- | -- | pass |
| equity_movement | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| obligation_perimeter | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| cash_flow_perimeter | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| disclosure_coverage | -- | -- | -- | pass | pass | pass | pass | -- | pass | -- |

0 of 10 at 7/7. DOCN 7/7.

## Progress

- **L6a (done).** `source_integrity` failed for six companies because a block cut short by the excerpt budget was compared with its full text and called a conflict. A truncated prefix now merges into the full block; any other difference still fails (`tests/test_truncated_block_views.py`). After the fix all ten pass `source_integrity`, the equity check is produced for all ten, and DOCN is unchanged at 7/7.

## Not yet done

Extended capture of every text document in each filing index; L1–L5; L6b (total liabilities); MSFT case-pricing check; final score; held-out verdict; independent audit. Paid runs are not approved.
