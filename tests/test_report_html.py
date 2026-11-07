"""An optional HTML copy of the report, for readers who do not open Markdown (#1419).

It is one self-contained file: no script, no remote asset, nothing a report's
text can inject; the Markdown report is unchanged.
"""

import re

import pytest

from tradingagents.reporting import write_report_tree

SETTINGS = {"version": "1.2.3", "llm_provider": "openai", "deep_think_llm": "gpt-6-sol",
            "quick_think_llm": "gpt-6-luna", "analysts": ["market", "news"], "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1, "data_vendors": {"core_stock_apis": "yfinance"}}


def _state(**overrides):
    state = {"trade_date": "2026-09-26",
             "market_report": "# Market view\n\nPrice | Level\n--- | ---\nClose | 181.2\n",
             "news_report": "News text.",
             "final_trade_decision": "**Rating**: Overweight\n\nAdd on weakness."}
    state.update(overrides)
    return state


def _html(tmp_path, **overrides):
    write_report_tree(_state(**overrides), "NVDA", tmp_path, settings=SETTINGS, html=True)
    return (tmp_path / "complete_report.html").read_text(encoding="utf-8")


@pytest.mark.unit
def test_the_html_page_is_written_unless_declined(tmp_path):
    write_report_tree(_state(), "NVDA", tmp_path / "plain", settings=SETTINGS, html=False)
    assert not (tmp_path / "plain" / "complete_report.html").exists()
    write_report_tree(_state(), "NVDA", tmp_path / "default", settings=SETTINGS)
    assert (tmp_path / "default" / "complete_report.html").exists()

    page = _html(tmp_path / "html")
    assert "<h1" in page and "NVDA" in page and "Overweight" in page and "2026-09-26" in page
    assert '<table>' in page and "181.2" in page


@pytest.mark.unit
def test_the_markdown_report_is_the_same_with_or_without_html(tmp_path):
    write_report_tree(_state(), "NVDA", tmp_path / "a", settings=SETTINGS, html=False)
    write_report_tree(_state(), "NVDA", tmp_path / "b", settings=SETTINGS)
    def undated(path):
        return re.sub(r"- Generated: .*\n", "", path.read_text(encoding="utf-8"))

    assert undated(tmp_path / "a" / "complete_report.md") == undated(tmp_path / "b" / "complete_report.md")


@pytest.mark.unit
def test_the_page_loads_nothing_and_runs_nothing(tmp_path):
    page = _html(tmp_path)
    assert "Content-Security-Policy" in page and "default-src 'none'" in page
    assert "<script" not in page.lower()
    assert not re.search(r'<(img|link|iframe|object|embed)\b', page, re.IGNORECASE)


@pytest.mark.unit
def test_report_text_cannot_inject_markup_or_fetch_anything(tmp_path):
    hostile = ("<script>alert(1)</script> <img src=x onerror=alert(1)>\n\n"
               "![pixel](https://tracker.example/p.png) [x](javascript:alert(1))")
    page = _html(tmp_path, news_report=hostile)
    assert "<script>alert" not in page and "<img" not in page.lower()
    assert "tracker.example/p.png" not in re.findall(r'(?:src|href)="([^"]*)"', page)
    assert 'href="javascript:' not in page


@pytest.mark.unit
def test_summary_text_cannot_inject_markup(tmp_path, monkeypatch):
    from tradingagents import report_html

    monkeypatch.setattr(report_html, "summary_input_for_report", lambda *args: {})
    from tradingagents import report_summary
    monkeypatch.setattr(report_summary, "resolve_summary", lambda *args: {
        "process": "<script>alert(1)</script>",
        "sentences": ["<img src=x onerror=alert(1)>"],
    })
    page = report_html.render_report("NVDA", _state(), SETTINGS, None)
    assert "<script>alert(1)</script>" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


@pytest.mark.unit
def test_direct_html_render_uses_new_order_and_old_partial_targets():
    from tradingagents.report_html import render_report

    state = {"market_report": "MARKET", "final_trade_decision": "Rating: Hold. Maintain exposure."}
    page = render_report("DOCN", state, None, None)
    nav = page[page.index('<nav class="contents"'):page.index("</nav>")]
    assert nav.index('href="#s2"') < nav.index('href="#s1"') < nav.index('href="#s3"')
    assert page.index('<section id="s2">') < page.index('<section id="s1">') < page.index('<section id="s3">')


@pytest.mark.unit
def test_header_values_are_escaped(tmp_path):
    write_report_tree(_state(), "<b>NV</b>", tmp_path, settings={**SETTINGS, "deep_think_llm": "<i>m</i>"}, html=True)
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    assert "<b>NV</b>" not in page and "&lt;b&gt;NV&lt;/b&gt;" in page and "<i>m</i>" not in page


@pytest.mark.unit
def test_an_agent_s_own_headings_sit_below_its_heading(tmp_path):
    page = _html(tmp_path)
    assert page.count("<h1") == 1                     # only the report's title
    assert re.search(r"<h4[^>]*>Market view</h4>", page)


def _fields(fragment):
    return re.findall(r'<span class="field">([^<]*)</span>', fragment)


@pytest.mark.unit
def test_run_details_show_each_value_as_its_own_field(tmp_path):
    settings = {**SETTINGS, "deep_think_provider": "anthropic", "deep_think_llm": "claude-opus-5-5",
                "data_vendors": {"core_stock_apis": "yfinance", "fundamental_data": "sec_edgar,yfinance"}}
    write_report_tree(_state(), "NVDA", tmp_path, settings=settings, html=True)
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    header = page[page.index('<aside class="report-meta"'):page.index("</aside>")]
    for value in ("anthropic", "claude-opus-5-5", "openai", "gpt-6-luna", "market", "news",
                  "sec_edgar", "yfinance"):
        assert value in _fields(header)
    # Vendors are named by what they serve, and a chain keeps its order.
    assert "Prices" in header and "Fundamentals" in header and "fundamental_data" not in header
    assert header.index(">sec_edgar<") < header.rindex(">yfinance<")


@pytest.mark.unit
def test_the_contents_name_each_section_once_and_list_its_agents_beneath(tmp_path):
    page = _html(tmp_path)
    nav = page[page.index('<nav class="contents"'):page.index("</nav>")]
    assert "<ol" not in nav                     # no list numbers beside the sections' own I-V
    assert re.search(r'<a href="#s2"><span class="num">I</span>\s*<span class="label">Final Portfolio Decision</span></a>', nav)
    assert re.search(r'<a href="#s1-1"><span class="label">Market Analyst</span></a>', nav)


@pytest.mark.unit
def test_the_contents_are_visible_without_hover_and_in_print(tmp_path):
    page = _html(tmp_path)
    css = page[page.index("<style>"):page.index("</style>")]
    assert ".contents { margin:" in css
    assert ".contents, .to-top { display: none; }" not in css
    assert "<h2>Table of contents</h2>" in page


@pytest.mark.unit
def test_the_sections_stay_within_reach(tmp_path):
    page = _html(tmp_path)
    nav = page[page.index('<nav class="contents"'):page.index("</nav>")]
    assert "<h2>Table of contents</h2>" in nav
    assert 'id="top"' in page and 'href="#top"' in page             # a way back on small screens
    assert page.index('<section class="summary"') < page.index('<nav class="contents"') < page.index('<aside class="report-meta"')


@pytest.mark.unit
def test_the_page_heading_is_the_ticker_and_its_rating(tmp_path):
    page = _html(tmp_path)
    heading = re.search(r"<h1>(.*?)</h1>", page).group(1)
    assert re.sub(r"<[^>]+>", "", heading).split() == ["NVDA", "Overweight"]


@pytest.mark.unit
def test_the_header_carries_the_official_logo_unaltered(tmp_path):
    from importlib.resources import files

    logo = files("tradingagents").joinpath("assets/tauric-logo.svg").read_text(encoding="utf-8").strip()
    page = _html(tmp_path)
    header = page[page.index("<header"):page.index("</header>")]
    assert logo in header                           # drawn in the page, nothing fetched
    assert 'href="https://tauric.ai"' in header and 'aria-label="Tauric Research"' in header
    assert header.index('class="logo"') < header.index("<h1")   # leads the header, above the title


@pytest.mark.unit
def test_the_page_credits_its_maker_in_a_line_of_text(tmp_path):
    page = _html(tmp_path)
    footer = page[page.index('<footer class="credit">'):page.index("</footer>")]
    assert re.sub(r"<[^>]+>", "", footer).split() == ["TradingAgents", "powered", "by", "Tauric", "Research"]
    # The logo already leads to tauric.ai; the credit leads to the project and the org.
    assert 'href="https://github.com/TauricResearch/TradingAgents"' in footer
    assert 'href="https://github.com/TauricResearch"' in footer and "tauric.ai" not in footer
    assert "<svg" not in footer and 'class="brand"' in footer
    assert page.index("</main>") < page.index('<footer class="credit">')


@pytest.mark.unit
def test_the_packaged_logo_stays_inert(tmp_path):
    # The logo is drawn inside every report, so it may only ever hold shapes:
    # no script, event handler, link, embedded document or external reference.
    from importlib.resources import files

    logo = files("tradingagents").joinpath("assets/tauric-logo.svg").read_text(encoding="utf-8")
    tags = set(re.findall(r"<\s*([a-zA-Z][\w:-]*)", logo))
    assert tags <= {"svg", "path", "rect", "circle", "g", "defs", "clipPath", "linearGradient", "stop"}
    assert not re.search(r"\son\w+\s*=|href|url\(|@import|javascript:|<!entity|<!doctype", logo, re.IGNORECASE)
