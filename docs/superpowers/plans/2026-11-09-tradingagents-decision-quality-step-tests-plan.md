# TradingAgents decision quality: cheap step tests

Drafted by Claude on 2026-11-09. **Approved by the user on 2026-11-09 with the stated limits ($25 development cap, no automatic retries). Start when the user issues the goal.** Reviewed against the repository the same day; the changes from that review are listed at the end.

**Goal:** Test the changes most likely to improve the final decision without paying for full runs during development. Build one small tool that re-runs a single step from a saved run, then use it for six tests. Full runs are limited to two: one traced baseline at the start, and one confirmation at the end only if a change is kept.

**Separate from:** `2026-11-08-large-filer-evidence-coverage-plan.md`. That plan owns everything about large companies reaching a rating (MSFT, CAT, the seven source checks). None of that work is in this plan.

Independent audit: required

## Delivery estimate

Build size: **small**. Recommended implementer: as in the table below. (Repository copy: this line restates the table's build size for the audit tool; the plan is otherwise verbatim.)

| | |
|---|---|
| Build size | Small |
| Recommended model | GPT-6 Sol (`gpt-6-sol`), medium reasoning, in Codex. In Claude Code: `claude-sonnet-5-5`, medium. |
| Active implementation and verification | 10–16 hours, including the independent audit and one round of gap closure |
| Baseline run | One traced full DOCN run, about $9–11 (prior measured cost per run), cap $12. It doubles as the confirming run Build W still owes, so it is not an extra run. Skipped if a traced run on the exact starting commit already exists. |
| Model spend during development | Estimated $6–15; cap **$25**. Not measured: see Costs. |
| Final confirmation | One full DOCN run, about $9–11, cap $12, **only if at least one prompt change is kept** |
| Independent audit | Separate from the caps above; the audit tool sets its own limit from the build size (the last, much larger, audit cost $6.43) |
| Codex credits | No credible estimate: the repository has no comparable usage measurements |

Sol is enough: the tool is a thin wrapper around existing step functions, and each prompt change is small and local. The hard part is judging outputs, which the pass rules and the audit handle. This is engineering judgment, not a measured comparison.

## Costs

- A full run makes 32 model calls and reads about 2.05M tokens (run `2a2e47dd`, 2026-11-09). There is no per-step breakdown today, so step costs below are estimates from call counts.
- Hard ceiling for everything in this plan except the independent audit: $12 + $25 + $12 = **$49**, and at most two full runs. Expected spend is lower.
- The tool records tokens and cost for every call it makes. After the first test, replace these estimates with measured figures.
- The "before" side of each comparison is the baseline run, so only the "after" side is paid.
- No automatic retries. Stop and report at the cap.

## Constraints

- No change to rating eligibility, publication gating, evidence-gate rules or numeric validation.
- Every existing safety and labelling instruction stays in the prompts.
- **Keep-or-drop:** a prompt change is kept only if its test passes. A change that fails, or whose result is unclear, is removed before the final commit and recorded as dropped.
- Every run in this plan, including the two full runs, writes to disposable results, cache and memory directories. Nothing writes to the real memory file, the launcher's logs or its publications.
- API keys are read from the existing `.env` and never printed, logged or committed. The tool reuses the trace recorder's redaction.
- No merge, push, install or promotion without separate approval.

## Starting point

The starting commit must include Build W of the report-defect plan, because W changes the risk, Portfolio Manager and Fundamentals prompts this plan tests. Checked 2026-11-09: GitHub `staging` is at `0236255d` and does **not** contain W; W is finished and audited at `7364abfc` on local branch `claude/report-defect-closure-20261109`, not integrated.

- If `staging` contains W when work starts, branch from that exact `staging` commit.
- If it does not, branch from the tip of `claude/report-defect-closure-20261109` and record that this branch can only be integrated after W is.
- Work in a new isolated worktree, slug `step-tests`. Record the exact starting commit.

## Baseline run

No saved run can serve as the "before". The two installed runs (`520623df`, `2a2e47dd`) were made without a prompt trace and before Build W. The traced runs under `audit-artifacts/workflow-gap-live-2026-11-08/` are from older code.

- Make one full DOCN run on the starting commit with `TRADINGAGENTS_TRACE=1`, same settings as the installed launcher (Opus 5.5 quick, Terra Pro deep, 3 debate and 3 risk rounds). This is also Build W's confirming run: record W's live checks (zero recovered Trader fallbacks, no duplicate condition rows) in the same review file.
- If the run stops at REVIEW or fails, stop and report. Do not retry.
- Every later test uses this run's saved state and trace.

## Build 1: the single-step tool

**Files:** one new script under `scripts/`, with focused tests. No production code changes.

- Load a saved run's full state (`full_states_log_<date>_<id>.json`), clear everything the chosen step and later steps wrote, and call the real step functions from `tradingagents/graph/setup.py` from that point, stopping at a named step.
- Task 0, before anything else: decide between calling the step functions directly on the saved state and forking from a LangGraph checkpoint. Pick whichever reproduces the original inputs exactly. If neither can, stop and report.
- **Proof it is faithful (free):** with no changes, the prompt the tool builds for each supported step must match, character for character, the prompt recorded in the baseline run's trace (`trace/NN-<stage>.jsonl`, `model_start` events). This check makes no model calls. A step whose prompt cannot be matched is not used for tests; report it.
- Supported start points: Fundamentals analyst, Research Manager, first risk turn, Portfolio Manager.
- Output per test: the step outputs, rendered prompts, tokens, cost, and a side-by-side of rating, key numbers and conditions against the saved run.

## Tests

Each test uses the baseline run as the "before". Staged so the cheapest check runs first and the wider one only if it shows a difference.

| # | Question | Step(s) re-run | Passes when | Est. cost |
|---|---|---|---|---|
| T1 | Evidence recall: do 10–15 known facts (the $1B ATM, RPO history, FY2026 outlook) reach the debate inputs? | None: code on saved data | Each fact is present in the material handed to Bull and Bear, or the miss is named with its cause | Free |
| T2 | Is the decision stable? | Portfolio Manager ×3, then Research Manager ×3 | Same rating all three times; key numbers and conditions agree | ~$2 |
| T3 | Does the prior rating anchor the new one? | Research Manager with the prior thesis withheld; onward only if the recommendation changes | Reported as a finding either way; no code change in this plan | ~$1–4 |
| T4 | Do the risk roles argue their own direction? The instruction and the research plan are already in the prompts (confirmed in source), so this first reads the baseline run. | None at first. Only if the baseline fails: one prompt fix, then round 1 of the three risk roles, then the full risk debate and Portfolio Manager | Each role states its own direction with the evidence that would change it; at least one differs from the Trader or says why none does; every number still traces to evidence | Free, then ~$1–4 if a fix is tried |
| T5 | Lessons shared with the Research Manager and risk roles (today only the Portfolio Manager gets them, confirmed in source) | Research Manager; onward only if its output changes | The digest is used where relevant and never overrides current evidence; Bull and Bear prompts are unchanged | ~$1–4 |
| T6 | Fewer model-caused disclosure rejections, by adding one worked example per record type. Skip if the baseline has none. | Fundamentals analyst | Rejections below the baseline run's count, with no new incorrect acceptance | ~$2 |

T3 is a measurement only. T4, T5 and T6 are the only tests that can change a production prompt, each under keep-or-drop.

Order: T1 and T2 first, because they are the yardstick for the rest. If T2 shows the decision is unstable on identical inputs, stop and report before T4–T6: on/off comparisons would not be readable.

One sample per side cannot separate a real effect from run-to-run variation. Where a result is close, repeat that step twice more within the cap, or record it as unclear and drop the change.

## Final confirmation

Only if at least one prompt change is kept: one full DOCN run on the final commit, in disposable directories. If nothing is kept, the baseline run already covers the final code and no second run is made. It checks what step tests cannot: that the whole pipeline still produces a publishable decision and that the kept changes behave the same end to end.

## Acceptance

Independent audit: required

- Full offline suite and Ruff green at one commit.
- The faithfulness proof passes for every start point used in a test.
- Total spend is reported against each cap, with the measured cost per step.
- Each test has a recorded result, cost and keep-or-drop decision in `docs/reviews/<date>-step-tests.md`, with the saved run ID and exact commit.
- Independent audit before any merge request. Every confirmed in-scope finding is fixed on the same branch with a regression test and re-checked.

## Not in scope

- Large-company evidence coverage (its own plan).
- Scoring decisions against later prices. Wanted later; `tradingagents/backtest.py` exists and should be reviewed when that work is planned.
- Changing debate rounds or which model each role uses.

## Decisions for you

1. ~~Approve the build and the $25 development cap?~~ Approved 2026-11-09.
2. **The baseline run and the conditional final run** (up to $12 each) are new since approval. Issuing the goal with those limits approves them.
3. **Order versus the large-filer plan.** That plan already waits for Build W to be integrated, and so does integrating this one. Recommended: this one first. It is small and its tool makes later testing cheaper.

## Review changes, 2026-11-09

Checked against the repository after approval:

- **Starting commit must include Build W.** W changes the prompts under test and is not in `staging` yet.
- **A traced baseline run is required.** No existing run has both a prompt trace and current code, so the free faithfulness proof had nothing to compare against. The run doubles as W's confirming run.
- **T4 starts as a free check.** The own-direction instruction and the research plan are already in the risk prompts.
- **The final run is conditional** on a change being kept.
- **Full runs also use disposable directories**, so nothing reaches the real memory file or the launcher.
- Count corrected from five tests to six; audit cost stated separately.
