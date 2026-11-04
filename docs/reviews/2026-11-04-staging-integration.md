# Staging integration and combined verification — 2026-11-04

User authority: merge this completed feature into local and GitHub staging, require GitHub CI, then retire only its feature worktree/local branch and run verified-safe disk cleanup. No production promotion, release or installed-app replacement.

The verified feature is 26f23dcd994351aacb66ab2475c911ca11cb1ad7. Local staging and fetched origin/staging were both 3411158f91eb267aab8760fc90afbf43556eb0bb before integration. A clean fast-forward retained the exact tested feature tree. GitHub staging was read back at 26f23dc after the authorized push. This record is a documentation-only successor; application, tests, dependency configuration and CI jobs are unchanged.

## Reused verification

| Check | Passing evidence | Why valid for integration |
| --- | --- | --- |
| Full offline suite | 1,826 passed, one optional dependency skip, one configured integration deselection, 100 subtests; evidence/narrative-final-suite.log | Source/fixture/artifact hashes revalidated; exact fast-forward tree; no application/configuration/dependency change. |
| Focused integration | 123 passed; evidence/narrative-final-focused.log | Same tested files and environment; includes real non-SEC scope gate through saved Markdown/HTML. |
| Ruff and dependency consistency | Full repository lint and pip check passed | Source/configuration unchanged; no installs or environment modifications. |
| Three live CLI proofs | narrative-source, narrative-unavailable and narrative-technical manifests and verified-summary.json | Runtime source d675a0b is unchanged in 26f23dc and this documentation successor. Labeled research, canonical memory separation, REVIEW and scope checked. |
| Independent audit and rendered reports | narrative-audit-closure-evidence.json and retained screenshots | Exact artifacts and source hashes verified; no product change during integration. |

The user explicitly authorizes combined verification rather than a duplicate local full suite. No local full suite is rerun solely for this fast-forward/documentation change. Failures or source changes require affected verification; broader reruns require a concrete coverage reason.

## Required remote verification

The fork initially reported Actions enabled but listed no workflows or runs. Reapplying the same repository enabled setting registered its existing CI and release-assets workflows. No permission expansion, release event or release dispatch was requested. This normal staging push should trigger the existing CI workflow.

Required on the exact published successor: five Python/TZ matrix test jobs, full lint and clean-install smoke. Previous local Python 3.12 results do not replace those jobs. Missing/failing/cancelled CI remains incomplete. Final run IDs, URLs, exact staging SHA and conclusions will be retained outside the retiring worktree in /Users/zipp/Developer/tradingagents-integrity/evidence/staging-wrap-up-receipt.json.

## Preservation and retirement

Surviving checkout: /Users/zipp/Developer/tradingagents-integrity/repository. Completed proof is already outside the feature worktree in sibling evidence; credentials remain in sibling private. Inspect untracked/ignored files and active/open-file use before removing the feature worktree and safely deleting only codex/report-evidence-integrity. Keep recovery/evidence and installed runtime. Physical recovery and cleanup dispositions will be recorded in the same wrap-up receipt after measurement.
