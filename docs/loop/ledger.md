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

### Cycle 5 result: valuation-input package for earnings cases (scored 2026-11-12; runs f5a/f5b/f5c dated 2026-11-12 on the 2026-11-11 close; evaluator Claude helper TAE-1.1-loop1)

Built (each with a failing test first): earnings anchor (forecast against the filed year, the filed quarters and the vendor range); a case period under half a year states its own return before the yearly figure; own price-to-earnings points from fiscal year ends, with each case multiple placed against them; analyst prompt asks for both comparisons in the rationales.

| company | ratings | Decision before (cycles 3-4) | Decision after (3 runs) | D1 before -> after | reading |
|---|---|---|---|---|---|
| WMT | Underweight x3 | 6.43 | 6.90 (6.8, 6.9, 7.0) | 5.33 -> 6.27 | measured gain: +0.47 on the mean, every run above every earlier run; D1 +0.94 |
| MSFT | Underweight x2, Hold | 6.73 | 6.73 (6.6, 6.8, 6.8) | 6.43 -> 6.77 | no change in Decision; D1 up inside noise |
| CAT (holdout, second end reading) | Underweight x3 | 5.8 (cycle 2); 6.7 (one baseline run) | 6.50 (6.8, 6.3, 6.4) | 6.0 -> 5.67 | recovered the cycle-2 fall (the no-purchase rule); not above its baseline |
| DOCN (guard; revenue cases, package does not apply) | Underweight x3 | 7.60 | 7.27 (7.0, 7.7, 7.1) | 7.27 -> about 6.9 | down 0.33, inside the 0.5 line; Research 8.07 -> 7.77, at the 0.3 guardrail |

