# Completed-price fallback and Part A publication

Authorized scope (2026-11-05): repair an empty latest completed close, publish Part A for staging CI, then implement B1 only separately. Merge, installation, B2 and the comparison remain unapproved. No new paid analysis is authorized.

## Price behavior

The reader normalizes actual missing provider closes (null, numeric NaN and blank strings) into retained nulls. The latest eligible completed bar with an empty close falls back to the last valid completed session, within the existing seven-calendar-day staleness bound. It retains the empty source bar, hash, selected session and explanation. Nonempty malformed values, infinity, boolean, nonpositive prices, unknown split actions and invalid issuer/currency metadata remain invalid. Incomplete/future sessions never supply the canonical close.

Source briefs, price-implied/scenario sections, stock/snapshot provenance and indicators display the selected date and fallback explanation. Indicators keep an empty newest date unavailable; they do not assign the prior close to that date. Checkpoint signatures advance price_observation to 3 and completed_market_inputs to 2; older records remain readable.

A peer with an earlier fallback date is shown as an individual dated diagnostic, excluded from the subject's same-session peer range. Its multiple is recomputed from validated source facts at its actual price date. A peer matching the subject's fallback date remains eligible for the ordinary data checks. Data validation does not establish business comparability.

## Retained evidence and limits

The retained NET source has November 5 missing and November 4 close 266.5799865722656. The legacy source encoded provider NaN as the nonempty string "nan"; the offline migration explicitly normalizes that known legacy encoding to null in a new derivative. Literal nonempty "nan" in a new provider response remains invalid. The original source/receipts are not edited; the derivative is retrospective offline evidence, not a new live quote or model analysis.

Original NET raw source SHA256: 51f34e13b69d5840669611af349d61e89c98a1da9d3ed9cb1684bc588a86c627. New canonical NET derivative SHA256: b1ec2988a3fe38f43b17c853f86d0049e34d3ade582c5270307f501040145f32.

Source dates, shares, revenue periods, conditional cover-share assumptions and price/source hashes remain retained. Earlier live audit findings and live model outputs are unchanged. No new observation establishes model peer-selection success or audit error-detection accuracy.

## Verification accounting

M1 Pro/16 GB identity reverified. GitHub staging fetched and still ac661ca291599a8e3e9701bed73f60d979d38a01, with no drift.

At the stable fallback candidate, 744 affected checks pass, covering acquisition, shared analyst contexts, tool capture/audit integration, price/peer arithmetic, report integrity, publication, checkpoint/restart and stock/crypto scope. A further 51 sibling no-data/rate-limit/cache-write/date-boundary checks pass. Full Ruff, pip check and git diff --check pass. Reader-specific 36 checks and OHLCV-specific 68 checks overlap those results; counts are not additive. Evidence logs, commands and source hashes are under the M1 task root evidence/price-fallback, with the sibling run in sibling-market-checks.log.

Reused: earlier passing full offline coverage and unaffected provider/funding/math checks, recorded in the Part A acceptance and peer/audit repair records. Sources outside the listed changes, Python environment and dependency pins remain unchanged; no dependency or model/preference changes were introduced. Fresh affected checks cover shared price/context/report/recovery consumers. Combined results across revisions are not one complete passing suite on one revision. Exact-head GitHub CI remains a publication gate.

Independent review identified a diagnostic presentation omission; the actual revenue period and accounting definition are now displayed. The final 42 consumer/flow/HTML checks and full Ruff pass after that correction. Earlier arithmetic/source checks remain valid because only these labels and their regression assertions changed.

The independent code/artifact review and current retained-input rendered replay are recorded in the task's private/evidence and evidence directories. All confirmed material findings must be resolved before push.

## Spend and release boundary

No new paid calls. Prior proof spend remains $2.33108810 for 34 settled requests; no retry authority is inferred from the unused ceiling.

Part A push and one staging PR are authorized for CI. Merge and installation remain pending separate approval. B1 begins only after publication, on a separate isolated branch/worktree. Its vendor "next fiscal year" sensitivities will carry unverified dates in a separate vendor block; fewer than three accepted peers will be individual rows, without a pooled range. B1 publication itself is not authorized.
