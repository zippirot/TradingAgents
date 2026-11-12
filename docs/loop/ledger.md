# Loop ledger

Target: Investment Decision Quality. Evaluator skill version is recorded with every score; scores across versions
are not compared. Differences under 0.3 between runs of the same code are treated as noise.

## Scores (one row per evaluated run)

| cycle | date | company | run | code | Decision (holistic / weighted) | Research | Operational | D1 | D2 | D3 | D4 | D5 | D6 | D7 | caps | evaluator | run cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2026-11-11 | DOCN | 46c345dc (Sell) | 2ff7a43c | 7.5 / 7.5 | 8.2 | 3 | 7.0 | 7.8 | 7.4 | 8.0 | 7.5 | 7.2 | 8.5 | CF3, CF6, CF10 | Claude helper, TAE-1.1-loop1 | 1.35 |
| 0 | 2026-11-11 | MSFT | 3d4741a9 (Underweight) | 2ff7a43c | 6.3 / 6.4 | 7.4 | 3 | 6.0 | 7.0 | 6.3 | 6.5 | 5.5 | 6.3 | 7.8 | CF3, CF4, CF6, CF10 | Claude helper, TAE-1.1-loop1 | 1.11 |
| 0 | 2026-11-11 | WMT | 7897e51f (Hold) | 2ff7a43c | 5.5 / 5.0 | 6.0 | 3 | 2.5 | 6.0 | 6.0 | 4.5 | 5.5 | 6.5 | 7.5 | CF1, CF3, CF6, CF10 | Claude helper, TAE-1.1-loop1 | 0.83 |
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

## State

2026-11-11: baseline (cycle 0) complete, 3.30 dollars spent. The user put cycle 1 ON HOLD while they finish the loop's design; do not start a fix or a paid run until they say so. Loop runs use a made-up portfolio with none of the three stocks held, so ratings are not comparable with the user's own runs.
