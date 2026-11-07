# Build C: Settlement and publication reliability

Build size: medium
Recommended model: GPT-6 Sol (`gpt-6-sol`), medium reasoning, as selected by the user. The settlement, identity and recovery contracts require integrated negative/reload proofs and independent review. Estimate: 8–12 active implementation/proof hours; credits not credibly estimable.

Independent audit: required

User approved Build A integration/push and Build C start on 2026-11-07. Local staging, origin/staging and GitHub staging were verified at `77ebc8abc30757f4bab0c106df9e3b56cd12aebf` after the authorized fast-forward/push. D1 and A are present with committed acceptance/audit records. Production remains `9ade69bf155d1b25699d3aecfff3c1b07752aff0`. Worktree `/Users/zipp/Documents/ChatGPT/Tauric/worktrees/settlement-reliability`, branch `codex/settlement-reliability`, created at that exact staging commit. Only C1–C5 are authorized here. No Build B start, subsequent integration/push, release, install or cleanup is authorized.

Implementation notes (requirements unchanged): publication settlement uses a per-pass price source; legacy reflection policy is retained. Ambiguous Yahoo no-price exceptions remain retryable. Calendar mismatch proof is bounded to independently published SPY/NYSE Arca2026 holiday closures; unsupported calendars/years remain retryable. Manual maintenance is documented in `docs/maintenance/publication-outcomes.md`. Verified source6649f23d passes3186 tests and Ruff; the real DOCN clone reports35 immature endpoints with one price read and no reflector call. Independent audit is pending; no C completion or integration authority is implied.

The original full plan is `/Users/zipp/Claude/2026-11-07-evidence-settlement-and-ops-gap-closure-plan.md`. The following frozen sections govern this handoff.

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

---

## Build C — Settlement and publication reliability

**Worktree slug:** `settlement-reliability`.

### Task C1: Reuse price series without shortening an endpoint's window

**Owner:** `tradingagents/memory/settlement.py` (price-window calculation and outer pass) and `tradingagents/memory/publication_outcomes.py`. Tests: `test_publication_outcomes.py`, `test_mature_session_settlement.py`, `test_settlement_coverage_reason.py`, `test_calendar_outcomes.py`.

- For pending publication endpoints, share the instrument and benchmark series across the actual settlement pass, including repeated records for a symbol and shared benchmarks across tickers. Fetch each needed symbol once over the necessary date range through the exclusive completed cutoff, not a fixed six months plus padding. No fetch for already terminal endpoints. Slice the shared input per record with the original publication-time, exchange-timezone, price adjustment, entry, exit and benchmark policies intact; no current or future bars. No persistent cache or change to legacy reflection policy.
- [ ] Test call counts across multiple records/tickers, repeated symbols and benchmarks, and the resulting prices/dates against the existing independent outcome fixtures. Exercise delayed entry after suspension and sparse trading sessions, including a six-calendar-month exit measured from the actual entry. Preserve existing completed-cutoff, coverage and timezone regressions.

### Task C2: Terminal states, retryable failures and honest counts

**Owner:** `settlement.py` for classification and result propagation; `publication_outcomes.py` for companion validation, writes, reload and summary; `graph/trading_graph.py::_memory_step` for the user-visible note.

