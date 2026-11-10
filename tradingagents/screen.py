"""Which companies can a run analyse? Source collection and the source checks only; no model is called.

    python -m tradingagents.screen DOCN NET AKAM [--date 2026-11-10] [--json]

A full run stops before the debate when a required source check does not pass. This runs only that
part: it fetches the filings and prices a run would fetch and reports each required check. The one
required check that reads a model's report (material claims) is left out, since no report exists here.
"""
from __future__ import annotations

import argparse
import json
import os

SOURCE_CHECK_NOTE = "material_claims is not run: it checks a model's report, and no model is called"


def source_checks() -> tuple[str, ...]:
    from tradingagents.agents.evidence_validation import REQUIRED_FINANCIAL_CHECKS
    return tuple(code for code in REQUIRED_FINANCIAL_CHECKS if code != "material_claims")


def screen(ticker: str, as_of: str) -> dict:
    """One ticker's required source checks. A failure to fetch or assess is reported, never raised."""
    from tradingagents.agents.evidence_validation import create_evidence_gate
    row = {"ticker": ticker.upper(), "as_of": as_of, "passes": False, "checks": {}, "reasons": []}
    try:
        result = create_evidence_gate(["fundamentals"])({
            "company_of_interest": row["ticker"], "trade_date": as_of, "asset_type": "stock", "fundamentals_report": ""})
        found = {check["code"]: check for check in result["evidence_quality"]["checks"]}
    except Exception as exc:  # noqa: BLE001 - one unreadable company must not stop the list
        row["reasons"] = [f"could not be assessed: {type(exc).__name__}: {str(exc)[:200]}"]
        return row
    for code in source_checks():
        check = found.get(code) or {"status": "unavailable", "message": "check not completed"}
        row["checks"][code] = check["status"]
        if check["status"] != "pass":
            row["reasons"].append(f"{code}: {check['status']}: {str(check.get('message') or '')[:200]}")
    row["passes"] = not row["reasons"]
    return row


def render(rows: list[dict]) -> str:
    codes = source_checks()
    lines = ["Ticker | Result | Required source checks passed | First reason it stops", "--- | --- | --- | ---"]
    for row in rows:
        passed = sum(status == "pass" for status in row["checks"].values())
        lines.append(f"{row['ticker']} | {'can be analysed' if row['passes'] else 'stops before the debate'} | "
                     f"{passed} of {len(codes)} | {row['reasons'][0] if row['reasons'] else ''}")
    lines += ["", f"{sum(row['passes'] for row in rows)} of {len(rows)} pass. {SOURCE_CHECK_NOTE}."]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--date", help="analysis date, yyyy-mm-dd (default: today)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    # No model can be reached from here: nothing below is given a model, and the keys are dropped as well.
    for name in list(os.environ):
        if name.endswith("_API_KEY"):
            del os.environ[name]
    from tradingagents.dataflows.date_window import get_current_date
    as_of = args.date or get_current_date()
    rows = [screen(ticker, as_of) for ticker in dict.fromkeys(t.upper() for t in args.tickers)]
    print(json.dumps(rows, indent=2) if args.json else render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
