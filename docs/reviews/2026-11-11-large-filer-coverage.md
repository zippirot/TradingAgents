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

- **L6b (done).** WMT, INTC and LLY report no total-liabilities line. Total liabilities is now derived as the filed liabilities-and-equity total less consolidated equity and any temporary equity, each cited, and replayed by the lineage check. For such a filer the balance check compares assets with the filed total (two independent reported figures). Nothing is derived when a noncontrolling balance exists but only the parent's equity is known, when two temporary balances could overlap, or when the filing carries an outside or temporary equity balance under a tag code does not read (standard or the filer's own). For a filer that reports liabilities and has outside interests (RTX), the identity uses consolidated equity plus temporary equity. `tests/test_total_liabilities_identity.py`. WMT's derived figure, 189,115M USD, matches an independent calculation from the filed facts. The extra facts are read only where needed: DOCN's fact set is identical to the baseline code's (992 facts, same identifiers).
- Development group after L6: all ten pass `source_integrity`, `core_statements` and `balance_sheet`. `equity_movement`, `obligation_perimeter` and `cash_flow_perimeter` pass for none; `disclosure_coverage` for five.

- **L1 (done).** Borrowings and leases from the filer's own declared liabilities list (filed XBRL instance plus SEC's structure file for the filing). The declared sum is checked against the filed figures, so a category with no line in it is nil by the filer's arithmetic. Verified by hand for MSFT (borrowings 35,481M), WMT (50,411M) and CAT (45,201M, stated together with finance leases); DOCN's own list reproduces its existing perimeter (462M / 924M / 667M) although DOCN never uses this path.
- **L2 (done).** The equity reconciliation as tagged: opening plus every movement shown in the statement, signed by each tag's balance type, must equal closing; total column, movements split along another axis, or component by component.
- **L3 (done).** Principal paid over the period from the filed financing cash flows; a complete list with no equipment-financing line settles equipment principal for that period only.
- **L4 (done).** Filings beyond the 120,000-character excerpt are retrieved and recorded with no excerpt; earnings exhibits come from the filing index when the cover does not link them in a known way; Item 4.02 notices are always selected and stop the check until an amended report is on file. The 120,000 figure, the 6-filing, 8-document and 10-request limits are unchanged; MSFT's acquisition takes 21 SEC requests in total and about 9 seconds on replay.
- **L5 (done).** Each blocker names the category, filing, accession and whether the filing does not state the item or could not be read.
- **Case-pricing check (done, free).** On the captured MSFT evidence one revenue case prices through `prepare_shared_valuation` (590.86 a share on illustrative inputs) with the derived borrowings accepted as a sourced perimeter, the cash model and the funded statement. Limitation found: the funding check reports "unassessed" because no finance-lease payment schedule is extracted for MSFT; the lease carry-forward built for DOCN does not yet read a large filer's lease maturity table.

## Development group at `17e40dbe` (offline, frozen inputs)

| Check | MSFT | CAT | WMT | PANW | RTX | JNJ | LRCX | INTC | LLY | CSCO |
|---|---|---|---|---|---|---|---|---|---|---|
| source_integrity | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| core_statements | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| balance_sheet | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| equity_movement | pass | pass | pass | pass | pass | pass | pass | pass | -- | pass |
| obligation_perimeter | pass | -- | pass | -- | -- | -- | -- | -- | -- | -- |
| cash_flow_perimeter | pass | -- | -- | -- | -- | -- | pass | -- | -- | -- |
| disclosure_coverage | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| Passing | 7 | 5 | 6 | 5 | 5 | 5 | 6 | 5 | 4 | 5 |

1 of 10 at 7/7 (baseline 0). DOCN unchanged at 7/7 with the same 11 requests and an identical fact set.

**Why the rest stop.** Borrowings are established for all ten. Nine stop because the filing scored (a 10-Q for seven, a 10-K for PANW and CSCO) states no finance-lease or operating-lease balance, or no finance-lease principal paid in the period; the plan forbids assuming a figure. Others: CAT's equipment-on-lease (lessor) payments have no verified bridge; INTC has a filer-specific financing line for equipment purchases that code does not classify; PANW discloses capitalised software without a matching cash amount; LLY's 10-Q gives no opening equity balance.

## Open decision before the candidate is frozen

The held-out verdict needs at least 5 of 20 newly at 7/7. On the development evidence the plan's strict rule would pass about one company in ten. The rule and its alternatives are the user's decision; nothing has been loosened.

## Not yet done

Decision above; final frozen score; live timing pass; held-out verdict; recomputation sample; independent audit; DOCN deterministic-section comparison. Paid runs are not approved.

