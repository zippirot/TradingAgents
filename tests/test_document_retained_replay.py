"""Offline replay against hash-verified retained SEC sources; no network calls."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

import pytest

from tradingagents.agents.context import get_instrument_context_from_state
from tradingagents.agents.document_questions import (
    document_followup_context,
    lookup_document_questions,
    parse_document_questions,
)
from tradingagents.dataflows.filing_search import corpus_hash, search_filing_evidence
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    extract_sections,
    select_search_filings,
)
from tradingagents.reporting import write_report_tree

ROOT = Path(os.environ.get("TRADINGAGENTS_DOCUMENT_REPLAY_ROOT",
                           "/Users/zipp/Developer/tradingagents-document-access-20261106"))
INPUTS = ROOT / "private/inputs"
DOCN = INPUTS / "sec_documents"
STATE = INPUTS / "DOCN_2026-11-06_terra-pro_state.json"
STATE_HASH = "6c1ff91846efc0075840ff36785c0c4f441add78cd02cda3ffaf342fab7fd7be"
SOURCE_HASHES = {
    "docn-20260930.htm": "ce31022f3663c2126809c55128ef3d993acae66a02ca15e2901954534208ae5e",
    "docn-20260630.htm": "8f6fa50d949703be12a622f4568299a6b655e8382709f67d84756525d48db13e",
    "tm2628707d1_424b5.htm": "7ffb3308d20439a143852557f2e179145379bfa2fae73ce0b8c7cd575cc3aabc",
    "ex11-equitydistributionagr.htm": "267e1d34aa29cda12f65ec9e09023456ad6e0cca45e2585db1c69d3033016184",
}


def _retained_corpus():
    if not STATE.is_file() or len(list(DOCN.glob("*.json"))) < 8:
        pytest.skip("Private hash-verified DOCN source inputs are unavailable")
    assert hashlib.sha256(STATE.read_bytes()).hexdigest() == STATE_HASH
    saved = json.loads(STATE.read_text())
    bounded_hashes = {d["url"]: d["content_hash"] for d in saved["filing_evidence"]["documents"]}
    metadata = None
    wrappers = []
    for path in DOCN.glob("*.json"):
        wrapper = json.loads(path.read_text())
        assert hashlib.sha256(wrapper["text"].encode()).hexdigest() == wrapper["content_hash"]
        if "/submissions/" in wrapper["url"]:
            metadata = json.loads(wrapper["text"])
        else:
            if wrapper["url"] in bounded_hashes:
                assert wrapper["content_hash"] == bounded_hashes[wrapper["url"]]
            wrappers.append(wrapper)
            name = wrapper["url"].rsplit("/", 1)[-1]
            if name in SOURCE_HASHES:
                assert wrapper["content_hash"] == SOURCE_HASHES[name]
    assert metadata is not None
    refs, gaps = select_search_filings(metadata, "0001582961", "2026-11-06")
    by_prefix = {
        ref.url.rsplit("/", 1)[0] + "/": ref for ref in refs
    }
    documents = []
    for source in wrappers:
        url = source["url"]
        filing = next((ref for prefix, ref in by_prefix.items() if url.startswith(prefix)), None)
        assert filing is not None, url
        blocks, _, extraction_gaps = extract_sections(
            source["text"], max_chars=max(1, len(source["text"]) * 2)
        )
        assert not any("Document text limit reached" in gap for gap in extraction_gaps)
        documents.append(FilingDocument(
            source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(),
            filing=filing, url=url, retrieved_at=source["retrieved_at"],
            content_hash=source["content_hash"], blocks=tuple(blocks),
            gaps=tuple(extraction_gaps),
        ))
    corpus = DisclosurePackage(
        cik="0001582961", as_of=date(2026, 11, 6),
        documents=tuple(documents), gaps=tuple(gaps),
        selected_accessions=tuple(ref.accession for ref in refs),
        scope="Offline retained source replay; eight available public SEC wrappers",
    )
    # The replay subset must include every source relevant to its assertions.
    assert len(corpus.documents) == 7
    return saved, corpus


def _state(corpus):
    scope = {
        "schema_version": 1, "ticker": "DOCN", "as_of": "2026-11-06",
        "asset_type": "stock", "analysis_clock": {
            "cutoff_utc": "2026-11-07T00:00:00+00:00",
            "analysis_timezone": "America/Denver",
        },
    }
    questions = {
        "bull": parse_document_questions(
            'Final turn.\n```document_questions\n["345,111 remaining performance obligations", "365,901 remaining performance obligations"]\n```',
            "bull",
        ),
        "bear": parse_document_questions(
            'Final turn.\n```document_questions\n["2,955,158 not yet commenced", "settlement date"]\n```',
            "bear",
        ),
    }
    return {
        "company_of_interest": "DOCN", "trade_date": "2026-11-06",
        "asset_type": "stock", "analysis_clock": scope["analysis_clock"],
        "issuer_identity": {"cik": corpus.cik},
        "document_sources": {
            **scope, "status": "ready", "cik": corpus.cik,
            "corpus": corpus.model_dump(mode="json"),
            "corpus_hash": corpus_hash(corpus), "reason": "",
        },
        "investment_debate_state": {"document_questions": questions},
    }


def test_retained_docn_followup_and_report_replay(tmp_path):
    saved, corpus = _retained_corpus()
    assert saved["publication_record"]["record_sha256"]
    state = _state(corpus)
    searches = [
        ("345,111 remaining performance obligations", "docn-20260930.htm", "block-148", "$345,111"),
        ("365,901 remaining performance obligations", "docn-20260630.htm", "block-149", "$365,901"),
        ("2,955,158 not yet commenced", "docn-20260930.htm", "block-218", "$2,955,158"),
        ("settlement date", "ex11-equitydistributionagr.htm", None, None),
        ("prospectus supplement", "tm2628707d1_424b5.htm", None, None),
    ]
    for query, source_name, locator, phrase in searches:
        result = search_filing_evidence(corpus, query)
        matches = [
            p for p in result["passages"]
            if p["url"].endswith(source_name)
            and (locator is None or p["locator"] == locator)
            and (phrase is None or phrase in p["text"])
        ]
        assert matches, (query, [(p["url"], p["locator"]) for p in result["passages"]])
        for passage in result["passages"]:
            assert passage["passage_hash"] == hashlib.sha256(passage["text"].encode()).hexdigest()
            assert passage["filing_date"] <= "2026-11-06"

    update = lookup_document_questions(state)
    state.update(update)
    results = state["document_followups"]["results"]
    assert len(results) == 4
    assert all(result["status"] == "relevant_passages_found" for result in results)
    expected = [
        ("docn-20260930.htm", "block-148", "$345,111"),
        ("docn-20260630.htm", "block-149", "$365,901"),
        ("docn-20260930.htm", "block-218", "$2,955,158"),
        ("ex11-equitydistributionagr.htm", None, None),
    ]
    for result, (source_name, locator, phrase) in zip(results, expected, strict=True):
        assert any(
            p["url"].endswith(source_name)
            and (locator is None or p["locator"] == locator)
            and (phrase is None or phrase in p["text"])
            for p in result["passages"]
        ), result["query"]
    assert lookup_document_questions(state) == {}
    context = document_followup_context(state)
    assert "UNTRUSTED RETRIEVED SOURCE TEXT" in context
    for result in results:
        assert result["passages"][0]["citation_ref"] in context
    # RM, risk debaters and PM all call this shared source context helper.
    for role in ("research_manager", "risk_debate", "portfolio_manager"):
        delivered = get_instrument_context_from_state(state, include_mechanical=(role != "risk_debate"))
        assert "$345,111" in delivered and "$365,901" in delivered
        assert "$2,955,158" in delivered
        assert "UNTRUSTED RETRIEVED SOURCE TEXT" in delivered

    cited = results[0]["passages"][0]["citation_ref"]
    state["final_trade_decision"] = "Offline replay decision cites " + cited
    state["unvalidated_outputs"] = {"portfolio_manager": {"reason": state["final_trade_decision"]}}
    target = Path(os.environ.get("DOC_REPLAY_ARTIFACT_DIR", str(tmp_path / "rendered")))
    report = write_report_tree(state, "DOCN", target, html=True)
    markdown = report.read_text()
    html = (target / "complete_report.html").read_text()
    assert "Debate document follow-up" in markdown and "Debate document follow-up" in html
    assert "cited in final decision" in markdown.lower() and cited in markdown
    assert "final-decision citation not verified." in markdown
    assert "RM answer judgment unavailable" in markdown
    assert "docn" in markdown.lower()
    assert "Retrieved source text, not accepted evidence" in markdown
    assert (target / "5_portfolio/decision.md").is_file()
    assert "Debate document follow-up" in (target / "5_portfolio/decision.md").read_text()


def _capturing_model(response_text, prompts):
    """Only the model boundary is replaced; agent nodes build real prompts."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    model = MagicMock()
    model.with_structured_output.side_effect = NotImplementedError("offline fake model")
    model.invoke.side_effect = lambda prompt: (
        prompts.append(prompt) or SimpleNamespace(content=response_text)
    )
    return model


