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
