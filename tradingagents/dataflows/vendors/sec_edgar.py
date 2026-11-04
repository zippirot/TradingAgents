"""Company statements as they were filed, from SEC EDGAR.

Every other fundamentals vendor serves a period's current value and cuts the
statement at the fiscal period end. That is two claims a run should not make: a
period that has ended is not public until the company files, weeks later, and a
figure that was later restated is not what investors saw at the time.

EDGAR reports every fact with the date it was filed, so a run dated ``as_of_date``
serves exactly what was on file by then, restatements included at the vintage
that was current: Apple's 2008 total assets read 39.6B until the 2010 amendment
restated them to 36.2B.

Access needs no key or account, only a User-Agent identifying the caller, which
SEC requires and refuses requests without. US filers only: anything absent from
EDGAR's ticker map falls through to the next configured vendor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

from tradingagents import __version__
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.files import replace_file

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# A filing history only changes when something new is filed, so one fetch per
# company per day serves every date a run asks about.
_CACHE_TTL_SECONDS = 24 * 60 * 60

# Line items, each with the tags filers use for it, best first. First match wins
# and values are never summed across tags: a company reporting revenue under two
# tags would otherwise be counted twice.
_STATEMENTS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "balance_sheet": [
        ("Total Assets", ("Assets",)),
        ("Current Assets", ("AssetsCurrent",)),
        ("Cash and Equivalents", ("CashAndCashEquivalentsAtCarryingValue",)),
        ("Total Liabilities", ("Liabilities",)),
        ("Current Liabilities", ("LiabilitiesCurrent",)),
        ("Stockholders Equity", ("StockholdersEquity",
                                 "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")),
    ],
    "income_statement": [
        ("Revenue", ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                     "SalesRevenueNet")),
        ("Cost of Revenue", ("CostOfRevenue", "CostOfGoodsAndServicesSold")),
        ("Gross Profit", ("GrossProfit",)),
        ("Operating Income", ("OperatingIncomeLoss",)),
        ("Net Income", ("NetIncomeLoss",)),
        ("Diluted EPS", ("EarningsPerShareDiluted",)),
    ],
    "cashflow": [
        ("Operating Cash Flow", ("NetCashProvidedByUsedInOperatingActivities",
                                 "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations")),
        ("Investing Cash Flow", ("NetCashProvidedByUsedInInvestingActivities",)),
        ("Financing Cash Flow", ("NetCashProvidedByUsedInFinancingActivities",)),
        ("Capital Expenditure", ("PaymentsToAcquirePropertyPlantAndEquipment",
                                 "PaymentsToAcquireProductiveAssets")),
    ],
}

# Keep totals and components separate. These rows do not imply additive debt
# perimeters: equipment financing and issuer-specific items need filed narrative.
_STATEMENTS["balance_sheet"] += [
    ("Long-term Borrowings (including current)", ("LongTermDebt",)),
    ("Current Long-term Borrowings", ("LongTermDebtCurrent",)),
    ("Noncurrent Long-term Borrowings", ("LongTermDebtNoncurrent",)),
    ("Short-term Borrowings", ("ShortTermBorrowings",)),
    ("Finance Lease Liabilities", ("FinanceLeaseLiability",)),
    ("Current Finance Lease Liabilities", ("FinanceLeaseLiabilityCurrent",)),
    ("Noncurrent Finance Lease Liabilities", ("FinanceLeaseLiabilityNoncurrent",)),
    ("Operating Lease Liabilities", ("OperatingLeaseLiability",)),
    ("Current Operating Lease Liabilities", ("OperatingLeaseLiabilityCurrent",)),
    ("Noncurrent Operating Lease Liabilities", ("OperatingLeaseLiabilityNoncurrent",)),
    ("Restricted Cash", ("RestrictedCash",)),
    ("Cash Including Restricted Cash", ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",)),
    ("Common Stock Par or Stated Value (Issued)", ("CommonStockValue",)),
    ("Additional Paid-in Capital", ("AdditionalPaidInCapital",)),
    ("Retained Earnings or Accumulated Deficit", ("RetainedEarningsAccumulatedDeficit",)),
    ("Accumulated Other Comprehensive Income", ("AccumulatedOtherComprehensiveIncomeLossNetOfTax",)),
    ("Treasury Stock at Cost", ("TreasuryStockValue",)),
    ("Common Shares Outstanding", ("CommonStockSharesOutstanding",)),
]
_STATEMENTS["income_statement"] += [
    ("Basic EPS", ("EarningsPerShareBasic",)),
    ("Basic Earnings Numerator", ("NetIncomeLossAvailableToCommonStockholdersBasic",)),
    ("Diluted Earnings Numerator", ("NetIncomeLossAvailableToCommonStockholdersDiluted",)),
    ("Weighted Average Basic Shares", ("WeightedAverageNumberOfSharesOutstandingBasic",)),
    ("Weighted Average Diluted Shares", ("WeightedAverageNumberOfDilutedSharesOutstanding",)),
    ("Income Tax Expense or Benefit", ("IncomeTaxExpenseBenefit",)),
    ("Nonoperating Interest Expense", ("InterestExpenseNonoperating",)),
    ("Debt Interest Expense", ("InterestExpenseDebt",)),
    ("Finance Lease Interest Expense", ("FinanceLeaseInterestExpense",)),
    ("Convertible Interest Net of Tax", ("InterestOnConvertibleDebtNetOfTax",)),
]
_STATEMENTS["cashflow"] += [
    ("Common Stock Issuance Proceeds", ("ProceedsFromIssuanceOfCommonStock",)),
    ("Stock Repurchase Payments", ("PaymentsForRepurchaseOfCommonStock",)),
    ("Long-term Debt Issuance Proceeds", ("ProceedsFromIssuanceOfLongTermDebt",)),
    ("Long-term Debt Repayments", ("RepaymentsOfLongTermDebt",)),
    ("Finance Lease Principal Payments", ("FinanceLeasePrincipalPayments",)),
    ("Equipment on Lease Payments", ("PaymentsToAcquireEquipmentOnLease",)),
    ("Software Development Payments", ("PaymentsToDevelopSoftware",)),
    ("Cash-flow Share-based Compensation", ("ShareBasedCompensation",)),
    ("Equity Share-based Compensation", ("AdjustmentsToAdditionalPaidInCapitalSharebasedCompensationRequisiteServicePeriodRecognitionValue",)),
    ("Noncash Finance Lease Additions", ("RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability",)),
    ("Noncash Operating Lease Additions", ("RightOfUseAssetObtainedInExchangeForOperatingLeaseLiability",)),
]

# A statement's figures cover a span: a quarter is about 90 days, a year about
# 365. One filing reports both the quarter and the year to date under the same
# end date, so a match on the end date alone can report half a year as a quarter.
_SPANS = {"quarterly": (60, 115), "annual": (300, 400)}

# A 10-Q's cash flows are often filed only year to date. A quarterly table takes
# the quarter where filed, else the span to date, named in the column; it never
# subtracts one filing from another, which would give a figure no filing states.
_YEAR_TO_DATE = ((150, 200, 6), (240, 290, 9))

# A fiscal year is a period an annual report covers. A 10-Q balance has no span
# to reject, and some filers' 10-Qs report twelve-month totals that pass the span
# check, so either would read as a fiscal year. The value is still the latest
# filing of any form: a recast after a split or spin-off counts from its filing.
_ANNUAL_FORMS = ("10-K", "20-F", "40-F")


def _user_agent() -> str:
    """Who SEC sees. No account or key exists; callers identify themselves.

    www.sec.gov, which serves the ticker map, refuses a User-Agent carrying no
    contact address: a client name alone or with a project URL gets 403, one
    with an address gets 200. So the default carries a placeholder address and
    the package version. Set SEC_EDGAR_USER_AGENT to your own name and address
    so SEC can reach you about your traffic rather than the project.
    """
    configured = os.getenv("SEC_EDGAR_USER_AGENT", "").strip()
    return configured or f"TradingAgents/{__version__} (contact@example.com)"




def _fetch_json(url: str) -> dict:
    """Read a public EDGAR document, respecting SEC's identification rule."""
    try:
        response = requests.get(url, headers={"User-Agent": _user_agent()}, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        # Every failure here is "this vendor cannot serve it now", so the router
        # moves on instead of seeing a transport exception it has no rule for.
        raise VendorUnavailableError(f"SEC EDGAR request failed ({status or type(exc).__name__})") from exc
    except ValueError as exc:
        raise VendorUnavailableError("SEC EDGAR returned an unreadable response") from exc


def _cached_json(url: str, name: str) -> dict:
    path = Path(get_config()["data_cache_dir"]) / "sec_edgar" / name
    if path.exists() and time.time() - path.stat().st_mtime < _CACHE_TTL_SECONDS:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass  # a truncated file is a miss, not a failure
    data = _fetch_json(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_file(path, lambda temp: Path(temp).write_text(json.dumps(data), encoding="utf-8"))
    return data


def cik_for(ticker: str) -> str | None:
    """The filer's CIK, or None when the ticker is not a US filer."""
    table = _cached_json(_TICKERS_URL, "company_tickers.json")
    wanted = ticker.strip().upper()
    for entry in table.values():
        if entry.get("ticker", "").upper() == wanted:
            return f"{int(entry['cik_str']):010d}"
    return None


def _span_index(fact: dict, spans: tuple[tuple[int, int], ...]) -> int | None:
    """Which of ``spans`` a duration fact covers (0 for an instant fact), or None."""
    if "start" not in fact:
        return 0
    days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
    return next((i for i, (low, high) in enumerate(spans) if low <= days <= high), None)


def _as_of_records(facts: dict, tags: tuple[str, ...], as_of_date: str,
                   spans: tuple[tuple[int, int], ...], forms: tuple[str, ...] = ()) -> dict:
    """Select consolidated facts with their original filing context and exact value.

    Tag preference is applied per period, never summed. Reject ambiguity rather
    than let JSON ordering choose a currency, duration or contradictory value.
    A recast can come from any form, but an annual period must have been reported
    in an annual filing with the same start date and unit by the cutoff.
    """
    cutoff = date.fromisoformat(as_of_date)
    chosen = {}
    for tag in tags:
        candidates = {}
        covered = set()
        container = facts.get(tag) or {}
        if not isinstance(container, dict) or not isinstance(container.get("units", {}), dict):
            raise VendorUnavailableError(f"Malformed SEC units for {tag}")
        for unit, values in container.get("units", {}).items():
            if not isinstance(unit, str) or not isinstance(values, list):
                continue
            for fact in values:
                if not isinstance(fact, dict) or fact.get("segment") or fact.get("dimensions"):
                    continue
                try:
                    end = date.fromisoformat(fact["end"])
                    filed = date.fromisoformat(fact["filed"])
                    value = fact["val"]
                    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
                        continue
                    if not Decimal(str(value)).is_finite() or end > cutoff or filed > cutoff:
                        continue
                    index = _span_index(fact, spans)
                except (KeyError, ValueError, TypeError, InvalidOperation):
                    continue
                if index is None:
                    continue
                key = (fact["end"], index)
                if key in chosen:
                    continue
                record = {**deepcopy(fact), "tag": tag, "unit": unit}
                candidates.setdefault(key, []).append(record)
                if not forms or str(fact.get("form", "")).startswith(forms):
                    covered.add((key, fact.get("start"), unit))
        for key, records in candidates.items():
            eligible = [r for r in records if (key, r.get("start"), r["unit"]) in covered]
            if not eligible:
                continue
            if len({(r.get("start"), r["unit"]) for r in eligible}) > 1:
                raise VendorUnavailableError(f"SEC period or unit ambiguous for {tag} at {key[0]}")
            newest = max(r["filed"] for r in eligible)
            latest = [r for r in eligible if r["filed"] == newest]
            meanings = {(r.get("start"), r["unit"], Decimal(str(r["val"]))) for r in latest}
            if len(meanings) != 1:
                raise VendorUnavailableError(f"SEC fact ambiguous for {tag} at {key[0]}")
            # Duplicate equivalent facts use a stable accession ordering.
            chosen[key] = max(latest, key=lambda r: str(r.get("accn", "")))
    return dict(sorted(chosen.items()))


def _as_of(facts: dict, tags: tuple[str, ...], as_of_date: str,
           spans: tuple[tuple[int, int], ...], forms: tuple[str, ...] = ()) -> tuple[dict, str]:
    """Compatibility view: exact values and one unambiguous unit per CSV row."""
    records = _as_of_records(facts, tags, as_of_date, spans, forms)
    units = {record["unit"] for record in records.values()}
    if len(units) > 1:
        raise VendorUnavailableError(f"SEC statement row has incompatible units for {tags[0]}")
    return {key: record["val"] for key, record in records.items()}, next(iter(units), "USD")


def _display_value(value, unit: str) -> str:
    """Scale USD for familiar tables without rounding away source precision."""
    exact = Decimal(str(value))
    if unit == "USD":
        exact /= Decimal(1000000)
    text = format(exact, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _statement(kind: str, ticker: str, freq: str, as_of_date: str, title: str) -> str:
    as_of_date = as_of_date or datetime.now().strftime("%Y-%m-%d")
    cik = cik_for(ticker)
    if cik is None:
        raise NoMarketDataError(ticker, ticker, "not a US SEC filer")

    facts = _cached_json(_FACTS_URL.format(cik=cik), f"CIK{cik}.json")
    us_gaap = (facts.get("facts") or {}).get("us-gaap")
    if not us_gaap:
        raise NoMarketDataError(ticker, ticker, "US filer with no us-gaap facts")

    quarterly = freq.lower() == "quarterly"
    if quarterly:
        spans = (_SPANS["quarterly"], *((low, high) for low, high, _ in _YEAR_TO_DATE))
        names = ["", *(f" ({months} months)" for _, _, months in _YEAR_TO_DATE)]
    else:
        spans, names = (_SPANS["annual"],), [""]
    forms = () if quarterly else _ANNUAL_FORMS
    lines = {label: _as_of(us_gaap, tags, as_of_date, spans, forms) for label, tags in _STATEMENTS[kind]}
    # Each row takes the shortest span it reports for a period, and a column
    # holds one span of one period, so a row filed only to date keeps its figure
    # beside a row filed by quarter.
    chosen = {label: {} for label in lines}
    for label, (values, _) in lines.items():
        for end, index in values:
            chosen[label][end] = min(index, chosen[label].get(end, index))
    periods = sorted({(end, index) for spans_of in chosen.values() for end, index in spans_of.items()})
    if not periods:
        raise NoMarketDataError(ticker, ticker, f"no {freq} {title.lower()} filed by {as_of_date}")

    header = (
        f"# {title} for {ticker.upper()} ({freq}), USD in millions unless the row says otherwise\n"
        f"# SEC EDGAR facts filed on or before {as_of_date}, at the values filed then\n\n"
    )
    rows = [",".join([""] + [end + names[index] for end, index in periods])]
    for label, (values, unit) in lines.items():
        # Every row spans the same columns, or a reader lines the table up wrong.
        if not values:
            rows.append(",".join([label] + ["unavailable (not tagged by this filer)"] * len(periods)))
            continue
        name = label if unit == "USD" else f"{label} ({unit})"
        # Plain numbers: a thousands separator would split the CSV field.
        cells = []
        for end, index in periods:
            value = values.get((end, index)) if chosen[label].get(end) == index else None
            cells.append("" if value is None else _display_value(value, unit))
        rows.append(",".join([name] + cells))
    return header + "\n".join(rows) + "\n"


def get_balance_sheet(ticker: str, freq: str = "quarterly", as_of_date: str | None = None) -> str:
    """Balance sheet as filed on or before ``as_of_date``."""
    return _statement("balance_sheet", ticker, freq, as_of_date, "Balance Sheet")


def get_income_statement(ticker: str, freq: str = "quarterly", as_of_date: str | None = None) -> str:
    """Income statement as filed on or before ``as_of_date``.

    A fourth quarter is never derived: filers report it only inside the annual
    figure, and subtracting three separately filed quarters would invent a number
    with no filing date behind it.
    """
    return _statement("income_statement", ticker, freq, as_of_date, "Income Statement")


def get_cashflow(ticker: str, freq: str = "quarterly", as_of_date: str | None = None) -> str:
    """Cash flow statement as filed on or before ``as_of_date``."""
    return _statement("cashflow", ticker, freq, as_of_date, "Cash Flow Statement")


def get_financial_evidence(ticker: str, as_of_date: str):
    """Bounded exact SEC facts, retaining the source fragment for each value.

    This path never substitutes undated vendor snapshots for filed evidence.
    Twelve recent statement ends and five fiscal year ends bound model context.
    """
    from tradingagents.dataflows.financial_evidence import (
        EvidencePackage,
        FinancialFact,
        SourceRecord,
        add_period_calculations,
    )

    cutoff = date.fromisoformat(as_of_date)
    cik = cik_for(ticker)
    if cik is None:
        raise NoMarketDataError(ticker, ticker, "not a US SEC filer")
    data = _cached_json(_FACTS_URL.format(cik=cik), f"CIK{cik}.json")
    if str(data.get("cik", "")).zfill(10) != cik:
        raise VendorUnavailableError("SEC companyfacts issuer does not match requested CIK")
    facts = (data.get("facts") or {}).get("us-gaap")
    if not isinstance(facts, dict) or not facts:
        raise NoMarketDataError(ticker, ticker, "US filer with no us-gaap facts")
    cache = Path(get_config()["data_cache_dir"]) / "sec_edgar" / f"CIK{cik}.json"
    observed = datetime.fromtimestamp(cache.stat().st_mtime, UTC) if cache.exists() else datetime.now(UTC)
    snapshot_hash = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    quarterly_spans = (_SPANS["quarterly"], *((low, high) for low, high, _ in _YEAR_TO_DATE))
    selected = {}
    quarterly_ends, annual_ends = set(), set()
    for rows in _STATEMENTS.values():
        for metric, tags in rows:
            quarter = _as_of_records(facts, tags, as_of_date, quarterly_spans)
            annual = _as_of_records(facts, tags, as_of_date, (_SPANS["annual"],), _ANNUAL_FORMS)
            quarterly_ends.update(k[0] for k in quarter)
            annual_ends.update(k[0] for k in annual)
            selected[metric] = (quarter, annual)
    allowed_quarters = set(sorted(quarterly_ends)[-12:])
    allowed_annual = set(sorted(annual_ends)[-5:])
    sources, records = {}, {}
    for metric, (quarter, annual) in selected.items():
        picked = [v for (end, _), v in quarter.items() if end in allowed_quarters]
        picked += [v for (end, _), v in annual.items() if end in allowed_annual]
        if not picked:
            identity = hashlib.sha256(f"{cik}:{as_of_date}:{metric}:missing".encode()).hexdigest()
            records[identity] = FinancialFact(fact_id=identity, metric=metric, value=None, unit="unknown",
                cik=cik, period_end=cutoff, as_of=cutoff, locator="Selected US-GAAP tags",
                missing_reason="No usable consolidated fact in the selected tags and periods")
        for record in picked:
            identity = hashlib.sha256(json.dumps([cik, metric, record], sort_keys=True).encode()).hexdigest()
            locator = f"us-gaap/{record['tag']}/{record['unit']}/{record.get('start', 'instant')}/{record['end']}/{record['filed']}"
            source_id = "sec-" + identity
            sources[source_id] = SourceRecord(source_id=source_id, cik=cik, url=_FACTS_URL.format(cik=cik),
                filed_date=record["filed"], retrieved_at=observed, content_hash=snapshot_hash,
                locator=locator, accession=record.get("accn"), form=record.get("form", "unknown"))
            records[identity] = FinancialFact(fact_id=identity, metric=metric, value=Decimal(str(record["val"])),
                unit=record["unit"], cik=cik, period_start=record.get("start"), period_end=record["end"],
                as_of=cutoff, source_ids=(source_id,), locator=locator)
    if not sources:
        raise NoMarketDataError(ticker, ticker, f"no statement evidence filed by {as_of_date}")
    return add_period_calculations(EvidencePackage(cik=cik, as_of=cutoff, facts=tuple(records.values()), sources=tuple(sources.values()),
        warnings=("Companyfacts coverage excludes issuer-specific narrative and untagged disclosures; this is not a complete financial validation.",)))
