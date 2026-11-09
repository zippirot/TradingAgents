# Decision-quality step tests — 2026-11-09

Plan: `~/Claude/2026-11-09-tradingagents-decision-quality-step-tests-plan.md` (approved 2026-11-09).
Branch `claude/step-tests-20261109`, worktree `~/Worktrees/step-tests`.

## Starting point

- Start commit: `b47fb367c5d0247976834aa0fd86b81697b5d92a` = GitHub `staging` on 2026-11-09.
  Staging contains Build W (`7364abfc` is an ancestor), so no dependency on an unintegrated branch.
- The launcher checkout is at the same commit (`claude/installed-report-followup-b47fb367`).

## Status

**Blocked before the baseline run.** The OpenRouter key in the TradingAgents `.env` is rejected
with `401 API key expired` (checked 2026-11-09 three times; it served run `eea86100` at 14:07 the
same day). No paid call has been made. Spend so far: $0 of every limit.

## Build 1: the single-step tool (`scripts/step_tests.py`)

Subcommands: `baseline`, `prove`, `step`, `recall`.

- **Task 0 decision (provisional, to be confirmed by the faithfulness proof):** load each start
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

Not run (blocked). Command, once the key works:

```bash
cd ~/Worktrees/step-tests
/Users/zipp/Documents/ChatGPT/Tauric/TradingAgents/.venv/bin/python scripts/step_tests.py baseline --root ~/Worktrees/step-tests-runs/baseline --ledger ~/Worktrees/step-tests-runs/ledger.jsonl
```

## Tests

| # | Result | Measured cost | Keep or drop |
|---|---|---|---|
| T1 | not run | — | measurement |
| T2 | not run | — | measurement |
| T3 | not run | — | measurement |
| T4 | not run | — | — |
| T5 | not run | — | — |
| T6 | not run | — | — |

## Spend

| Limit | Cap | Spent |
|---|---|---|
| Baseline | $12 | $0 |
| Development | $25 | $0 |
| Final confirmation | $12 | $0 (conditional) |