Verdict: KEEP. WMT is the loop's one measured Decision gain from a build (with cycle 1). MSFT flat. DOCN's weaknesses in these runs are the asserted scenario weights and, in one run, the analyst pricing a 2026 period 50 days out; neither comes from this package, but DOCN has not improved in the loop and its guard reading is at the edge.
Where each company ended against its noise baseline: WMT 5.5 -> 6.9 (+1.4); MSFT 6.67 -> 6.73 (flat); DOCN 7.33 -> 7.27 (flat); CAT 6.7 (one run) -> 6.5 (flat).
Still open, by evidence in these evaluations:
1. Scenario weights are asserted and equal weights flip the answer (named on DOCN, MSFT, WMT). Type 3 (what the manager is told) and a product question: should code require a stated basis for weights or show the rating at equal weights as the default?
2. Case period: analysts still choose periods far shorter than the six-month horizon (WMT fiscal year end 81 days out: CF9 on 3 of 3; DOCN once at 50 days). The short-period line states it; nothing yet makes the analyst price the next year.
3. The size check's figures are withheld from the published record when the manager repeats them, so a reader cannot see why the manager overrode the research rating (MSFT f5c, CF3). The Hold size is tested at 5.0% while 5.2% is held (same report, CF2/CF5).
4. Earnings cases are EPS times a multiple with "funding unassessed" (CF4 on every MSFT report): no built-up earnings bridge.
5. MSFT's direction is unstable between batches (Overweight, Underweight, Hold on the same close).
Cost of cycle 5: 12 runs, about 12 dollars. Total paid spend for the loop: about 64 dollars of the 250 allowed.
Not done: the full Codex check at the end (the plan's second opinion).

## After the loop (user's "yes to both", 2026-11-12)

- Codex second opinion at the end (full, WMT f5c): Decision 7.3 against the Claude helper's 7.0 on the same report, Research 7.1 against 7.0. Inside the 0.5 line: the two evaluators agree.
- Scenario weights need a stated basis: when equal weights would put the accepted cases on the other side of the close, the manager is asked once for `weight_basis` and the card prints it, or says none was given. Boundary: nothing is asked where equal weights agree with the manager's. It would have fired on 5 of the 12 cycle-5 reports. One paid MSFT check (w6a): the manager gave a case-by-case basis. Not scored in a three-run batch.
- Merge to staging and launcher install approved by the user.

## After the loop, continued (2026-11-12; user: "execute your recommendations ... as if this was your codebase")

### Case period reaches the horizon (8f2998f4) - KEEP
Analyst is told the earliest acceptable period end (run date plus the horizon) and to price the following fiscal year when the current one ends sooner; code notes any case that still ends short. Nine runs p6a/b/c: no case ended short (WMT priced the year to 2028-01-31; its return read -9.8% a year, not -61%).
| company | Decision before | after (3 runs) |
|---|---|---|
| WMT | 6.90 | 7.07 (7.0, 7.0, 7.2) |
| DOCN | 7.27 | 7.37 (7.3, 6.9, 7.9) |
| MSFT | 6.73 | 5.93 (6.2, 5.3, 6.3): caused by the size check below, not by this change |

### DEFECT FOUND AND FIXED: the size check bent the rating (introduced in cycle 4, merged in 005215b8, fixed in 70f49644, installed as 820598eb)
`size_feedback` asked the manager to answer when the rating's size broke the loss budget in the lowest accepted case. In p6a/b/c all three MSFT runs rated Underweight for that reason alone ("Even the 5.0% standard allocation exceeds that limit, so the available 2.5% Underweight is the appropriate discrete size"), once against an Overweight research view; the evaluator scored that report 5.3 (CF3). Earlier single cases (k3c, f5c) were the same thing. Fix: the test is printed by code and never sent back; the printed line says the rating is not changed by it. Confirmed on three paid MSFT runs (q7a/b/c): no rating cited the budget. Lesson: a correction sent back to the manager with "or revise the rating" will be answered by revising the rating. Send back only what should change the rating.
Also lesson: the cycle-4 batch was scored at "no change" for MSFT with one Hold in three; the mechanism was visible then (ledger noted "the rating bending to the position limit") and I kept it. A noted side effect on what a rating means should have blocked the keep.

### Diagnosis: why MSFT's rating flips (free, thirteen saved runs on one close)
Weighted value today within -4.6% to +5.3% of the close in every run. Rating follows the sign of the yearly return against the 9.88% required return: 14% to 20% Overweight; 2% to 6% Underweight; 9% and 13% Hold. Base inputs stable since the anchor (20.00 x 28); the spread comes from the downside and upside cases and the weights. Not a case for the earnings model.

### Inside 10 percent the cases support Hold; a Hold with nothing held opens no position (owner's decision under the user's delegation; reversible)
Inside the band code already calls "near the close", any rating other than Hold owes a reason from outside the cases, on either side; the manager is told before deciding and asked once after. A Hold on an unheld stock prints "no purchase" (the portfolio review already read it as "No action"); only Buy or Overweight opens a position. On the twelve latest saved runs the rule would have asked on 7 (all MSFT, one DOCN).

### Result: the soft Hold rule did NOT work and was removed (2026-11-12)
Three paid MSFT runs (h8a/b/c) with the rule: Overweight (+4.5% against the close, reason given: growth and margins), Hold (+1.4%), Underweight (-2.2%, reason given). The manager states a reason and keeps its rating; a soft ask does not steady it. Removed the same day (one strike, clear mechanism). Kept: a Hold with nothing held opens no position (agrees with the portfolio review's "No action").
Open for the user: inside the 10 percent band, should CODE set the published rating to Hold? That is the only version that would steady MSFT, and it makes the rating a function of the scenario arithmetic there. DOCN (h8, unscored): Underweight x3, weighted value today 11% to 24% below the close; unaffected.
Total paid spend to date: about 90 dollars.

### Carry-forward test for earnings cases (2026-11-12; four paid MSFT follow-up runs that kept their history)
Before the fix (local commit "Earnings cases are carried to the next run like revenue cases") the carry-forward selected revenue cases only, so MSFT, WMT and CAT re-derived every input each run.
Result: every follow-up reproduced its predecessor's three cases and the manager's weights exactly (weighted value today identical to the cent: 544.82, 528.52, 509.49). Ratings: Overweight -> Overweight; Underweight -> Underweight; Hold -> Underweight, Underweight on identical numbers (+1.4% against the close, +12.3% a year against a required 9.88%; the Research Manager said Underweight and the manager kept it "as a portfolio risk judgment").
Reading: the numbers are now steady in normal use; what still moves is the judgment call when the stock is valued at about its price. That is the case the "Hold (on the line)" label is for. The loop's fresh-start runs overstated the flipping in the numbers.
Total paid spend to date: about 96 dollars.

### Hold (on the line) (user decision 2026-11-12: "execute this")
Trigger, from the report's own weight arithmetic and never a fixed percentage of the price: equal weights put the accepted cases on the other side of the close, or the highest case's weight needs to move by no more than 10 points (the spread measured between runs) for the weighted value today to equal the close. Then the published rating is Hold, set by code; the manager's own rating is recorded as the lean (asked once, as an instruction, not a choice); the holding is left as it is; the report says so beside the rating and on the scenario card, with the manager's words on what would move it.
Free check on 37 saved runs: MSFT on the line in 12 of 16, WMT 0 of 6, DOCN 2 of 9, CAT 2 of 3.
Paid check, three MSFT follow-up runs with history (h8a/b/c): +1.4% and -2.2% against the close -> Hold (on the line), lean Underweight both, executive summary rewritten for holding; +4.5% -> Overweight, off the line (no reweighting of its cases reaches the close), the same rating as its two predecessors. With carry-forward each history now repeats its own answer.
Also installed earlier today: earnings cases carried forward (fc60981e).
Known limit: two fresh starts can still land on different sides (one on the line, one not). The label steadies a history; it does not make fresh starts agree.
Total paid spend to date: about 99 dollars.

### MSFT scored after the day's changes: 5.6 average, DOWN from 6.7 (three follow-up runs h8a/b/c; reports made just before the final wording fix)
| run | rating | Decision | biggest weakness named |
|---|---|---|---|
| h8a | Overweight (off the line) | 5.6 | the printed size test: 6.2% loses 1.31% against a 1.00% budget in the report's own downside case, the case allows 4.8%, 5.2% is already held, and nothing in the report acts on it |
| h8b | Hold (on the line), lean Underweight | 5.9 | see evaluation; CF3 and CF5 again |
| h8c | Hold (on the line), lean Underweight | 5.4 | code-set Hold overrides a chain that all leaned Underweight; rating changed from the prior run on identical inputs (the rule arrived between the two runs: one-off); position left outside the loss budget |
Reading (two strikes on MSFT: 5.9 with the size check sent back, 5.6 with it printed only): the size-against-downside line is the common factor. Printed and unanswered it reads as an unresolved breach on every held stock whose downside case exceeds budget / weight; sent back, it bends the rating. The only consistent resolution is that the loss budget sets the SIZE: the parked risk-based-sizing decision. Partly an artefact of the loop's made-up portfolio (5% standard weight with a 1% loss budget fails any stock with a downside case worse than 20%).
The on-the-line label is not shown to help or hurt by these three: its two reports scored 5.9 and 5.4, the untouched one 5.6. STOP building on MSFT until the user decides the sizing question.
Total paid spend to date: about 99 dollars.

### "Hold (on the line)" REMOVED (2026-11-12, same day it was installed)
The user's own DOCN run on the launcher (their real portfolio: DOCN about 39% of it, 15% loss budget) published Hold while the Research Manager said Underweight, the Trader Sell and all three risk analysts reduce; their evaluator scored the decision 5.0 against 8.1 to 8.5 on the three runs before. Cause: the code-set Hold. I had tested it only on a 5% position in the made-up portfolio.
Lessons: (1) the launcher is what the user decides with; nothing goes there on single confirming runs; (2) the loop needed a test portfolio with a large position over its loss limit, now `docs/loop/portfolio.concentrated.json` (select with LOOP_PORTFOLIO); (3) code must not override the chain's rating.

### Clean comparison (fresh runs, 2026-11-12): today's code against a copy with the label and the printed size line switched off
| company, portfolio | today's code | stripped copy |
|---|---|---|
| MSFT, standard made-up portfolio | 6.43 (6.1, 6.6, 6.6) | 6.23 (6.3, 6.2, 6.2) |
| DOCN, concentrated portfolio | 7.5 (one run; label did not trigger at -14.1%) | 7.17 (7.4, 7.1, 7.0); Underweight x3, Research Manager Underweight x3 |
Reading: on fresh runs neither suspect moves MSFT (inside noise); the 5.6 reported earlier came from follow-up runs that continued a history, not from the code. MSFT sits 0.3 to 0.5 under its end-of-loop 6.73, at the edge of noise. The printed size line is neutral on score and is kept; the label is removed because of the real failure above, not because of these scores.
Open: follow-up runs (the way the user really runs) score lower than fresh runs on MSFT (5.4 to 5.9 against 6.1 to 6.6); evaluators name carried cases shown as "accepted", "unusable" and "not adopted" at once. Not yet diagnosed.
Total paid spend to date: about 109 dollars.

### Rollback confirmed on the user's real DOCN run (2026-11-12, launcher at 8072ae71)
Published Underweight, matching the Research Manager, the Trader and the risk analysts. The user's evaluator: decision 8.1 (5.0 with the override; 8.1 to 8.5 on the three runs before), research 9.2. It names as the remaining weakness that the downside case runs out of cash with no funding modelled (the loop's item on DOCN financing). Visible defect to fix on the bench: the Trader's code-written sentence "opening one where none is held; it is not an exit" printed for a held position.

### Bench batch validated on both portfolios (2026-11-12; follow-up runs, three each)
Changes: the Trader's reading no longer speaks of opening a position that is held; a case ending short of cash states the shortfall, the share sale it is equivalent to and what filed investments would cover (no value change; replayed on the user's real DOCN run: 11.1M, 197,952 shares, investments cover it 16 times); the comparison with the last decision reads earnings cases (they were all printed "unusable").
| company, portfolio | before | after (3 follow-up runs) |
|---|---|---|
| MSFT, standard | follow-ups 5.63 (5.6, 5.9, 5.4); same histories fresh 6.23 | 6.70 (6.8, 6.5, 6.8); Underweight x3, each holding its predecessor's rating; 0 "unusable" lines |
| DOCN, concentrated | 7.17 fresh | 7.17 (7.0, 7.3, 7.2); Underweight x3; the wrong Trader sentence gone |
Verdict: KEEP. MSFT follow-ups +1.07 against the earlier follow-ups (which also carried the Hold label on two of three, so not all of the gain is this fix) and level with the end-of-loop 6.73. DOCN unchanged. No loop DOCN run ended short of cash, so the shortfall line is proven by replay only.
Total paid spend to date: about 121 dollars.

