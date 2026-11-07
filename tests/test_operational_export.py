"""Reader-visible operational audit publication boundaries."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from html.parser import HTMLParser
from threading import Barrier, Lock
from time import sleep

import pytest

from tradingagents.operational_audit import observation
from tradingagents.report_html import render_report
from tradingagents.reporting import write_report_tree


def _state(run_id="run-one"):
    state = {"run_id": run_id, "company_of_interest": "DOCN", "trade_date": "2026-11-06",
             "run_settings": {"analysts": ["market"]}, "market_report": "Market analysis.",
             "final_trade_decision": "**Rating:** Hold. Decision text."}
    source = observation(state, "Source Acquisition", expected_stages=["Source Acquisition", "Market Analyst"])
    row = observation(state, "Market Analyst")
    state["operational_observations"] = {item["event_id"]: item for item in (source, row)}
    return state


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


def test_saved_reports_end_with_matching_clickable_audit(tmp_path):
    state = _state()
    original = deepcopy(state)
    out = write_report_tree(state, "DOCN", tmp_path)
    md = out.read_text()
    page = (tmp_path / "complete_report.html").read_text()
    audit = (tmp_path / "operational_audit.md").read_text()
    assert state == original
    assert "**Operational quality: 3/5 — Degraded**" in md
    assert "**Operational quality: 3/5 — Degraded**" in audit
    assert md.rstrip().endswith("[./operational_audit.md](./operational_audit.md)")
    links = Links()
    links.feed(page)
    assert "./operational_audit.md" in links.hrefs
    assert page.rfind("Operational quality") > page.rfind("TradingAgents</a>")
    assert "Stages: completed" in md and "Audit coverage: sufficient" in page
    assert "executive summary is unavailable" in md


def test_reused_folder_keeps_old_audit_and_links_each_report_to_new_companion(tmp_path):
    write_report_tree(_state(), "DOCN", tmp_path)
    old = (tmp_path / "operational_audit.md").read_bytes()
    second = _state("run-two")
    write_report_tree(second, "DOCN", tmp_path)
    assert (tmp_path / "operational_audit.md").read_bytes() == old
    md = (tmp_path / "complete_report.md").read_text()
    assert "./operational_audit-" in md
    path = md.rstrip().split("(")[-1].rstrip(")")
    assert (tmp_path / path).read_text().find("run-two") > 0


def test_audit_failure_leaves_report_with_unrated_and_no_stale_link(tmp_path, monkeypatch):
    import tradingagents.operational_audit as audit

    write_report_tree(_state(), "DOCN", tmp_path)
    def fail(*args, **kwargs):
        raise OSError("audit failed")
    monkeypatch.setattr(audit, "render_audit", fail)
    out = write_report_tree(_state("run-two"), "DOCN", tmp_path)
    md = out.read_text()
    page = (tmp_path / "complete_report.html").read_text()
    assert "Unrated — audit unavailable" in md and "Unrated — audit unavailable" in page
    assert "Full operational audit" not in md and "operational_audit.md" not in page


def test_direct_html_has_assessment_but_no_sidecar_link():
    page = render_report("DOCN", _state(), None)
    assert "Operational quality" in page
    assert "Report integrity: not applicable (in-memory rendering)" in page
    assert "Report integrity: verified" not in page
    assert "Full operational audit" not in page


def test_direct_html_claimed_publication_is_unverified_without_store():
    state = _state()
    state["publication_record"] = {"decision_id": "claimed", "published_at": "2026-11-06",
                                   "record_sha256": "0" * 64}
    page = render_report("DOCN", state, None)
    assert "Operational quality: 2/5 — Low confidence" in page
    assert "Report integrity: unverified" in page
    assert "Full operational audit" not in page


def test_markdown_only_links_written_audit_without_creating_html(tmp_path):
    out = write_report_tree(_state(), "DOCN", tmp_path, html=False)
    assert out.read_text().rstrip().endswith("[./operational_audit.md](./operational_audit.md)")
    assert (tmp_path / "operational_audit.md").is_file()
    assert not (tmp_path / "complete_report.html").exists()


def test_report_write_failure_propagates(tmp_path, monkeypatch):
    from tradingagents import reporting
    original = reporting.replace_file
    def fail_report(path, writer, **kwargs):
        if path.name == "complete_report.md":
            raise OSError("disk full")
        return original(path, writer, **kwargs)
    monkeypatch.setattr(reporting, "replace_file", fail_report)
    with pytest.raises(OSError, match="disk full"):
        write_report_tree(_state(), "DOCN", tmp_path)


def test_concurrent_same_directory_exports_keep_one_matching_report(tmp_path, monkeypatch):
    from tradingagents import reporting

    original = reporting._write_report_tree_locked
    arrivals = Barrier(2)
    monitor = Lock()
    active = 0
    maximum = 0

    def watched(*args, **kwargs):
        nonlocal active, maximum
        with monitor:
            active += 1
            maximum = max(maximum, active)
        try:
            sleep(0.05)
            return original(*args, **kwargs)
        finally:
            with monitor:
                active -= 1

    monkeypatch.setattr(reporting, "_write_report_tree_locked", watched)

    def export(run_id):
        arrivals.wait(timeout=5)
        return write_report_tree(_state(run_id), "DOCN", tmp_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(export, "run-one")
        two = pool.submit(export, "run-two")
        one.result(timeout=10)
        two.result(timeout=10)

    assert maximum == 1
    md = (tmp_path / "complete_report.md").read_text()
    page = (tmp_path / "complete_report.html").read_text()
    path = md.rstrip().split("(")[-1].rstrip(")")
    audit = (tmp_path / path).read_text()
    assert ("run-one" in audit) != ("run-two" in audit)
    assert path in page
    assert md.count("Operational quality:") == 1
