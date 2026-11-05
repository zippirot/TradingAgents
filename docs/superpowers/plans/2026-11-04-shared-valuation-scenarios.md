# Shared valuation scenarios before the investment debate

Date: 2026-11-04. Historical implementation plan. **Current status:** this subset is implemented and verified on the approved A/B/C base `f1e846d67bd9d02446956df882650f4eedac3a1b`; preserve the original technical scope below as a reference, and reuse its evidence rather than rebuilding it. See `docs/reviews/2026-11-04-shared-valuation-evidence.json` and `2026-11-04-shared-valuation-staging-integration.md`.

## Outcome and size

Give the bull and bear researchers the same small, calculated scenario table before their first arguments. They should identify the assumptions they accept or dispute and explain the implications. Keep the Portfolio Manager's final target calculation and publication validation authoritative.

Success for the reader: the report makes clear what assumptions support each scenario, what the debate challenges, and which financial implications were actually calculated.

- **Build size:** small.
- **Recommended model:** GPT-6 Sol (`gpt-6-sol`), **medium reasoning**, following the user's model-selection policy. Existing valuation contracts and focused integration tests make this bounded engineering work; no new financial model is required. This is engineering judgment, not a measured speed comparison. [Official model documentation](https://developers.openai.com/api/docs/models/gpt-6-sol) confirms the model and effort support; it identifies GPT-6.1 Sol as newer, but this recommendation preserves the user's stated GPT-6 Sol baseline.
- **Historical active implementation and verification estimate:** **4–7 hours**, assuming the existing development environment and fixtures are usable. Includes focused checks, one final offline suite and report inspection; excludes approval or unavailable-provider waits.
- **Codex credits:** no credible range without measured usage for this workload. API prices do not establish Codex credit consumption.
- **Runtime cost:** no additional model invocations or data requests by design. Added prompt/report tokens can increase existing-call cost. The prior live proof and its evidence are complete. New A/B/C paid work follows the approved USD 100 combined ceiling in the governing plan (USD 70 for at most seven Shallow live proofs including retries; USD 30 for independent audit/rechecks; Codex credits separate).

## Current execution boundary and historical baseline

The original small task was verified and integrated before this A/B/C worktree was created. Its historical estimate and task list below document that completed scope. The active governing plan is [DOCN review gap closure](2026-11-04-docn-review-gap-closure.md): use the existing isolated `/Users/zipp/Documents/ChatGPT/Tauric/worktrees/docn-abc-gap-closure` worktree and `codex/docn-abc-gap-closure` branch at base `f1e846d67bd9d02446956df882650f4eedac3a1b`. Do not create another valuation worktree, reimplement these tasks, or integrate intermediate slices into staging. No launcher changes, merge, push, PR, deployment, installation or worktree cleanup are authorized by the A/B/C plan.

The earlier Machine 1 and `b075166df6f1738ef691cee23d1473e5085e05a1` observations belong to the historical planning baseline, not the current implementation baseline. The launcher remains unchanged. Verify the completed valuation contracts on current source before extending them in Build B. Reuse recorded evidence when source, dependencies and assumptions still match; rerun affected checks after relevant changes.

## Scope and approach

Use the current sequence with one deterministic addition inside the existing Evidence Check:

```text
Existing analyst calls
  → existing evidence/accounting checks
  → calculate shared scenarios, when supported
  → existing bull/bear debate and Research Manager
  → existing Trader and risk debate
  → existing Portfolio Manager target calculation and publication validation
```

The fundamentals analyst supplies optional scenario inputs in its normal final response. Code calculates the results using `validate_target` in `tradingagents/agents/valuation.py` and `grounded_outlooks` in `valuation_outlooks.py`. The model does not supply authoritative prices.

Support the existing EV/revenue and P/E methods only, with one method per shared table. Scope follows the existing eligible SEC-stock evidence path. Missing scenarios do not create a new REVIEW condition or block an otherwise permitted debate; existing insufficient-evidence REVIEW still stops it.

**Excluded:** DCF, discounting, derivatives, reverse valuation, price feeds or return-to-current-price calculations, portfolio sizing, new agents/providers/dependencies/configuration, more debate rounds, mid-debate calculator tools, automatic repair/recalculation loops, and claims of improved investment performance. Debate proposals for different numbers remain unvalidated until the existing final calculator evaluates an explicit request.

## Task 1 — Prepare a bounded, optional scenario package