## Wider mix, first pass (2026-11-12; user: "go on the default mix")
Six companies of different kinds, none seen before; private store `~/.tradingagents/private/wide-mix-20261112/store`; free offline source checks, then one paid run where open.
| company | kind | open offline | what stops it | reading |
|---|---|---|---|---|
| SNOW | unprofitable growth software | yes, 7 of 7 | - | paid run w13a reached Underweight, but the analyst submitted NO valuation cases ("the capital structure needs updating": notes issued after the balance date), so the rating is opinion only. Not yet scored |
| COP | oil and gas | no | cash spending: no capital-expenditure line under the two tags read (it files its own line) | reading gap, same family as earlier own-line fixes |
| NEE | utility | no | revenue filed as RegulatedAndUnregulatedOperatingRevenue; no capex under the tags read; latest primary filing not matched | reading gaps |
| PLD | property (REIT) | no | spending filed as real-estate acquisition and development; equity and financing reconciliations do not close; latest primary filing not matched | reading gaps; valuation method (funds from operations) is a separate question |
| PGR | insurer | no | unrestricted cash not established (only the cash-including-restricted tag) | financial company: net debt is not the right frame |
| JPM | bank | no | revenue filed as RevenuesNetOfInterestExpense; cash as CashAndDueFromBanks; no capex | financial company: needs its own path |
Reading: 1 of 6 open. The 80 to 90 percent figure held for industrial, technology and consumer filers only. Two groups: reading gaps the present model can absorb (COP, NEE, PLD), and financial companies that need a path without net debt or revenue multiples (JPM, PGR). New failure kind: a company that passes every source check and still gets no valuation because the analyst declines to submit cases (SNOW).
Installed state: staging 9cfd8033 (bench batch), CI green; launcher still at 8072ae71 because a session was open on it.
Total paid spend to date: about 122 dollars.

