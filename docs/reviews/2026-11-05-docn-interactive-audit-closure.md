# Interactive audit correction record

The user-supplied interactive audit of 2b338e3571116faab2a346fbf7ace46878401a71
identified three medium acceptance defects missed by the earlier frozen audit.
The original completion statement was too broad. This follow-up stays on the
same isolated branch; it does not authorize integration or installation.

## Confirmed medium findings and corrections

1. New crypto publications incorrectly required exact SPY session dates.
   New crypto records now retain the existing nearest-prior benchmark-close
   policy, labeled asof with actual benchmark dates. Stock records remain exact.
   Existing immutable publication policies are not rewritten. Real calendar
   series tests exercise weekend entry/exit, settlement, one-time reflection,
   pending longer endpoints, legacy crypto imports and immutable re-export.
2. Predicate truth was displayed as though it always represented thesis support.
   Conditions now carry explicit advisory thesis_role: supports_thesis,
   reconsideration_trigger or unspecified. A false trigger is 'not met', not a
   failed thesis. Unclassified old records remain unclassified. Role metadata
   does not rekey measurement IDs or change ratings; original observations keep
   their interpretation. Conflicting roles stay unspecified. The PM schema and
   prompt request this intent; card and detailed report use distinct labels.
   Checkpoint advisory-thesis contract advanced to 2. A committed compiled-graph
   test covers memory, canonical observation, actual PM prompt, disposition,
   publication and a fresh graph restart for all three roles. Its upstream
   canonical evidence is a deterministic fixture, not a paid provider proof.
3. A source quote cut before '+' could pass the unscoped exact-value path, and
   explicit future periods could be labeled historical. Both now fail source
   validation. Valid at_least guidance and fiscal-year labels remain supported;
   no fiscal calendar is invented. Baseline/current recorded-source replay
   preserved all 15 DOCN and one NVDA valid claims with identical payloads.

Independent focused reviews accepted all three corrections. Crypto's affected
selection passed169 checks; disclosure selection passed172 and independent142;
role/graph/PM selection passed90 and final independent27. An initial full suite
found PM instructions exceeded the existing70000-character bound (70178); the
paragraph was condensed without loosening that bound or dropping semantics.
Final full suite:2230 passed,100subtests,one optional langchain_aws skip,one
integration deselection,20warnings,21.57seconds. Ruff/diff checks passed.
Log: results/docn-abc/interactive-audit-final-offline.log.

## Acceptance limits and deferred low findings

The audit's missing exact-commit CI, Python3.11/3.13 legs, clean-install smoke,
no live final target, no live forward-funding request, no live observed met/
breached Q4 condition, and saved-depth5 coverage are not represented as verified.
All paid proofs are deliberately Shallow under the user's seven-run budget;
no saved model/depth changes or depth5 run is authorized here. A numerical target
is not forced without supported inputs. Scripted graph coverage is separately
labeled and cannot substitute for required provider/runtime proofs.

Historical date-only prior-thesis lookup uses UTC end-of-day; evening US
publications on the following UTC date may be absent when rerunning the prior
date. This is a disclosed cutoff limitation. Switching it to current time would
admit future knowledge; a changed historical session-cutoff contract is deferred.
The reviewer-reported non-US63-session retrieval slack, pre-existing unversioned
legacy in-progress bars, exact-label condition matching, and remaining numerical/
source-reference presentation issues are deferred. None is silently claimed fixed.

The seventh/final authorized Shallow run and a connected targeted audit are pending.
No merge,push,PR,installation,deployment,production creation or cleanup is authorized.
