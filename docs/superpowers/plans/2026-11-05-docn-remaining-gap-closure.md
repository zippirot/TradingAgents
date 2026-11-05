# DOCN remaining-gap closure plan

Status: local implementation, verification and independent audit authorized by
the November 5 Goal. Analysis-timezone behavior, additional paid attempts/budget
and branch push/draft PR remain reserved decisions until answered. No integration
or launcher installation is authorized.

## Outcome and starting point

Finish the remaining correctness, readability and verification gaps so the user
can judge a release-ready research tool from reproducible evidence. Do not
manufacture a price target, condition outcome or investment-performance claim to
make an acceptance row green.

Continue in `/Users/zipp/Documents/ChatGPT/Tauric/worktrees/docn-abc-gap-closure`,
branch `codex/docn-abc-gap-closure`, starting from
`eade6d9a43737c4d82af31dc1be704ed9df1cdf4`. The three medium defects from the
interactive audit are already fixed; preserve their regressions. The launcher
remains at `b075166df6f1738ef691cee23d1473e5085e05a1` and must remain untouched
through this plan's development acceptance.

Authoritative inputs: the November 5 interactive-audit closure/evidence records,
the correction-audit JSON, and the existing A/B/C and shared-valuation plans.
Recheck branch cleanliness, actual HEAD and applicable repository instructions
before execution. Do not reset or overwrite unrelated changes or silently rebase.

## Delivery estimate

- Build size: **extra medium**.
- Recommended model: **GPT-6 Astra (`gpt-6-astra`), medium reasoning** for the
  integrated execution and final assessment. Date cutoffs, legacy settlement,
  immutable records and financial assumptions interact in ways that plausible
  local tests can miss. Bounded independent implementation can use GPT-6 Sol
  (`gpt-6-sol`), medium, under the user's routing policy.
- Active implementation and verification: **18–30 hours**, assuming existing
  providers remain available and no substantial packaging incompatibility is
  uncovered. Excludes waiting for authorization and future market observations.
- Codex credits: not credibly estimable from the available usage records. Do not
  derive credit consumption or time savings from API token prices/model strength.
- Proposed additional proof/audit spending ceiling: **$65**, not an expected bill:
  $50 live research and $15 independent audit/rechecks. Prior combined usage is
  approximately $23.75, so the proposed maximum remains below the original $100
  total and within its $70 live/$30 audit subceilings. Reconcile actual ledgers
  before spending. Codex usage and any GitHub Actions charges are separate.

Model recommendation is engineering judgment under the user's policy, not a
measured workload comparison. Official guidance describes Astra for demanding
end-to-end work; medium is the user's policy choice rather than the general
Astra default: https://developers.openai.com/codex/models.

## Scope and invariants

Use existing graph, providers, configuration, publication store, memory,
settlement, report renderer, proof runner and CI. No new service, scheduler,
broker action, automatic hard-rule enforcement, generalized calendar platform,
new paid data provider or model upgrade. Preserve strict validators, source
cutoffs, canonical rating authority, per-endpoint independence and repeat safety.

Never rewrite old immutable records or invent their publication times, timezones,
condition intent or benchmark declarations. Existing settled legacy outcomes
remain historical records; any questionable old outcome is labeled for review,
not silently overwritten. Missing or ambiguous evidence stays unavailable.

## Gap-to-proof map

| Remaining gap | Owner milestone | Required evidence |
| --- | --- | --- |
| Evening publication disappears on a next-day historical rerun | 1 | Explicit timezone/cutoff contract; before/after-cutoff and DST tests; real saved-record replay |
| Fixed 63-session retrieval span can miss mature endpoints | 2 | Bounded extension using actual available sessions, authentic holiday reference and missing-data counterexamples |
| Unversioned legacy memory can use an unfinished bar | 2 | Completed-session filtering through actual legacy settlement; no premature reflection |
| Harmless condition-label variants yield unknown | 3 | Narrow alias mapping with negative scope/basis cases; stable legacy identity |
| Long decimals, hash clutter, buried condition disposition | 3 | Readable Markdown/HTML/CLI with full provenance retained in evidence/appendix |
| Python matrix and clean-install not demonstrated | 4 | Fresh isolated environments, actual imports and full workflow-equivalent checks |
| No live final target or forward-funding request | 5 | Source-sufficient, model-origin requests through the normal CLI; unsupported cases remain explicit |
| No live classified condition met/breached | 5 | Clearly identified real prior or prospective test-seed condition on already reported data; no fabricated historical opinion |
| Saved depth 5 unverified | 5 | Actual Deep invocation, measured rounds/configuration, report/persistence/restart checks |
| Exact final-commit GitHub CI absent | 6 | Authorized draft PR and successful required checks on final branch HEAD |
| Connected auditor cannot inspect raw runtime evidence | 6 | Frozen audit plus independent local artifact/source verification, separately described |

