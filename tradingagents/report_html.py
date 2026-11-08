"""The report as one self-contained HTML page (#1419).

The page reads well in a browser, on a phone and in print. It loads nothing;
a CSP hash permits only the fixed copy script. Report text is rendered as
CommonMark with raw HTML and images
off, so nothing a model wrote can inject markup or load a remote asset.
"""

import base64
import hashlib
from datetime import datetime
from html import escape
from importlib.resources import files

from markdown_it import MarkdownIt

from tradingagents.agents.rating import run_rating
from tradingagents.reporting import (
    _DESCRIPTIONS,
    analyst_names,
    historical_anchors,
    prepare_report_state,
    render_token_usage,
    report_sections,
    summary_input_for_report,
)

# Ratings by direction, so the page can show which way the call leans.
_TONE = {"Buy": "up", "Overweight": "up", "Hold": "level", "Underweight": "down", "Sell": "down"}

# The Tauric Research logo as published (tauric.ai/brand/tauric-logo.svg), drawn
# in the page so it loads nothing.
_LOGO = (
    files("tradingagents").joinpath("assets/tauric-logo.svg").read_text(encoding="utf-8").strip()
)
_COMPANY = "https://tauric.ai"
_ORG = "https://github.com/TauricResearch"
_PROJECT = f"{_ORG}/TradingAgents"

_COPY_SCRIPT = """(() => {
  const button = document.getElementById('copy-all');
  let reset;

  function reportText() {
    const source = document.getElementById('top');
    const copy = source.cloneNode(true);
    copy.removeAttribute('id');
    copy.querySelectorAll('button, script, .logo, .to-top').forEach(node => node.remove());
    copy.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
    copy.classList.add('copy-source');
    copy.style.width = source.getBoundingClientRect().width + 'px';
    copy.setAttribute('aria-hidden', 'true');
    copy.inert = true;
    document.body.appendChild(copy);
    try {
      return copy.innerText.trim();
    } finally {
      copy.remove();
    }
  }

  function fallback(text) {
    const active = document.activeElement;
    const selection = window.getSelection();
    const ranges = [];
    if (selection) {
      for (let i = 0; i < selection.rangeCount; i++) ranges.push(selection.getRangeAt(i).cloneRange());
    }
    const buffer = document.createElement('textarea');
    buffer.className = 'copy-buffer';
    buffer.value = text;
    buffer.readOnly = true;
    buffer.setAttribute('aria-label', 'Report text to copy');
    document.body.appendChild(buffer);
    try {
      buffer.select();
      return document.execCommand('copy');
    } finally {
      buffer.remove();
      if (active && active.focus) active.focus({preventScroll: true});
      if (selection) {
        selection.removeAllRanges();
        ranges.forEach(range => selection.addRange(range));
      }
    }
  }

  button.addEventListener('click', async () => {
    if (button.disabled) return;
    clearTimeout(reset);
    button.disabled = true;
    let copied = false;
    try {
      const text = reportText();
      if (!text) throw new Error('Empty report');
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch {
        copied = fallback(text);
      }
    } catch {
      copied = false;
    } finally {
      button.disabled = false;
      button.textContent = copied ? 'Copied' : 'Copy failed, select the text manually';
      if (copied) reset = setTimeout(() => { button.textContent = 'Copy All'; }, 2000);
    }
  });
})();"""


def _copy_script_csp_hash() -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(_COPY_SCRIPT.encode()).digest()).decode()


