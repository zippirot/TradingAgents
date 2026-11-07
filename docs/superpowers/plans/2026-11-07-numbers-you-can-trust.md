# Build A: Numbers you can trust

Build size: medium
Recommended model: GPT-6 Sol (`gpt-6-sol`), medium reasoning, as explicitly selected by the user. Preserve the plan’s integrated verification and independent Claude review. Estimate: 10–14 active hours; credits not credibly estimable.

Independent audit: required

User approved D1 staging integration/push and Build A start on 2026-11-07. D1 is now integrated at 9ba8aa9c931cdc2b98fa25e94a39defdf3cad258, the verified GitHub/local staging base of this branch. Production remains 9ade69bf155d1b25699d3aecfff3c1b07752aff0. Only A1–A7 are authorized here; A7 is diagnostic unless reproduced. No Build C start, next integration/push, production release, installation or cleanup is authorized.

Execution checkpoint, 2026-11-07: A1–A6 implemented and verified; A7 not reproduced, evidence-only. Corrected source `9562c373`, final audited candidate `750cf0bc`. Full suite 3,135 passed, Ruff clean, initial Claude audit and final correction closure complete with no open material findings. The checklists below preserve the frozen instructions; actual results and Low dispositions are authoritative in `docs/reviews/2026-11-07-numbers-you-can-trust-acceptance.md`. No integration/push or next-build start is authorized.

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

## Build A — Numbers you can trust

**Worktree slug:** `numbers-you-can-trust`.

### Task A1: Forecast magnitude guard

