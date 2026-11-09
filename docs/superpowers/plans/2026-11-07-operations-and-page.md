# Build D: Required operations and report behavior

Build size: medium
Recommended model: GPT-6 Sol (`gpt-6-sol`), medium reasoning, user-selected. Provider-error/truncation boundaries, historical price basis and actual offline CLI recovery require integrated verification and independent audit. Estimate: 8–14 active implementation/proof hours; credits not credibly estimable.

Independent audit: required

Authorized start, 2026-11-07: user approved exact Build B staging integration/push and D start. Fetched and compared local staging, origin/staging and GitHub staging at bd27b742e6346ff7e6bd22f1823e263934f3e1aa; inspected six B commits and clean B branch. Fast-forwarded/pushed exact B handoff 1b0ffc4fd5118e4ed99b360fa949ed4d40929514, refetched and verified all three staging refs matching. D1/A/C/B predecessors present. Production unchanged 9ade69bf155d1b25699d3aecfff3c1b07752aff0. Branch codex/operations-and-page and isolated worktree /Users/zipp/Documents/ChatGPT/Tauric/worktrees/operations-and-page begin at exact B staging commit. Only D2–D10 authorized; D11 explicitly excluded. No D integration/push, release/install or cleanup authority.

External governing plan: /Users/zipp/Claude/2026-11-07-evidence-settlement-and-ops-gap-closure-plan.md. Frozen approved sections follow; no requirement change.

## Branch and Release Boundary


- **Feature completion — Machine 2.** Only after a build start is authorized, fetch remote refs and compare the intended local `staging` SHA to canonical GitHub `staging`. If they differ, report both and stop before branching; do not silently pick one or rewrite either. From the verified exact commit create a new `codex/<build-slug>` branch and isolated worktree at `~/Documents/ChatGPT/Tauric/worktrees/<build-slug>`. Develop, run proofs and commit code and verification evidence there. No ordinary development on `main`, `staging` or `production`.
- **Development integration.** Feature completion leaves a verified local commit. Only explicit development-integration approval permits integration into `staging`; push GitHub `staging` only if that approval explicitly authorizes the push. Staging remains unreleased. Before any dependent build, verify its prerequisites are actually present at its new staging baseline.
- **Stable release.** Only separate, explicit stable-release approval permits integrating the exact verified staging state into `production`. Push GitHub `production` only if explicitly authorized. No passing check authorizes a merge, fast-forward, push, deployment or app replacement.
- **Machine 1 installation and acceptance.** Only after deliberate promotion and publication to GitHub `production`, and when the release authorizes installation, Machine 1 pulls the exact resulting production commit and builds, installs, launches and verifies that stable version. Machine 1 acceptance is not a prerequisite for development. Machine 2 uses the isolated worktree and disposable copies for runtime proof; neither installed launcher is a proof target.

## Global Constraints


- No new dependencies. No network in tests (`_no_network` autouse fixture). No paid model calls for proof.
- A4 is the sole intentional change to rating eligibility (see the separate decision below). No task dictates a directional rating, sizes a position, or adds an operator confirmation to the product.
- New filing records carry `source_id`, locator(s), `content_hash` and `filed_date`; calculated rows cite their verified inputs. These are filing statements or calculations, never forecasts or newly accepted valuation balances.
- Exception text from vendors never reaches model prompts or state; record `type(exc).__name__` only.
- Each handoff must pass the full default `pytest -q` and repository `ruff check` on the tested candidate; record actual counts and exclusions. Reuse unaffected evidence without representing checks from different commits as one run.

## Review Focus

Cross-cutting cases; each is proved by the named owning task.

1. A forecast in a different currency or unit string from the baseline must be rejected before the magnitude band is applied (A1).
2. Two retained disclosures filed the same day with conflicting guidance for one period must ground neither (A2).
3. A convertible-note sentence that names a principal but no maturity, or a maturity in the past relative to `as_of`, must produce no record (B1).
4. A failed benchmark fetch leaves dependent, otherwise evaluable endpoints pending with a retryable failure; unrelated benchmarks and already terminal endpoints are unaffected (C2).
5. The Copy All button must copy nothing but the page's own text: no script URL, no clipboard write of HTML (D1).

