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

## Decision and freeze

The user chose to pass on what the filing presents (plan Amendment 3). Frozen before any held-out result was opened:

- Candidate production code and scorer: `a57111f5a47f74b6e1a9a94930564698a1128524`. Cohort, cutoff and inputs as frozen above; capture scope per Amendment 2; no replay miss and no automated fill was needed for any of the 31 issuers.
- Sealed files, by SHA-256: baseline held-out `d22afbfceed21efb`, final held-out `3532504650d09a01`.
- Development group, final score: MSFT, CAT, WMT, PANW, RTX, JNJ, LRCX and CSCO at 7/7 (8 of 10, from 0); INTC 6/7 (a filer-specific financing line for equipment purchases is not classified); LLY 6/7 (its 10-Q gives no opening equity balance). DOCN 7/7, unchanged.
- DOCN regression: everything the acquisition step produces from the code under test (facts, source checks, calculations, canonical context) is identical between `9942114f` and the candidate on the same frozen inputs. Fields that differ between two runs of the same code (timestamps, live non-SEC sources) were excluded; the required-return field differed only because one checkout has a FRED key in its environment.
- Live timing on the candidate, free SEC only, all 31 issuers: slowest 12.9 seconds, most requests 30, no request or time budget exhausted.
- Not done: the pre-freeze paid MSFT run through the real app (paid runs are not approved). The offline score therefore stands without a live route confirmation.

## Held-out verdict (opened once, after the freeze)

| Group | Size | At 7/7 before | At 7/7 after | Newly passing | Gain |
|---|---|---|---|---|---|
| Development | 10 | 0 | 8 | 8 | 80 points |
| Held out | 20 | 0 | 7 | 7 | 35 points |

- **Numerical criterion met:** seven held-out companies newly clear all seven checks (the floor is five): AAPL, NVDA, MU, ORCL, MRK, HD, PM. Baseline headroom was 20 of 20.
- **Development improved far more than held out** (80 against 35 points). The readers generalise, but less well than the development group suggests; the reasons below show where.
- **No regression:** no check that passed at baseline fails or is unavailable after, in either group. No input failure, replay miss or automated fill in either scoring run.

Held-out passes per check, before and after: source_integrity 9 to 20, core_statements 12 to 19, balance_sheet 9 to 19, equity_movement 0 to 13, obligation_perimeter 0 to 13, cash_flow_perimeter 0 to 19, disclosure_coverage 8 to 19.

| Ticker | Before | After | Not passing after, with the reason given and what the data shows |
|---|---|---|---|
| AMZN | 0 | 6 | cash flow: a filer-specific financing line (`amzn:RepaymentsOfLongTermFinancingObligations`) reads like equipment financing and is not classified. True as stated. |
| AVGO | 3 | 6 | core statements: no Net Income fact at the balance date under the tags read. Reader limit. |
| TSLA | 2 | 5 | balance sheet: residual without source rounding. Obligations: two filer-specific debt-and-finance-lease lines are not classified. True as stated. |
| AMD | 0 | 6 | equity: the quarter's opening balance is not filed and the year-to-date treasury component does not reconcile. |
| ABBV | 0 | 6 | equity: the other-comprehensive-income component does not reconcile. |
| COST | 3 | 5 | equity: paid-in capital does not reconcile. Disclosure: the 6-filing and 8-document limits were reached; a documented acquisition limit, not an omission by the filer. |
| KO | 1 | 5 | equity: components do not add up to total equity. Obligations: `us-gaap:NotesAndLoansPayable` is not in the borrowing classification. Reader limit. |
| CVX | 1 | 6 | obligations: `us-gaap:LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities` is not classified, and no unrestricted cash fact is read. Reader limit. |
| PG | 2 | 5 | equity: the noncontrolling component does not reconcile. Obligations: no unrestricted cash fact is read at the balance date; the message shown names leases, which is not the blocking cause. Message defect. |
| GE | 1 | 5 | equity: opening balance not filed for the quarter. Obligations: no unrestricted cash fact is read. |
| AMAT | 2 | 6 | obligations: two sourced borrowings totals disagree (the filing-table total and the one derived from the filed lines), so neither is used; the message says "not stated". Message defect. |
| TXN | 4 | 6 | equity: opening balance not filed for the quarter; year-to-date paid-in capital does not reconcile. |
| TMO | 2 | 6 | obligations: the filed liabilities lines add up to 59,337M, which is not the total liabilities figure used. True as stated. |

Every non-pass is "unavailable" and none is a wrong pass. Two messages name the wrong cause (PG, AMAT). These are follow-up work and were **not** corrected: a change made after the results were opened could not be validated on this cohort.

## Recomputation of every new pass

The sampling method was not frozen before the scores were seen, as the plan requires. Every newly passing company was therefore recomputed rather than a sample (15: eight development, seven held out).

`docs/reviews/large-filer-proof-tools/recheck.py` does not use the SEC-extracted instance the readers use. It reads the primary filing document, takes each tagged figure as printed (text, scale, sign), and redoes three sums with its own arithmetic: the liability lines add up to total liabilities and the borrowing lines to the borrowings used; opening equity plus each printed movement equals closing equity, component by component; the financing lines add up to financing cash flow for the period. All three hold for all 15 (`recheck-results.json`).

The tool's first run disagreed for three companies. Each was a fault in the tool, found and fixed, not in the readers: it read only the outer of two nested tags on one printed number (HD, ORCL), and treated a printed zero as missing (CAT). Limits of this recomputation: it takes the list of line items from the package (it does not rediscover the statement structure), and it does not recompute lease balances, the investing section, share counts or disclosure coverage.

Auditor sample, drawn after the scores as the first five by SHA-256 of `large-filer-audit-2026-11-11:` plus ticker: MU, RTX, CAT, MRK, HD. Their printed lines are in `recheck-auditor-sample.json`.

## Offline acceptance

Pass on the numerical criterion, the recomputation and the DOCN regression, with these stated limits: the sampling method was fixed late (mitigated by checking every new pass); development gains exceed held-out gains by 45 points; no live run through the real app has been made, so delivery of a decision for a large filer is unverified.

## Follow-up work found (not started)

1. Borrowing classification gaps: `NotesAndLoansPayable`, `LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities`, and filer-specific debt-with-lease lines (TSLA).
2. Unrestricted cash and net income under other tags (CVX, PG, GE, AVGO).
3. Equity reconciliations that do not close for seven held-out layouts, and quarterly filings with no opening balance (LLY, AMD, GE, TXN).
4. Two misleading obligation messages (PG, AMAT) and the bare "required input fact unavailable".
5. Filer-specific financing lines for equipment purchases (INTC, AMZN).
6. Filing and document count limits (COST).
7. Lease payment schedule for large filers, so the funding check is assessed rather than "unassessed".
8. A fresh cohort is needed to validate any of the above; this one is spent.