_CSS = """
:root {
  --paper: #fbfbfa; --ink: #1c2126; --muted: #5d6670; --rule: #e2e5e8; --wash: #f2f4f5;
  --accent: #087a59; --up: #087a59; --down: #b4372f; --level: #5d6670; --edge: #d3d8dc; --mark: #878f97;
  --serif: Charter, "Bitstream Charter", "Sitka Text", Cambria, Georgia, serif;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #131a1f; --ink: #e4e8eb; --muted: #9aa6af; --rule: #263239; --wash: #1a242a;
    --accent: #14c290; --up: #14c290; --down: #ef6f63; --level: #9aa6af; --edge: #3d4c55; --mark: #66737c;
  }
}
@media (prefers-color-scheme: dark) {
  .masthead .logo [stroke="#363636"] { stroke: var(--muted); }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font: 17px/1.62 var(--serif); font-kerning: normal;
}
.page { max-width: 46rem; margin: 0 auto; padding: 3.5rem 1.5rem 6rem; }
main h2, main h3 { scroll-margin-top: 1rem; }
a { color: var(--accent); text-underline-offset: 0.15em; }
h1, h2, h3, h4 { text-wrap: balance; }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.masthead { position: relative; padding-bottom: 1.75rem; border-bottom: 1px solid var(--rule); }
.copy-all { position: absolute; top: 0; right: 0; max-width: calc(100% - 10rem);
  padding: 0.35rem 0.6rem; border: 1px solid var(--edge); border-radius: 4px;
  background: var(--paper); color: var(--muted); font: 0.8rem/1.4 var(--sans); cursor: pointer; }
.copy-all:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.copy-all:disabled { cursor: wait; }
/* Render the same layout off-screen so innerText preserves paragraphs and tables. */
.copy-source, .copy-buffer { position: fixed; left: -100000px; top: 0; pointer-events: none; }
/* The logo leads at the top left, where readers look for it, 24px tall (the usual
   on-screen floor for a wordmark) with at least its height clear below. */
.masthead .logo { display: block; width: fit-content; margin: 0 0 2.25rem; }
.masthead .logo svg { display: block; height: 1.5rem; width: auto; }
.masthead h1 {
  margin: 0; font: 600 2.6rem/1.1 var(--sans); letter-spacing: -0.02em;
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.2em 0.5em;
}
.masthead .rating { font-weight: 500; }
.rating.up { color: var(--up); } .rating.down { color: var(--down); } .rating.level { color: var(--level); }
.rating.review { color: var(--muted); font-style: italic; }
.masthead .date { margin: 0.55rem 0 1.5rem; font: 1rem/1.4 var(--sans); color: var(--muted); }
.run { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 0.45rem 1.25rem;
  font: 0.85rem/1.5 var(--sans); }
.run > div { display: contents; }
.run dt { color: var(--muted); }
.run dd { margin: 0; overflow-wrap: anywhere; }
.run .note dd { color: var(--down); }
.field { display: inline-block; margin: 0 0.15rem 0.15rem 0; padding: 0 0.4rem; border: 1px solid var(--edge);
  border-radius: 4px; background: var(--wash); font: 0.8rem/1.6 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.run .group { display: inline-block; margin-right: 0.9rem; white-space: nowrap; }
.run .group > .name { color: var(--muted); margin-right: 0.3rem; }
.run .then { color: var(--muted); margin: 0 0.2rem; }

/* A visible in-flow outline remains readable on wide screens, phones and print. */
.summary { margin: 2.25rem 0 0; }
.summary h2, .contents h2 { margin: 0 0 0.8rem; font: 600 1.35rem/1.3 var(--sans); }
.summary p { margin: 0 0 1rem; overflow-wrap: anywhere; }
.contents { margin: 2.25rem 0; padding: 1.25rem 1.5rem; border: 1px solid var(--rule);
  background: var(--wash); font: 0.9rem/1.45 var(--sans); }
.contents ul { margin: 0; padding: 0; list-style: none; }
.contents > ul > li { margin: 0 0 0.75rem; }
.contents ul ul { margin-top: 0.2rem; padding-left: 1.6rem; font-size: 0.85rem; }
.contents ul ul li { margin: 0.1rem 0; }
.contents li { overflow-wrap: anywhere; }
.contents a { display: inline-flex; align-items: baseline; gap: 0.6rem; color: var(--muted); text-decoration: none; }
.contents > ul > li > a { color: var(--ink); }
.contents .num { min-width: 1.6rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.contents .description { display: block; margin-left: 2.2rem; color: var(--muted); font-size: 0.82rem; }
.contents a:hover .label, .contents a:focus-visible .label { color: var(--accent); text-decoration: underline; }
.to-top { position: fixed; right: 1rem; bottom: calc(1rem + env(safe-area-inset-bottom));
  padding: 0.25rem 0.6rem; border: 1px solid var(--edge); border-radius: 4px; background: var(--paper);
  color: var(--muted); font: 0.8rem/1.4 var(--sans); text-decoration: none; }


/* The maker's credit: one quiet line at the foot. */
.credit { margin-top: 4.5rem; padding-top: 1.25rem; border-top: 1px solid var(--rule);
  color: var(--muted); font: 0.8rem/1.4 var(--sans); }
.credit a { color: inherit; text-decoration: none; }
.credit a.brand { color: var(--accent); }
.credit a:hover, .credit a:focus-visible { text-decoration: underline; }

/* Three levels of separation: the five groups, the agents within a group, and
   breaks an agent draws inside its own text. */
main h2 {
  margin: 4.5rem 0 0.25rem; padding-top: 1.5rem; border-top: 2px solid var(--ink);
  font: 600 1.45rem/1.3 var(--sans); letter-spacing: -0.01em;
}
main section:first-child h2 { margin-top: 3rem; }
main h3 { margin: 2.75rem 0 0.75rem; padding-top: 1.1rem; border-top: 1px solid var(--rule);
  font: 600 1.15rem/1.35 var(--sans); color: var(--accent); }
main h2 + h3 { margin-top: 1.25rem; padding-top: 0; border-top: 0; }
main h4, main h5, main h6 { margin: 1.75rem 0 0.5rem; font: 600 1rem/1.4 var(--sans); }
main h5, main h6 { color: var(--muted); }
main p, main ul, main ol { margin: 0 0 1rem; }
main p, main li { overflow-wrap: anywhere; }
main li { margin: 0.25rem 0; }
main strong { font-weight: 650; }
main blockquote { margin: 1.25rem 0; padding: 0.1rem 0 0.1rem 1rem; border-left: 3px solid var(--rule);
  color: var(--muted); }
main code { font: 0.88em/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--wash); padding: 0.1em 0.3em; border-radius: 3px; }
main pre { background: var(--wash); padding: 0.9rem 1rem; border-radius: 4px; overflow-x: auto; }
main pre code { background: none; padding: 0; }
main hr { width: 3rem; margin: 2rem auto; border: 0; border-top: 1px solid var(--rule); }

.table { overflow-x: auto; margin: 0 0 1.25rem; }
table { border-collapse: collapse; width: 100%; font: 0.86rem/1.45 var(--sans);
  font-variant-numeric: tabular-nums; }
th, td { padding: 0.45rem 0.7rem; text-align: left; vertical-align: top; border-bottom: 1px solid var(--rule); }
th { font-weight: 600; border-bottom-color: var(--muted); }
tbody tr:last-child td { border-bottom: 0; }

@media (max-width: 34rem) {
  body { font-size: 16px; }
  .page { padding: 2rem 1rem 3rem; }
  .masthead h1 { font-size: 2rem; }
  .masthead .logo svg { height: 1.25rem; }
  .run { grid-template-columns: 1fr; gap: 0 0; }
  .run dd { margin-bottom: 0.45rem; }
  .run .group { white-space: normal; }
}
@media print {
  :root { --paper: #fff; --ink: #000; --muted: #444; --rule: #bbb; --accent: #000; --wash: #f2f2f2;
    --edge: #bbb; --up: #087a59; --down: #b4372f; --level: #444; }
  body { font-size: 11pt; }
  .table { overflow: visible; }
  .page { max-width: none; padding: 0; }
  .contents { background: none; border: 1px solid var(--rule); break-inside: avoid; }
  .to-top { display: none; }
  .copy-all { display: none; }
  main h2 { break-before: page; border-top: 0; margin-top: 0; }
  main section:first-child h2 { break-before: auto; }
  main h3, main h4 { break-after: avoid; }
  a { color: inherit; text-decoration: none; }
  table { break-inside: avoid; }
}
"""


