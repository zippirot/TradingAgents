"""Offline scorer for the seven required source checks (plan L0).

Plan: docs/superpowers/plans/2026-11-08-large-filer-evidence-coverage-plan.md.

Drives the real first graph step, ``create_source_acquisition(["fundamentals"])``, and reads the
statuses it stores. No analyst or model is started. Raw SEC responses are recorded beneath
``requests.get`` on capture and replayed from disk on score, so transport limits, parsing and
package selection all run in production code.

  capture  live SEC pulls for the named tickers into a private store (free; no model call)
  score    replay only: the network is refused and a missing response is an input failure

The store holds raw SEC material and stays outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

REQUIRED = ("source_integrity", "core_statements", "balance_sheet", "equity_movement",
            "obligation_perimeter", "cash_flow_perimeter", "disclosure_coverage")


class ReplayMiss(RuntimeError):
    """A response the store does not hold. Never fetched in its place."""


class _Response:
    def __init__(self, url, status, headers, body):
        self.url, self.status_code, self.headers, self.content = url, status, headers, body
        self.encoding = "utf-8"

    @property
    def text(self):
        return self.content.decode(self.encoding or "utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)

    def iter_content(self, chunk_size=65536):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start:start + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            error = requests.HTTPError(f"{self.status_code} for {self.url}")
            error.response = self
            raise error

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Store:
    """Raw responses by URL: ``raw/<sha256(url)>`` plus one manifest of status, headers and content hash."""

    def __init__(self, root):
        self.root = Path(root)
        self.manifest_path = self.root / "manifest.json"
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {}

    def _path(self, url):
        return self.root / "raw" / hashlib.sha256(url.encode()).hexdigest()

    def put(self, url, status, headers, body):
        path = self._path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        self.manifest[url] = {"status": status, "headers": headers, "sha256": hashlib.sha256(body).hexdigest(),
                              "bytes": len(body), "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.manifest_path.write_text(json.dumps(self.manifest, indent=1, sort_keys=True))

    def get(self, url):
        entry, path = self.manifest.get(url), self._path(url)
        if entry is None or not path.exists():
            raise ReplayMiss(f"not in store: {url}")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != entry["sha256"]:
            raise ReplayMiss(f"hash mismatch in store: {url}")
        return _Response(url, entry["status"], entry["headers"], body)


class Transport:
    """Stands in for ``requests.get``. ``live`` is the real function on capture and None on score."""

    def __init__(self, store, live=None):
        self.store, self.live, self.calls, self.misses = store, live, [], []

    def __call__(self, url, **kwargs):
        from urllib.parse import urlsplit

        import requests
        host = urlsplit(url).hostname or ""
        if not (host == "sec.gov" or host.endswith(".sec.gov")):
            # Non-SEC sources are off: they cannot affect the seven checks and are never recorded.
            raise requests.ConnectionError(f"non-SEC source refused by the scorer: {host}")
        self.calls.append(url)
        if self.live is None:
            try:
                return self.store.get(url)
            except ReplayMiss:
                self.misses.append(url)
                raise
        response = self.live(url, **{**kwargs, "stream": False})
        headers = {key: value for key, value in response.headers.items()
                   if key.lower() in ("content-type", "content-length", "last-modified", "location")}
        self.store.put(url, response.status_code, headers, response.content)
        return self.store.get(url)


def _open(checks) -> bool:
    """Whether the run would go on to the analysts: no required source check stops it (the model's own claim
    check is assumed passed; an integrity check that is only unavailable lowers confidence and does not stop)."""
    from tradingagents.agents.evidence_validation import evidence_quality

    rows = [{"code": code, "status": row["status"], "message": row["reason"]} for code, row in checks.items()]
    rows.append({"code": "material_claims", "status": "pass", "message": "assumed for source-only scoring"})
    return evidence_quality(rows)["status"] != "insufficient"


def score_one(ticker, as_of, transport):
    """Seven statuses and reasons for one issuer, from the production acquisition step."""
    import requests

    from tradingagents.agents.evidence_validation import create_source_acquisition

    real, started = requests.get, time.monotonic()
    requests.get = transport
    before = len(transport.calls)
    try:
        with tempfile.TemporaryDirectory() as scratch:                     # no cached copy may stand in
            os.environ["TRADINGAGENTS_CACHE_DIR"] = scratch
            from tradingagents.dataflows.config import get_config, set_config
            set_config({**get_config(), "data_cache_dir": scratch})
            update = create_source_acquisition(["fundamentals"])(
                {"company_of_interest": ticker, "trade_date": as_of, "asset_type": "stock"})
    finally:
        requests.get = real
    record = update.get("evidence_acquisition") or {}
    found = {row.get("code"): row for row in record.get("source_checks") or () if isinstance(row, dict)}
    checks = {code: {"status": (found.get(code) or {}).get("status", "unavailable"),
                     "reason": (found.get(code) or {}).get("message") or "required check not produced"}
              for code in REQUIRED}
    return {"ticker": ticker, "as_of": as_of, "acquisition_status": record.get("status"),
            "acquisition_reason": record.get("reason") or "",
            "checks": checks, "passes": sum(1 for row in checks.values() if row["status"] == "pass"),
            "all_seven": all(row["status"] == "pass" for row in checks.values()),
            "open": _open(checks),
            "requests": len(transport.calls) - before, "replay_misses": list(transport.misses),
            "seconds": round(time.monotonic() - started, 1)}


def run(mode, tickers, as_of, store_dir, out):
    import requests

    store = Store(store_dir)
    results = []
    for ticker in tickers:
        transport = Transport(store, live=requests.get if mode == "capture" else None)
        try:
            row = score_one(ticker, as_of, transport)
            if row["replay_misses"]:          # production code may absorb the miss as "unavailable"; it is not one
                row = {"ticker": ticker, "as_of": as_of, "all_seven": False, "passes": None,
                       "input_failure": f"{len(row['replay_misses'])} response(s) not in the store",
                       "replay_misses": row["replay_misses"]}
            results.append(row)
        except Exception as exc:  # noqa: BLE001 - one issuer's failure is a recorded input failure, not a crash
            results.append({"ticker": ticker, "as_of": as_of, "input_failure": f"{type(exc).__name__}: {exc}"[:300],
                            "replay_misses": list(transport.misses), "all_seven": False, "passes": None})
    payload = {"mode": mode, "as_of": as_of, "code": _revision(), "results": results}
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(payload, indent=1))
    return payload


_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A")
_TEXT = (".htm", ".html", ".txt", ".xml", ".xsd", ".json")


def capture_index(tickers, as_of, store_dir, pause=0.15):
    """Save every text document in the index of each periodic and current report since the latest 10-K.

    The final code may request documents the baseline reader never did; they must already be in the store.
    Nothing is parsed or printed beyond counts. Images, archives, the rendered viewer pages (R*.htm) and
    the whole-submission text file are listed in the manifest as skipped, not downloaded.
    """
    import re

    import requests

    from tradingagents.dataflows.vendors.sec_edgar import _user_agent, cik_for

    store, receipts = Store(store_dir), []
    skipped_path = Path(store_dir) / "index_skipped.json"
    skipped = json.loads(skipped_path.read_text()) if skipped_path.exists() else {}

    def fetch(url):
        if url in store.manifest and store.manifest[url]["status"] == 200:
            return store.get(url)
        time.sleep(pause)
        response = requests.get(url, headers={"User-Agent": _user_agent()}, timeout=120)
        store.put(url, response.status_code, {"Content-Type": response.headers.get("Content-Type", "")},
                  response.content)
        return store.get(url)

    real = requests.get
    for ticker in tickers:
        requests.get = Transport(store, live=real)           # the ticker map and submissions go through the store
        try:
            cik = int(cik_for(ticker))
        finally:
            requests.get = real
        recent = fetch(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()["filings"]["recent"]
        rows = [(form, filed, accession) for form, filed, accession in
                zip(recent["form"], recent["filingDate"], recent["accessionNumber"], strict=True) if filed <= as_of]
        annual = max((filed for form, filed, _ in rows if form == "10-K"), default=None)
        # Production selects current reports from the latest quarterly report's period end, which can precede
        # the latest annual report's filing date (plan Amendment 2).
        reports = dict(zip(recent["accessionNumber"], recent["reportDate"], strict=True))
        quarter = max((reports[accession] for form, _, accession in rows if form == "10-Q" and reports[accession]),
                      default=None)
        since = min(date for date in (annual, quarter) if date) if (annual or quarter) else None
        wanted = [row for row in rows if row[0] in _FORMS and since is not None and row[1] >= since]
        documents = failures = 0
        for _form, _filed, accession in wanted:
            base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
            try:
                listing = fetch(f"{base}/index.json").json()["directory"]["item"]
            except Exception:  # noqa: BLE001 - recorded, never guessed
                failures += 1
                continue
            for item in listing:
                name = item.get("name", "")
                url = f"{base}/{name}"
                whole = name == f"{accession}.txt"
                if not name.lower().endswith(_TEXT) or re.fullmatch(r"R\d+\.htm", name) or whole:
                    skipped[url] = "whole submission" if whole else "viewer page or binary"
                    continue
                try:
                    if fetch(url).status_code == 200:
                        documents += 1
                    else:
                        failures += 1
                except Exception:  # noqa: BLE001
                    failures += 1
        skipped_path.write_text(json.dumps(skipped, indent=0, sort_keys=True))
        receipts.append({"ticker": ticker, "filings": len(wanted), "documents": documents, "failures": failures})
        print(f"{ticker}: filings={len(wanted)} documents={documents} failures={failures}", flush=True)
    return receipts


def _revision():
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "score", "capture-index"))
    parser.add_argument("--tickers", required=True, help="comma-separated")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--store", required=True, help="private directory for raw SEC responses")
    parser.add_argument("--out")
    parser.add_argument("--quiet", action="store_true", help="print only a completion receipt (sealed groups)")
    args = parser.parse_args(argv)
    if args.mode == "capture-index":
        capture_index([t.strip().upper() for t in args.tickers.split(",") if t.strip()], args.as_of, args.store)
        return 0
    payload = run(args.mode, [t.strip().upper() for t in args.tickers.split(",") if t.strip()], args.as_of,
                  args.store, args.out)
    for row in payload["results"]:
        if args.quiet:
            print(f"{row['ticker']}: done")
        elif "input_failure" in row:
            print(f"{row['ticker']}: INPUT FAILURE {row['input_failure']}")
        else:
            print(f"{row['ticker']}: {row['passes']}/7 requests={row['requests']} seconds={row['seconds']}")
            for code, check in row["checks"].items():
                print(f"   {code}: {check['status']} | {check['reason'][:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
