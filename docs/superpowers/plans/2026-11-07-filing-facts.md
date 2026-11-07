# Build B: Facts the filing already states

Build size: medium
Recommended model: GPT-6 Sol (`gpt-6-sol`), medium reasoning, user-selected. Source lineage, matching units/vintages and actual prompt/export proof require integrated verification. Estimate: 8–12 active implementation/proof hours; credit range not credibly estimable.

Independent audit: required

Authorized start, 2026-11-07: user approved C integration/push and B start. Local staging, origin/staging and GitHub staging matched77ebc8ab before the approved fast-forward/push to exact C handoff bd27b742e6346ff7e6bd22f1823e263934f3e1aa. Refetched and verified all three atbd27b742; inspected seven C commits and confirmed D1/A predecessors. Production unchanged9ade69bf155d1b25699d3aecfff3c1b07752aff0. This branch codex/filing-facts and isolated worktree /Users/zipp/Documents/ChatGPT/Tauric/worktrees/filing-facts start at that verified C commit. Only B1–B3 are authorized here; no B integration/push, D start, release/install or cleanup.

External governing plan: /Users/zipp/Claude/2026-11-07-evidence-settlement-and-ops-gap-closure-plan.md. The following approved sections are frozen for B.

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

## Build B — Facts the filing already states


**Worktree slug:** `filing-facts`. Use the existing SourceAcquisition sequence **before analyst fan-out**: `evidence_validation.py` already calls `prepare_document_sources` before `context.py::build_shared_source_brief`. B1/B2 read the full cached filing text from the same validated corpus that document search uses; B3 reads companyfacts and uses the same brief/export path. Retain only source-bound records, calculation inputs and the bounded lines needed by the analysts, debate, trader, risk and Portfolio Manager. No dependency on A3's block ranking or budget, second fetch, new cache, model-initiated search, or change to the existing 8-K event path. Missing evidence produces no invented record or zero. No new EV inputs.

### Task B1: Convertible-note terms and the stated funding plan

**Files:**
- Create: `tradingagents/dataflows/instrument_terms.py`
- In source acquisition, after `prepare_document_sources` and before building the shared brief, pass `document_access.validated_document_corpus(state)` (with the acquisition update included) to the deterministic extractors. The search reader already obtains complete sections from the cached SEC document bytes and verifies source pins. Use only eligible selected primary 10-Q/10-K filings matching issuer, as-of, accession, URL and hash; use the latest applicable reporting period for current terms and do not mix numbers or sentences across filing vintages. Bind each field to its complete section locator and explicit unit. Do not read arbitrary cache files by ticker or feed the whole filing into prompts. If the validated corpus or a field is unavailable, preserve the existing unavailable behavior. No A3 retention edits.
- Test: `tests/test_instrument_terms.py`

**Interfaces:**
- Produces: `class ConvertibleNoteRecord(BaseModel)`: `name` ("2026 Convertible Notes"), `principal_outstanding: Decimal`, `principal_unit: str` (explicit currency and scale from retained source context; do not assume dollars when scale is missing), `as_of: date`, `maturity_date: date`, `conversion_price: Decimal | None`, `settlement_election: str | None`, `stated_plan: str | None`, `source_id`, `locator`, `content_hash`, `filed_date`.
- `discover_convertible_terms(package: DisclosurePackage, as_of: date) -> tuple[ConvertibleNoteRecord, ...]`, matching these DOCN 10-Q sentence shapes (copy them into the test fixture verbatim):
  - `The outstanding $ 312,322 of aggregate principal amount of 2026 Convertible Notes will mature on December 1, 2026 unless earlier converted, redeemed, or repurchased.`
  - `Upon conversion of the 2026 Convertible Notes, the Company will pay or deliver, as the case may be, cash, shares of common stock or a combination of cash and shares of common stock, at the Company’s election.`
  - `equivalent to an initial conversion price of approximately $ 178.51 per share`
  - `We plan to repurchase, repay, acquire or otherwise settle the remaining outstanding principal of our 2026 Convertible Notes by using cash on hand and cash generated from our operations.`
  A record needs the first sentence; the other three are optional fields. Maturity before `as_of` → no record (Review Focus 3).
- Rendered line: `- Instrument terms (source-bound): 2026 Convertible Notes; principal outstanding 312,322 USD thousands as of 2026-09-30; matures 2026-12-01; initial conversion price ≈ 178.51 USD/share; settlement at the Company's election in cash, shares or both; stated plan: "We plan to … operations." Management statement of intent, not a completed transaction. Source: <url>, <locator>; filed <date>; hash <hash>.`