## Banks and insurers: their own path (user decision 2026-11-12: "yes build it"; bench only, NOT installed)
Built, tests first: a company is recognised as a bank or an insurer from its own filing tags (revenue net of interest expense, deposits; premiums earned, claims liability). For it the obligation and cash-spending checks lower the status when unavailable and no longer stop the run (a failure still does; every other check stays required); bank revenue is read from RevenuesNetOfInterestExpense; the analyst is told to use earnings cases.
Free checks: JPM 5 of 7 and PGR 6 of 7 passing, both now open. The 51 earlier companies are unchanged (31 of 31 and 18 of 20 open); only UNH is recognised as an insurer, correctly, and it passed every check already.
Paid, one run each (standard made-up portfolio):
- JPM x14a: Underweight, three earnings cases priced (base 25.50 x 15). Evaluator: Decision 6.3, Research 6.6. Biggest weakness: the hurdle is anchored on fiscal 2025 EPS while nine-month 2026 EPS is in the evidence; no build from bank drivers, no book-value or return-on-equity cross-check; peer reference unsuited to banks. Credited: net debt and free cash flow explicitly not used; the unheld Sell read as no purchase.
- PGR x14a: stopped at REVIEW, cause unrelated to the path: the claim model allowed a 160-character metric name and the analyst had copied the code's own 190-character fact label. Fixed (limit 400); the saved answer then passes offline. PGR x14b: Underweight, three earnings cases priced (base 16.20 x 12). Not yet scored.
Not done: three runs on both portfolios (the install rule); a book-value or return-on-equity reference for financial companies; bank-suited peers.
Other wider-mix items still open: reading gaps on COP, NEE, PLD; SNOW's analyst submitting no cases.
Total paid spend to date: about 125 dollars.