**Files:**
- Modify: `tradingagents/agents/valuation.py` (`_ev` after the revenue baseline is loaded, ~line 280; `_pe` after `eps` is loaded, ~line 445) and `tradingagents/agents/valuation_cases.py::price_case` (the Build 2 case path; apply the same check to each case's revenue against the same baseline)
- Test: `tests/test_valuation.py` and `tests/test_case_valuation.py`.

**Interfaces:**
- Produces: `_magnitude_check(label: str, forecast: Decimal, baseline: Decimal) -> None`, raises `ValueError(f"{label} forecast {forecast} is outside 0.1×–10× of the source baseline {baseline}; unit scale mismatch suspected")`. Called from inside `_forecast`, which gains a keyword argument `baseline: Decimal | None`; `_ev` passes `revenue.value`, `valuation_cases.price_case` passes its `revenue.value`, `_pe` passes `eps.value` only when `eps.value > 0`. One check point covers the scenario path and the Build 2 case path. `validate_target` and `price_case`'s callers already turn `ValueError` into `status="unsupported"` with the message as the reason.

- [ ] **Step 1: Write the failing tests** in `tests/test_valuation.py` using the existing `evidence()`/`forecast()`/`ev_request()` helpers:

```python
@pytest.mark.parametrize("value", [Decimal("1.2"), Decimal("1200000")])
def test_ev_forecast_a_thousand_times_off_is_unsupported(value):
    result = validate_target(ev_request_with_forecast(value), evidence())
    assert result.status == "unsupported" and "unit scale mismatch" in result.reasons[0]

def test_ev_forecast_within_band_is_unchanged():
    assert validate_target(ev_request_with_forecast(Decimal("1200")), evidence()).target == Decimal("39")

def test_ev_forecast_unit_mismatch_rejected_before_magnitude():  # Review Focus 1
    result = validate_target(ev_request_with_forecast(Decimal("1200"), unit="EUR"), evidence())
    assert result.status == "unsupported" and "unit" in result.reasons[0] and "scale" not in result.reasons[0]
```
plus the PE pair (`eps` baseline from `pe_request()`; forecast ×1000 → unsupported; negative baseline EPS → no magnitude check), plus `test_case_revenue_a_thousand_times_off_is_unsupported` in `tests/test_case_valuation.py`.

- [ ] **Step 2:** Run both valuation test modules with the proposed tests; confirm the three out-of-scale paths fail before the change.
- [ ] **Step 3:** Call `_magnitude_check` only inside `_forecast`, after unit/basis validation. Pass the source baseline from `_ev`, `_pe` (positive EPS only) and `price_case`. Verify the inclusive 0.1× and 10× boundaries.
- [ ] **Step 4:** `pytest tests/test_valuation.py tests/test_case_valuation.py tests/test_shared_valuation.py tests/test_mechanical_valuation.py -q` → PASS.
- [ ] **Step 5:** Commit `fix(valuation): reject forecasts outside 0.1x-10x of the source baseline`.

### Task A2: Grounded outlooks from every retained disclosure, newest wins

**Files:**
- Modify: `tradingagents/agents/valuation_outlooks.py` (`grounded_outlooks`, the claim loop ~line 155)
- Test: `tests/test_valuation_outlooks.py`

**Interfaces:**
- Treat model claims and deterministic discovery as candidates. Replay discovery/validation against uniquely identified, untruncated retained blocks and matched canonical source records (issuer, as-of, filing date, accession, URL and hash). A cached extraction or a “verified” label alone cannot ground a value.
- Keep `grounded_outlooks(state)` and the existing source-backed IDs. Among validated candidates for the same metric, normalized unit/currency, basis, period and kind, choose the latest filing date. Keep guidance separate from ambition. Conflicting normalized ranges at the latest date ground neither; report the conflict in the existing disclosure warnings without mutating a frozen publication. Preserve `test_model_claim_cannot_self_certify_against_unmodified_source`; test a tampered discovery candidate, a later ambition alongside guidance, and both input orders.

- [ ] **Step 1: Write the failing tests** with a two-document package (old 8-K guidance 1170–1180, newer 8-K 800–900, both retained):
```python
def test_newer_retained_guidance_supersedes_older_even_if_model_quoted_only_the_old():
    outlooks = grounded_outlooks(state_with(model_quotes=["old"], discovered=["old", "new"]))
    assert [o.low for o in outlooks] == [Decimal("800000000")]

def test_same_day_conflicting_guidance_grounds_neither():  # Review Focus 2
    assert grounded_outlooks(state_with(discovered=["a_same_day", "b_same_day"])) == ()
```
- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** `pytest tests/test_valuation_outlooks.py tests/test_disclosure_gate_discovery.py -q` → PASS. **Step 5:** commit `fix(outlooks): ground from all retained disclosures and prefer the newest filing`.

### Task A3: SEC document truncation keeps guidance and the latest release

**Files:**
- Modify: `tradingagents/dataflows/vendors/sec_documents.py` (`extract_sections` priority ~line 479–526; `get_filing_evidence` document loop ~line 673–700; `select_filings` ordering ~line 203)
- Test: `tests/test_sec_documents.py`

**Interfaces:**
- Keep meaningful guidance blocks ahead of generic boilerplate. Under the existing limits (six filing references by default, eight documents, 40,000 characters per document and 120,000 per package), protect both required statements and the latest eligible item 2.02 exhibit. Account separately for the 8-K primary needed to discover the exhibit and the exhibit text itself. Allocate remaining capacity to other material in priority order. Preserve source locators and report omissions.
- [ ] **Step 1:** In a crowded fixture where primaries and their exhibits would exceed both budgets, assert the selected 10-K and 10-Q retain useful statement blocks **and** EX-99.1 retains its actual guidance sentence. Include a large 2.02 primary, several notices/exhibits and boilerplate competing with a numerical guidance block. Empty document shells do not pass.

- [ ] **Step 2–5:** FAIL → implement → `pytest tests/test_sec_documents.py tests/test_prior_quarter_disclosures.py -q` PASS → commit `fix(sec): keep guidance blocks and the latest release under the text budget`.

### Task A4: Unidentified stock and SEC accounting scope

**Owner:** `create_source_acquisition` and the evidence gate in `tradingagents/agents/evidence_validation.py`; `tests/test_evidence_gate.py`.

- For a stock with fundamentals selected, retain a limited assessment only under the foreign non-filer exception when existing authoritative evidence verifies the issuer's identity and confirms it is a foreign issuer that does not file with the SEC as of the analysis date. Label it “Limited assessment: confirmed foreign non-filer; US SEC accounting validation was not performed.” It remains eligible for a directional rating under the existing rules.
- **Behavior at delivery:** `cik_for` provides a positive SEC mapping, but the app has no authoritative source confirming that a particular foreign issuer is a non-filer. With fundamentals selected, every unmapped stock therefore goes to `REVIEW`, with the reason visible and no directional rating. Yahoo’s country or exchange field, a foreign listing, a ticker suffix or an SEC-map miss does not establish filing status. Preserve ordinary validation for mapped domestic and foreign SEC filers, non-stock assets and fundamentals not selected. Do not add a provider or invent an override for this exception.
- [ ] From acquisition through publication, exercise an unmapped ticker, including one with Yahoo country/exchange metadata identifying a foreign market. Both must end in `REVIEW`. Verify mapped domestic and foreign filers, non-stock instruments and fundamentals not selected retain their existing behavior. The limited exception is an approved policy, not a reachable production path at this baseline; a fabricated source or test flag is not delivery proof.

### Task A5: Peer facts are checked only for the periods used

**Files:**
- Modify: `tradingagents/dataflows/vendors/sec_edgar.py` (`_select_facts`, ambiguity check ~line 270) and the peer call in `tradingagents/agents/valuation_reference_flow.py::_fetch_peer` (~line 237)
- Test: new `tests/test_peer_period_scope.py`

**Interfaces:**
- Produces: `get_financial_evidence(ticker, as_of, *, peer_revenue_definitions=False, period_floor: date | None = None)`; when `period_floor` is set, `_eligible_records` drops records whose period end is before it before any ambiguity check. `_fetch_peer` passes `period_floor = as_of - 3 years`. CRWV's multi-class exclusion is unchanged; its reason text is unchanged.

- [ ] **Step 1:** `test_ambiguity_in_an_old_period_does_not_exclude_the_peer` (synthetic companyfacts with two conflicting `Assets` records at 2015-12-31 and clean 2024–2026; peer statistics status `available`). `test_ambiguity_inside_the_window_still_excludes`.
- [ ] **Step 2–5:** FAIL → implement → `pytest tests/test_peer_period_scope.py tests/test_peer_revenue_tags.py tests/test_peer_cover_shares.py tests/test_sec_edgar.py -q` PASS → commit.

### Task A6: Assumption changes since the prior publication, on the card

**Files:**
- Create: `tradingagents/agents/assumption_history.py`
- Modify: `tradingagents/agents/decision_context.py` (`prepare_decision_context` return dict; `render_decision_context`), `tradingagents/report_html.py` and `tradingagents/reporting.py` only through the existing condition-summary rendering path
- Test: `tests/test_assumption_history.py`

**Interfaces:**
- At run finalization compute the comparison once, from the current effective Build 2 case requests (including an accepted post-debate revision, never a rejected one) and decision horizon. Compare with the verified evidence of the latest eligible prior directional publication for this ticker. Apply the timezone-aware known-at rule used by `load_latest_thesis`, exclude the current run and later publications, and use sequence only to break timestamp ties. Do not choose by requested date alone.
- Retain `assumption_changes` with the decision context in the run/publication evidence: status (`available`, `no_prior`, `unavailable`), prior ID/as-of and changed scenario/field/value pairs (multiple, forecast, period, share basis, horizon). Show “No new filing was retained” only when verified inventories establish it; unknown is not false. Render and re-export from that retained comparison without reading today's publication store. Legacy exports without it say unavailable. Display only.
- [ ] Test changed multiple and horizon, no prior, a later or self publication, same-day prior revisions, and accepted/rejected revisions. Add a subsequent publication before re-export: the saved comparison must not change.

- [ ] **Step 2–5:** FAIL → implement → `pytest tests/test_assumption_history.py tests/test_publication_evaluation.py tests/test_report_html.py -q` PASS → commit.

### Task A7: Check the reported missing prior condition

**Owner:** `tradingagents/memory/thesis.py` and `tests/test_thesis.py`, only if a loss is reproduced. The named November 7 DOCN parent has four conditions, four observations and four `kept` prior-condition rows. Its gross-margin thresholds are 55.5% and 50.15%. The “below 53%” reference is narrative, not a condition in the parent or child thesis record. `observe_conditions` creates an `unknown` observation when a valid condition has no matching fact.

- [ ] In the Build A evidence, identify the parent publication/version, compare its condition IDs with the child rows, and trace any reported loss through observation, disposition and rendering. If a concrete ID is lost, fix that path and add a replay regression. Otherwise record “not reproduced; no code change.” Missing evidence alone must never assert that a condition was superseded.

### Build A proof
- `pytest -q` green on the branch; `ruff check`.
- Replay November 7 DOCN against a disposable copy of the publication store with the producing cutoff; verify the actual November 6 predecessor and condition IDs. For post-debate behavior absent from that pre-Build-2 run, use the accepted/rejected Build 2 fixtures. Reopen both report formats after a later publication and verify comparison stability.
- Offline replay of the 11-07 evidence package preserves the source-only FY2026 revenue guidance ($1.208–$1.211 billion), and A3 keeps the Q3 press release's guidance blocks. Baseline/candidate inspection establishes that the valuation-outlook adapter returns no annual outlook for this particular saved state on either version: its period/basis context does not meet that stricter adapter contract. Prove A2's new discovery/supersession behavior with source-bound fixtures rather than inventing missing fiscal/calendar or accounting context for DOCN. This corrects the original proof's attribution; it does not relax grounding rules.

---

## Integrated acceptance

Independent audit: required

- **One owner per required handoff, in order:** D1 owns the real local HTML-to-clipboard result; A owns valuation validation, guidance retention, A4 eligibility, decision comparison and the A7 evidence disposition; C owns the ledger/outcome lifecycle and memory note; B owns extraction from validated full filing text and companyfacts, delivery to real prompts and export; D2–D10 own the remaining operator changes. D1 is complete or incomplete on its own. At each authorized start verify the necessary predecessor evidence and code at the exact staging SHA. B does not need A3 to retain its passages. D11 cannot block the five builds, their audits, integration or release.
- On Machine 2 exercise the smallest working user/system path first; fix any runtime blocker before broadening it. After hardening, re-run the complete affected path from its real trigger, using the handoff's prescribed disposable inputs. Record the observable output and destination in `docs/reviews/<date>-<slug>.md`. Fake only external providers needed for a no-cost replay, not the application path under proof. An unexercised required path remains incomplete.
- **Each of D1, A, C, B and D:** full default `pytest -q` and `ruff check` clean on the candidate; record exact tested SHA, results and limitations. Use the existing independent Claude review route evidenced in `docs/reviews/2026-11-07-operational-report-audit-acceptance.md` (frozen range, bounded executor, existing authorized spend limits). The marker above declares the requirement; it does not launch or pay for an audit. During future authorized work, commit the governing requirements for that handoff (including the marker and proof) at a repo-relative path on its isolated branch; the standalone file in `~/Claude` is not a frozen input. Provide the approved runner the frozen requirements, relevant source, receipts and sanitized proof. Verify its required inputs are available at that SHA; never claim a self-review, missing packet or capped review as complete.
- Reproduce each High locally against the candidate; distinguish the implementer's reproduction from what a read-only auditor actually ran. Fix confirmed in-scope findings with regression evidence and re-audit the final change. Close with no open in-scope Critical/High/Medium; document lower findings and dispositions, or “no gaps found.” Identify the final feature commit, verified candidate, audited range and any evidence-only follow-up accurately. Passing this gate grants no integration or release authority.
- **Not applicable to these development proofs:** broker/trade execution, production databases and deployment. The touched persistence is the existing local ledger and run/report files. No new service, database migration, retention daemon or Machine 1 install is required.

## Approved product decision — A4: confirmed foreign non-filers

**Approved by the user on 2026-11-07.** With fundamentals selected, keep a clearly labeled limited assessment for a confirmed foreign non-filer and disclose that US SEC accounting validation was not performed. If the issuer or its SEC filing status cannot be verified, use `REVIEW`. A verified foreign SEC filer follows the ordinary filer path. At delivery there is no authoritative non-filer source; for stocks with fundamentals selected, all SEC-map misses therefore yield `REVIEW`, even if Yahoo supplies a country or exchange.