- Settle a priced outcome only from its actual first eligible instrument close and observed horizon. Never interpret `None`, a single missing row or elapsed time alone as terminal. A verified `exact_sessions` calendar mismatch may be `unresolvable`; an absent benchmark row or a failed fetch alone is retryable, and never licenses `asof`.
- **Persistent zero instrument coverage:** Mark an endpoint `unresolvable` after **three distinct settlement runs** each return a verified zero-session response for the entire eligible instrument window after the nominal horizon, with **at least 14 calendar days between each counted run** (at least 28 days from first to third). Record the reason as “No eligible instrument sessions on three post-horizon checks”; this stops automatic retries, not a finding that the issuer delisted or the investment lost value.
- **When counting can start without an instrument entry:** Use the endpoint's existing historical/prospective entry cutoff (respect the actual publication time for prospective records). For this retry policy only, use the first eligible completed benchmark session after that cutoff as the reference: require the benchmark to have also completed the declared number of subsequent sessions, or to have a completed session on or after the declared calendar-month anniversary. This is a nominal horizon for scheduling checks, never an instrument entry, price, return or proof of actual maturity. If benchmark coverage or the entry cutoff cannot be verified, keep pending without counting.
- Count only an explicit provider no-data response or a successful, well-formed response with zero eligible instrument sessions for the full interval. `get_closes` currently collapses some missing/malformed responses to an empty series: preserve the distinction in the settlement fetch path; exceptions, outages, rate limits, empty results of unknown origin, short/partial coverage and failed benchmark reads never count. Any verified eligible instrument session clears the zero streak and resumes ordinary settlement. Store at most three dates and distinct pass identifiers per endpoint in the existing locked, hash-checked companion; app retries, restart or concurrent passes cannot double-count. Between counted checks do not fetch solely to recheck that endpoint before its next due date.
- **Manual reopen:** Document one local maintenance invocation taking the publication ID and endpoint name. Under the existing lock, validate the companion, reopen only that zero-coverage terminal endpoint to `pending`, and reset its retry evidence. Preserve the reason and terminal/reopen timestamps for historical reporting; do not edit the immutable publication, delete the companion, or reset sibling outcomes. No automatic reopen or new service.
- Preserve `ineligible` and old companions. Validate terminal status, bounded reason and timezone-aware `known_at` on write **and read**, against the original eligible endpoint and immutable publication identity; reject malformed combinations. Surface terminal outcomes with their reason only at/after that knowledge time, once per endpoint in a summary; never fetch solely for them while terminal or count them as resolved performance. Propagate distinct counts through `settle_all_pending` into `_memory_step`. Report “await maturity” only for immature endpoints and “could not be settled this run” only for retryable failures. A failed benchmark keeps its dependent endpoints retryable without blocking unaffected benchmarks.
- [ ] Prove immaturity, temporary failure and recovery, delayed instrument entry, and a verified exact-session mismatch. For the zero-coverage rule, use distinct runs at day 0, 13, 14, 27 and 28 after the nominal horizon: only 0/14/28 count. Include a pre-horizon attempt, duplicate run, partial data, provider/benchmark outage and a positive instrument row that clears the streak. Reopen the store between attempts. Verify the third qualifying run writes the reason, subsequent runs make no endpoint-only request, and a manual reopen followed by restored prices settles the right endpoint without changing siblings or historical visibility. Reject corrupt companions; a failed benchmark must not block another benchmark.

### Task C3: Evidence is read only when an endpoint resolves

**Files:** `tradingagents/memory/publication_outcomes.py::settle_publications`. Verify the evidence snapshot at most once per record in the pass, after the first valid resolving outcome and before committing it. Existing integrity checks for writes stay in place.
- [ ] `test_settlement_pass_does_not_read_evidence_when_nothing_resolves` (patched `load_evidence` counter → 0). Implement, run, commit.

### Task C4: Isolate bad files on reads; protect publication identity on writes

**Owner:** `tradingagents/memory/publication.py` and callers in settlement, memory notes and report listings. `list_records`, exact reads, publication writes and decisions needing a complete history remain strict by default. Opt in to a tolerant scan only for read-only listings and settlement of independently verified records. Return/report skipped integrity failures with that scan; do not keep a process-global list. Do not skip a corrupt record to select a prior thesis or assign a primary, sequence or revision link. A corrupt file of unknown identity can affect global ordering; publication must stop visibly before writing a new canonical record.

- [ ] Damage a primary in a disposable store; show unaffected entries can still be listed/settled with a visible omission count. Attempt same-ticker/same-day publication while the file is unreadable: assert no new canonical publication. Restore it, publish normally, and verify unique increasing sequence, one primary and an intact revision link. The audit simulation of skip-on-write produced two primaries, both sequence 1. Cover strict readers and a clean subsequent scan.

### Task C5: Memory-log append is atomic

**Files:** `tradingagents/memory/log.py::store_decision` (~line 76), `tests/test_memory_log.py`: write `raw + entry` to a temp file and `replace_file`, under the existing lock.
- [ ] `test_partial_append_cannot_swallow_next_entry` (simulate a crash after a partial write by writing a block without `ENTRY_END`, then `store_decision`; assert the new entry is indexed and the partial block is quarantined into `<log>.partial-<timestamp>.md`). Implement, run, commit.

### Build C proof
- `pytest -q` green; `ruff check`.
- On Machine 2, copy the DOCN ledger to a disposable results tree; pin the clock to the historical proof date and replay recorded series. Exercise the actual graph memory step with an empty/disposable legacy memory log and a no-call reflector. Inspect the operator note and durable companions for immature, retryable, resolved and terminal cases as applicable. Add controlled historical cases for outcomes absent from DOCN. Reopen the store and verify recovery, summary cutoffs, identity and the three-check timeline. Demonstrate that a terminal endpoint stops fetching and that the documented manual reopen can resume settlement. No live ledger writes or paid reflections.

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