**Files:** `tradingagents/agents/analysts/fundamentals_analyst.py`; new `tradingagents/agents/shared_valuation.py`; reuse `valuation.py` and `valuation_outlooks.py` without changing their formulas or final-request contracts.

**Implementation:**

- Add one named `valuation_scenarios` JSON fence to the fundamentals analyst's normal output instructions, alongside the existing financial-claim/disclosure fences. The payload is a list of at most three `{name, request}` entries. An empty list is valid when inputs or method suitability are inadequate. Do not force scenarios for every company.
- Reuse existing EV/revenue or P/E request types. Each EV/revenue entry contains exactly one scenario with `weight=1`, solely to evaluate that row independently through the existing API. Do not compute or display an early weighted target or probability. P/E entries use the existing single-request form.
- Require explicit assumptions and rationales, exact source fact IDs, and the existing management-outlook grounding rules. The analyst normally supplies `analyst_forecast` assumptions: downstream grounded outlook IDs do not yet exist in its tool context, so it must not manufacture them or self-certify management guidance. The calculator still compares assumptions with grounded outlooks when available. Never invent source IDs, debt components or shares, or silently substitute adjusted for GAAP earnings. Choose a suitable supported method and explain the choice; do not infer suitability merely because arithmetic is possible.
- Keep independently valid rows comparable: common method, units, period and accounting basis; for EV/revenue, common source baseline, capital snapshot, share count and obligation perimeter; for P/E, common EPS baseline/share basis and historical-versus-forecast basis. Forecast amounts and multiples may differ. Reject a mixed collection with a clear reason rather than presenting incomparable prices as one range.
- Follow the existing bounded named-fence parsing pattern: exactly one matching fence, bounded payload size, at most three uniquely named entries, and no evaluation of embedded instructions. Missing/duplicate/oversized/malformed blocks yield an unavailable result. Preserve valid rows when an individual request fails, identify omitted rows and label a partially available table. No repair call or invented defaults.
- Store JSON-safe requests, successful `TargetResult` values, warnings and rejection reasons in one optional `shared_valuation_scenarios` state record. Use Decimal calculations already provided by the calculator. Rendering must identify forecasts and multiples as assumptions, prices as conditional scenario outputs, and future-period values as undiscounted to today.

**Verification:** reuse synthetic valuation fixtures to prove exact EV/equity/share and P/E results, source references and assumption labels; malformed/absent blocks; row isolation; mixed-basis/period rejection; no probabilities or combined target; and unchanged rejection of unsupported DCF, missing facts and incompatible capital inputs. Do not duplicate the calculator's entire test suite.

## Task 2 — Make the scenarios available before debate

**Files:** `tradingagents/graph/setup.py`, `tradingagents/agents/state.py`, `tradingagents/agents/context.py`, `tradingagents/agents/researchers/{bull,bear}_researcher.py`, `tradingagents/agents/managers/research_manager.py`.

**Implementation:**

- At the tail of the existing Evidence Check node, evaluate the optional package against the merged post-check state. Reuse the original fundamentals text retained in `financial_claim_validation.raw_report`; the gate replaces `fundamentals_report` with its checked summary. No new graph node, analyst output channel, network request or model call is necessary.
- Skip calculation for insufficient evidence and out-of-scope runs. An eligible run with unavailable scenarios receives a short reason; it follows the existing decision path. Do not change evidence quality or the financial fact package based on optional scenario availability.
- Extend the existing shared context path (`get_instrument_context_from_state`) to provide the same deterministically rendered table to downstream agents. Keep conditional scenario assumptions visibly separate from historical facts. Both debaters and the Research Manager must receive it directly; subsequent decision agents receive it through that same path.
- Ask each debater to identify the relevant scenario/assumption, support agreement or disagreement with evidence, and explain what would change the case. Neither side is required to adopt the analyst's base scenario. Numerical alternatives stated in debate remain model claims; do not label them recalculated.
- Ask the Research Manager to distinguish disputed assumptions from established inputs. Preserve existing ratings, debate order/counts, portfolio blindness for research agents, and absent-report behavior. Keep the table unchanged throughout debate.

**Verification:** run the graph with mocked models and recorded/synthetic evidence; assert preparation precedes the first bull turn, both sides and the Research Manager receive identical rows, scenario preparation makes zero model/network calls, and existing call counts remain unchanged. Cover fundamentals-disabled/non-SEC/crypto scopes, REVIEW bypass, malformed scenarios and ordinary fallback. Inspect generated prompts for explicit assumption challenges.

