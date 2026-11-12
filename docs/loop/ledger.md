# Loop ledger

Target: Investment Decision Quality. Evaluator skill version is recorded with every score; scores across versions
are not compared. Differences under 0.3 between runs of the same code are treated as noise.

## Scores (one row per evaluated run)

| cycle | date | company | run | code | Decision (holistic / weighted) | Research | Operational | D1 | D2 | D3 | D4 | D5 | D6 | D7 | caps | evaluator | run cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2026-11-11 | DOCN | 46c345dc (Sell) | 2ff7a43c | 7.5 / 7.5 | 8.2 | 3 | 7.0 | 7.8 | 7.4 | 8.0 | 7.5 | 7.2 | 8.5 | CF3, CF6, CF10 | Claude helper, TAE-1.1-loop1 | 1.35 |
| 0 | 2026-11-11 | MSFT | 3d4741a9 (Underweight) | 2ff7a43c | 6.3 / 6.4 | 7.4 | 3 | 6.0 | 7.0 | 6.3 | 6.5 | 5.5 | 6.3 | 7.8 | CF3, CF4, CF6, CF10 | Claude helper, TAE-1.1-loop1 | 1.11 |
| 0 | 2026-11-11 | WMT | 7897e51f (Hold) | 2ff7a43c | 5.5 / 5.0 | 6.0 | 3 | 2.5 | 6.0 | 6.0 | 4.5 | 5.5 | 6.5 | 7.5 | CF1, CF3, CF6, CF10 | Claude helper, TAE-1.1-loop1 | 0.83 |
| 0 (second opinion) | 2026-11-11 | WMT | 7897e51f (Hold) | 2ff7a43c | 5.2 / 5.2 | 6.7 | 3 | 2.5 | 7.5 | 8.0 | 4.0 | 4.5 | 4.0 | 8.5 | CF1 and others, see evaluation.codex.md | Codex, user's skill TAE-1.1 (full; 956k input tokens of which 884k cached, 21k output, 12 minutes) | Codex allowance |
| skill check | 2026-11-11 | DOCN | saved 3f72250f (Underweight), older code | b-series | 7.5 / 7.5 | 8.2 | 3 | 6.8 | 7.8 | 7.6 | 7.5 | 7.3 | 8.0 | 8.5 | CF3, CF4, CF5, CF9, CF10 | Claude helper, TAE-1.1-loop1 | 0 |
| skill check | 2026-11-11 | MSFT | saved 5bc202c4 (Overweight), before the case fix | pre-2ff7a43c | 5.2 / 5.0 | 6.9 | 3 | 2.5 | 6.0 | 5.5 | 5.0 | 6.0 | 6.5 | 7.0 | CF1, CF4, CF5, CF6, CF7, CF10 | Claude helper, TAE-1.1-loop1 | 0 |

## Fixes (one row per fix)

| cycle | date | company | finding | type | target factor | estimated effect | fix commit | replay: outputs changed | paid run id | score before → after | verdict | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Not worth it / not confirmed

| date | finding | why it was not built |
|---|---|---|

## Waiting for the user's decision

| date | item | why it needs a decision |
|---|---|---|

## Noise baseline (cycle 0, portfolio v2 with MSFT held; three independent runs each on 2ff7a43c; evaluator Claude helper TAE-1.1-loop1)

