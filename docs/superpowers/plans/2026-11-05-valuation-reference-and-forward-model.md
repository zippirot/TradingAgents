# Valuation reference points and forward price range

Date: 2026-11-05. Author: Claude; reviewed and updated by Codex. Revised the same day for formula basis, consensus separation, comparison fairness, audit independence, peer sequencing, dates, baseline and execution-contract consistency. Current status: Part A is published for CI at 24172f6 and all seven exact-head CI jobs pass; B1 is implemented locally under the authorized amendment below. B2, decision adoption, comparison, merge and installation remain on hold. See docs/reviews/2026-11-05-mechanical-valuation-b1-acceptance.md. Historical budget and planning statements below are preserved; the latest authorized amendment governs this follow-up.

This is the second plan. It starts after `docs/superpowers/plans/2026-11-05-market-evidence-valuation-gap-closure.md` ("plan one") is accepted, and builds on it. It does not change plan one's scope.

## Outcome

Every eligible stock report answers "is this price attractive?" with evidence a reader can check:

1. Where today's valuation sits against the company's own history.
2. Where it sits against comparable companies the tool selects itself.
3. What analysts expect, shown beside management guidance.
4. A pessimistic, middle and optimistic price for the end of the forecast year, with the return against the last completed close.

Added to Part A at the user's request on 2026-11-05, from an external review's suggestions:

5. An advisory audit pass that lists unsupported claims and numerical inconsistencies before the final decision.
6. A two-round debate option, so less of each run is spent on repeated arguments.
7. A fair pilot comparison of two model setups, judged on checkable measures.

The rating remains the Portfolio Manager's research opinion. Nothing here forces a rating, sizes a position or places an order.

## What already exists and is reused

Reviewed at `6340c9d` (read). Plan one has since been merged: GitHub `staging` is `ac661ca291599a8e3e9701bed73f60d979d38a01` with CI green (checked 2026-11-05). It adds a Source Acquisition step before the analysts, source-only price multiples and scenario suitability. Re-read the modules below at the current staging commit before starting; the descriptions are from the earlier commit:

- `agents/valuation.py`: EV/revenue and P/E calculator with scenarios.
- `agents/funding.py`: forward cash, obligations and share-count bridge (`ForwardCapital`). Never yet exercised by a live run.
- `agents/shared_valuation.py`: the Fundamentals Analyst proposes up to three scenarios in a `valuation_scenarios` block before the debate.
- `agents/valuation_comparison.py`: "what the price implies". Plan one makes this independent of model scenarios.
- `agents/event_comparison.py`: results versus guidance, with an empty consensus slot ("no typed, timestamped consensus source is configured") and one hardcoded peer (`DOCN → AKAM`).
- `dataflows/vendors/sec_edgar.py` and `yahoo/price_observation.py`: verified SEC facts and completed-session prices for any US filer.

