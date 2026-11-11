"""Freeze the large-filer cohort before any evidence is inspected (plan: "Freeze the companies").

Selects the first 30 distinct eligible issuers in SEC's published ``company_tickers.json`` order and
splits them 10 development / 20 held out. Eligibility is mechanical, from metadata only:

  * SIC present and outside 6000-6799 (submissions metadata);
  * files both 10-K and 10-Q, and no 20-F or 40-F, among recent forms (submissions metadata);
  * exactly one ``dei:EntityCommonStockSharesOutstanding`` cover-page fact in the latest 10-K or 10-Q
    filed by the cutoff. More than one means more than one class; none is ambiguous. Both are skipped.

Only those cover-page tags are read from a filing; nothing else in it is parsed or printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SALT = "large-filer-2026-11-09:"
ANCHORS = ("MSFT", "CAT", "WMT")
_COVER = re.compile(rb"<ix:nonFraction\b[^>]*\bname=\"dei:EntityCommonStockSharesOutstanding\"[^>]*>", re.I)
_CONTEXT = re.compile(rb"\bcontextRef=\"([^\"]+)\"", re.I)


def _get(url, pause=0.2):
    import requests

    from tradingagents.dataflows.vendors.sec_edgar import _user_agent
    time.sleep(pause)
    response = requests.get(url, headers={"User-Agent": _user_agent()}, timeout=60)
    response.raise_for_status()
    return response.content


def cover_classes(document: bytes) -> int:
    """How many distinct cover-page share counts the filing states (one per class of common stock)."""
    return len({match.group(1) for tag in _COVER.findall(document) if (match := _CONTEXT.search(tag))})


def assess(submissions: dict, cutoff: str, fetch) -> dict:
    """Eligibility decision for one issuer, with its basis."""
    sic = str(submissions.get("sic") or "").strip()
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms, dates = recent.get("form") or [], recent.get("filingDate") or []
    if not sic.isdigit():
        return {"eligible": False, "basis": "SIC unknown"}
    if 6000 <= int(sic) <= 6799:
        return {"eligible": False, "basis": f"SIC {sic} is a financial or real-estate code"}
    kinds = set(forms)
    if kinds & {"20-F", "40-F", "20-F/A", "40-F/A"} or not {"10-K", "10-Q"} <= kinds:
        return {"eligible": False, "basis": "not a filer of both 10-K and 10-Q among recent forms"}
    latest = next((i for i, form in enumerate(forms) if form in ("10-K", "10-Q") and dates[i] <= cutoff), None)
    if latest is None:
        return {"eligible": False, "basis": "no 10-K or 10-Q filed by the cutoff"}
    accession, document = recent["accessionNumber"][latest], recent["primaryDocument"][latest]
    cik = int(submissions["cik"])
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}"
    classes = cover_classes(fetch(url))
    basis = {"accession": accession, "form": forms[latest], "filed": dates[latest],
             "report_date": (recent.get("reportDate") or [""] * (latest + 1))[latest], "cover_share_counts": classes}
    if classes != 1:
        return {"eligible": False, "basis": "more than one class of common stock on the cover" if classes > 1
                else "cover share count not found; ambiguous", **basis}
    return {"eligible": True, "basis": "one cover share count; SIC and forms eligible", "sic": sic, **basis}


def split(tickers: list[str], ciks: dict[str, int]) -> tuple[list[str], list[str]]:
    """Ten development (named anchors first, then ascending salted hash), twenty held out."""
    development = [t for t in ANCHORS if t in tickers]
    rest = sorted((t for t in tickers if t not in development),
                  key=lambda t: (hashlib.sha256((SALT + t.upper()).encode()).hexdigest(), ciks[t]))
    development += rest[:10 - len(development)]
    return development, [t for t in tickers if t not in development]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--out", required=True, help="private directory for the dated inputs and the manifest")
    parser.add_argument("--count", type=int, default=30)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = _get(TICKERS_URL)
    (out / "company_tickers.json").write_bytes(raw)
    table = json.loads(raw)
    decisions, chosen, ciks, seen = [], [], {}, set()
    for key in sorted(table, key=int):
        entry = table[key]
        cik, ticker = int(entry["cik_str"]), str(entry["ticker"]).upper()
        if cik in seen:
            continue
        seen.add(cik)
        body = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        try:
            decision = assess(json.loads(body), args.cutoff, _get)
        except Exception as exc:  # noqa: BLE001 - an unreadable issuer is skipped with its reason, never guessed
            decision = {"eligible": False, "basis": f"could not be established: {type(exc).__name__}"}
        decisions.append({"order": int(key), "ticker": ticker, "cik": cik,
                          "submissions_sha256": hashlib.sha256(body).hexdigest(), **decision})
        print(f"{int(key):>3} {ticker:<6} {'ELIGIBLE' if decision['eligible'] else 'skip    '} {decision['basis']}")
        if decision["eligible"]:
            chosen.append(ticker)
            ciks[ticker] = cik
            if len(chosen) == args.count:
                break
    development, held_out = split(chosen, ciks)
    assert len(set(ciks.values())) == len(chosen) and not set(development) & set(held_out)
    manifest = {"cutoff": args.cutoff, "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tickers_url": TICKERS_URL, "tickers_sha256": hashlib.sha256(raw).hexdigest(), "salt": SALT,
                "cohort": chosen, "development": development, "held_out": held_out, "controls": ["DOCN"],
                "decisions": decisions}
    (out / "cohort.json").write_text(json.dumps(manifest, indent=1))
    print(f"\ncohort {len(chosen)}: development {development}\nheld out {held_out}")
    return 0 if len(chosen) == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