| company | ratings | Decision mean (spread) | Research mean | D1 | D2 | D3 | D4 | D5 | D6 | D7 |
|---|---|---|---|---|---|---|---|---|---|---|
| DOCN | Sell x3 | 7.33 (0.5) | 8.27 | 7.1 (0.7) | 7.8 (0.0) | 7.2 (0.8) | 7.6 (1.0) | 7.2 (0.7) | 6.93 (0.2) | 8.57 (0.2) |
| MSFT | Overweight x3 | 6.67 (0.4) | 7.47 | 6.37 (0.2) | 6.67 (0.5) | 6.5 (1.0) | 6.37 (1.0) | 6.97 (0.9) | 7.6 (1.2) | 7.77 (0.7) |
| WMT | Hold x3 | 5.5 (0.0) | 6.23 | 2.67 (0.5) | 6.4 (0.3) | 6.5 (0.0) | 5.5 (0.0) | 6.33 (1.5) | 6.5 (1.0) | 7.33 (0.5) |
| CAT (holdout, one run) | Sell | 6.7 | 7.0 | 6.0 | 7.0 | 6.8 | 7.5 | 7.5 | 6.5 | 7.8 |

Lines a change must beat (three-run means): Decision by more than 0.5; a single factor by more than 1.0 (1.5 for D5). Rating agreement is 3 of 3 everywhere, so stability starts at its ceiling; the goal is not to lose it. Cost of the ten runs: 11.74 dollars. Open question: MSFT rated Underweight in the one portfolio-v1 run (not held) and Overweight in all three v2 runs (held); not yet investigated.

## State

2026-11-11: baseline (cycle 0) complete, 3.30 dollars spent. The user put cycle 1 ON HOLD while they finish the loop's design; do not start a fix or a paid run until they say so. Loop runs use a made-up portfolio with none of the three stocks held, so ratings are not comparable with the user's own runs.