## Build D — Operations and the report page


**Worktree slug:** `operations-and-page`. This final required handoff owns D2–D10. D11 is listed last as an optional follow-up; it is outside Build D implementation, proof and audit.

### Task D2: A log file per run

**Files:** `cli/run.py::run_analysis` (before the `Live` context); `tests/test_cli_headless.py` (new tests beside the existing headless-run tests).
- Produces: `_configure_run_logging(results_dir: Path) -> Path` installing one `logging.FileHandler(results_dir / "run.log")` at `WARNING` on the root logger (removing a previous run's handler first), format `%(asctime)s %(levelname)s %(name)s: %(message)s`. After "Analysis Complete!" print `Run log: <path>`. In `_offer_reports`, log a sanitized diagnostic with stack location. On an interactive save failure offer one retry with a fresh path; unattended mode reports failure without prompting. Do not persist raw provider diagnostics or credentials in this handler.
- [x] `test_warnings_reach_run_log`, `test_report_save_failure_is_logged_with_traceback_and_retried_once`. Implement, run, commit.

### Task D3: A run directory per attempt

**Files:** `cli/run.py::_run_directory` and the `message_tool.log`/`reports` wiring (~line 136–141); `tradingagents/graph/trading_graph.py::_log_state` (~line 702).
- Produces: `_run_directory(config, ticker, trade_date, attempt_id)` → `results_dir/<T>/<date>/<HHMMSS>-<attempt_id[:8]>/`. `_log_state` writes `full_states_log_<date>_<run_id[:8]>.json` and also rewrites `full_states_log_<date>.json` as the latest (so existing snapshots and the replay technique keep working).
- [x] `test_two_runs_same_day_keep_both_report_sets`, `test_state_log_is_written_per_run_and_as_latest`. Implement, run, commit.

### Task D4: Cost line and source revision

**Files:** `cli/run.py` (after "Analysis Complete!"), `cli/stats_handler.py::get_stats`, `tradingagents/graph/trading_graph.py::run_settings`, `tradingagents/report_html.py::_run_details`, `tradingagents/reporting.py` header, `tradingagents/default_config.py` and `cli/updates.py`.
- Print observed `Tokens: <in> in / <out> out (<coverage>)`; never turn unavailable usage into zero or label a partial estimate as the whole run. Show an estimate at configured per-million prices only when both prices are present and valid and usage is observed. Save source fingerprint and provider effort as producing-run metadata; use the existing `publication_versions["code"]` fingerprint and label it as a source hash, not a Git SHA. Re-export uses retained provenance, not today's installation. Parse `TRADINGAGENTS_NO_UPDATE_CHECK` with the existing boolean convention so `0` means the check is enabled. The launcher’s `.env` suppression is already complete; no tracked launcher override or second configuration change.
- [x] `test_cost_line_prints_only_with_configured_prices`, `test_run_settings_include_source_revision_and_effort`, `test_no_update_check_zero_means_enabled`. Implement, run, commit.

### Task D5: Save-path prompt cannot take "y" as a folder

**Files:** `cli/run.py::_offer_reports` (~line 452).
- Produces: `_resolve_save_path(answer: str, default: Path, results_dir: Path) -> Path`: empty → default; `answer.strip().lower()` in `{"y", "yes", "n", "no"}` or shorter than three characters → re-prompt once, then default; a relative path resolves under `results_dir / "reports"`.
- [x] `test_save_path_y_is_rejected_and_default_used`, `test_relative_save_path_lands_under_results_reports`. Implement, run, commit. The original stray directory was already removed; no cleanup action belongs to D5.

### Task D6: Reasoning effort on OpenRouter

**Files:** `tradingagents/llm_clients/factory.py::build_llm_kwargs`, `tradingagents/llm_clients/openai_client.py` (`_PASSTHROUGH_KWARGS` loop ~line 398), `cli/selections.py` (~line 343), `tests/test_openrouter_model_select.py`.
- Produces: for provider `openrouter`, `openai_reasoning_effort` is forwarded as `extra_body={"reasoning": {"effort": <value>}}` (verify the parameter name against OpenRouter's reasoning documentation at build time and record the URL in the commit); the native-OpenAI model regex gate is skipped for OpenRouter; the CLI shows the Step 8 effort prompt for OpenRouter; any configured effort that a provider adapter drops logs `logger.warning("reasoning effort %r not forwarded to provider %r")`.
- [x] `test_openrouter_forwards_reasoning_effort_in_extra_body`, `test_dropped_effort_is_warned_not_silent`. Implement, run, commit.

### Task D7: Keep raw vendor exceptions out of downstream messages

**Owner:** `tradingagents/dataflows/router.py` (vendor errors returned as text, including optional categories), `tradingagents/graph/setup.py` (escaped tool exceptions), `tests/test_analyst_execution.py` and router tests. Keep safe, bounded typed reason codes; do not interpolate vendor exception messages into sentinels, retained tool evidence, logs introduced here or model prompts. Preserve actionable, locally generated no-data reasons and existing vendor fallback behavior.

- [x] With a dummy secret in an exception, exercise **both** a raised tool exception and a router-returned unavailable sentinel through the real graph. Verify the run continues, the next agent receives the unavailable message, and the raw diagnostic is absent from retained messages, evidence and the new log.

### Task D8: Mark the output actually delivered when it was truncated

**Owner:** `tradingagents/operational_capture.py`, `agents/analysts/turn.py`, `agents/structured.py` and their research/trader/risk/portfolio callers where a raw response becomes text. Reuse the existing finish/stop-reason detection (including generation metadata) at the point where raw metadata is still available; the structured helper returns a parsed model, not a raw message. Keep typed contracts and rating parsing intact; tag the narrative presented downstream, not JSON used for validation.

- [x] With offline responses, inspect the **next prompt** or advisory audit input for the truncation note on analyst, wrap-up, structured and free-text fallback paths. Verify a complete fallback after a truncated failed attempt is not labeled truncated, a truncated fallback is labeled, an ordinary stop is unmarked, and the operational footer does not count an event twice.

### Task D9: Identify reports for which all requested tools returned no usable data

**Owner:** `tradingagents/graph/setup.py::_analyst_graph.finish` and retained tool evidence. For at least one actual request and no usable result across its matching tool outputs (typed errors and returned `DATA_UNAVAILABLE:` / `NO_DATA_AVAILABLE:` sentinels), prefix the report with a plain warning and set `all_tools_failed` in the evidence. State precisely that these tool calls supplied no support; distinguish any independently supplied shared filing evidence.

- [x] Exercise all failed, mixed success, zero calls and separately supplied evidence. Inspect the next prompt, retained report and evidence flag, not only the footer event count.

### Task D10: Verify historical split basis before removing later rows

**Owner:** `tradingagents/dataflows/vendors/yahoo/ohlcv.py::load_ohlcv`; `tests/test_ohlcv_latest_bar.py`. On historical requests verify split actions and sufficient coverage **before** filtering to `as_of`, on both the download and cache-hit paths. Request actions; an old cache without trustworthy action data must take the existing refetch/verification path or return typed unavailable. Follow `price_observation._verify_adjustment_basis` for failure semantics. Never pass future rows, split ratios or later action dates into historical model inputs.

- [x] Test a later split (unavailable), split only before cutoff (comparable), verified absence, and a legacy/missing-actions cache with successful and failed verification. Inspect the resulting tool response and cutoff on the data actually delivered.

### Build D proof
- `pytest -q` green; `ruff check`.
- On Machine 2, launch the real CLI from the worktree with disposable results, a fake/local model and recorded vendor data; block external network and isolate credentials. Exercise normal completion, one save failure/retry and an interruption/restart. Inspect the actual attempt directories, warning logs, summary and reopened reports. A Ctrl-C against a live model is not an offline proof. D1's browser proof belongs to D1; repeat only if D changes its output or script.

---

## Integrated acceptance


Independent audit: required

- **One owner per required handoff, in order:** D1 owns the real local HTML-to-clipboard result; A owns valuation validation, guidance retention, A4 eligibility, decision comparison and the A7 evidence disposition; C owns the ledger/outcome lifecycle and memory note; B owns extraction from validated full filing text and companyfacts, delivery to real prompts and export; D2–D10 own the remaining operator changes. D1 is complete or incomplete on its own. At each authorized start verify the necessary predecessor evidence and code at the exact staging SHA. B does not need A3 to retain its passages. D11 cannot block the five builds, their audits, integration or release.
- On Machine 2 exercise the smallest working user/system path first; fix any runtime blocker before broadening it. After hardening, re-run the complete affected path from its real trigger, using the handoff's prescribed disposable inputs. Record the observable output and destination in `docs/reviews/<date>-<slug>.md`. Fake only external providers needed for a no-cost replay, not the application path under proof. An unexercised required path remains incomplete.
- **Each of D1, A, C, B and D:** full default `pytest -q` and `ruff check` clean on the candidate; record exact tested SHA, results and limitations. Use the existing independent Claude review route evidenced in `docs/reviews/2026-11-07-operational-report-audit-acceptance.md` (frozen range, bounded executor, existing authorized spend limits). The marker above declares the requirement; it does not launch or pay for an audit. During future authorized work, commit the governing requirements for that handoff (including the marker and proof) at a repo-relative path on its isolated branch; the standalone file in `~/Claude` is not a frozen input. Provide the approved runner the frozen requirements, relevant source, receipts and sanitized proof. Verify its required inputs are available at that SHA; never claim a self-review, missing packet or capped review as complete.
- Reproduce each High locally against the candidate; distinguish the implementer's reproduction from what a read-only auditor actually ran. Fix confirmed in-scope findings with regression evidence and re-audit the final change. Close with no open in-scope Critical/High/Medium; document lower findings and dispositions, or “no gaps found.” Identify the final feature commit, verified candidate, audited range and any evidence-only follow-up accurately. Passing this gate grants no integration or release authority.
- **Not applicable to these development proofs:** broker/trade execution, production databases and deployment. The touched persistence is the existing local ledger and run/report files. No new service, database migration, retention daemon or Machine 1 install is required.

## Not in scope

- Historical-backtest reflection costs and calendar-day sampling (November 6 audit A12) are deferred. C changes publication endpoint settlement; it is not a backtest/legacy-reflection redesign.

- Changes to the Build 2 case contract, the Portfolio Manager's valuation request or the card's basis rule. Build 2 is shipped at the baseline; this plan only reads its records (A6) and extends its magnitude check (A1).
- A second LLM audit of the Portfolio Manager's final text. If wanted later, do it as a code check of cited F/C numbers, not another deep-model call.
- Multi-class peer share structures (CRWV). Its exclusion reason stays as is.
- Deterministic macro arithmetic in the news analyst (the CPI annualization slip). Record as a prompt note only.
- Locking the decision horizon by configuration. A6 makes a horizon change visible; forcing a value is a product decision the user has not made.
- Reducing `source_references` in publication records (A2 of the audit's settlement finding). C1–C3 remove the per-run cost that made it matter; revisit if records exceed 1 MB.
- Checkpoint binding to the source hash. Completed runs delete their checkpoint; the exposure is crash → edit → resume, and the manual version tokens cover it today.
- Prompt-injection hardening of the wrap-up turn (tool results replayed as human turns). Design-level; needs its own discussion.

## Limits to state in the report

- A convertible-note "stated plan" is management intent on the filing date, not a completed transaction.
- Uncommenced lease commitments are undiscounted future payments, not a present-value liability, and are not added to any enterprise-value perimeter.
- Cash plus marketable securities is statement liquidity, not unrestricted valuation cash.
- "Changed since the prior run" rows describe the model's assumptions, not new evidence.


## Execution checkpoint — final local handoff

D2–D10 complete locally. Corrected application/tests15657050; full3309 tests,10 skips,1 deselection,100 subtests; full Ruff clean, actual offline CLI normal/retry/resume and preserved Safari/Chrome copy proof. Initial and closure Claude audits completed; material D7 and D5 corrections closed, lower findings/turn-counter discrepancy recorded in docs/reviews/2026-11-07-operations-and-page-acceptance.md. Closure manifest validated verified/complete atdce9bba1; final records only. All25 Goal tasks reconciled, D11 excluded. No D integration/push, production advancement, install or cleanup authority.
