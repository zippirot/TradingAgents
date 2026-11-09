# Decision-quality step tests — 2026-11-09

Plan: `~/Claude/2026-11-09-tradingagents-decision-quality-step-tests-plan.md` (approved 2026-11-09).
Branch `claude/step-tests-20261109`, worktree `~/Worktrees/step-tests`.

## Starting point

- Start commit: `b47fb367c5d0247976834aa0fd86b81697b5d92a` = GitHub `staging` on 2026-11-09.
  Staging contains Build W (`7364abfc` is an ancestor), so no dependency on an unintegrated branch.
- The launcher checkout is at the same commit (`claude/installed-report-followup-b47fb367`).

## Status

Complete through T6. The key was renewed on 2026-11-09 (the earlier one returned `401 API key
expired`; no paid call was attempted with it). Final confirmation run: see below.

## Build 1: the single-step tool (`scripts/step_tests.py`)

Subcommands: `baseline` (also the final run, `--budget final`), `prove`, `step`, `recall`,
`disclosures` (re-runs the real Evidence Check offline on a Fundamentals output; $0 cap).

- **Task 0 decision (confirmed by the proof below):** load each start
  point's input from the run's own LangGraph checkpoint, which the baseline keeps by disabling
  only the post-success checkpoint cleanup. The alternative, rebuilding the input from the final
  state log, is also implemented so the proof compares both. The final log keeps only end values
  (for example the Research Manager may revise the shared valuation cases, and the risk debate's
  per-speaker fields are not logged), so it is expected to miss. Checkpointing does not enter the
  run signature (`_NOT_IN_SIGNATURE`) and changes no prompt.
- Steps are the real node runnables from `TradingAgentsGraph.workflow` (the same `observed_node`
  wrappers the graph runs), with the launcher's settings: OpenRouter, Opus 5.5 quick, GPT-6.1 Terra
  Pro deep, 3 debate and 3 risk rounds, default reasoning effort, SDK retries 0.
- Fetched inputs replay from the run's trace (`ReplaySession`); a miss is fetched live and counted.
- The advisory audit is not re-run when a test continues to the Portfolio Manager; the baseline's
  audit is reused.
- Cost meter: refuses, before it is sent, any call that could pass the cap (conservative estimate:
  prompt characters / 3 tokens plus 12,000 output tokens at list rate); records each completed call's
  tokens and the provider-reported cost (list rate when none is reported); a failed call keeps its
  reservation. One ledger per budget spans all invocations. Unknown models are refused.
- Isolation: every run writes under `~/Worktrees/step-tests-runs/<name>/`; a path inside
  `~/.tradingagents` is refused. The baseline seeds copies of the launcher's cache (no checkpoints),
  publications and memory file, so it starts from what the launcher's next run would read. Only
  `OPENROUTER_API_KEY`, `SEC_EDGAR_USER_AGENT`, `FRED_API_KEY` and `ALPHA_VANTAGE_API_KEY` are read
  from the `.env`; none is printed or written.

### Verification so far

- Full offline suite at `26dd4d57`: 4120 passed, 10 skipped (private DOCN fixtures absent), 1 deselected; Ruff clean. Interim only; the final commit is re-run.

- `tests/test_step_tests_tool.py`: 12 passed (scripted, offline): checkpoint proof reproduces the
  Research Manager, first risk turn and Portfolio Manager prompts exactly; a changed prompt is
  reported with its first difference; onward runs follow the graph's routing; the meter refuses,
  records, de-duplicates and rejects unbudgeted models; launcher paths are refused; recall windows.