def _markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False}).enable("table").disable("image")
    md.add_render_rule("table_open", lambda *a: '<div class="table"><table>\n')
    md.add_render_rule("table_close", lambda *a: "</table></div>\n")
    return md


def _render_agent_text(md: MarkdownIt, text: str) -> str:
    """An agent's text, its own headings placed below the agent's heading (h3)."""
    tokens = md.parse(text)
    for token in tokens:
        if token.type in ("heading_open", "heading_close"):
            token.tag = f"h{min(int(token.tag[1]) + 3, 6)}"
    return md.renderer.render(tokens, md.options, {})


# What each data category serves, as a reader would name it.
_CATEGORY = {
    "core_stock_apis": "Prices",
    "technical_indicators": "Indicators",
    "fundamental_data": "Fundamentals",
    "news_data": "News",
    "macro_data": "Macro",
    "prediction_markets": "Prediction markets",
}


def _fields(values) -> str:
    return " ".join(f'<span class="field">{escape(str(v))}</span>' for v in values)


def _chain(vendors: str) -> str:
    """A vendor chain in the order it is tried: ``a,b`` reads a, then b."""
    names = [v.strip() for v in str(vendors).split(",") if v.strip()]
    return ' <span class="then">\u2192</span> '.join(_fields([n]) for n in names)