## Aperture loop, lean version (APPROVED by the user 2026-11-12: "anything, go"; plan `~/Claude/2026-11-12-tradingagents-aperture-loop-plan.md`)
The eight: DOCN, MSFT, WMT, CAT, CVX, JPM, PGR, UNH. No survey (the user's list is "anything" and eight kinds work).
Step 4, confirmation runs on bench head (all reached a valued decision, three priced scenarios each):
| company | portfolio | ratings | Decision (3 runs) |
|---|---|---|---|
| JPM | standard | Underweight, Hold, Underweight | 6.57 (6.3, 6.9, 6.5) |
| JPM | bank as the large position (about 39%, 15% loss budget) | Underweight x3 | 6.70 (6.6, 6.6, 6.9); no CF3 or CF5 |
| PGR | standard | Underweight x3 | 6.87 (7.0, 6.6, 7.0) |
| UNH | standard | Underweight (one run, not scored) | - |
| CVX | standard | Underweight (one run, not scored) | - |
Bank and insurer path verdict: passes the install rule (three runs, both kinds of portfolio); scores sit in the same range as MSFT (6.2 to 6.7) and WMT (7.1).
OBSERVATION for the quality loop: of the eight companies' latest runs, every one rates Underweight except one JPM Hold. A tool that gives one answer to a bank, an insurer, an oil company, a health insurer, a retailer and two technology companies is not telling them apart. Not diagnosed. Candidates: the fixed 9.88% required return, downside-weighted scenario sets, a manager that reads any shortfall against the hurdle as Underweight.
Backlog with cause: COP, NEE, PLD (lines filed under names not read); IBM (financing arm); XOM (new registrant); SNOW (analyst submitted no scenarios, once).
Total paid spend to date: about 134 dollars.

## Quality loop restarted on the eight (user: "yes", 2026-11-12). First target: nearly every company rates Underweight
Free diagnosis from 90 saved runs with accepted scenarios (all eight companies, every batch since the noise baseline):
- Ratings: 60 Underweight, 13 Sell, 6 Hold, 11 Overweight. Every Overweight is MSFT. 81 percent negative.
- Weights are the same shape for every company: base about 0.50, downside about 0.30, upside about 0.18 (CAT 0.51/0.31/0.18; DOCN 0.48/0.36/0.17; MSFT 0.53/0.30/0.17; WMT 0.52/0.28/0.21; JPM 0.52/0.32/0.17; PGR 0.52/0.25/0.23; UNH 0.50/0.30/0.20; CVX 0.62/0.28/0.20). The downside gets about 1.7 times the upside's weight whatever the company.
- Scenario values today against the close, mean: base -2.6 to -15.5 percent for every company but MSFT (+3.6); downside -24 to -48; upside +10 to +42. The central case sits a little under the price once discounted at the 9.88 percent required return, i.e. the analysts' central cases are roughly "the stock goes sideways".
- Weighted value against the close, mean: CAT -10.1, CVX -19.9, DOCN -12.2, UNH -9.3, WMT -13.2, MSFT +0.2. With equal weights: CAT -5.7, CVX -21.8, DOCN -4.2, UNH -5.7, WMT -12.2, MSFT +3.8. So the weights explain about 8 points on DOCN and 4 on CAT and UNH, and almost nothing on WMT and CVX, where the scenarios themselves are low.
- Every base case (68 of 68) applies a lower multiple than the price pays today, on average 20 percent lower. Partly proper (a forward multiple on higher forecast earnings), so not proof of bias on its own.
- Then the rating: anything short of the required return is rated Underweight; there is no middle band (the earlier MSFT finding).
Reading: three things stack in the same direction: central cases anchored near the current price so they miss a 9.88 percent hurdle; a fixed downside tilt in the weights that does not vary by company; and no Hold band. None of this says the ratings are wrong (no outcome has settled), only that the tool is not discriminating.
Not built. Each candidate fix changes what the manager is asked or what a rating means, so they go to the user.

### Equal weights as the starting point (user: "test it"; bench, NOT installed) - partial batch
Check run and batch on bench head; fresh runs. OpenRouter ran out of credit mid-batch (HTTP 402): JPM x3 and WMT x2 failed and are owed. Completed:
| company, portfolio | weights used | weighted value vs close | ratings | Decision before | after |
|---|---|---|---|---|---|
| MSFT, standard | 0.33/0.33/0.33 in 3 of 3 (was about 0.53/0.30/0.17) | -2.4, -0.3, +2.3 | Underweight x3 | 6.2 to 6.4 (fresh) | 6.33 (6.5, 6.3, 6.2) |
| DOCN, concentrated | 0.33/0.33/0.33 in 3 of 3 | -6.9, +1.4, -6.7 | Underweight x3 | 7.17 | 7.17 (7.1, 7.1, 7.3) |
| WMT, standard | 0.33 x3 (one run) | -15.6 | Underweight | 7.07 | not scored |
Reading: the instruction is followed every time, so the habit in the weights is gone. Scores do not move, and neither do the ratings: every run is still Underweight, two of them (MSFT +2.3, DOCN +1.4) with the valuation above the close; the MSFT one drew CF3 for it. So the weights were not what makes everything Underweight. What is left: central cases near today's price against a 9.88 percent hurdle, and no Hold band. Verdict held until the five owed runs are in; nothing to keep or revert on score.
Also built, bench only: the required-return premium can be set in the portfolio file (default unchanged).
Proposed to the user, not built: "Conditional Hold" (within 3 points of the required return; chosen by the manager; code checks consistency only).
Total paid spend to date: about 141 dollars.

## Aperture loop CLOSED (user, 2026-11-12). Improvement loop restarted on a new yardstick
Aperture end state: eight kinds reach a valued decision (DOCN, MSFT, WMT, CAT, CVX, JPM, PGR, UNH); backlog with cause: COP, NEE, PLD, IBM, XOM, SNOW.
Agreed with the user, replacing score-chasing on single evaluator complaints (most fixes moved less than the noise; one company improved in two days and about 141 dollars):
1. Two rating fixes: the caller's own required return in the portfolio file (built), and Conditional Hold.
2. Validate both on both made-up portfolios.
3. Look-back test: run as of past dates on the eight and compare ratings with what the shares then did. First a free check that an as-of run cannot see later information.
4. Choose what to improve next from that.
Blocked for paid runs: the provider account is out of credit (the user's to top up).

### Conditional Hold built (bench, NOT installed) and what the free replay says about it
Built with tests: band of 3 points of yearly return either side of the required return, or the figure in the portfolio file (`hold_band_points`); inside it a Hold is printed as a Conditional Hold with its conditions, any other rating owes a reason other than this valuation (asked once), and code never changes a rating. Suite 4,829.
Free replay over 88 distinct saved runs: only 9 fall inside a 3-point band (7 MSFT, 2 DOCN). Gap to the required return, points, median (min to max): CAT -17.4 (-33 to +12), CVX -19.4, DOCN -8.5 (-57 to +1), MSFT -1.0 (-8 to +10), UNH -9.0, WMT -49 (-71 to -11; the early runs carry the short-period distortion).
Reading: the uniform Underweight is NOT a matter of narrow misses. For every company but MSFT the accepted scenarios return far less than 9.88 percent a year. The Conditional Hold is right for MSFT-like cases and will change little else. The dominant cause is the first one: how the scenarios themselves are built (central cases near today's price; every base case on a lower multiple than the price pays). Whether that bearishness is right is a question about outcomes, not report quality.

### Look-back test, free pre-check (2d-1)
Source acquisition run as of 2026-08-03 for MSFT, DOCN, JPM: no filing dated after the date, no reporting period after it, price session 2026-08-03, latest documents 2026-07-23 to 2026-07-29. The filed data and prices are clean as of a past date.
NOT clean, and no code can fix it: (a) the model itself may know what happened after the date if the date falls inside its training period; (b) news, social and vendor feeds are not all dated (the vendor estimates reader already refuses past dates; StockTwits and headlines return recent items). So a look-back is only meaningful for dates after the model's knowledge cutoff, with the undated feeds switched off or accepted as degraded, and only short horizons (5, 21, 63 sessions) will have matured. The model's cutoff is not known to me and must be established before any paid look-back run.

### Model knowledge cutoff, probed (two calls, a few cents; 2026-11-12)
`openai/gpt-6.1-terra-pro`, asked from memory with no tools, "unknown" allowed: knows MSFT diluted EPS for the quarters ended 2025-03-31 (3.46), 2025-09-30 (3.72) and 2025-12-31 (5.16, reported late January 2026) and the year ended 2025-06-30 (13.64). Says unknown for WMT year ended 2026-01-31 (reported mid-February 2026), DOCN calendar 2025 (February 2026), and everything reported later (MSFT year to 2026-06-30, the 2026 quarters). It did not know DOCN quarterly revenue even for 2025, so small-company figures are a weak probe.
Reading: knowledge ends about late January to early February 2026. A look-back date from 2026-05 onward is outside it with margin.
Look-back design that follows: as-of dates 2026-06-01, 2026-07-01, 2026-08-03 for the eight companies; analysts limited to market and fundamentals (news and social feeds are not dated and would leak); outcomes at 21 and 63 trading sessions against SPY, all matured by 2026-11-11. 24 runs, about 24 dollars. Small and overlapping sample: evidence, not proof.

### Validation batch for equal weights + Conditional Hold (12 fresh runs s17/t17, bench head; NOT scored)
All 12 reached a valued decision; equal weights in 11 of 12 (one DOCN 0.40/0.40/0.20). Ratings: 11 Underweight, 1 Hold (JPM). Conditional Hold printed in 0 of 12.
The finding that matters: the rating no longer follows the valuation at all.
- MSFT, three runs: scenarios return +9.8, +12.0 and +7.3 percent a year against a required 9.98, all inside the 3-point band. All three rated Underweight. The manager's stated reason (s17b): "valuation alone offers little support for an underweight ... The trim instead reflects ... the portfolio's existing NVDA and AAPL exposure."
- DOCN on the concentrated portfolio (t17a): scenarios worth 23.4 percent ABOVE the close, +32.4 percent a year against 9.98. Rated Underweight. Reason: "the Underweight call is not supported by that scenario valuation alone. Preserve a 5% position for upside rather than exit."
Reading: the rating is carrying two different things. One is the view of the stock (is it worth more than its price). The other is what to do with this portfolio's position (it is 39 percent of the book, so reduce it; it sits beside two other technology holdings, so trim). When the position is large or the book is concentrated, the second swamps the first and everything reads Underweight whatever the valuation says. That is the user's parked decision "split the stock view from the position action" (map 2a-5), and it explains the uniform Underweight better than weights, bands or the required return did. The Conditional Hold cannot work while the rating means both.
Not scored: the mechanism is visible in the reports; scoring would cost 12 evaluations to confirm a contradiction the reports state themselves.
Total paid spend to date: about 154 dollars.

## Look-back test, first pass (2026-11-12; user approved; 24 runs as of 2026-06-01, 2026-07-01, 2026-08-03; market and fundamentals analysts only; `scripts/lookback_outcomes.py`)
17 of 24 runs reached a rating. Not rated: DOCN x3 and CVX x3 stopped at REVIEW on all three past dates (DOCN: a debt-like line on the filed balance sheet not classified; CVX: cash spending not established), so coverage depends on the date as well as the company; JPM as of 2026-08-03 failed on the model's context limit.
Price change after the rating, less SPY's over the same sessions:
| rating | count | 21 sessions: mean, share below the market | 63 sessions: mean, share below the market |
|---|---|---|---|
| Overweight | 3 (MSFT x2, PGR) | +8.0, 1 of 3 | +17.4, 0 of 3 |
| Hold | 2 | -2.0, 1 of 2 | -1.6, 1 of 2 |
| Underweight | 12 | +1.3, 6 of 12 | -4.0, 8 of 12 |
Directional calls right: 8 of 15 at 21 sessions, 11 of 15 at 63. Rank correlation between the valuation against the close and the later excess return: 0.40 at 21 sessions, 0.92 at 63 (12 runs with a valuation figure; JPM and PGR carry none in the card).
Reading, with its limits: at about three months the ratings and, more strongly, the valuations pointed the right way. That is the first evidence that the tool's caution is not simply a habit. It is thin: 17 ratings from six companies, windows that overlap, the 0.92 resting largely on MSFT (rose) and CAT (fell) appearing on all three dates, one market period, and a cut-down pipeline (no news or social analyst). At one month there is no signal.
Total paid spend to date: about 178 dollars.

## The split: stock view and position action (user decision 2026-11-12; bench, NOT installed)
Built, tests first (suite 4,838): the manager gives `stock_view` (Attractive, Fair, Unattractive: the stock alone) and the rating becomes the position action. Code prints its own reading of the accepted scenarios beside the view (yearly return against the required return; the 3-point band is Fair) and asks once for a reason when view and reading differ, or when action and view point different ways (then the reason must be about the position or portfolio, and the view is not to be changed to fit). The report opens with the stock view above the rating. Code changes neither. A decision with no stock view is read as before. The Hold-band sentence was taken out of the manager's instructions: "Fair" carries it.
Note: the manager's prompt is at its 70,000-character test limit; one heading line had to be dropped to fit.
Check run (v19a, DOCN on the concentrated portfolio): "Stock view: Attractive (code's reading: Attractive, +19.9% a year against 9.98%)"; "Position action: Underweight ... DOCN is 40.4% of this portfolio, versus the 5% ... reduce concentration while retaining a core." The two answers are now apart and each is stated with its own reason.
Running: measured batch (MSFT x3, WMT x3 standard; DOCN x3 concentrated; JPM x3 bank-concentrated) and the look-back re-run (24 runs, tags ls0601/ls0701/ls0803).

### The split: measured batch and look-back re-run (2026-11-12; bench head; fresh runs)
| company, portfolio | stock view / code's reading | position action | Decision before | after (3 runs) |
|---|---|---|---|---|
| MSFT, standard (held at standard weight) | Fair / Fair x3 | Underweight x3 | 6.33 | 6.10 (6.2, 6.3, 5.8) |
| WMT, standard (not held) | Unattractive / Unattractive x3 | Underweight x3 | 7.07 | 7.03 (7.0, 7.0, 7.1) |
| DOCN, concentrated (39% held) | Attractive, Unattractive, Unattractive (matches the reading each time) | Underweight x3 | 7.17 | 7.13 (7.0, 7.0, 7.4) |
| JPM, bank as the large position | Fair x3 (no reading printed) | Underweight x3 | 6.70 | 6.57 (6.8, 6.5, 6.4) |
Verdict: no score movement (all inside noise). The split does what it was built for: the two answers are apart, the manager's view matched code's reading in every run, and the uniform Underweight is now visibly the position action. What the split exposes on MSFT, and evaluators mark down (CF3 on 3 of 3): the manager trims a position that is at its standard weight on a stock it calls Fair, and its stated reason restates the valuation rather than giving a portfolio reason. That is the next target, and it is the manager's (and the Research Manager's) habit of caution, not a wording problem.
Gaps seen: JPM and PGR cards carry no valuation against the close, so no reading and no position-action line print for them; DOCN's view flips between fresh runs because its scenarios do (carry-forward steadies this in normal use).

Look-back re-run on the split (24 fresh runs, tags ls*; 17 rated; DOCN and CVX again at REVIEW on past dates):
| stock view | count | 21 sessions vs SPY | 63 sessions vs SPY |
|---|---|---|---|
| Attractive | 3 | +8.0 | +17.4, none below the market |
| Unattractive | 14 | +0.8 | -3.7, 9 of 14 below the market |
Directional calls right: 9 of 16 at 21 sessions, 12 of 16 at 63. Rank correlation of valuation with later excess return: 0.27 and 0.83. A second independent set of runs gave the same picture as the first (11 of 15; 0.92), which makes a fluke less likely; the sample limits are unchanged.
Total paid spend to date: about 214 dollars.