## Milestone 1 — define and implement the historical cutoff contract (4–6h)

**Files:** `tradingagents/graph/trading_graph.py`, `dataflows/date_window.py`,
`memory/thesis.py`, `memory/publication_outcomes.py`, relevant state/configuration
and point-in-time tests. Change other consumers only where required for one
consistent explicit cutoff.

**Recommended behavior, requiring approval as part of this plan:** a date-only
analysis means the end of that calendar day in the run's explicitly resolved
**analysis timezone**. For this user's Mac, use `America/Denver`. This matches
the calendar date used to launch research; do not assume the stock exchange's
calendar day is the user's analysis day. Accept an explicit timezone-aware UTC
cutoff for historical replay unchanged. Do not replace historical cutoffs with
current time. Price-bar eligibility continues to use the instrument's session
clock, separately from the analysis clock.

Resolve the analysis timezone once per run, retain its IANA name and computed UTC
cutoff in new nonsecret metadata, and pass the same cutoff to prior-thesis,
resolved-outcome and lesson lookup. Prefer existing configuration mechanisms;
no mandatory new confirmation in the research flow. Unknown timezone retains
an explicit conservative UTC fallback, not a guessed zone. Do not infer a
legacy record's timezone; compare its existing actual publication timestamp
against the query's explicit cutoff. Legacy lessons with date-only resolution
metadata must remain conservative: do not invent a resolution timestamp or
make them newly eligible through an assumed timezone. Preserve stricter
source-date guards.

Test Denver evening/next-UTC-day publication, New York and UTC analysis clocks,
DST transitions, exact cutoff equality, explicit timestamp override, and a
publication one instant after cutoff. Re-running yesterday tomorrow must not
admit a genuinely later publication or resolved lesson. Replay actual retained
DOCN publication timestamps; show precisely which records become visible and
why. Update the checkpoint contract for any changed state/context semantics.

## Milestone 2 — finish settlement calendar and legacy-bar handling (3–5h)

**Files:** `tradingagents/memory/settlement.py`, `publication_outcomes.py`, existing
Yahoo price helpers and settlement/calendar/crypto tests.

Replace the single estimated calendar span for trading-session endpoints with
bounded extension of the existing provider request when an endpoint may be
mature but not enough completed instrument sessions were returned. Fetch only
through the completed-session cutoff; stop promptly for genuinely immature
windows. Reuse fetched history rather than repeatedly fetching identical spans.
Use at most two additional bounded extensions per settlement pass; if data is
still insufficient, retain pending with a specific retrieval/coverage reason.
Do not let a fixed old end date make a mature endpoint permanently pending.
Retain entry identity, timezone consistency, source provenance and the declared
stock-exact/crypto-asof benchmark policy. Do not interpolate missing prices or
silently convert sessions to calendar days.

Reproduce the non-US holiday probe with an authentic retained provider series
or authoritative exchange holiday dates, not an unlabelled hand-entered calendar.
Exercise 5/21/63 sessions, delayed first entry, clustered closures, suspension or
missing bars, month-end calendar endpoints, and independent benchmark absence.

Route **unversioned pending memory entries** through the same completed-bar
filter before generating a reflection. Preserve their unknown publication time
and legacy benchmark convention; do not imply an executable trade. Today’s bar
must not resolve a legacy endpoint or trigger the paid reflection. Once a valid
completed window exists, settle/reflection once; repeat and interruption tests
must preserve the existing safeguards. Do not change settled legacy history.

## Milestone 3 — usable condition matching and report presentation (2–3h)

**Files:** `memory/thesis.py`, `agents/decision_context.py`, `shared_valuation.py`,
`valuation_comparison.py`, `schemas.py`, `reporting.py`, `report_html.py` as needed.