def _group(name: str, values_html: str) -> str:
    return f'<span class="group"><span class="name">{escape(name)}</span>{values_html}</span>'


def _run_details(final_state: dict, settings: dict | None) -> list[tuple[str, str]]:
    """The run details as (label, value HTML); every value from the run is escaped."""
    publication = final_state.get("publication_record")
    label = "Export generated" if publication else "Generated"
    details = [(label, escape(datetime.now().strftime("%Y-%m-%d %H:%M")))]
    if publication:
        details.extend([
            ("Decision ID", escape(publication["decision_id"])),
            ("First published", escape(publication["published_at"])),
        ])
    if settings:
        s = settings.get
        for tier in ("deep", "quick"):
            provider = s(f"{tier}_think_provider") or s("llm_provider", "?")
            details.append(
                (f"{tier.capitalize()} model", _fields([provider, s(f"{tier}_think_llm", "?")]))
            )
        details.append(("Analysts", _fields(analyst_names(s("analysts")))))
        details.append(
            (
                "Debate rounds",
                " ".join(
                    (
                        _group("research", _fields([s("max_debate_rounds", "?")])),
                        _group("risk", _fields([s("max_risk_discuss_rounds", "?")])),
                    )
                ),
            )
        )
        vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
        if vendors:
            details.append(
                (
                    "Data vendors",
                    " ".join(_group(_CATEGORY.get(k, k), _chain(v)) for k, v in vendors.items()),
                )
            )
        details.append(("Version", escape(f"TradingAgents {s('version', '?')}")))
        if s("source_hash"):
            details.append(("Source hash", escape(str(s("source_hash")))))
        for key, label in (("openai_reasoning_effort", "OpenAI/OpenRouter reasoning effort"),
                           ("anthropic_effort", "Anthropic effort"),
                           ("google_thinking_level", "Google thinking level")):
            if s(key):
                details.append((label, escape(str(s(key)))))
    if final_state.get("memory_note"):
        details.append(("Memory log", escape(final_state["memory_note"])))
    if not final_state.get("evidence_quality"):
        details.append(("Evidence", "Legacy export — financial evidence unvalidated"))
    return details


def render_report(ticker: str, final_state: dict, settings: dict | None, parts=None, *,
                  diagnostics_sidecar: bool = False) -> str:
    """Build a direct HTML export with current validation and no model calls."""
    prepared = prepare_report_state(final_state)
    parts = report_sections(prepared, None if prepared != final_state else parts)
    display_settings = (prepared.get("run_settings") if isinstance(prepared.get("run_settings"), dict)
                        else settings)
    from tradingagents.report_summary import resolve_summary

    summary = resolve_summary(summary_input_for_report(prepared, display_settings, parts),
                              prepared.get("executive_summary"))
    from tradingagents.reporting import _operational_assessment, _unavailable_assessment

    try:
        assessment = _operational_assessment(final_state, summary,
                    "unverified" if final_state.get("publication_record") else "not_applicable")
    except Exception:
        assessment = _unavailable_assessment("The operational audit could not be completed for this export.")
    return _render_prepared_report(ticker, prepared, display_settings, parts, summary,
                                   diagnostics_sidecar=diagnostics_sidecar, assessment=assessment)