Codex check (2026-11-11): works from this Mac with `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex exec -s read-only --skip-git-repo-check -o OUT "/evaluate-tradingagents-report PATH"` run from `~/Documents/ChatGPT/Tauric` (the user's skill lives in `.agents/skills` there). Its record uses different key names from the helper's (`C_decision_quality_rubric.D1.score`, `section_18_machine_readable_record`). On WMT the two evaluators agree on Decision (5.2 vs 5.5) and on D1 (2.5 both) but differ by up to 2.5 on D3 and D6 and by 0.7 on Research.

## Cycle 1 (APPROVED by the user 2026-11-11; diagnosis done, nothing built yet)

Target: D1 on WMT (2.67, no valuation). User's direction: keep DOCN-level accuracy, but handle what other companies file differently; three input levels (verified / corroborated / unverified) approved in principle.

Diagnosis (reproduced in saved state `~/.tradingagents/loop/logs-n1/WMT/...`): WMT passes all seven required source checks. The only blocker is "Common Shares Outstanding": value None. Walmart tags no balance-date share count; it gives only the cover count (7,933,746,241, dated late August, after the 2026-07-31 balance date). `face_liabilities._filed_shares` refuses a cover count dated after the balance date by design. So the fix needs NO vendor fallback: the figure is filed.

Planned fix (not started): in `_filed_shares`, last resort = cover count `dei:EntityCommonStockSharesOutstanding` dated after the balance date (within about 120 days, not after as_of), accepted only if within about 2% of the quarter's filed weighted-average basic shares (WMT: 7,954M vs 7,934M, 0.3%). Emit an input fact "Cover Shares Outstanding" at its true date plus a derived "Common Shares Outstanding" at the balance date with a new formula id (pattern: `derive_shares_outstanding` / `shares_issued_less_treasury_v1` in `dataflows/financial_evidence.py`); add the formula to `evidence_validation.validate_calculation_lineage` (line ~144) and to `counted` in `valuation_cases.py:867`; print a plain label in the case assumptions. Failing test first (see `tests/test_face_liabilities.py:325`). Then: replay (DOCN/MSFT must not change), offline 31-company count of companies with a share count, three WMT runs, must beat 0.5.
Also open: MSFT Underweight (not held) vs Overweight x3 (held) not investigated.

MSFT held-versus-not-held question, RESOLVED 2026-11-11 (free check on saved states): not caused by holdings. The single portfolio-v1 run priced MSFT at the 2026-11-10 close (533.16) because the 11-11 bar was not yet posted; the three v2 runs used the 11-11 close (521.13), and their cases used multiples of 11 against 10.5. Rule for the loop from now on: every run uses `--date 2026-11-11` so price and filings are the same in every cycle. Left as an observation, not a target: a 2.3% lower price plus a slightly higher multiple moved MSFT two notches (Underweight to Overweight) in one comparison.

## Cycle 1 result (WMT, three runs on 6e1f35d4; fixes b4faf29d cover share count, the derived-count brief fix, 6e1f35d4 mistyped reference)

| | baseline (3 runs) | cycle 1 (3 runs) |
|---|---|---|
| Rating | Hold x3 | Sell x3 |
| Reached a decision | 3 of 3 | 3 of 3 (an interim batch had 1 of 3 stop at REVIEW on a mistyped reference; fixed) |
| Valuation cases priced | 0 of 3 | 3 of 3 |
| Decision | 5.5, 5.5, 5.5 | 6.3, 6.4, 6.2 (mean 6.3, +0.8, beats the 0.5 line) |
| Research | 6.2, 6.0, 6.5 | 6.8, 6.8, 6.7 |

Verdict: mattered. Cost of cycle 1 paid runs: about 8.5 dollars (nine WMT runs; the first three were run before the second fix and were wasted: rule added, one run before three).
Fix 4 (ecd7ee3a, action reading agrees with the holding) is built and tested but not yet in a paid run.
Offline coverage 2026-11-11: 15 of 31 stored companies pass all seven source checks (16 blocked: equity_movement 8, obligation_perimeter 7, cash_flow_perimeter 3, core_statements 1, balance_sheet 1, disclosure_coverage 1).
User decisions 2026-11-11: build an earnings-based valuation for mature companies (approved); run remaining cycles unattended (approved, after the 16-blocked question is settled). New loop rules: one run before three; track "reached a decision"; track offline coverage count.

## Aperture program (APPROVED by the user 2026-11-11: "yes to both, include step 3, complete all the work")

Work in this order, each with a failing test first, the offline 31-company coverage count before and after, replay of saved runs (DOCN and MSFT must not change), then one live run before three:
1. Equity-movement check becomes a warning that lowers stated confidence, not a stop (unblocks LLY, AMD, ABBV, TXN; needed with step 2 for KO, PG, GE, COST).
2. Teach the readers: cash under other tags (CVX, PG, GE); debt-like face lines (TSLA, KO); company-specific financing lines (INTC, NVDA, AMZN); net income tag (AVGO).
3. Labelled outside-data fallback, capped (revenue always verified; at most one of shares, cash, debt unverified; any number corroborated), for what is left (TSLA rounding, COST document limit, AMAT, TMO).
4. Earnings-based valuation for mature profitable companies (approved separately).
5. Fresh-company test: a new set of companies never used for tuning, offline, to claim general coverage.
6. Loop rules added (one run before three; track reached-a-decision; track coverage), then remaining cycles unattended.
Nothing is merged, pushed or installed without the user's explicit approval.

### Aperture progress, 2026-11-11 late (all committed locally; suite 4,763 passing; 27 saved runs replay unchanged)

Offline coverage ("open" = no required source check stops the run): 15 -> 27 of 31. All seven checks passed: 15 -> 20.
Done: step 1 (equity check advisory when unavailable); step 2: cash from the filer's own current-assets cash line (CVX, PG, GE), debt lines (KO NotesAndLoansPayable, CVX LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities, TSLA own DebtAndFinanceLeases lines), own financing lines read as equipment principal (INTC, NVDA, AMZN), profit as parent income when no noncontrolling interest (AVGO).
Still blocked (4): TSLA balance_sheet "nonzero residual cannot be assessed without source rounding precision"; COST disclosure_coverage (filing count limit 6 / document count limit); AMAT borrowings not on a separate line (within other liabilities); TMO filed liabilities sum differs from total liabilities.
Next: step 3 for these four; step 4 earnings-based valuation; step 5 fresh-company test (the 31 are now tuned on); step 6 loop rules; live check of one opened company (one run before three); fix 4 (action reading) still not in a paid run.

### Aperture progress, 2026-11-11 night (committed; suite 4,766 passing)

Offline coverage on the 31 tuned companies: open 30 of 31 (was 15); all seven checks 23 (was 15).
Added since the last note: TSLA (one temporary-equity balance under two tags counted once), AMAT (borrowings from a complete filed list stand over overlapping tags), TMO (a filed list closes on a derived total within rounding: 3 units and at most 0.005%).
Still blocked: COST only. disclosure_coverage: "Filing count limit 6 reached" and "Document count limit reached" (Costco files many current reports). The selection already keeps statements, non-reliance notices, the latest earnings and the latest financing report; what is dropped is older general 8-Ks, and some exhibits. Making those two notices warnings is a change to a deliberate rule ("omitted filings/exhibits remain critical"); not done, recommended to the user.
Step 3 (outside-data fallback): NOT built. All four failure modes closed by reading the filings, and the one remaining block is not a missing figure, so there is nothing for a fallback to supply on these companies. Decide after the fresh-company test shows what is actually missing.
Step 5 running: fresh cohort of 20 never-tuned companies captured to ~/.tradingagents/private/fresh-cohort-20261111 (XOM, UNH, V, PEP, MCD, NKE, DIS, VZ, BA, HON, UPS, LOW, SBUX, ADBE, CRM, NFLX, QCOM, IBM, PFE, DE); result in capture.json there.
Not yet done: live run of a newly opened company (one before three); step 4 earnings-based valuation; step 6 loop rules; fix 4 (action reading) in a paid run.

### Fresh-company test, 2026-11-11 night (committed; suite 4,769 passing)

20 companies never used for tuning (XOM, UNH, V, PEP, MCD, NKE, DIS, VZ, BA, HON, UPS, LOW, SBUX, ADBE, CRM, NFLX, QCOM, IBM, PFE, DE), store ~/.tradingagents/private/fresh-cohort-20261111.
Out of the box: open 16 of 20 (80%), all seven checks 9. That is the honest general-coverage figure.
After two fixes found there: open 18 of 20, all seven 10. DE: us-gaap:SecuredDebt / UnsecuredDebt classified as borrowings. PEP: a borrowing-detail tag stated in several currencies at one date gives nothing instead of stopping the read (core figures still stop it). Also added: older SEC submissions archives are read when the recent list has no 10-K (built for XOM; not the cause there).
Still blocked: XOM (registrant CIK 0002115436 has only 42 filings since 2026-07-01 and no 10-K: a new registrant; correct to stop); IBM (financing arm: filed liability lines and financing lines do not add up; three checks).
Tuned set unchanged: 30 of 31 (COST).

### 2026-11-11 late night

Costco opened (3b8b61f6): tuned set 31 of 31. Live check (one run before three): CVX, blocked this afternoon, reached a valued decision live: Sell, Base 206.1 / Downside 141.2 vs close 213.27, evidence "limited", cash read from cvx:CashAndCashEquivalentsExcludingTimeDeposits; fix 4's reading line appears as intended. Run folder ~/.tradingagents/loop/logs-live-cvx.
User 2026-11-11: do the remaining work and apply my recommendations (Costco warning: done; outside-data fallback: skipped, nothing needs it).
Earnings case: plan in docs/loop/earnings-case-plan.md. Task 1 (model and pricing) built and tested. Tasks 2 to 5 open.

### Cycle 2: earnings-based valuation (built 2026-11-11 night; suite 4,779 passing; saved runs replay unchanged)

Commits: task 1 model and pricing; task 2 weighable in the valuation step, mixed methods refused; tasks 3 and 4 manager weighing, printing, analyst prompt; split check and price comparison.
One run before three (WMT, ~/.tradingagents/loop/logs-e1, 1.00 dollar): the analyst chose earnings cases unprompted by anything but the new instructions: Base 2.95 x 38 = 112.10, Downside 2.60 x 30 = 78.00, Upside 3.20 x 42 = 134.40, close 125.66; weighted value 106.33 printed; rating Underweight. Defect found in that run: "No comparable completed close is available" (the case was anchored to the earnings year end, before the price coverage starts). Fixed and proven by replaying the same saved run: all three cases now compare with the 125.67 close.
Paid check running: three runs each of WMT, CAT, DOCN, MSFT (tags e2a, e2b, e2c). CAT is the holdout: these three runs are its end reading and must not be used to adjust anything.
Open note: prior-case comparison and own-history placement do not yet cover earnings cases (they say nothing rather than something wrong).

### Cycle 2 result: earnings-based valuation (scored 2026-11-12; evaluator Claude helper TAE-1.1-loop1)

| company | method chosen | ratings | reached a decision | Decision before | Decision after (3 runs) | D1 before -> after |
|---|---|---|---|---|---|---|
| WMT | earnings | Underweight, Sell, Sell | 3 of 3 | 6.3 (cycle 1) | 6.23 (5.6, 6.5, 6.6) | 5.17 -> 5.53 |
| MSFT | earnings | Overweight x2, Underweight | 3 of 3 | 6.67 (baseline) | 6.83 | 6.37 -> 6.7 |
| DOCN | revenue (unchanged) | Sell x2 scored (third evaluation pending) | 2 of 2 | 7.33 (baseline) | 7.7 | 7.1 -> 7.6 |
| CAT (holdout, end reading) | earnings | Underweight x3 | 3 of 3 | 6.7 (one run) | 5.8 | 6.0 -> 6.0 |

Verdict against the keep rule: NO MEASURED GAIN. No company moved by more than the 0.5 line upward; the holdout fell 0.9 (its baseline was one run); rating agreement fell from 3 of 3 to 2 of 3 on WMT and MSFT. The "wrong method for the company" finding is gone. Not reverted: left for the user's decision (recommendation: keep, because valuing a mature retailer on revenue was the wrong tool and the score is now held down by other things).
What now holds Decision down, seen across companies in these runs:
1. A negative rating on a stock not held becomes an opening purchase (Underweight = half the standard weight) with a negative modelled return and no stated override: CF3 and CF6 on almost every report. CAT's fall is this: at baseline it rated Sell (no purchase), now Underweight (buy). Needs the user's decision on what a rating means for an unheld stock.
2. The target weight is not tested against the accepted downside case: CF5 on CAT and MSFT ("exceeds the loss budget in the downside case while the report says inside the budget").
3. Earnings-case inputs are not anchored: forecast EPS not reconciled with filed year-to-date earnings or the vendor range printed in the same report; multiples not compared with the trailing multiple. The "what the price implies" line (4c781db9) was added after these runs and is not in them.
4. Case period ends 81 days out for WMT (fiscal year end) against a six-month horizon: CF9.
Cost of cycle 2: about 18.5 dollars (one WMT, twelve of which nine crashed on a printing bug introduced after the one-run check, then one WMT and eight reruns). Lesson recorded: after any change, however small, replay the saved run through the WHOLE report path (prepare and render), not only the step that changed, before paying for a batch.
Total paid spend to date: about 43 dollars.

DOCN third cycle-2 evaluation (e2c): Decision 7.1, Research 7.9. DOCN after: 7.7, 7.7, 7.1, mean 7.5 against the 7.33 baseline (+0.17, inside noise); ratings Sell x3; reached a decision 3 of 3.

## User decisions 2026-11-12 ("Yes yes yes")

1. Earnings method: KEEP.
2. For a stock not held, Underweight or Sell means do not buy: YES. Built as "a rating below Hold never opens or enlarges a position" (f0b4b8c8 and the commit after it): unheld Underweight prints "no purchase"; a holding smaller than the Underweight weight is not added to; a Trader Sell with nothing held reads as no purchase; the agents are told the rule in the portfolio block and the Trader prompt. The portfolio review already read an unheld negative rating as "No action", so the two now agree.
3. Remaining loop cycles unattended: YES.

## Cycles 3 and 4 (one paid batch, attribution by company)

- Item 1 (no purchase under a negative rating) is measured on the unheld companies: WMT and DOCN.
- Item 2 (the rating's size tested against the lowest accepted case and the loss budget; the manager asked once to answer an OUTSIDE result) is measured on the held company: MSFT.
- The two do not touch the same reports, so one batch of nine runs measures both and saves nine runs and nine evaluations. Owner's change to the approved "three cycles": two measured batches instead of three (this one, then earnings-case anchors with CAT's end reading).
- Free checks before paying: suite; 18 saved cycle-2 reports re-rendered offline through the whole report path (all render; unheld Underweight shows "no purchase"; held MSFT unchanged).

### Cycles 3 and 4 result (scored 2026-11-12; nine runs k3a/k3b/k3c on f0b4b8c8..downside-size commit; evaluator Claude helper TAE-1.1-loop1)

| company | ratings | reached a decision | Decision before (cycle 2) | Decision after (3 runs) | D1 after | what it measures |
|---|---|---|---|---|---|---|
| WMT | Underweight x3 | 3 of 3 | 6.23 | 6.43 (6.5, 6.3, 6.5) | 5.33 | item 1, no purchase |
| DOCN | Underweight x3 (was Sell x3) | 3 of 3 | 7.5 | 7.6 (7.6, 7.5, 7.7) | 7.27 | item 1, no purchase |
| MSFT | Underweight x2, Hold (was Overweight x2, Underweight) | 3 of 3 | 6.83 | 6.73 (7.0, 6.7, 6.5) | 6.43 | item 2, size against the downside case |

Verdict against the keep rule: KEEP both, on the second leg of the rule (a code-checkable wrong result removed), not on the score. No company moved by more than the 0.5 line. What changed in the findings: CF3 (contradictory logic) triggered on 0 of 9 reports and CF5 (portfolio risk mismatch) on 0 of 9; CF6 once, mitigated. In cycle 2 these were on almost every report. Spread between runs narrowed (WMT 5.6 to 6.6 became 6.3 to 6.5).
Things to know:
- The size check changed a rating once: MSFT k3c, Research Manager Overweight, Portfolio Manager Hold after being told the Overweight size broke the loss budget in its own downside case. That is the rating bending to the position limit; it bears on the parked decision "split stock view from position action".
- MSFT's direction is not stable between batches (baseline Underweight; cycle 2 Overweight x2; now Underweight x2 and Hold), with the same close.
- CONFOUND: these nine runs had no vendor estimates. The fixed run date 2026-11-11 became a past date on 2026-11-12, and the vendor reader correctly refuses a past date without a retained snapshot. The cycle-2 reports had the vendor table; these did not. Remaining runs use `--date 2026-11-12` (the last completed close is still 2026-11-11 until that day's close).
- What holds Decision down now, named as the biggest weakness in 8 of 9 evaluations: the valuation inputs. Multiples have no own-history or peer reference; case weights are asserted and equal weights flip the answer; EPS is not built up or tested against the quarter already filed; WMT's 81-day case window is annualised to "-52% a year" (CF9 on 3 of 3).
Cost: nine runs, about 9 dollars. Total paid spend to date: about 52 dollars.

## Cycle 5 (last batch): the valuation-input package for earnings cases

Built before paying, each with a test first:
1. Earnings anchor (done): each earnings case states its forecast against the filed prior year, the filed quarters of the forecast period, and the vendor range when retrieved.
2. A case period much shorter than a year is not annualised (to build).
3. Own-history price-to-earnings reference for earnings cases (to build if it can be stated safely across splits).