- [ ] **Step 1:** tests: `test_docn_2026_notes_record_has_principal_maturity_price_election_and_plan`, `test_principal_without_maturity_yields_no_record`, `test_maturity_before_as_of_yields_no_record`, `test_2030_notes_sentence_does_not_bleed_into_2026_record`.
- [ ] **Step 2–5:** FAIL → implement → `pytest tests/test_instrument_terms.py tests/test_evidence_gate.py -q` PASS → commit `feat(evidence): source-bound convertible note terms and stated funding plan`.

### Task B2: Uncommenced lease commitments

**Files:**
- Create: `tradingagents/dataflows/commitments.py`
- Consume the same pre-analyst validated full-document source as B1; attach the precise locator, source and quote to each commitment. No dependence on a follow-up or a particular analyst search.
- Test: `tests/test_commitments.py`

**Interfaces:**
- Produces: `class LeaseCommitmentRecord(BaseModel)`: `undiscounted_amount: Decimal`, `unit: str`, `as_of: date`, `commencement_start: str` ("2026-11"), `commencement_end: str` ("2028-06"), `weighted_average_term_years: Decimal | None`, `nature: str`, `quote: str`, plus the source fields. `discover_lease_commitments(package, as_of) -> tuple[LeaseCommitmentRecord, ...]`, matching: `As of September 30, 2026, the Company had $ 2,955,158 of estimated undiscounted fixed payment obligations primarily for leases of co-location space at data center facilities that have not yet commenced and were not included in the condensed consolidated balance sheets. These leases are scheduled to commence between November 2026 and June 2028, and have a weighted-average lease term of 11.1 years.` (and the MD&A variant `$2,955.2 million`; normalize units, match obligation/scope, reporting and commencement dates, and use the rounding interval of the less precise disclosure. The $42,000 difference is consistent with rounding to $0.1 million: retain one record at the precise notes value, with its source. A genuinely different obligation or amount outside that interval is not a duplicate).
- Rendered line labels it: `undiscounted future payments over the lease terms; not a present-value liability; not included in the balance sheet or in any enterprise-value perimeter above.`

- [ ] **Step 1:** `test_docn_uncommenced_lease_record`, `test_notes_and_mdna_variants_deduplicate_to_one_record`, `test_amount_without_not_yet_commenced_phrase_yields_no_record`.
- [ ] **Step 2–5:** FAIL → implement → PASS → commit.

### Task B3: Cash plus marketable securities as a calculation

**Files:**
- Modify: `tradingagents/dataflows/vendors/sec_edgar.py` (reported balance sheet facts), `tradingagents/agents/accounting_checks.py` (calculation `cash_plus_marketable_securities_v1`), and B1's shared delivery path. In the September 30 DOCN filing the value is reported under `AvailableForSaleSecuritiesDebtSecurities` and `MarketableSecurities`; the three current-tag candidates (`MarketableSecuritiesCurrent`, `AvailableForSaleSecuritiesDebtSecuritiesCurrent`, `ShortTermInvestments`) have no value for that date. An unqualified tag alone is not proof of current classification. Verify current classification against the retained balance-sheet presentation and require matching issuer, date, unit, scope and filing vintage; aliases for the same holding count once. If ambiguous, report unavailable.
- Test: `tests/test_accounting_checks.py`, `tests/test_sec_edgar.py`

**Interfaces:**
- Produces: a C-row `cash plus marketable securities: pass; <sum> USD; Statement cash and current marketable securities; not unrestricted valuation cash and not a liquidity forecast; inputs F<cash>, F<securities>`; status `unavailable` with reason "Marketable securities not reported" when the fact is absent. The EV bridge keeps using `Cash and Equivalents` only.

- [ ] Test available, missing, duplicate-tag and noncurrent/ambiguous inputs. The actual filed figures are 666,096,000 USD cash + 178,645,000 USD current securities = **844,741,000 USD**; verify those units, sources and result, and verify the EV bridge still uses cash alone.
- [ ] **Step 2–5:** FAIL → implement → `pytest tests/test_accounting_checks.py tests/test_sec_edgar.py tests/test_valuation.py -q` PASS → commit.

### Build B proof

- Offline, use the November 7 DOCN state and copies of its cached 10-Q and companyfacts. Exercise fresh acquisition from the cached/recorded bytes and replay the saved validated search corpus, with **unchanged** short-package budgets. For the September 10-Q the full-corpus locators include `block-205` (maturity), `block-430` (funding plan), `block-204` ($178.51 conversion price) and `block-218` (precise lease amount). Prove extraction succeeds even without those blocks in the short package, with no additional fetch or analyst search. Reject a wrong issuer, cutoff or changed source hash. Do not claim the maturity sentence was missing from the run.
- Run the real acquisition, graph prompt construction and report export with offline model doubles. Inspect the inputs to each selected analyst and the debate, trader, risk and Portfolio Manager, plus the reopened brief and `evidence.json`. Require one sourced note (including the available election, conversion price and plan), one precise lease record and the 844,741,000 USD calculation; no duplicated or invented inputs. Recheck after hardening; full suite, Ruff and independent audit apply.

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

