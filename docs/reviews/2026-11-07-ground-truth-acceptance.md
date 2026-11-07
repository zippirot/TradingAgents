# Ground Truth Audit build acceptance

November 7, 2026. Work in progress on `codex/ground-truth-audit`, based on staging `77ebc8abc30757f4bab0c106df9e3b56cd12aebf`. The plan was frozen in `2c0a5839`. Setup and the independent DOCN reference assessment were committed in `33f8cd54`.

## Authorized decisions

The user selected one Portfolio Manager reassessment before publication when a source-backed material correction undermines the recommendation. Source excerpts and mathematical fields receive code checks. The Portfolio Manager independently assesses their meaning and can retain the rating. Unsupported conjectures and vendor-only replacements do not establish a confirmed correction. Existing publication validators apply to the candidate.

The user authorized $50 combined provider spending for the pilot and independent Claude initial/closure review, including retries. Current allocation reserves up to $30 for the pilot and $20 for independent review. Unknown spending remains conservatively reserved. Private pilot payloads and billing artifacts live outside Git under the workspace output directory, `ground-truth-audit-proof`.

## Verification to date

- The setup agent ran 111 focused CLI/configuration tests successfully after observing the new behavior fail first.
- Primary ran 113 combined CLI, audit, export, publication and checkpoint checks successfully during integration. Subsequent engine and source-trust corrections require affected checks and the final full suite on the stable candidate. These results across revisions are not a full-suite pass on one commit.
- The DOCN reference assessment records ten independently adjudicated flags and seven additional later/final controls. Private offline reference checks passed, and a lossless inventory accounts for 324,689 Unicode characters in 62 chunks of the original 326,074-byte report. This proves text coverage, with model claim coverage still pending.
- Read-only supporting review found untrusted financial-source URLs, missing intraday cutoff scope and a correction attaching to repeated text in another quarter. Regression tests now exercise trusted issuer addresses, conservative filing-day availability and exact character locations while keeping tables intact.
- Rendering checks cover default-off exports, missing opted-in results, direct HTML, offline matching audit reuse and invalidation after a changed claim. The saved report presents a concise assessment and links to detailed findings.

## Provider proof and recovery

Two one-request diagnostics and a stopped whole-report attempt have been performed. The first response reported usage beyond the sent output cap and the pilot wrapper's input estimate. The application sent the configured cap with SDK retries disabled. The provider cause is unestablished. A second response was preserved and contained valid JSON, exposing an engine bug that parsed a Pydantic AIMessage envelope before its content. A realistic message regression now covers the corrected adapter.

The stopped whole-report attempt produced six answered requests. Exact saved-prompt offline replay retained 166 valid claims, with two truncated JSON responses and four rejected claim records. Known financial figures were sometimes called unsupported because the selected packet omitted their available source rows. Additional review found table chunks could lose column headers or split a row. The run was stopped before further paid calls while these context and output limitations are corrected. No full-report completion is claimed.

Spending across nine attempts is $0.72307450 in provider-reported charges, $0.367540 conservatively charged for the first diagnostic from observed tokens, and $7.17 reserved for the interrupted request with unknown delivery/billing. Total accounted exposure is **$8.26061450** against the $30 pilot allocation. Unknown exposure has not been refunded. Public pricing was checked at https://openrouter.ai/api/v1/models/openai/gpt-6.1-terra-pro/endpoints. Dated pricing, every sent prompt, raw response, interrupted-run summary and per-call reservations remain in the private proof directory.

The first broad suite found two existing proof-runner fixtures awaiting the new question. That fixed-scope runner now explicitly selects No. Its 23 tests pass. Subsequent complete suite invocations passed 3,186 and 3,189 tests respectively, with ten known optional/private-input skips, one integration deselection and 100 subtests. These runs predate the next source-context correction candidate and remain historical evidence, not a claim that its final required suite has passed.

Supporting review also reproduced an actual publication/export mismatch caused by diagnostic filenames changing after audit. A regression now verifies the saved audit matches frozen Markdown/HTML and direct HTML, with the correct companion and unchanged publication content. An injected audit-companion write failure no longer cancels an otherwise valid research export. The detailed build audit by Claude remains pending.

## Remaining acceptance

Complete supplemental trusted source retrieval and its tests, finish stable offline integration, run the repository suite and lint, assess actual provider output and whole-report coverage against the reference cases, and inspect rendered outputs. Commit the stable candidate, obtain the independent Claude build audit, close confirmed material gaps with affected verification, and obtain independent closure. The Goal remains active and incomplete. Integration, push, installation and release require separate authority.