- `$0` dry run of the baseline (`--dry-run`, placeholder key, $0 cap) on real DOCN data: seeding,
  unattended CLI, trace and kept checkpoint all worked; the first model call was refused unsent;
  imports came from this worktree (an earlier dry run exposed that `python scripts/...` loaded the
  main checkout's package; the script now pins and checks its own checkout). Launcher home unchanged.
- T1 recall check exercised on the older traced run `Na-DOCN` (2026-11-07 code): 12 of 15 facts
  reached Bull and Bear there. Not a T1 result; T1 runs on the baseline.

## Baseline run

- Run `8f9378ac-c7a9-4ea8-9647-c980513ecff5` (attempt `153128-a109f3a4`), DOCN, 2026-11-09, on
  `b47fb367` through `scripts/step_tests.py baseline` (the real CLI, traced, checkpoint kept,
  disposable directories under `~/Worktrees/step-tests-runs/baseline`).
- Outcome: **Underweight**, evidence quality `limited` (not REVIEW); 31 graph model calls plus the
  Trader's recovered retry (32 metered), 2.02M input / 0.13M output tokens.
- Cost: **$8.53** by OpenRouter's key usage (fresh key, $0 before); $8.56 by the tool's ledger.

### Build W live checks (from the baseline)

| Check | Result |
|---|---|
| No duplicate condition rows | **Pass**: 10 stored thesis conditions, 0 duplicates, all have a thesis role |
| Zero recovered Trader fallbacks | **Fail (1)**: the Trader's structured call returned no parsed result (`ValueError: structured output returned no parsed result`; Opus answered in plain text). The free-text retry succeeded, one extra Opus call. Out of this plan's scope; recorded for the user. |

## Faithfulness proof (free)

`prove` on the baseline: the checkpoint rebuild reproduces the recorded prompt **exactly** for all
four start points (Fundamentals analyst, Research Manager, first risk turn, Portfolio Manager). The
final-state rebuild misses all four: the final log holds values rewritten after the decision (the
instrument context and the Trader plan's sizing relabel), and Fundamentals' message history is not
logged. Task 0: checkpoint.

## Tests

Before side of every test: baseline `8f9378ac`. Costs are the tool ledger's provider-reported
figures.

| # | Question | What was run | Result | Measured cost | Keep or drop |
|---|---|---|---|---|---|
| T1 | Do known facts reach Bull and Bear? | `recall`, 15 facts (`2026-11-09-step-tests-facts.json`) | **13 of 15** reach both. Missed: FY2026 non-GAAP EPS $1.60–1.62 and the ~$472M 2030-notes repurchase. Both were in the Fundamentals analyst's tool results but not in its report; the EPS record was among the 7 rejected disclosure records (block-48); the repurchase was never submitted. Both survive only as raw source blocks in state. | $0 | measurement |
| T2 | Is the decision stable on identical inputs? | Portfolio Manager ×3, Research Manager ×3 | **Stable.** PM Underweight 3/3, RM Underweight 3/3 (baseline Underweight both). RM key numbers agree (Q4 guide $348–351M, RPO $799.7M, GAAP gross margin 50.15%, EBITDA 42–43%). PM conditions vary in count (2–4 vs baseline 2); the $87 price trigger is in all three; one repeat added an EBITDA-margin < 42% trigger. | PM $0.37, RM $0.11 | measurement |
| T3 | Does the prior rating anchor the new one? | Research Manager ×3 with prior thesis withheld (trace confirms no prior rating in prompt) | **No anchoring seen**: Underweight 3/3, same as with the prior thesis. The debate itself never mentions the prior thesis. No onward run needed. | $0.25 | measurement |
| T4 | Do the risk roles argue their own direction? | Free read of the baseline's 9 risk turns | **Pass on the baseline; no fix tried.** Round 1: Aggressive = hold (differs from the Trader's trim), Conservative = reduce faster, Neutral = reduce modestly; each lists what would change it. Figures not in a turn's own prompt (e.g. $515.7M conversions, $134.1M year-end RPO) all appear earlier in the run's source records or debate. | $0 | no change |
| T5 | Lessons digest for the Research Manager and risk roles | Prompt change (digest after the debate history / round instruction); free prove confirmed only that text changed; RM ×3 | **Dropped.** Underweight 3/3, and none of the three plans used or mentioned the digest, so "used where relevant" is not shown; by the plan the risk roles are not run when the RM output does not change. Reverted (diff kept at `step-tests-runs/t5-dropped.diff`). | $0.29 | **drop** |
| T6 | Fewer model-caused disclosure rejections | Prompt change: one worked record per kind (fictional values) showing `period_locator`; Fundamentals ×3 (third cut off by a session kill); real Evidence Check re-run offline | **Kept.** Baseline 1 accepted / 7 rejected (all "period not in quoted span", `period_locator` omitted); re-check reproduces this exactly. With the change: 5/3 and 8/1. All 13 accepted records in the two re-runs checked against the press release: correct values, periods and heading locators, 60%+ still guidance; no incorrect acceptance and no example value leaked. Caveat: two earlier unchanged runs had 0 and 2 rejections, so part of the baseline's 7 may be chance. | $3.31 ledger + ~$0.57 for the cut-off repeat (OpenRouter counter) | **keep** |

Kept change: `679a0bd4` (`tradingagents/agents/analysts/fundamentals_analyst.py`, regression test
`tests/test_disclosure_worked_examples.py`).

## Final confirmation run

- Run `0355c9ad-5a9b-4562-bfb7-0fdb2c95e9c0`, DOCN, 2026-11-09, on `f00390fb` (product code identical
  to `679a0bd4`; the later commit only names the run's budget), same settings and disposable seeding
  as the baseline (`~/Worktrees/step-tests-runs/final`).
- Outcome: **Underweight**, evidence `limited`, publishable decision recorded; 30 graph model calls;
  no fallback or other non-completed operational observation; 12 thesis conditions, 0 duplicates.
- T6 end to end: model disclosures 5 accepted / 2 rejected (baseline 1 / 7). All 5 accepted records
  are correct (Q3 revenue $321M; Q4 guide $348–351M; FY2026 revenue $1.208–1.211B, EBITDA margin
  41–42%, adjusted FCF margin 20–22%). Rejections: one quote carried a prior-year clause (correctly
  refused); one supplied `value_quote` without the required `period_locator` (model error the
  examples do not cover). No example value appears in the output.
- Cost: **$8.33** (OpenRouter counter 13.42 → 21.75).

## Spend

| Limit | Cap | Spent (OpenRouter counter) |
|---|---|---|
| Baseline | $12 | $8.53 |
| Development | $25 | $4.90 (ledger $4.32 + one call cut off mid-flight) |
| Final confirmation | $12 | $8.33 |
| Total | $49 | $21.75 |