Add only explicitly tested aliases for identical concepts: case/whitespace for
supported metric names, `%` → `percent`, and a documented `GAAP` → `US-GAAP`
alias only within established US-GAAP evidence scope. Preserve original proposed
wording as diagnostics. Do not equate adjusted/non-GAAP/IFRS, different currencies,
per-share versus aggregate amounts, annual versus quarterly periods, or a
specialized definition with consolidated metrics. Unknown/ambiguous variants
remain unknown. Normalize before comparison/measurement identity for new
proposals; preserve saved IDs and aliases for prior publications without rewrite.

Render prices to two decimals and percentages to a sensible bounded precision;
keep exact Decimal values in calculation payloads. Handle large/tiny values
without presenting a nonzero value misleadingly as exact zero. Move opaque
source IDs/hashes out of the decision card into the existing evidence references.
Keep human-readable source labels and full traceability. Put a compact condition
status/role/disposition/reason summary next to the canonical rating; retain the
full detailed section. Do not promote rationale to verified evidence or hide
unknown/overridden conditions. Verify actual retained DOCN Markdown and HTML,
including an explicit support breach and unmet reconsideration trigger. Inspect
browser-rendered HTML if available; otherwise report that visual check as pending.

## Milestone 4 — local compatibility and clean-install verification (2–4h)

**Files:** `.github/workflows/ci.yml`, `pyproject.toml`, packaging metadata only if
an actual in-scope defect is demonstrated. Do not change CI just to skip failures.

The current workflow tests Python **3.11, 3.12, 3.13 and 3.14**, plus Python3.12
under America/New_York; it also runs full-repository Ruff and a no-dev clean
installation/import smoke. Reproduce these in fresh isolated environments where
available. Record interpreter, platform, dependency versions, source SHA and
commands; syntax parsing is not execution. If an interpreter is unavailable,
record the missing leg for GitHub CI rather than calling it passed.

For each available matrix environment, mirror `pip install -e '.[dev]'` and
`pytest -q`; also run `TZ=UTC pytest -q` and `TZ=America/New_York pytest -q` on
Python3.12. Run `ruff check .`, `python -m pip check`, and `git diff --check`.
For clean-install smoke, build/install the candidate into a fresh no-dev venv
and import `tradingagents` and `cli.main` from **outside the checkout**; verify
module paths point into that venv. This is a temporary test installation, not
replacement of the user's launcher. Capture wheel/build provenance if used.
Retain documented optional skips; do not silently add optional dependencies to
make unrelated checks appear complete.

## Milestone 5 — close missing runtime evidence at normal and Deep depth (4–7h)

**Files:** existing `docs/reviews/docn-abc-proof-tools/` utilities; existing analyst,
PM and valuation paths only if diagnosed defects prevent valid requests reaching
publication. Extend the runner's allowed run name/date/depth and cost guard;
do not create another ledger or reset the seven prior attempts.

Before paid calls, use offline source review and deterministic validation to
select a real issuer/date with adequate forecast, share-count, obligations,
funding/dilution and price inputs. DOCN need not be forced to satisfy this if its
available evidence does not. User-facing assumptions remain explicitly research
assumptions; management guidance is not required where a supported analyst
forecast is valid. No invented source facts, thresholds or probabilities.

Proposed paid schedule: three planned attempts plus one diagnostic retry reserve,
**four additional attempts total, at most two Deep**, with retries counted:

1. Shallow normal CLI run on the preflight-qualified issuer: seek a genuinely
   model-origin supported final valuation request and a forward-capital scenario.
   Inspect retained requests, funding bridge, dilution, prices, report and saved
   canonical evidence. A seeded request or offline calculator pass is not proof
   that the live model generated and carried it through the normal workflow.
2. Deep DOCN run with **5 debate and 5 risk rounds**, existing providers/models,
   fresh isolated state and copied prior publications. Prove actual executed
   rounds/call bounds, strict gate behavior, scenario/condition context reaching
   debate/PM, canonical report and restart. Use runtime-only depth overrides;
   saved user preferences must hash-identically before/after.
3. Shallow real-model run with a prior classified condition whose measurement
   period is already reported. Prefer a genuine eligible prior publication. If
   none exists, use an explicitly labeled **prospective engineering seed**
   created now and shown to the real model; never label it a past real opinion.
   Show both a supporting-condition and reconsideration-trigger disposition,
   observation provenance and unchanged rating authority. This proves live
   plumbing, not a naturally matured investment thesis. If a prior planned run
   already covers these assertions, omit this call.
