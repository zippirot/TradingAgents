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
import re
import time
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

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
        ("Consolidated Profit (Loss)", ("ProfitLoss",)),
        ("Net Income Attributable to Noncontrolling Interests",
         ("NetIncomeLossAttributableToNoncontrollingInterest",)),
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

# Retain these as candidates, not current balances. Unqualified tags need the
# matching filed balance-sheet presentation before they can support liquidity.
_SECURITY_CANDIDATES = (
    "AvailableForSaleSecuritiesDebtSecurities",
    "MarketableSecurities",
    "MarketableSecuritiesCurrent",
    "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    "ShortTermInvestments",
)
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

_STATEMENTS["cashflow"] += [
    ("Other Comprehensive Income Attributable to Parent", ("OtherComprehensiveIncomeLossNetOfTaxPortionAttributableToParent",)),
    ("Employee Stock Purchase Plan Issuance Value", ("StockIssuedDuringPeriodValueEmployeeStockPurchasePlan",)),
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
    from tradingagents.source_replay import current_session, external_input

    if current_session() is None:
        return _cached_json_live(url, name)
    path = Path(get_config()["data_cache_dir"]) / "sec_edgar" / name

    def acquire():
        data = _cached_json_live(url, name)
        return {"data": data, "mtime": path.stat().st_mtime}

    retained = external_input("sec_json", {"url": url, "name": name}, acquire)
    if current_session().baseline is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        replace_file(path, lambda temp: Path(temp).write_text(json.dumps(retained["data"]), encoding="utf-8"))
        import os

        os.utime(path, (retained["mtime"], retained["mtime"]))
    return retained["data"]


def _cached_json_live(url: str, name: str) -> dict:
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


def _eligible_records(facts: dict, tag: str, cutoff: date,
                      spans: tuple[tuple[int, int], ...], forms: tuple[str, ...],
                      allowed_ends: set[str] | None = None, period_floor: date | None = None) -> dict:
    """Group eligible source records without resolving conflicting meanings."""
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
                if (not Decimal(str(value)).is_finite() or end > cutoff or filed > cutoff
                        or (period_floor is not None and end < period_floor)):
                    continue
                index = _span_index(fact, spans)
            except (KeyError, ValueError, TypeError, InvalidOperation):
                continue
            if index is None:
                continue
            key = (fact["end"], index)
            if allowed_ends is not None and key[0] not in allowed_ends:
                continue
            record = {**deepcopy(fact), "tag": tag, "unit": unit}
            candidates.setdefault(key, []).append(record)
            if not forms or str(fact.get("form", "")).startswith(forms):
                covered.add((key, fact.get("start"), unit))
    return {
        key: eligible for key, records in candidates.items()
        if (eligible := [r for r in records if (key, r.get("start"), r["unit"]) in covered])
    }


# Peer statistics read the latest four quarters and the four before them, so
# every period they can consume ends within 24 months of the newest one.
_PEER_CONSUMED_METRICS = {"Revenue", "Gross Profit", "Common Shares Outstanding"}
_PEER_STATISTICS_MONTHS = 24


def _peer_exclusion_floor(facts: dict, tags: tuple[str, ...], cutoff: date, spans, allowed_ends: set[str],
                          period_floor: date | None) -> str | None:
    ends = [key[0] for tag in tags
            for key in _eligible_records(facts, tag, cutoff, spans, (), allowed_ends, period_floor)]
    if not ends:
        return date.max.isoformat()  # Annual-only filer: statistics read no period of this metric.
    newest = date.fromisoformat(max(ends))
    months = newest.year * 12 + newest.month - 1 - _PEER_STATISTICS_MONTHS
    return date(months // 12, months % 12 + 1, 1).isoformat()


def _as_of_records(facts: dict, tags: tuple[str, ...], as_of_date: str,
                   spans: tuple[tuple[int, int], ...], forms: tuple[str, ...] = (),
                   *, allowed_ends: set[str] | None = None, period_floor: date | None = None,
                   ambiguity: Literal["raise", "exclude"] = "raise",
                   exclude_before: str | None = None, excluded: list[str] | None = None) -> dict:
    """Select consolidated facts with their original filing context and exact value.

    Tag preference is applied per period, never summed. Reject ambiguity rather
    than let JSON ordering choose a currency, duration or contradictory value.
    A recast can come from any form, but an annual period must have been reported
    in an annual filing with the same start date and unit by the cutoff.

    With ambiguity="exclude", an ambiguous period ending before exclude_before
    is dropped and named in excluded. A newer one still raises, because dropping
    it would silently move the statistic onto an older window.
    """
    cutoff = date.fromisoformat(as_of_date)
    chosen = {}

    def drop(tag: str, end: str) -> bool:
        if ambiguity != "exclude" or exclude_before is None or end >= exclude_before:
            return False
        if excluded is not None:
            note = f"{tag} ambiguous at {end}; period excluded; not used for peer statistics"
            if note not in excluded:
                excluded.append(note)
        return True

    for tag in tags:
        candidates = _eligible_records(facts, tag, cutoff, spans, forms, allowed_ends, period_floor)
        for key, eligible in candidates.items():
            if key in chosen:
                continue
            if len({(r.get("start"), r["unit"]) for r in eligible}) > 1:
                if drop(tag, key[0]):
                    continue
                raise VendorUnavailableError(f"SEC period or unit ambiguous for {tag} at {key[0]}")
            newest = max(r["filed"] for r in eligible)
            latest = [r for r in eligible if r["filed"] == newest]
            meanings = {(r.get("start"), r["unit"], Decimal(str(r["val"]))) for r in latest}
            if len(meanings) != 1:
                if drop(tag, key[0]):
                    continue
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


_OUTSIDE_EQUITY_CONCEPT = re.compile(r"redeemable|temporaryequity|mezzanine|noncontrolling|minorityinterest", re.I)
_READ_EQUITY_CONCEPTS = frozenset({
    "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "MinorityInterest"})


def _unread_equity_concepts(data: dict, end: str, read: frozenset) -> list[str]:
    """Balances at ``end`` under any taxonomy whose name says outside or temporary equity and which code does not read.

    Every face line item of a filed balance sheet carries a tag, standard or the filer's own. One that code
    does not read means the equity deducted from the filed total may be incomplete, so nothing is derived.
    """
    found = []
    for concepts in (data.get("facts") or {}).values():
        for name, body in (concepts or {}).items():
            if name in read or not _OUTSIDE_EQUITY_CONCEPT.search(name):
                continue
            if any(row.get("end") == end and "start" not in row
                   for rows in (body.get("units") or {}).values() for row in rows):
                found.append(name)
    return sorted(found)


def _derived_total_liabilities(data, records, end, derive):
    """Total liabilities at ``end`` from the filed total less all equity, or None when that cannot be established."""
    from tradingagents.dataflows.financial_evidence import (
        LIABILITIES_AND_EQUITY,
        NONCONTROLLING,
        TEMPORARY_EQUITY_METRICS,
        TEMPORARY_EQUITY_TAGS,
        TOTAL_EQUITY,
    )
    at_end = [f for f in records.values() if f.value is not None and f.period_start is None
              and str(f.period_end) == end and f.origin == "reported"]

    def one(metric):
        found = [f for f in at_end if f.metric == metric]
        return found[0] if len(found) == 1 else None

    total, temporary = one(LIABILITIES_AND_EQUITY), [f for f in at_end if f.metric in TEMPORARY_EQUITY_METRICS]
    if total is None or len(temporary) > 1 or _unread_equity_concepts(
            data, end, _READ_EQUITY_CONCEPTS | frozenset(TEMPORARY_EQUITY_TAGS)):
        return None
    equity = one(TOTAL_EQUITY)
    if equity is None and not any(f.metric == NONCONTROLLING for f in at_end):
        parent = one("Stockholders Equity")
        # The parent's equity is all equity only when the filing carries no noncontrolling balance at all.
        equity = parent if parent is not None and "/StockholdersEquity/" in parent.locator else None
    if equity is None:
        return None
    try:
        return derive((total, equity, *temporary))
    except ValueError:
        return None


def get_financial_evidence(ticker: str, as_of_date: str, *, peer_revenue_definitions: bool = False,
                           period_floor: date | None = None):
    """Bounded exact SEC facts, retaining the source fragment for each value.

    This path never substitutes undated vendor snapshots for filed evidence.
    Twelve recent statement ends and five fiscal year ends bound model context.
    """
    from tradingagents.dataflows.financial_evidence import (
        LIABILITIES_AND_EQUITY,
        NONCONTROLLING,
        TEMPORARY_EQUITY_TAGS,
        TOTAL_EQUITY,
        EvidencePackage,
        FinancialFact,
        SourceRecord,
        add_period_calculations,
        derive_parent_net_income,
        derive_total_liabilities,
        temporary_equity_metric,
    )

    # The broader reported-revenue definition is permitted only for peer
    # diagnostics, where its tag and comparability limitation are displayed.
    # Subject/history/target callers keep their existing definition contract.
    statements = {
        **_STATEMENTS,
        "securities_candidates": [
            (f"Unclassified Marketable Securities [{tag}]", (tag,))
            for tag in _SECURITY_CANDIDATES
        ],
        # Read for every filer, kept only where the balance sheet needs them (see below): a filer that
        # reports no total-liabilities line, or one with noncontrolling or temporary equity.
        "balance_identity": [
            (LIABILITIES_AND_EQUITY, ("LiabilitiesAndStockholdersEquity",)),
            (TOTAL_EQUITY, ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",)),
            (NONCONTROLLING, ("MinorityInterest",)),
            *((temporary_equity_metric(tag), (tag,)) for tag in TEMPORARY_EQUITY_TAGS),
        ],
    }
    identity_metrics = {metric for metric, _ in statements["balance_identity"]}
    ambiguous_identity = set()
    if peer_revenue_definitions:
        statements = {
            kind: [(metric, tags + ("RevenueFromContractWithCustomerIncludingAssessedTax",)
                    if metric == "Revenue" else tags) for metric, tags in rows]
            for kind, rows in statements.items()
        }
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
    # Discover the eligible period window before resolving values. Ambiguities
    # outside this explicitly discarded history cannot invalidate current facts;
    # every selected period still goes through the same strict resolver.
    quarterly_ends, annual_ends = set(), set()
    for rows in statements.values():
        for _, tags in rows:
            for tag in tags:
                quarterly_ends.update(key[0] for key in _eligible_records(
                    facts, tag, cutoff, quarterly_spans, (), period_floor=period_floor))
                annual_ends.update(key[0] for key in _eligible_records(
                    facts, tag, cutoff, (_SPANS["annual"],), _ANNUAL_FORMS, period_floor=period_floor))
    allowed_quarters = set(sorted(quarterly_ends)[-12:])
    allowed_annual = set(sorted(annual_ends)[-5:])
    selected = {}
    peer_gaps = []
    ambiguous_security_metrics = set()
    for rows in statements.values():
        for metric, tags in rows:
            try:
                tolerance = {}
                if peer_revenue_definitions and metric in _PEER_CONSUMED_METRICS:
                    tolerance = {"ambiguity": "exclude", "excluded": peer_gaps,
                                 "exclude_before": _peer_exclusion_floor(facts, tags, cutoff, quarterly_spans,
                                                                         allowed_quarters, period_floor)}
                quarter = _as_of_records(facts, tags, as_of_date, quarterly_spans,
                                         allowed_ends=allowed_quarters, period_floor=period_floor, **tolerance)
                annual = _as_of_records(facts, tags, as_of_date, (_SPANS["annual"],), _ANNUAL_FORMS,
                                        allowed_ends=allowed_annual, period_floor=period_floor, **tolerance)
            except VendorUnavailableError as exc:
                ambiguity = re.fullmatch(
                    r"SEC (?:period or unit|fact) ambiguous for .+ at (\d{4}-\d{2}-\d{2})",
                    str(exc),
                )
                if (peer_revenue_definitions and ambiguity
                        and metric not in _PEER_CONSUMED_METRICS):
                    peer_gaps.append(f"{metric} ambiguous at {ambiguity.group(1)}; not used for peer statistics")
                    continue
                if metric in identity_metrics:
                    quarter, annual = {}, {}
                    ambiguous_identity.add(metric)
                elif not metric.startswith("Unclassified Marketable Securities ["):
                    raise
                else:
                    quarter, annual = {}, {}
                    ambiguous_security_metrics.add(metric)
            selected[metric] = (quarter, annual)
    sources, records = {}, {}

    def instants(metric, end):
        return [v for (when, _), v in selected.get(metric, ({}, {}))[0].items() if when == end and "start" not in v]

    asset_ends = [end for (end, _), v in selected.get("Total Assets", ({}, {}))[0].items()
                  if end in allowed_quarters and "start" not in v]
    balance_end = max(asset_ends) if asset_ends else None
    outside_interests = balance_end is not None and any(
        instants(metric, balance_end) for metric in identity_metrics - {LIABILITIES_AND_EQUITY, TOTAL_EQUITY})
    no_total_liabilities = balance_end is not None and not instants("Total Liabilities", balance_end)
    keep_identity = (outside_interests or no_total_liabilities) and not ambiguous_identity
    for metric, (quarter, annual) in selected.items():
        if metric in identity_metrics:
            # Only the latest balance date, and only for a filer whose balance sheet needs these rows.
            if not keep_identity:
                continue
            quarter, annual = {key: v for key, v in quarter.items() if key[0] == balance_end and "start" not in v}, {}
            if not quarter:
                continue
        picked = [v for (end, _), v in quarter.items() if end in allowed_quarters]
        picked += [v for (end, _), v in annual.items() if end in allowed_annual]
        if not picked and metric.startswith("Unclassified Marketable Securities [") and metric not in ambiguous_security_metrics:
            continue  # Absence is unavailable, not five extra empty candidate metrics.
        if not picked:
            identity = hashlib.sha256(f"{cik}:{as_of_date}:{metric}:missing".encode()).hexdigest()
            records[identity] = FinancialFact(fact_id=identity, metric=metric, value=None, unit="unknown",
                cik=cik, period_end=cutoff, as_of=cutoff, locator="Selected US-GAAP tags",
                missing_reason=("Ambiguous securities candidate in selected periods"
                                if metric in ambiguous_security_metrics else
                                "No usable consolidated fact in the selected tags and periods"))
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
    # NetIncomeLoss is the direct parent-income tag. When absent, retain the
    # separate consolidated/NCI values and bridge only one exact filing vintage.
    direct_periods = {
        (fact.period_start, fact.period_end)
        for fact in records.values()
        if fact.metric == "Net Income" and fact.value is not None
    }
    profits = [fact for fact in records.values()
               if fact.metric == "Consolidated Profit (Loss)" and fact.value is not None]
    nci_facts = [fact for fact in records.values()
                 if fact.metric == "Net Income Attributable to Noncontrolling Interests"
                 and fact.value is not None]
    bridged = False
    for profit in profits:
        if (profit.period_start, profit.period_end) in direct_periods:
            continue
        for nci in nci_facts:
            if (profit.period_start, profit.period_end) != (nci.period_start, nci.period_end):
                continue
            try:
                derived = derive_parent_net_income(
                    profit, nci, sources[profit.source_ids[0]],
                    sources[nci.source_ids[0]],
                )
            except ValueError:
                continue
            records[derived.fact_id] = derived
            bridged = True
            break
    # A filer that tags only consolidated profit and has never tagged a noncontrolling interest: the profit is
    # the parent's income.
    def other_owner(tag):
        # A nonzero noncontrolling figure for any period ending in the three years before the cutoff.
        floor = str(int(str(cutoff)[:4]) - 3) + str(cutoff)[4:]
        return any(row.get("val") and floor <= str(row.get("end", "")) <= str(cutoff)
                   for rows in ((facts.get(tag) or {}).get("units") or {}).values() for row in rows)

    if not any(f.value for f in nci_facts) and not any(
            other_owner(tag) for tag in ("NetIncomeLossAttributableToNoncontrollingInterest", "MinorityInterest")):
        from tradingagents.dataflows.financial_evidence import derive_profit_as_parent_income
        for profit in profits:
            if (profit.period_start, profit.period_end) in direct_periods:
                continue
            try:
                derived = derive_profit_as_parent_income(profit, tuple(records.values()))
            except ValueError:
                continue
            records[derived.fact_id] = derived
            bridged = True
    if bridged:
        # A value with exact source lineage supersedes the generic missing row.
        records.pop(hashlib.sha256(
            f"{cik}:{as_of_date}:Net Income:missing".encode()
        ).hexdigest(), None)
    if keep_identity and no_total_liabilities:
        derived = _derived_total_liabilities(data, records, balance_end, derive_total_liabilities)
        if derived is not None:
            records[derived.fact_id] = derived
            records.pop(hashlib.sha256(f"{cik}:{as_of_date}:Total Liabilities:missing".encode()).hexdigest(), None)
    if not sources:
        raise NoMarketDataError(ticker, ticker, f"no statement evidence filed by {as_of_date}")
    return add_period_calculations(EvidencePackage(cik=cik, as_of=cutoff, facts=tuple(records.values()), sources=tuple(sources.values()),
        warnings=("Companyfacts coverage excludes issuer-specific narrative and untagged disclosures; this is not a complete financial validation.",
                  *peer_gaps)))


def _displayed_current_balance(block: str, label: str) -> Decimal | None:
    """Read the first balance-sheet column only, inside current assets."""
    area = re.search(r"\bCurrent assets:\s*(.*?)\bTotal current assets\b", block, re.I | re.S)
    if area is None:
        return None
    match = re.search(
        rf"(?:^|;)\s*{re.escape(label)}\s*\|\s*(?:\$\s*\|\s*)?([\d,]+)\b",
        area.group(1), re.I,
    )
    return Decimal(match.group(1).replace(",", "")) if match else None


def confirm_current_marketable_securities(package, corpus):
    """Classify one sourced balance only when companyfacts and the retained
    primary balance sheet agree. No fetch occurs here; ambiguity stays absent.
    """
    from tradingagents.dataflows.financial_evidence import (
        EvidencePackage,
        FinancialFact,
        SourceRecord,
    )

    if not any(f.metric == "Current Marketable Securities" or
               f.metric.startswith("Unclassified Marketable Securities [") for f in package.facts):
        return package  # Unrelated packages retain their existing validation path.
    # A replay may carry an old classification. Always derive it again from the
    # retained raw aliases and currently validated corpus.
    # A figure established from the filing's own declared current-assets sum is not a replayed classification.
    def structural(f):
        return bool(f.source_ids) and all(i.startswith("sec-instance-") for i in f.source_ids)
    stale = tuple(f for f in package.facts if f.metric == "Current Marketable Securities" and not structural(f))
    if len(stale) != sum(f.metric == "Current Marketable Securities" for f in package.facts):
        return package
    original = tuple(f for f in package.facts if f.metric != "Current Marketable Securities")
    used_sources = {sid for fact in original for sid in fact.source_ids}
    stale_source_ids = {sid for fact in stale for sid in fact.source_ids}
    package = EvidencePackage.model_validate(package.model_dump() | {
        "facts": original,
        "sources": tuple(s for s in package.sources
                         if s.source_id not in stale_source_ids or s.source_id in used_sources),
    })
    if corpus is None or corpus.cik != package.cik or corpus.as_of != package.as_of:
        return package
    cashes = [f for f in package.facts if f.metric == "Cash and Equivalents"
              and f.value is not None and f.period_start is None and f.unit == "USD"]
    if not cashes:
        return package
    end = max(f.period_end for f in cashes)
    cashes = [f for f in cashes if f.period_end == end]
    candidates = [f for f in package.facts if f.metric.startswith("Unclassified Marketable Securities [")
                  and f.value is not None and f.period_start is None and f.period_end == end]
    if any(f.missing_reason and f.missing_reason.startswith("Ambiguous securities candidate")
           for f in package.facts):
        return package
    if len(cashes) != 1 or not candidates or len({f.value for f in candidates}) != 1:
        return package
    cash = cashes[0]
    sources = {s.source_id: s for s in package.sources}
    if any(f.unit != "USD" or f.basis != cash.basis or len(f.source_ids) != 1
           for f in candidates) or len(cash.source_ids) != 1:
        return package
    cash_source = sources[cash.source_ids[0]]
    candidate_sources = [sources[f.source_ids[0]] for f in candidates]
    def vintage(s):
        return (s.cik, s.filed_date, s.accession, s.form, s.content_hash)
    if not cash_source.accession or any(vintage(s) != vintage(cash_source)
                                        for s in candidate_sources):
        return package
    matching_docs = [d for d in corpus.documents
                     if d.filing.cik == package.cik and d.filing.report_date == end
                     and d.filing.accession == cash_source.accession
                     and d.filing.filed_date == cash_source.filed_date
                     and d.filing.form in {"10-Q", "10-K"}
                     and d.filing.url == d.url and d.content_hash]
    if len(matching_docs) != 1:
        return package
    doc = matching_docs[0]
    presentations = []
    for index, block in enumerate(doc.blocks):
        preceding = doc.blocks[max(0, index - 3):index]
        if len(preceding) != 3 or (
            preceding[0].text.strip().upper() != "CONDENSED CONSOLIDATED BALANCE SHEETS"
            or preceding[1].text.strip().lower() != "(in thousands, except share amounts)"
            or preceding[2].text.strip().lower() != "(unaudited)"
        ):
            continue
        displayed_date = f"{end.strftime('%B')} {end.day}, {end.year}"
        first_column = re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", block.text)
        if (block.truncated or block.currency != "USD" or first_column is None
                or first_column.group(0) != displayed_date):
            continue
        displayed_cash = _displayed_current_balance(block.text, "Cash and cash equivalents")
        displayed_security = _displayed_current_balance(block.text, "Marketable securities")
        if displayed_cash and displayed_security and displayed_cash * 1000 == cash.value:
            presentations.append((block, preceding, displayed_security * 1000))
    if len(presentations) != 1 or presentations[0][2] != candidates[0].value:
        return package
    block, heading, _ = presentations[0]
    table_locator = f"{heading[0].locator}; {heading[1].locator}; {block.locator}"
    selected = next(f for tag in _SECURITY_CANDIDATES for f in candidates
                    if f.metric == f"Unclassified Marketable Securities [{tag}]")
    doc_source = SourceRecord(
        source_id=doc.source_id, cik=package.cik, url=doc.url,
        filed_date=doc.filing.filed_date, retrieved_at=doc.retrieved_at,
        content_hash=doc.content_hash, locator="document",
        accession=doc.filing.accession, form=doc.filing.form,
    )
    identity = hashlib.sha256(f"current-marketable:{selected.fact_id}:{doc.source_id}:{block.locator}".encode()).hexdigest()
    confirmed = FinancialFact(
        fact_id=identity, metric="Current Marketable Securities", value=selected.value,
        unit="USD", cik=package.cik, period_end=end, as_of=package.as_of,
        source_ids=(selected.source_ids[0], doc.source_id),
        locator=f"{selected.locator}; {table_locator}",
    )
    prior = next((s for s in package.sources if s.source_id == doc_source.source_id), None)
    if prior is not None and prior != doc_source:
        return package
    return EvidencePackage.model_validate(package.model_dump() | {
        "sources": (*package.sources, *((doc_source,) if prior is None else ())),
        "facts": (*package.facts, confirmed),
    })
