# D1: Copy All in the local HTML report

Build size: very small. Model: GPT-6 Sol (`gpt-6-sol`), medium reasoning. Estimate: 1.5–2.5 active hours; credits unavailable.

Independent audit: required

Authorized 2026-11-07 in this chat. Only D1 starts; A, C, B and D need separate approval. Base: 49b67a309ec01df1900a87d049b8f1a55d917c58. Source plan: /Users/zipp/Claude/2026-11-07-evidence-settlement-and-ops-gap-closure-plan.md. The following requirements are frozen for this handoff.

## Branch and Release Boundary

- **Feature completion — Machine 2.** Only after a build start is authorized, fetch remote refs and compare the intended local `staging` SHA to canonical GitHub `staging`. If they differ, report both and stop before branching; do not silently pick one or rewrite either. From the verified exact commit create a new `codex/<build-slug>` branch and isolated worktree at `~/Documents/ChatGPT/Tauric/worktrees/<build-slug>`. Develop, run proofs and commit code and verification evidence there. No ordinary development on `main`, `staging` or `production`.
- **Development integration.** Feature completion leaves a verified local commit. Only explicit development-integration approval permits integration into `staging`; push GitHub `staging` only if that approval explicitly authorizes the push. Staging remains unreleased. Before any dependent build, verify its prerequisites are actually present at its new staging baseline.
- **Stable release.** Only separate, explicit stable-release approval permits integrating the exact verified staging state into `production`. Push GitHub `production` only if explicitly authorized. No passing check authorizes a merge, fast-forward, push, deployment or app replacement.
- **Machine 1 installation and acceptance.** Only after deliberate promotion and publication to GitHub `production`, and when the release authorizes installation, Machine 1 pulls the exact resulting production commit and builds, installs, launches and verifies that stable version. Machine 1 acceptance is not a prerequisite for development. Machine 2 uses the isolated worktree and disposable copies for runtime proof; neither installed launcher is a proof target.

## Build D1 — Copy All (first standalone handoff)

**Worktree slug:** `report-copy-all`. This handoff ends at the standalone D1 proof and audit.

### Task D1: Copy All button on the HTML report (user request)

**Files:**
- Modify: `tradingagents/report_html.py` (CSP meta ~line 336; masthead ~line 342; `_CSS`; new module constant `_COPY_SCRIPT`)
- Test: `tests/test_report_html.py`

**Interfaces:**
- Produces: `_COPY_SCRIPT: str`, a fixed inline script with no URLs and no external loads. `_copy_script_csp_hash() -> str` returns `"sha256-" + base64(sha256(_COPY_SCRIPT.encode()))`. The CSP becomes `default-src 'none'; style-src 'unsafe-inline'; script-src '<hash>'`, so only this exact script can run and any injected script is still blocked. Masthead gains `<button type="button" class="copy-all" id="copy-all" aria-label="Copy the full report as text">Copy All</button>` as the first child (the new `operational-assessment` section at the foot of the page is inside `#top`, so it is copied too); `.masthead { position: relative; }` and `.copy-all { position: absolute; top: 0; right: 0; }` with the page's existing font, border and muted colors.
- From the rendered report, construct **one plain-text payload** in visible reading order: start at ticker/rating, include report sections, details and the Tauric credit, and end with the complete operational assessment. Exclude button/status text, “Top” navigation controls and scripts. The written table of contents stays. Use that same string in `navigator.clipboard.writeText` and, if absent or rejected, a plain-text textarea or equivalent text-only fallback. Never select the rich page or write HTML. Show success only on a successful write; otherwise show a manual-copy message. Keep the button outside the printed content.

- [ ] **First vertical proof (D1 owner):** In the Machine 2 feature worktree export the saved DOCN state through `save_reports` to a disposable folder. Open the generated `complete_report.html` via `file://` in Safari and Chrome. Click the real button and paste into a local scratch document; inspect the plain-text clipboard type and the exact text from title through the final assessment line inside `.operational-assessment`. Run this first as soon as the minimal button works, before broader hardening.
- [ ] Preserve hostile-content escaping and the no-external-assets policy. In `tests/test_report_html.py` replace only the old no-script assertion: require one fixed inline script, its CSP hash matching the **actual emitted script bytes**, no source URL, and no additional script/load. Exercise repeat clicks, no API/denied permission, and failure of both copy paths without a false “Copied”. Clipboard success must exclude “Copy All”, “Copied” and “Top”.
- [ ] **Final proof:** After the security and fallback checks, repeat the complete file → click → paste path in both browsers, with normal clipboard access and with the primary API denied/unavailable. Compare the actual pasted plain text and recorded clipboard types across both paths; if both methods fail, verify the failure message. Record browser versions, output and results. If a required real-browser path cannot be exercised, mark D1 incomplete. Full suite, Ruff, evidence and the independent audit in Integrated acceptance also apply to this standalone handoff.

---

## Integrated acceptance

Independent audit: required

- **One owner per required handoff, in order:** D1 owns the real local HTML-to-clipboard result; A owns valuation validation, guidance retention, A4 eligibility, decision comparison and the A7 evidence disposition; C owns the ledger/outcome lifecycle and memory note; B owns extraction from validated full filing text and companyfacts, delivery to real prompts and export; D2–D10 own the remaining operator changes. D1 is complete or incomplete on its own. At each authorized start verify the necessary predecessor evidence and code at the exact staging SHA. B does not need A3 to retain its passages. D11 cannot block the five builds, their audits, integration or release.
- On Machine 2 exercise the smallest working user/system path first; fix any runtime blocker before broadening it. After hardening, re-run the complete affected path from its real trigger, using the handoff's prescribed disposable inputs. Record the observable output and destination in `docs/reviews/<date>-<slug>.md`. Fake only external providers needed for a no-cost replay, not the application path under proof. An unexercised required path remains incomplete.
- **Each of D1, A, C, B and D:** full default `pytest -q` and `ruff check` clean on the candidate; record exact tested SHA, results and limitations. Use the existing independent Claude review route evidenced in `docs/reviews/2026-11-07-operational-report-audit-acceptance.md` (frozen range, bounded executor, existing authorized spend limits). The marker above declares the requirement; it does not launch or pay for an audit. During future authorized work, commit the governing requirements for that handoff (including the marker and proof) at a repo-relative path on its isolated branch; the standalone file in `~/Claude` is not a frozen input. Provide the approved runner the frozen requirements, relevant source, receipts and sanitized proof. Verify its required inputs are available at that SHA; never claim a self-review, missing packet or capped review as complete.
- Reproduce each High locally against the candidate; distinguish the implementer's reproduction from what a read-only auditor actually ran. Fix confirmed in-scope findings with regression evidence and re-audit the final change. Close with no open in-scope Critical/High/Medium; document lower findings and dispositions, or “no gaps found.” Identify the final feature commit, verified candidate, audited range and any evidence-only follow-up accurately. Passing this gate grants no integration or release authority.
- **Not applicable to these development proofs:** broker/trade execution, production databases and deployment. The touched persistence is the existing local ledger and run/report files. No new service, database migration, retention daemon or Machine 1 install is required.