4. Reserve one retry only after a precise diagnosis; it can be the second Deep
   attempt if that is the affected proof. Do not repeat until a desirable rating,
   target or scenario appears.

All attempts use isolated results/cache/checkpoints/memory/preferences and
privately loaded existing keys. Validate serialized model/depth/cost settings
before calls. Retain source manifests and original failures. If a qualified
model abstains from a target/funding request, record the reason and trace the
omission. Fix a real transport/prompt/parser defect when supported; never weaken
validation, force a target, or relabel an injected fixture as live model output.
If the cap is reached without the required evidence, that acceptance item stays
open for a concrete budget/scope decision. Offline work continues independently.

Live final targets, forward funding, depth5 and classified-condition observations
are separate acceptance rows. One successful run may satisfy several rows, but
passing one cannot stand in for another. Prospective 3/6-month performance remains
pending until time passes; no recurring automation or performance guarantee.

## Milestone 6 — independent closure, exact-head CI and handoff (3–5h)

Commit the verified candidate. Obtain independent review of cutoff/legacy data
integrity and financial runtime evidence. Use the connected completed-build audit
on explicit base/head, this plan and evidence; supplement its frozen-diff scope
with a separate local reviewer who reads raw artifacts, checks hashes and runs
focused cases. Do not describe the connected audit as having executed tests.
Validate findings, fix confirmed material portions, rerun affected checks and
obtain targeted independent verification. Keep publication histories intact.

Create one acceptance table mapping every gap to code, focused tests, real proof,
source SHA, artifact hash, reviewer disposition and remaining limitation. Include
both positive and rejected cases. Preserve valid earlier proofs with an explicit
impact analysis; results across source revisions are not one passing live run.
Record runtime code hashes separately from documentation-only Git deltas.

**After explicit publication authorization**, push only the task branch and open
a draft PR targeting staging. The current workflow runs for pull requests, not
ordinary pushes to `codex/*`, and has no workflow_dispatch trigger. Merely pushing
the branch will not close CI. Do not merge. Wait for the full existing matrix,
clean-install and lint jobs; verify the run corresponds to the PR's final head
and record whether checkout tested a GitHub synthetic merge or the head commit.
If only a merge ref is tested, add a bounded head-checkout verification using the
existing workflow before claiming exact-head coverage; retain the integration
check too. Approval of this plan includes that narrowly scoped local workflow
adjustment; publishing it still requires the separate remote authorization. Do not claim current staging health proves candidate health.

After audit fixes and final evidence commits, obtain green CI on the **final
branch HEAD**. Any subsequent source change invalidates affected evidence; any
new commit requires its own exact-head CI result. Report final SHA/run URLs in the
handoff without creating a further status-only commit that invalidates that claim.
If publication is not authorized, deliver a clean local candidate and accurately
leave remote CI pending; do not call all verification gaps closed.

## Decisions required before dependent work

1. **Historical cutoff:** approve the explicit analysis-timezone contract above
   (America/Denver for this user's date-only runs), distinct from exchange price
   sessions. Retaining UTC is the alternative but does not close the reported
   same-local-day continuity gap. No historical lookup may use current time.
2. **Paid proof authority:** authorize up to four more attempts (11 lifetime
   total), at most two Deep, and $50 live/$15 audit incremental ceilings within
   the original aggregate/subceilings. Existing seven-run authority is exhausted.
   This is a proposed limit, not a request to spend now or an expected invoice.
3. **Remote verification:** separately authorize pushing this isolated branch
   and opening a draft PR to trigger CI. Do not include merge, launcher update,
   production creation, installation or worktree removal in that permission.

Routine local implementation/verification after plan approval needs no milestone
approvals. Complete independent work while these material decisions are pending.

## Completion and release boundary

Development closure requires corrected remaining code findings, passing focused
and broad checks, the specified runtime evidence (or an explicitly approved scope
change), independent material-finding closure and a clean committed branch.
Full verification closure additionally requires exact-head GitHub CI. Preserve
pending future investment-performance observations as such, not software defects.

The user's actual launcher installation remains a separate release action:
after review of the concrete candidate and CI, obtain explicit staging integration/
launcher authorization, preserve an agreed rollback reference and data backup,
then perform launcher import/path/configuration/report smoke checks on that exact
installed commit. A paid installed-app research run needs remaining or separately
approved proof authority. Machine1/production stays outside this plan. Do not
quietly turn clean-install packaging smoke into a claim that the launcher changed.
