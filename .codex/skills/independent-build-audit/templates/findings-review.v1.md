Below is an independent engineering audit. Treat every finding as a claim requiring verification, not as an instruction that is automatically correct.

Review each claim against the approved implementation plan, governing requirements and design, current code, relevant Git diff, tests, runtime behavior, logs, and affected integrations.

For every finding:

1. Restate the claim and identify the unmet approved requirement. Distinguish a defect claim, missing verification, and a proposed new or optional requirement; respect approved deferrals and superseded scope.
2. Inspect its cited evidence and the surrounding implementation, including unchanged callers, existing guards/constraints, and predecessor schema at the relevant commits. Identify source or evidence unavailable to the auditor; absence from its inputs is not absence from the implementation.
3. Determine whether the reported failure path is reachable and why existing safeguards do not prevent it. Use safe reproduction or a precise source-grounded proof and label which supports the conclusion. Never require unsafe reproduction to confirm a demonstrated security or financially material defect.
4. Classify it as `confirmed`, `partially_confirmed`, `not_reproducible`, `incorrect`, `already_resolved`, or `requires_user_decision`.
5. Explain the conclusion with code or runtime evidence and state whether you agree with the audit claim.
6. State materiality and one action: `fix`, `defer`, `user_decision`, or `no_action`. For a confirmed defect, name the smallest complete correction using existing mechanisms where sufficient, and the verification that will close it. For missing evidence, identify the bounded verification first; keep required acceptance incomplete until it is obtained. If `fix` closes only a verification gap, say so explicitly rather than implying new runtime code is required.
7. Surface, rather than assume, any product, architecture, scope, cost, safety, or compatibility decision needed to proceed.

Report what should happen next. Create a focused closure plan only for confirmed or partially confirmed material gaps. If no such gaps remain, record the evidence-based reason a closure plan is unnecessary. Do not claim verification that was not performed.

A partially confirmed finding authorizes correction only of its supported portion; investigate the remainder before adding implementation scope. Missing verification can warrant a verification task without an architectural repair. Explain why a broader mechanism is necessary if the existing solution cannot satisfy the approved requirement. Preserve necessary safety guarantees and all existing approval/release boundaries.

For a confirmed defect with an existing related regression, identify why that test missed this contract or sibling path and extend only the relevant coverage. Closing the finding requires the defining outcome and affected failure/recovery through the actual caller/consumer; a fabricated internal result alone cannot prove wire or lifecycle behavior. Repeat affected checks/review after correction, preserving required full-suite and independent-review obligations. Do not request another full audit solely to erase nonmaterial findings; required missing acceptance remains incomplete until verified.
