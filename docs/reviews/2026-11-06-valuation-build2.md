# Valuation Build 2 and amendment A3

Baseline: `3d1b8f329f53b98daaecf05df4e522bc5491c87c`, accepted staging and
production after PR #11. Development uses the isolated Machine 2 worktree
`/Users/zipp/Developer/tradingagents-valuation-build2-20261106/source`, branch
`codex/valuation-cases-build2-a3`. The installed Machine 1 release is unchanged
by this build. No Build 2 publication or installation is authorized.

## Implementation

Revenue cases require dated, sourced and explained closing capital assumptions.
Code prices equity and named enterprise bases separately, keeps guided average
shares and alternate debt definitions as sensitivities, and leaves missing
categories unknown. Funding feasibility remains unassessed. Accepted financing
authorizations have a separate explicitly hypothetical gross-proceeds line;
actual issuance, remaining capacity and fees remain unknown.

The existing Research Manager call may submit one revised set. Original and
replacement requests remain available, with versioned identities and rejected
revision reasons. The retained analyst submission, rather than a cached
projection, determines version-one inputs. Compatible case values form an
advisory range; different periods and bases remain separate. Only the raw
Portfolio Manager's valid exact-version selection establishes valuation basis.
A3 requires either explicit absence of a dated assumption or a validated date,
compatible completed quote and substantive assumption. No interpolation,
discounting or automatic short-term price is introduced.

## Verification and corrections

Private source inputs and outputs remain outside Git in the sibling `private`
directory. Input SHA-256 values and baseline/environment are in
`../evidence/setup.json`; five fresh real-state replays and four explicitly
synthetic positive variants are in `../private/replay-final`. All original
hashes, ratings and publication identities remain unchanged. Markdown, HTML,
captured CLI, repeated exports, sealed passage reuse and tamper refusal were
checked. The synthetic arithmetic independently reconciles $35/$47 and the
revised $59 case; it is not model or live proof. A local browser rendering of
the range and dated assumption was inspected.

Plan adjustment: neither retained Opus report supplies the new per-value future
capital contract. Inventing that input would contradict sections 2.1 and 2.4.
Their legacy requests remain readable but unavailable for a new range.
Positive arithmetic therefore uses separately labeled synthetic assumptions;
natural live proposals must establish live feature acceptance.

The full offline inventory was executed. Initial failures exposed related mock
and legacy contract expectations, which were corrected with their assertions
preserved. The final full invocation recorded 2,934 passes and five failures
asserting that an untrusted cached scenario-status sentinel reached prompts.
After correcting that expectation to require its exclusion, all 43 affected
deduplication, case and shared-context tests passed. This is combined evidence,
not one complete passing invocation on a single revision. Broader repeats were
needed while financial source/replay behavior changed; after the last source
freeze only that test expectation changed.

Ten skips in the full inventory were investigated. Nine private-input checks
were completed within a separate 24-test passing invocation using transferred,
hash-verified source files on Machine 2. The remaining optional Bedrock native
integration requires an uninstalled extra and is outside this build; the live
DeepSeek integration was deselected and is not authorized. The private checks
used module path overrides because the general test configuration deliberately
blanks application environment overlays. No source or network behavior was
mocked for retained retrieval/calculation/report export.

Repository-wide Ruff, dependency checking and `git diff --check` passed.
Existing publication/restart tests and new real SQLite pre/post-revision
checkpoint tests were included. Proof-control siblings passed 128 tests; the
final Build 2/document guard subset passed 39 tests. A time-dependent old proof
fixture was corrected to derive its session date and close from one completed
session. Actual endpoint metadata was parsed offline, including long-context
thresholds and conservative cache pricing.

The independent Astra audit reproduced and closed six material findings: raw
PM authority, dated split comparability, incomplete off-basis sensitivities,
legacy reader recovery, verification of every published case, and cached
analyst input tampering. The audit and its 28-test final independent subset are
recorded in `../evidence/build2-independent-audit.md`. No paid request was used
for review or qualification.

## Paid proof boundary

Fresh authority is $24 aggregate for at most two Medium-depth DOCN CLI attempts,
Opus 5.5 quick and Terra Pro deep, all four analysts. This does not reuse old
allowances or release unknown historical holds. The first attempt is capped
at $16; any second is limited by the remaining settled and reserved authority.
SDK retries are zero; the existing one bounded audit retry counts within the
same allowance. No automatic rerun or additional comparison call is permitted.

The operator must freeze a clean committed candidate, refresh actual account,
endpoint and after-close session receipts, and retain isolated runtime/ledger
outputs. Empty or rejected proposals prove fallback only. Paid execution and
its feature acceptance are pending at this implementation checkpoint. Required
exact-head GitHub CI remains pending future publication approval.
