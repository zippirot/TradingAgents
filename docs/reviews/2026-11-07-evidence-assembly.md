# R1 evidence assembly — in progress

R1 starts on Machine 2 in `/Users/zipp/.codex/worktrees/evidence-assembly/TradingAgents`, branch `codex/evidence-assembly`, from exact fetched/confirmed staging `730bbe04ce7ba382367463dccca57bc39b7e0e92`. R5 was fast-forwarded and pushed to staging on explicit user approval. All seven GitHub CI jobs passed on that SHA, including Python 3.11–3.14, non-UTC Python 3.12, strict Ruff and clean-install smoke. Fresh local full suite: 3358 passed, 10 skipped, 1 deselected, 100 subtests; Ruff/diff clean. Full receipt in `2026-11-07-evidence-assembly-baseline.json`. Production remains `9ade69bf155d1b25699d3aecfff3c1b07752aff0`; R5 worktree is preserved. No release, installation or worktree removal.

Approved Amendment 1 G2/G4/G5/G7 tasks are now copied under their R1 host. R3/Na tasks remain pending their own build starts; the approved amendment text is unchanged. R1 implementation, offline proof, complete suite and independent Claude Fable audit/closure are pending. No paid product calls authorized by Phase 1.

## R1.7 diagnosis before code changes

Replayed both original DOCN `cfae95e9` requests through the actual `RevenueCase` and `price_case` using the retained canonical package and current `grounded_outlooks`. The base target is 77.734375; cautious target 44.6691176470588235294117647058823529411764705882352941176471. Both sensitivity maps are empty because their submitted capital obligations contain only borrowings. `price_case` correctly reports missing finance/equipment and operating-lease categories. Neither an exception nor a delivery failure caused the absence. Actual source state SHA-256: d9505e263d70b0e59aba03d6f75c250c7c6d320e22070cbc5002876811e27f2b; source file was only read. Diagnostic receipt `/tmp/r1-lease-baseline.json`, bounded results copied in the baseline JSON.

The package retains dated 2026-09-30 finance/equipment obligations of 923,599,000 USD and current/noncurrent operating-lease facts. The correction must preserve submitted requests, capital assumptions and base targets, reuse `price_case` with separately labelled source-bound sensitivity requests, and explicitly hold those balance-sheet obligations constant against the future case period. Missing or conflicting categories remain unavailable.

## G5 metrics inventory before code changes

Read `calculate_peer_statistics`, its helpers and `render_peer_statistics`. They use Revenue (current/prior TTM), Gross Profit (same-period TTM margin), and Common Shares Outstanding (point-in-time equity/share basis), plus verified identity, quote and lineage metadata. No Assets, debt, net income or EPS metric contributes to those peer statistics or their renderer. Both share diagnostic and live peer callers use the same revenue/share inputs. Unused-metric ambiguity may be dropped only in peer packages with an explicit gap; these three required metrics and all subject-issuer ambiguity remain strict.