def test_retained_docn_passages_reach_actual_decision_nodes(tmp_path, monkeypatch):
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
    from tradingagents.agents.managers.research_manager import create_research_manager
    from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator

    saved, corpus = _retained_corpus()
    replay = _state(corpus)
    state = {**saved, **replay}
    state["investment_debate_state"] = {
        **saved["investment_debate_state"], **replay["investment_debate_state"],
        "count": 1,
    }
    # Saved terminal states omit ephemeral debate counters and speaker slots.
    state["risk_debate_state"] = {
        "count": 0,
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
        **saved["risk_debate_state"],
    }
    state.update(lookup_document_questions(state))
    results = state["document_followups"]["results"]
    ref = results[0]["passages"][0]["citation_ref"]
    required = ("$345,111", "$365,901", "$2,955,158", ref)

    rm_prompts = []
    rm = create_research_manager(_capturing_model(
        "Recommendation: Hold\nRationale: Offline replay source review.\nStrategic Actions: None.",
        rm_prompts,
    ))
    rm_update = rm(state)
    assert len(rm_prompts) == 1
    assert all(text in rm_prompts[0] for text in required)
    assert rm_update["investment_debate_state"]["document_questions"] == (
        state["investment_debate_state"]["document_questions"]
    )
    state.update(rm_update)

    risk_prompts = []
    risk = create_neutral_debator(_capturing_model(
        "Offline risk discussion includes retained filing questions.", risk_prompts
    ))
    risk_update = risk(state)
    assert len(risk_prompts) == 1
    assert all(text in risk_prompts[0] for text in required)
    state.update(risk_update)

    pm_prompts = []
    pm = create_portfolio_manager(_capturing_model(
        "Rating: Hold\nExecutive Summary: Offline replay cites " + ref
        + "\nInvestment Thesis: Retained filing text needs validation."
        + "\nTime Horizon: 6 months.",
        pm_prompts,
    ))
    pm_update = pm(state)
    assert len(pm_prompts) == 1
    assert all(text in pm_prompts[0] for text in required)
    assert ref in pm_update["final_trade_decision"]
    state.update(pm_update)

    # A deterministic fake model decision is displayed by the actual renderer.
    state.pop("publication_record", None)
    target = Path(os.environ.get(
        "DOC_REPLAY_NODE_ARTIFACT_DIR", str(tmp_path / "node-rendered")
    ))
    rendered = write_report_tree(state, "DOCN", target, html=True)
    markdown = rendered.read_text()
    html = (target / "complete_report.html").read_text()
    assert ref in markdown and ref in html
    assert "cited in final decision" in markdown.lower()
    assert "final-decision citation not verified." in markdown
    assert "RM answer judgment unavailable" in markdown
    assert 'Retrieved source text, not accepted evidence; final-decision citation not verified.' in html
    assert "Retrieved source text, not accepted evidence" in markdown

    # The CLI complete-report path prepares the same state before display.
    from io import StringIO

    from rich.console import Console

    import cli.display as cli_display

    cli_output = StringIO()
    monkeypatch.setattr(
        cli_display, "console", Console(file=cli_output, width=160, color_system=None)
    )
    cli_display.display_complete_report(state)
    visible = cli_output.getvalue()
    if os.environ.get("DOC_REPLAY_NODE_ARTIFACT_DIR"):
        (target / "complete_report_cli.txt").write_text(visible)
    assert "Portfolio Manager Decision" in visible
    assert "Debate document follow-up" in visible
    normalized_cli = " ".join(visible.replace("│", " ").split())
    assert 'Retrieved source text, not accepted evidence; final-decision citation not verified.' in normalized_cli


def test_public_docn_passages_reach_actual_decision_nodes(tmp_path, monkeypatch):
    """Run the original node proof on public sources with a scripted initial state."""
    import socket

    from tests.docn_workflow_fixture import source_json
    from tradingagents.graph.propagation import Propagator

    public = DisclosurePackage.model_validate(source_json("cfae95e9-corpus.json.gz"))
    assert public.as_of == date(2026, 11, 7)
    assert all(doc.filing.filed_date <= date(2026, 11, 6) for doc in public.documents)
    # A later-acquired public corpus projected to this filing-date cutoff; this
    # is a mixed scripted fixture, not the missing private historical replay.
    corpus = DisclosurePackage.model_validate({
        **public.model_dump(mode="json"), "as_of": "2026-11-06",
    })
    def deny_network(*args, **kwargs):
        raise AssertionError("Public node proof forbids network access")
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    scripted = Propagator().create_initial_state("DOCN", "2026-11-06")
    scripted["trader_investment_plan"] = "Hold: offline scripted proposal."
    monkeypatch.setattr(
        "tests.test_document_retained_replay._retained_corpus", lambda: (scripted, corpus),
    )
    test_retained_docn_passages_reach_actual_decision_nodes(tmp_path, monkeypatch)