## Approved product decision — A4: confirmed foreign non-filers

**Approved by the user on 2026-11-07.** With fundamentals selected, keep a clearly labeled limited assessment for a confirmed foreign non-filer and disclose that US SEC accounting validation was not performed. If the issuer or its SEC filing status cannot be verified, use `REVIEW`. A verified foreign SEC filer follows the ordinary filer path. At delivery there is no authoritative non-filer source; for stocks with fundamentals selected, all SEC-map misses therefore yield `REVIEW`, even if Yahoo supplies a country or exchange.

## Decisions already recorded

- Execution order: **D1 → A → C → B → D**, in Codex. Build starts remain separately authorized.
- A1 uses the inclusive 0.1×–10× band. C2 preserves exact-session alignment and stops retries after three qualifying post-horizon zero-coverage checks at least 14 days apart; that endpoint can be reopened manually. D1 copies plain text with one CSP-allowlisted script and no external loads.
- Launcher housekeeping is complete. Git integration, release and Machine 1 installation follow the separate approvals in Branch and Release Boundary.

## Post-plan audit disposition (2026-11-07)

**Verdict: revised and ready.** The approved A4 decision closes the last open plan item. The following classifications describe the plan as reviewed and the recorded corrections; they are not implementation or release results.

| Reviewed section | Finding | Disposition in this plan |
|---|---|---|
| D1; Integrated acceptance | **PARTIAL** — selected page text included controls, and the stated end preceded the assessment. | One text payload; early and final Safari/Chrome proof, with fallback; independent standalone handoff. |
| A1–A3, A6–A7 | **PARTIAL** — duplicated guard instructions, unchecked claim/filing retention and an unbounded “prior” comparison; the 53% loss was not present in the named run. | One validated guard, replayed guidance, protected statements/exhibit, cutoff-bound frozen comparison; A7 is evidence-only unless reproduced. |
| A4 | **PARTIAL** — the old rule conflated unidentified stocks and confirmed foreign non-filers. | Policy approved. No authoritative non-filer source exists at delivery: all unmapped stocks with fundamentals selected go to `REVIEW`. Yahoo country and exchange are not proof. |
| C1–C4 | **FAIL** — maturity and missing benchmark data were conflated, terminal reads were unsupported, and tolerant publication writes could duplicate primaries. | Preserve strict writes; exercise reload/recovery and manual reopen. Three qualifying post-horizon zero-session checks at least 14 days apart stop automated retries, without inferring a delisting. |
| B1–B3 | **FAIL** — the short package was not a complete extraction source, the proposed XBRL tags missed the securities balance, and the original hook ran after analyst fan-out. | Use the validated full-document search corpus before fan-out without retuning A3. Verify source locators, current classification, rounded duplicates, prompt delivery and exported facts. |
| D7–D10 and D proof | **PARTIAL** — returned error text, discarded model metadata, legacy caches and later split rows escaped proposed checks. An interrupted live run would not prove zero paid calls. | Verify downstream messages and actions before cutoff filtering. Run the real CLI against offline doubles. Full-payload tracing is deferred. |
| Baseline, Integrated acceptance, Decisions | **PARTIAL** — the audit marker was external, D1 order was optional, completed housekeeping was still pending, and installation referred to staging. | Freeze per-handoff requirements only at future authorized execution. Record the approved order and separate feature completion, staging integration, production release and Machine 1 acceptance. |

Review evidence: both remote branch tips and the launcher were inspected read-only. The prior review ran five focused baseline regression cases, inspected the saved DOCN state and cached filings, and reproduced duplicate primaries in a temporary store under the proposed skip rule. No new feature, installed-app, browser, or release proof is claimed by this plan audit.

## Optional follow-up after Build D — D11: per-node trace

Deferred. Full model prompts and tool returns could explain what an agent saw, but they also write sensitive content to disk. Build D ends at D10. D11, a traced DOCN run and any later workflow audit are outside all five required handoffs; none is authorized or a release prerequisite.

If separately requested after D, allow roughly two additional hours for the trace itself. Reuse the node callback and D3 attempt directory; keep tracing off by default. Store ordered, run- and stage-bound prompt/tool/response events only in private, operator-removable local files outside report exports. Exclude credentials and raw provider diagnostics; mark interrupted writes incomplete. Verify default-off, ordering across concurrent stages, separation after restart and secret exclusion with synthetic data before capturing a real run.
