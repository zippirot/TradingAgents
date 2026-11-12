# Improvement loop

Plan: `~/Claude/2026-11-12-tradingagents-improvement-loop-plan.md`. This folder is the loop's working record, so a
session that has lost its context can resume from here.

**The one score the loop works on is Investment Decision Quality** (TAE-1.1, D1 to D7). Research and Operational are
guardrails: a fix that lowers either by more than 0.3 on a company is reverted or taken to the user.

Settings (user's answers, 2026-11-12): 5 cycles; 50 dollars per cycle; Shallow depth only; `openai/gpt-6.1-terra-pro`
for both models; companies DOCN, MSFT, WMT; runs from this worktree with their own results folder.

| File | What it is |
|---|---|
| `ledger.md` | One row per baseline score and per fix. The loop's memory. |
| `state.json` | Paid runs with their measured cost, per cycle. Written by `scripts/loop_run.py`. |
| `portfolio.loop.json` | Made-up portfolio used for loop runs. The user's own file is never read. |
| `evaluator-skill-TAE-1.1-loop1.md` | Copy of the evaluator skill the scores were produced with (frozen for the loop). |

Tools (run from the worktree with `PYTHONPATH=$PWD` and the launcher's Python):

| Step | Command |
|---|---|
| Replay every saved run through today's code | `scripts/replay_runs.py replay --out DIR` (add `--logs ~/.tradingagents/loop/logs` for loop runs) |
| What a code change moved | `scripts/replay_runs.py compare BEFORE AFTER` |
| Every saved model answer of a kind against today's code | `scripts/answer_corpus.py check --kind valuation_cases` |
| One paid Shallow run | `scripts/loop_run.py --ticker WMT --cycle N` (`--dry-run` to see it first) |
| Check an evaluator's record | `scripts/loop_eval_check.py RUN/reports/evaluation.json` |

Where things are: loop runs under `~/.tradingagents/loop/logs/<TICKER>/<date>/<run>/reports/`; the user's own saved
runs (read only) under `~/.tradingagents/logs/`; baseline copies under `~/.tradingagents/loop/baseline/`.

Evaluation: a fresh helper is given only the report folder and the skill, never what was changed. It writes
`evaluation.md` and `evaluation.json` beside the report.

Not allowed without the user: merge, push, install, production promotion, worktree removal, other depths or models,
anything that changes what a rating means or how a money figure is defined.

## Rules added after cycle 1 (2026-11-11)

1. **One run before three.** After a fix passes the free checks, pay for one run and read it. Only then repeat to three.
2. **Reached a decision.** A run that stops at REVIEW has no Decision score. `scripts/loop_noise.py` reports "reached a decision N of M" beside the averages; a fix that raises the average by losing runs is not a gain.
3. **Coverage.** Before and after any reader change, count how many stored companies are open: `scripts/large_filer_score.py score --tickers ... --store ~/.tradingagents/private/large-filer-20261111/store --out FILE` (field `open`). The 20-company fresh set is in `~/.tradingagents/private/fresh-cohort-20261111/store`; use it to check a claim of general coverage, and do not tune on it more than has been done.
4. Every run uses `--date 2026-11-11` so price and filings are the same in every cycle, and `--fresh TAG` so repeats do not see each other.