def _render_prepared_report(ticker: str, final_state: dict, settings: dict | None, parts,
                            summary: dict, *, diagnostics_sidecar: bool = False,
                            assessment: dict | None = None, audit_path: str | None = None) -> str:
    """Render one already prepared and resolved presentation."""
    anchors = historical_anchors(parts)
    md = _markdown()
    rating = run_rating(final_state) if final_state.get("final_trade_decision") else ""
    tone = _TONE.get(rating, "review")
    date = final_state.get("trade_date", "")

    title = f'<span class="ticker">{escape(ticker)}</span>'
    if rating:
        title += f' <span class="rating {tone}">{escape(rating)}</span>'
    export_view = ("<p>" + escape(final_state["report_view_note"]) + "</p>"
                   if final_state.get("report_view_note") else
                   "<p>Historical publication identity not verified against a configured store; current validated projection.</p>"
                   if final_state.get("publication_record") else "")
    details = "".join(
        f'<div class="{"note" if label == "Memory log" else "detail"}">'
        f"<dt>{escape(label)}</dt><dd>{value}</dd></div>"
        for label, value in _run_details(final_state, settings)
    )

    contents, body = [], []
    for heading, folder, written in parts:
        anchor = anchors[folder]
        agents = "".join(
            f'<li><a href="#{anchor}-{m}"><span class="label">{escape(agent)}</span></a></li>'
            for m, (agent, _f, _t) in enumerate(written, 1)
        )
        numeral, _, name = heading.partition(". ")
        contents.append(
            f'<li><a href="#{anchor}"><span class="num">{escape(numeral)}</span> '
            f'<span class="label">{escape(name)}</span></a>'
            f'<span class="description">{escape(_DESCRIPTIONS[folder])}</span><ul>{agents}</ul></li>'
        )
        body.append(f'<section id="{anchor}"><h2>{escape(heading)}</h2>')
        for m, (agent, _filename, text) in enumerate(written, 1):
            if diagnostics_sidecar:
                text = text.replace("evidence.json diagnostics", "diagnostics.json")
            body.append(f'<h3 id="{anchor}-{m}">{escape(agent)}</h3>\n{_render_agent_text(md, text)}')
        body.append("</section>")

    summary_html = (
        '<section class="summary" aria-labelledby="executive-summary">'
        '<h2 id="executive-summary">Executive summary</h2>'
        f'<p>{escape(summary.get("process") or "")}</p>'
        f'<p>{escape(" ".join(summary.get("sentences") or []))}</p></section>'
    )

    if assessment is None:
        from tradingagents.reporting import _unavailable_assessment

        assessment = _unavailable_assessment("The operational audit was not available for this export.")
    from tradingagents.operational_audit import render_assessment

    audit_html = _markdown().render(render_assessment(assessment, audit_path))

    page_title = " ".join(x for x in (ticker, date, rating) if x)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src '{_copy_script_csp_hash()}'">
<title>{escape(page_title)}: TradingAgents report</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page" id="top">
<header class="masthead">
<button type="button" class="copy-all" id="copy-all" aria-label="Copy the full report as text" aria-live="polite">Copy All</button>
<a class="logo" href="{_COMPANY}" rel="noopener" aria-label="Tauric Research">{_LOGO}</a>
<h1>{title}</h1>
<p class="date">{escape(f"Analysis of {date}" if date else "Analysis")}</p>
</header>
{summary_html}
<nav class="contents" aria-label="Table of contents"><h2>Table of contents</h2><ul>{"".join(contents)}</ul></nav>
<aside class="report-meta" aria-label="Report details">
<dl class="run">{details}</dl>
{export_view}
</aside>
<main>
{"".join(body)}
</main>
<p class="credit">{escape(render_token_usage(final_state.get("run_metrics")))}</p>
<footer class="credit"><a href="{_PROJECT}" rel="noopener">TradingAgents</a> powered by <a class="brand" href="{_ORG}" rel="noopener">Tauric Research</a></footer>
<a class="to-top" href="#top">Top</a>
<section class="operational-assessment" aria-label="Operational quality assessment">{audit_html}</section>
</div>
<script>{_COPY_SCRIPT}</script>
</body>
</html>
"""