The installed launcher checkout remains `180b245d6b4ea996b55a4a41f9167ec9b80a0d56`, containing Build 1 and the user's pinned model choices. It is not the implementation baseline for this plan. Any eventual Part A installation needs separate authorization and must preserve those choices and user data. Staging acceptance is recorded in [plan one's final CI](https://github.com/zippirot/TradingAgents/actions/runs/42101608197); installation is a separate state.

Feasibility checked today (ran): the SEC package for DOCN holds quarterly revenue, shares outstanding and cash from the end of 2022 (13 quarter-ends); the price cache holds five years; the free Yahoo source returns revenue and EPS estimates with analyst counts, a price-target range, four quarters of surprises and estimate revisions.

## Dependencies on plan one

- **Completed-session prices (1A):** every price used here is a completed close.
- **Independent price-implied table (2A):** Part A extends that section; it does not rebuild it.
- **Scenario suitability metadata (2B):** Part B's cases carry the same validity, suitability and assumption fields.
- **Evidence before analysts (Build 3):** Part A's own-history, expectations and default-peer data are fetched in that Source Acquisition step, so all analysts see them.

All four are delivered on staging at `ac661ca`. Before starting, fetch GitHub `staging`, record its exact commit, and reconcile any difference between what plan one actually delivered and what is assumed here.

## Delivery estimate

- Build size: **extra medium** overall. Part A medium to extra medium (grown by the audit pass, depth option and comparison); Part B medium to large.
- Recommended model: **GPT-6 Sol (`gpt-6-sol`), medium reasoning** for Part A. **GPT-6 Astra (`gpt-6-astra`), medium reasoning** for Part B, where a plausible but wrong share, period or obligation basis would pass local tests. Engineering judgment, not a measured comparison.
- Active implementation and verification: **31–48 hours**. Part A 16–23 (reference points 9–13, audit pass 4–5, depth option up to 1, comparison tooling 3–4), Part B 12–20, integrated verification and review 3–5. Approximate planning ranges, with the upper total corrected to match the component estimates. Excludes external waits; assumes narrow extensions to the existing runners and providers suffice.
- Codex credits: not credibly estimable; no usage measurements exist for this repository.
- Paid proof: **approved by the user on 2026-11-05: $10 aggregate ceiling for at most two live CLI attempts at the lowest depth**, allocated one to Part A and one to Part B. Failed attempts count; there is no additional authorized retry. Refresh actual provider usage and pricing before each attempt, reserve a conservative cost allowance, and stop before the ceiling would be exceeded. Any extra attempt or budget increase needs separate approval. The Part B attempt also waits for the Part B go-ahead below. This budget approval does not start implementation and does not cover the A7 comparison or additional reports the user may request.
- Model comparison (A7): six further CLI attempts plus six rubric-review calls, with a separate, not-yet-approved ceiling. Public OpenRouter pages checked again on 2026-11-05 list input/output rates per million tokens of $1/$5 for [GPT-6.1 Terra Pro](https://openrouter.ai/openai/gpt-6.1-terra-pro), $2/$10 for [GPT-6.1 Sol](https://openrouter.ai/openai/gpt-6.1-sol), and $4/$20 for [Claude Opus 5.5](https://openrouter.ai/anthropic/claude-opus-5.5). Before proposing the ceiling, name the common reviewer's exact model and settings, verify actual route rates, and estimate the two-round workflow, its internal audit, all six external review calls, reasoning tokens, tool turns and failed calls. These are public base rates, not an account-specific quote or a subscription price. No comparison calls or automatic replacement attempts are authorized yet.

## Boundaries

Same machine, branch, isolation and release rules as plan one. A new isolated `codex/` branch and worktree from verified staging. No push, merge, installation or worktree removal without separate authorization. Preserve the launcher, keys, preferences, reports, memory and publication records.

Development and verification run on Machine 1: `ssh -i /Users/zipp/.ssh/tradingagents_machine1 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes zipp@100.89.132.10`. Confirm Apple M1 Pro / 16 GB before mutations; this Mac coordinates only. Keep private inputs and credentials outside Git. Preserve plan one's asset scopes, REVIEW behavior, final claim validation, and memory/scoring exclusions; these additions do not grant trading authority.

Not in scope: the weekly watchlist (parked by the user), discounted cash-flow models, paid data services, calibrated probabilities, peer groups maintained by hand as a requirement, automatic rating rules, portfolio sizing.

## Part A — reference points, audit pass and model comparison

**Files:** `agents/{valuation_comparison,event_comparison,evidence_validation,context,state,schemas}.py`, `analysts/fundamentals_analyst.py`, a new small `agents/valuation_reference.py`, a new small `agents/audit_pass.py`, `graph/setup.py`, `managers/portfolio_manager.py`, `cli/{prompts,prefs}.py`, the existing proof runner under `docs/reviews/`, `dataflows/vendors/yahoo/` for one new expectations reader, `reporting.py`, `report_html.py`, tests and recorded fixtures.

### A1. Own history

For each fiscal quarter-end whose filing was filed on or before the analysis date, calculate market value ÷ trailing-twelve-month revenue:

- Market value = completed close on the quarter-end date (or the nearest earlier session) × common shares outstanding measured at that quarter-end. Record the shares' actual measurement date. If the only share count for a quarter is measured on a different date (for example the cover-page count near the filing date), that quarter is unavailable; do not mix dates.
- Price and shares must be on the same split basis. Reconcile them from the retained split record, and state the basis used.
- This is an **equity-value ÷ revenue** multiple. Label it that way wherever it appears.
- Trailing revenue from compatible, non-overlapping reported periods only.
- Publish low, median, high, the number of quarters, and where today's figure sits. Enterprise-value multiples exist only for the current date, where the obligation perimeter is verified; never compare an enterprise-value multiple with an equity-value one.
- Label the history as a retrospective series assembled from filings available by the analysis cutoff, not information necessarily available on each historical quarter-end or a backtest. Retain each price session, share date, revenue period and filing date.
- If a stock split falls inside the window and the two bases cannot be reconciled, mark the series unavailable with that reason. Fewer than four usable quarters: unavailable.

### A2. Peers selected by the model

**Sequence, with no added model calls:**

1. **Source Acquisition (before the analysts):** fetch peer statistics for the default peer set, which is the user's pinned list if one exists, otherwise the previous published set for the ticker. On a first run with neither, there are no peer statistics at this point.
2. **Fundamentals Analyst:** sees the default set and its statistics, and ends its report with one named `peers` block that keeps or changes an unpinned set. It cannot replace a user-pinned set.
3. **Evidence step (after the analysts, in code):** validates any newly proposed peers, fetches their facts and prices, and fixes the final peer table for the run.
4. **Debate onward:** both debaters, the Research Manager, the audit and the Portfolio Manager receive the final table.

Consequence: an analyst can cite statistics only for peers that were in the default set. On a first run its reasoning uses own history and guidance only, and the report says peers applied from the debate onward.

- The `peers` block holds up to five tickers, each with a one-line reason. An empty list is valid.
- Code accepts a peer only if it resolves in the SEC issuer map, is not the subject company, reports in the same currency and has usable verified revenue and shares by the analysis cutoff. Select the latest eligible facts at that cutoff; a later filing does not disqualify earlier usable facts. Rejected peers are listed with the reason.
- For each accepted peer, code fetches verified facts and a completed close and calculates the same market value ÷ trailing revenue, plus trailing revenue growth and gross margin. No model calls are added.
- Use the subject's canonical completed-session cutoff, compatible TTM revenue periods and consistent price/share units and split bases. Show the actual share and filing dates; missing growth or gross margin makes that cell unavailable rather than inventing a value. Retain both the default and final peer snapshots so an analyst's earlier citations remain resolvable.
- The report labels the set "model-selected" or "user-pinned" and prints the reasons and any exclusions. Peer numbers are verified; business comparability is not established by passing these data checks.
- **Stability:** the default set comes from the previous publication through the existing prior-publication path; add no new store. Changes from the default are shown.
- **User override:** an optional peers file takes priority for any ticker listed in it, including an explicitly empty set. Apply the same validation; show rejected pins without silently substituting model choices. It is never required.
- Remove the hardcoded `DOCN → AKAM` peer in `event_comparison.py` and route that comparison through this mechanism.

### A3. Analyst expectations

- Read revenue and EPS estimates (average, low, high, analyst count), the price-target range, the last four earnings surprises and estimate revisions from the configured Yahoo source.
- Store them as a typed record with retrieval time, labeled **vendor consensus, unverified**. They fill the existing consensus slot in `event_comparison.py`.
- They never enter verified calculations and never become accepted evidence. Any price sensitivity built on them (B1) is a separate block labeled as vendor-consensus based, kept apart from guidance-based figures.
- **Historical runs:** the vendor has no point-in-time history. Do not fetch today's estimates for a past analysis date. A previously retained snapshot captured at the original run's cutoff may be replayed with its original timestamp and hash; otherwise expectations are unavailable, with that reason.
- Show management guidance beside consensus for the same period. State the difference only when fiscal period, metric, currency, unit and accounting basis match; an unknown basis or adjusted-versus-GAAP mismatch is not comparable. Retain vendor as-of information when supplied; retrieval time alone does not establish freshness.

### A4. One valuation section

Extend plan one's "what the price implies" into a single section, near the top of the decision:

- The implied multiple today, on each share and obligation basis plan one publishes. Every multiple in the section states its basis: equity value or enterprise value.
- Own-history low, median, high and today's position.
- Peer table: multiple, growth, gross margin, with dates.
- Guidance versus consensus.

Give the same section to both debaters, the Research Manager and the Portfolio Manager through the existing shared context. Each row is independently available or unavailable with a reason; a missing peer or missing consensus does not hide the rest. These rows do not establish fair value.

### A5. Advisory audit pass

One new step after the risk debate and before the Portfolio Manager decides.

- **Input:** the accepted evidence brief, the valuation section, the four analyst reports, both debates, the Research Manager's plan and the trader proposal.
- **Task:** list claims unsupported by the supplied evidence, claims that contradict it, and figures that do not reconcile with each other or with the brief. Absence from a bounded brief means "not supported by the supplied material", not proof that no source exists. It does not give a rating or an opinion on the stock.
- **Output:** a bounded structured list (at most 20 findings). Each names the role, quotes a claim actually present in that role's supplied text, gives the issue type and cites a known evidence label or states that support is absent from the supplied material. Code validates labels and quoted-claim attribution, and excludes invalid findings while retaining rejection counts and reasons. A valid label alone does not verify the auditor's interpretation.
- **Model:** the deep-tier model. No new model setting is added.
- **Independence, disclosed by role:** the deep tier also writes the Research Manager's plan, so the audit is same-model review of that plan in every setup. It is cross-model review of the analysts, debaters and trader only when the quick and deep tiers differ. The report states, per role, whether the reviewer was a different model. Do not call the pass independent without that qualification.
- **Status:** one of `completed with findings`, `completed with zero findings` or `unavailable` (failed, malformed, over limit or all submitted findings rejected). A valid empty list is zero findings; rejecting a nonempty list is not. Disclose partial rejection with the retained findings.
- **Authority:** advisory. The audit node cannot mutate the canonical rating or accepted evidence, or add a publication veto. The Portfolio Manager may reach a different decision after reading it and states which findings mattered. Existing final validation and publication gates still apply.
- **Report:** a short "Advisory audit findings — model-generated, unverified" section, with status, the independence statement and counts by issue type saved in the run state. The counts describe this run; they do not rank setups (see A7).
- **Arithmetic:** debaters are told to cite calculated figures from the brief instead of computing their own. A computed figure absent from the brief is unverified and eligible for a finding, not automatically a proven error. No calculator tool is added to the debate.
- This adds exactly one model call per run. Version the checkpoint signature so older runs cannot resume past it.

### A6. Two-round debate option

- Add a two-round choice to the research-depth menu, for both the research and risk debates, alongside the existing 1, 3 and 5. Accept it in saved preferences.
- Do not change the user's saved depth. The user selects it.
- Record rounds, model calls and debate length in the run state, so the effect of depth is measurable.

### A7. Model-setup comparison

A fixed pilot procedure, run by the existing proof runner, so that two setups can be compared on the same footing.

- **Setups (decided by the user, 2026-11-05):**
  - **A, baseline:** GPT-6.1 Terra Pro (`openai/gpt-6.1-terra-pro`) for both tiers. This is the user's current setup, kept so the result shows whether switching helps.
  - **B:** GPT-6.1 Sol (`openai/gpt-6.1-sol`) for the quick tier (analysts, debaters, trader) and Claude Opus 5.5 (`anthropic/claude-opus-5.5`) for the deep tier (Research Manager, Portfolio Manager, audit).
  - Confirm all three model IDs are served by the configured provider before any paid run. The table carries each setup's audit-independence statement from A5. No silent model substitution.
- **One-time test.** Six runs, done once. No schedule and no recurring cost. The procedure stays available for a later rerun only on request.
- **Design:** same ticker, same analysis date, after the US close, two rounds, three runs per setup.
  - **Frozen inputs:** use one retained subject package and cutoff, covering SEC facts and filings, canonical price/history/indicators, consensus, news/social samples and default-peer data. Start each run from the same prior-publication and memory snapshot; never feed an earlier comparison run into a later one. New peer selections may differ as an output: each new peer lookup must be cutoff-bound and retained, with the same request receiving the same source data across runs. Record common-input and per-request hashes separately. If a material input cannot be held fixed, disclose the difference and report descriptive results without a controlled-comparison ranking.
  - **Held constant:** source/prompt versions, depth, tool limits, analyst selection and declared output/context caps. Record each model's reasoning settings, resolved model/provider, truncation and cache usage; do not pretend unlike providers have identical reasoning controls.
  - **Order:** balance adjacent pairs (A, B, B, A, A, B) to reduce order bias; this does not eliminate provider or latency variation.
  - Three runs per setup show run-to-run spread. They support a pilot reading, not a general claim that one setup is better.
- **Primary measures, computed in code and independent of any auditor:**
  - accepted, rejected and submitted counts for structured financial claims and disclosure records, plus acceptance rates; zero submissions is `N/A`, not 100%. These checks do not measure every free-text assertion;
  - whether valid peers were proposed;
  - whether the debate and decision cite valid valuation-section evidence labels; citation presence is usage, not proof that the conclusion follows;
  - model calls and cost.
- **Secondary measure, one common rubric:** one runner-only reviewer model and fixed settings, named with the budget proposal, scores each saved output against its retained evidence and calculations using the same rubric. Give it fresh context, randomize opaque run IDs/order, and remove model/setup metadata and each run's own audit verdict; retain substantive analysis and citations. Do not reveal the mapping until scores are saved. Disclose overlap with a setup's models and that writing style may still reveal identity. This adds six review calls, whose findings remain model judgments rather than verified error counts; it adds no product model setting.
- **Reported but not used to rank:** each run's own audit findings. The two setups use different auditors, and a weaker auditor may simply miss more.
- **Not a measure:** investment outcomes on past dates. Each model already knows what happened after a past date, by a different amount, so that comparison would be biased. Outcomes are recorded going forward as usual and are not used to pick a winner here.
- **Output:** one comparison table with per-run values, completeness/failures and min–max spread for each measure. No composite winner from arbitrary weights. If within-setup spread exceeds the between-setup gap, label that measure inconclusive; a smaller spread does not establish statistical significance. State the result as a pilot on one ticker and date, and distinguish evidence acceptance, reference use, reviewer judgments and cost.
- Isolated results, cache, memory and preferences. The user's saved model choices are not changed.

**Runner work before paid execution:** the tracked `docs/reviews/docn-abc-proof-tools/live_cli.py` currently fixes Terra Pro, depths 1/5 and an older budget; `frozen_c_replay.py` freezes SEC companyfacts, not a full analyst run. Inventory the retained plan-one harness and extend the applicable existing code narrowly for depth 2, the named models, per-model reservations and the required frozen inputs. Use new task-specific proof and comparison ledgers; preserve all old ledgers and never inherit their spending authorization. Enforce caps before each request, disable automatic retries, retain reservations for unknown costs, and keep jobs observable and recoverable without duplicate launches. Qualify the harness offline before either budget can be spent. The comparison remains a source-frozen paid experiment, not a substitute for either live CLI proof.

**Proof (Part A):**

- The DOCN history series reproduces by hand from the retained November 5 evidence and price cache.
- Recorded packages for two peers reproduce by hand.
- Peer rejection cases: unknown ticker, the subject itself, foreign currency, no revenue.
- A split inside the window; fewer than four quarters; missing consensus; a historical date.
- A peer uses older eligible facts when its latest filing is after the cutoff; it is excluded only when no usable cutoff-eligible package exists. Pinned, empty-pinned and rejected-pinned sets retain their authority.
- The previous peer set is reused and a change is displayed.
- Reference points add no model calls; the audit pass adds exactly one. The shared context stays bounded.
- A second issuer from existing fixtures.
- Audit pass: offline fixtures cover unsupported and contradictory claims, unknown labels, misattributed quotes, partial/all-rejected findings, failure and valid empty output. The node does not mutate rating or accepted evidence; the Portfolio Manager still has decision authority and normal validation. Per-role independence is correct. In the Part A live proof, verify the node executes and manually reconcile its findings/status with the supplied reports. Parser fixtures do not prove real-model detection accuracy; if no relevant errors occur, report execution as verified and error-detection behavior as unobserved.
- Depth option: two rounds produce two research and two risk rounds; existing 1, 3 and 5 are unchanged; a saved preference is not overwritten.
- Comparison: common input hashes match across runs, repeated peer requests match and no cross-run memory leaks occur; primary measures reproduce, including zero submissions and failed runs; reviewer inputs contain the evidence but omit setup labels and internal audit verdicts; incomplete or confounded results are not ranked. Offline checks prove the new model/depth budgets and recovery without paid calls.
- Peer sequence: a first run shows no peer statistics to the analyst and a final table to the debate; a later run pre-fetches the default set; a changed peer is fetched after the analysts with no added model call.
- History dates: a quarter with only a cover-page share count is unavailable; quarter-end shares carry their measurement date.

## Part B — forward price range

**Files:** `agents/{valuation,funding,shared_valuation,valuation_comparison,schemas,decision_context}.py`, `analysts/fundamentals_analyst.py`, `managers/portfolio_manager.py`, reporting and tests.

### B1. Mechanical grid, no model input

Whenever Part A's reference points and a verified revenue outlook exist, code publishes a small grid:

- **Basis:** Part A's history and peer multiples are equity value ÷ revenue. On that basis, price = revenue × multiple ÷ shares, with **no** deduction for obligations. Deduct net obligations only when the multiple is enterprise value ÷ revenue, and never mix the two in one row. State the basis on every row.
- **Multiples, kept separate:** one block using the own-history low, median and high, and one block using the peer low, median and high. Do not merge the two ranges or compute a statistic across them.
- **Revenue rows, sourced values only:**
  - Guidance-based: the low and high ends of a management range for the guided period. A growth floor (for example "at least 60%") yields one row labeled "at the guidance floor", with the source, base revenue, base period and held-fixed assumptions stated. It is not a lower bound on the future share price and is never expanded into an invented low, middle and high.
  - Vendor-consensus sensitivity: the consensus low, average and high, in a **separate, clearly labeled block**. It is never placed beside guidance rows as if equally sourced and never becomes verified evidence.
- **Shares:** reported shares and, where source-grounded, guided diluted shares as a labeled sensitivity. Retain share date, guidance period and the distinction between outstanding shares and period-weighted diluted shares; do not describe a weighted average as a forecast year-end count.
- **Return:** each price against the last completed close.
- **Periods:** show the revenue period and valuation horizon on every row. Do not combine current-year guidance with next-year consensus or pool prices from different horizons into one range. Returns are price changes against the completed close, not annualized or dividend-inclusive returns.

Label it "mechanical sensitivity from reference ranges, not a forecast". It is the floor: the section exists even when the model proposes nothing, which has been the case in most real runs.

### B2. Three model cases with funding and dilution

- Replace the free-form scenario list with one structured set: pessimistic, middle and optimistic. Each case states revenue, operating cash margin, cash capital spending, lease and debt principal, how any shortfall is funded (equity at a stated price, or debt), and an exit multiple.
- Code runs each case through the existing `ForwardCapital` bridge to get closing cash, obligations and share count, then prices it. A funding shortfall the case does not fund stays visible as a gap; no cash is plugged.
- Each case states its multiple's basis and is priced with the matching formula from B1. An EV/revenue assumption cannot cite an equity/revenue statistic as though it were the same multiple; any conversion requires a matching, verified obligation perimeter, otherwise it remains unavailable as that reference. Preserve vendor-derived assumptions as conditional, never accepted evidence.
- Each assumption must cite a reference point available to the analyst when it writes: a guidance record, a history statistic, a verified fact, a default-set peer statistic or a consensus row (cited as vendor data). After the final peer table is fixed, code labels any assumption outside the published reference range as **outside reference range**, with its stated reason. The cases still reach both debaters before their first turn, with no added model call.
- Scenarios built on a past earnings period are published only as historical diagnostics, under plan one's suitability metadata.
- Case weights are optional and remain labeled subjective. No expected return is published from them.
- The price is for the end of the forecast year and is not discounted. Say so beside every figure. Do not relabel it as a 3–6 month target.

### B3. Decision use

- Both debaters receive the grid and the three cases before their first turn and are asked to dispute specific assumptions.
- The Portfolio Manager may adopt or revise a case through the existing final valuation request. Final validation and publication authority are unchanged. Tampered saved prices are recalculated.
- The decision card states the basis: "valuation" only when the final validated request supports the adopted case, otherwise "risk assessment" as today. It shows comparable supported cases for the same horizon and where the completed close sits; if it falls outside, say so. Unfunded, rejected or decision-ineligible historical cases remain diagnostics and do not set the decision range.
- Advisory thesis conditions may reference a case assumption (for example, the revenue the middle case needs), using the existing condition records.

**Proof (Part B):**

- Each grid cell and each case recomputes by hand on the DOCN fixture, on the stated basis; an equity-basis row with an obligation deduction, or a row mixing bases, fails a test.
- History and peer blocks are separate; a growth floor produces one labeled row; the consensus block is separate and labeled, and removing consensus leaves the guidance-based grid unchanged.
- Mixed fiscal horizons, unknown consensus accounting basis, weighted-average versus closing shares and an unsupported EV/equity multiple conversion cannot silently produce a comparable decision range.
- Equity-funded, debt-funded and unfunded-gap cases.
- Share-basis mismatch and negative equity value.
- An out-of-range multiple is labeled; an assumption with no reference is rejected.
- A missing outlook yields a specific unavailable reason and no guessed grid.
- The grid appears when the model block is empty or malformed.
- A valid early case cannot bypass an invalid final request.
- Canonical rating authority unchanged; no added model calls.
- Old checkpoints cannot resume under the changed prompt contract; old records stay readable.

## Integrated acceptance

Part A, then Part B. Each is independently reviewable and releasable; do not hold Part A for Part B.

Part A's reference/audit/depth features and comparison tooling can be accepted after their applicable checks pass while the unapproved paid comparison remains explicitly pending. Do not hold those features or the user's opportunity to review reports for an unapproved experiment, and do not claim the comparison itself is complete. Additional report generation remains outside the two-attempt proof budget.

**Stop after Part A.** Completing Part A does not authorize Part B. Part B starts only on the user's explicit go-ahead, given after they have reviewed two or three real reports containing Part A. Reconcile Part B's design with what those reports show before starting it.

At each part's boundary, account for the complete offline test inventory using fresh results and demonstrably valid reused evidence. Run affected and previously unrun tests; use the full-suite command below when coverage impact or an explicit gate requires a fresh full run. Run full lint, dependency and diff checks from the worktree's environment:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m pip check
git diff --check
```

Reuse earlier passing results only with a recorded source, dependency and configuration justification. After corrections, rerun the affected checks; repeat the full suite only when impact or an explicit gate requires it. Results combined across revisions are not one full run on one commit. Evidence reuse does not replace the independent review, the recovery and resume checks, or CI on the exact published commit.

Affected recovery checks cover interruption before/after the new audit, publication retries without duplicate records/calls, and legacy records/checkpoints. Recheck REVIEW/no-action-memory/scoring exclusions and nonstock/technical-only paths. Live proofs must record source timestamps, canonical completed-session metadata and exact source/configuration versions. Missing live observations remain disclosed; an empty peer/case output is not evidence that the intended live feature worked.

Replay the retained November 5 run into new artifacts and inspect the rendered Markdown, HTML and CLI. Verify the originals by hash.

Once implementation of the relevant part is authorized: one real CLI attempt per part under the approved two-attempt/$10 aggregate proof budget, all four analysts, lowest depth, started after the US close. Part B remains subject to its separate start approval. The A7 comparison is a separate paid step requiring its own approved ceiling, run only after Part A's own proof passes. Record honestly whether the model proposed peers and cases. An empty proposal proves the fallback, not the feature; investigate the cause before requesting any additional attempt. Fixtures prove arithmetic; they do not prove live model behavior.

One independent code-and-artifact review per part, focused on share, period and obligation bases, cutoff integrity for peers and consensus, and the separation of vendor and verified data. Close confirmed material findings in the same worktree.

Finish with committed source, tests and evidence records, a clean worktree, the exact commit, spend, deferred findings and risks. CI must run on the exact published commit when publication is later authorized.

## Limits to state in the report

- A reference range describes how the market has valued the company and its peers. It is not fair value.
- Model-selected peers can be imperfect comparisons. The reasons are shown so a reader can judge.
- Vendor consensus comes from one free source and can be missing or stale.
- Nothing here shows the ratings have predictive value. Only a track record can, and the watchlist that would build one quickly is parked.

## Decisions

- **Approved in conversation:** valuation is the focus; the model selects peers by default; the audit pass, two-round option and model comparison are added to Part A.
- **Comparison setups:** decided. A is GPT-6.1 Terra Pro for both tiers; B is GPT-6.1 Sol (quick) with Claude Opus 5.5 (deep). One-time test.
- **Comparison budget:** not yet decided. It covers six runs plus six rubric-review calls, and follows a token estimate for the two-round workflow.
- **Part B timing:** confirmed by the user on 2026-11-05. Part B does not start automatically. After Part A is accepted and separately authorized for installation, the user reviews two or three real reports that contain it, then gives a separate go-ahead for Part B. Preparing a design for both parts does not authorize building both straight through.
- **Paid proof:** $10 aggregate ceiling for at most two attempts, one per part, approved by the user on 2026-11-05. Failures count; extra attempts require approval. Comparison runs and additional report generation are outside this allowance.
- **Deferred:** weekly watchlist and scoring summary, discounted cash-flow valuation, a second consensus source, a separate third model setting for the audit.


## Authorized B1-only amendment — 2026-11-05

The user's later Goal authorizes the missing-close repair, Part A push and staging PR for exact-head CI, then **B1 only** in a separate isolated worktree. This supersedes the earlier blanket Part B start hold only for B1. B2 model cases, B3 decision adoption/prompt expansion, the model comparison and installation remain unapproved. Merge, B1 publication and worktree removal require separate approval.

- Vendor annual "next fiscal year" estimates may produce conditional arithmetic only in the separate vendor-consensus block, explicitly labeled **unverified dates** when exact fiscal dates are absent. Retain the vendor relative period code; never infer calendar/fiscal start or end dates. Unknown units/currency still prohibit prices; unknown accounting basis remains visible and cannot become a comparable verified decision range.
- With fewer than three accepted same-session peers, show individual peer multiples and individual sensitivities. Publish no small-sample low/median/high aggregate. Earlier saved schema 1/2 references remain exactly replayable; new schema 3 references use the minimum-three rule.
- B1 remains deterministic from source-only guidance and retained validated reference/price records, independent of model scenarios, targets and prose. Its report/CLI pane and typed evidence remain separate from the canonical decision, memory learning, scoring and any final target. REVIEW continues to withhold financial output; asset and recovery boundaries remain intact.
- No new paid CLI/model/audit call is authorized by this follow-up. Retained-input offline replay is labeled retrospective and is not live proof. Any later paid B1 proof requires approval of its exact scope and reservation; preserve earlier ledgers and do not infer retry authority.
- Part A is frozen at 24172f6c05a332f4c74f8b9984e61564feae09d4 in [staging PR #5](https://github.com/zippirot/TradingAgents/pull/5). All seven jobs in [CI run 42150548960](https://github.com/zippirot/TradingAgents/actions/runs/42150548960) passed, including exact-head test/install/lint steps. It has not been merged or installed.
- B1 branch: codex/valuation-reference-b1, worktree /Users/zipp/Developer/tradingagents-valuation-reference-20261105/part-b1. Its environment uses the same 90 noneditable dependency pins, with independent runtime paths and private retained inputs outside Git.

Focused B1 estimate: **medium**, recommended **GPT-6 Sol (gpt-6-sol), medium reasoning**, honoring the user's explicit Sol choice. Approximate active implementation/verification **3–6 hours**, assuming the existing source-only guidance reader and publication/report mechanisms suffice. This narrower B1 scope excludes funding cases and final target adoption; stronger model guidance in the original full-Part-B estimate is not silently applied. Codex credits cannot be estimated credibly without workload measurements. This is planning guidance, not a new spending limit.