## Task 3 — Publish the table and preserve final authority

**Files:** `tradingagents/reporting.py`, `tradingagents/graph/trading_graph.py`; touch `agents/output_validation.py` or `report_html.py` only if an actual publication caller requires it. Inspect, preserve and test `agents/managers/portfolio_manager.py` and its final validation behavior.

**Implementation:**

- Show one compact **Shared valuation scenarios — conditional research inputs** section with the fundamentals/evidence presentation in existing Markdown/HTML reports and the corresponding CLI report view. Include method, horizon, source IDs, assumptions, calculated prices, warnings and omitted-row reasons. Keep existing model narrative readable and separately labeled. Do not present a scenario as the final `Price Target`.
- Retain the optional scenario record in existing full-state logs and `evidence.json`; do not create another report system or change historical artifacts. The Python state exposes the same record. Re-export must not duplicate the table or mutate state. Publication must replay saved requests against canonical evidence rather than trust stored calculated prices, matching the existing final-target principle.
- The Portfolio Manager may use or revise early assumptions, but must continue producing its existing final `valuation_request`. Do not automatically select an early row, copy its price into `target_validation`, or bypass `validate_target`/`enforce_publication`. Missing/invalid final requests and free-text fallback still omit the final target. No numerical sizing is introduced, and decision memory retains its existing canonical content.
- Add a run-signature version marker for the new pre-debate inputs so an old checkpoint cannot resume past scenario preparation with incompatible prompts. Preserve old checkpoint files; absence of the optional record remains readable in legacy exports. Test same-version recovery without repeating completed analyst calls.

**Verification:** render and inspect Markdown/HTML with valid, partially available and absent scenarios. Test direct rendering, saved reports, CLI/Python state and repeat export. Tampered stored scenario prices must not become checked outputs. Verify an early valid scenario plus invalid final request still yields no final target, and a different valid final request is recalculated independently. Preserve REVIEW, canonical memory and final target omission tests.

## Task 4 — Verify the complete small change and record its limits

Use a new `tests/test_shared_valuation.py` for the adapter and extend existing integration tests. From the implementation worktree's development environment, after the focused checks pass:

```sh
python -m pytest -q tests/test_shared_valuation.py tests/test_valuation.py tests/test_portfolio_valuation.py tests/test_evidence_gate.py tests/test_graph_end_to_end.py tests/test_structured_agent_prompts.py tests/test_evidence_reporting.py tests/test_output_publication.py tests/test_stream_publication.py tests/test_reporting.py tests/test_report_html.py tests/test_checkpoint_resume.py tests/test_review_authority.py tests/test_review_memory_backtest.py
python -m pytest -q
python -m ruff check .
python -m pip check
git diff --check
```

Confirm test names/environment before execution; extend the focused selection only for affected callers. The final offline suite is warranted by shared agent context, checkpoint signatures and publication paths. Keep existing external-service test exclusions; record skips and do not claim remote CI passed before an authorized publication triggers it.

The representative live smoke for this subset is recorded in the shared-valuation evidence. For new B extensions, use the governing A/B/C plan's bounded live-proof path and combined budget; this historical task does not separately authorize another paid call. Inspect the actual scenario inputs, calculated table, first bull/bear arguments and final target/omission. If all scenarios are omitted, investigate the specific cause; it proves fallback handling, not successful use. Do not add repeated paid attempts or weaker validation to obtain a passing example. If no budget/provider is available, keep live acceptance explicitly pending rather than claiming it is proved by mocked tests.

Inspect the complete diff and report artifacts before completion. Record the exact commit, check results, live-proof status, meaningful adjustments and remaining limits in the existing review-document location; commit implementation and evidence on the isolated branch. No profitability/backtest project or layered review workflow is part of this small change.

## Acceptance and deferred work

This subset was accepted when supported scenarios reached both debaters before their first arguments; assumptions and disagreement are understandable in the report; optional scenario failures do not change existing evidence policy; final targets are still independently validated; required checks and the bounded live proof pass; and all task changes are committed. No claim that arbitrary reasoning is verified or investment returns are improved.

The historical subset has no unresolved product choice. The A/B/C extensions follow the governing plan. Deferred: additional valuation methods, verified calculations during debate, calibration of scenario probabilities, and evidence that this change improves investment outcomes. Revisit only after observing whether the shared table improves actual reports.
