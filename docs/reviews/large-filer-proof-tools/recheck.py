"""Recompute newly passing checks from the figures printed in the filing document itself.

The readers under test use SEC's extracted XBRL instance (``*_htm.xml``). This tool does not. It reads the
primary filing document (the HTML a person reads), takes each tagged figure as displayed (text, scale and
sign), and redoes the three sums with its own arithmetic:

  liabilities   the liability lines the package holds, at the displayed figures, add up to total liabilities,
                and the borrowing lines add up to the borrowings used;
  equity        opening equity plus each displayed movement, signed as the package signed it, equals closing;
  financing     the displayed financing lines add up to financing cash flow for the period.

Usage: PYTHONPATH=<repo> python recheck.py <store> <as-of> TICKER [TICKER ...]
Raw filings stay in the private store; only the comparison is printed.
"""
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
# One displayed number can carry several tags, nested (the same figure for two dates). Each opening tag is
# read with the text up to the next closing tag, so a nested tag and its parent both get the figure.
_OPEN = re.compile(r"<ix:nonFraction\b([^>]*)>", re.I)
_CLOSE = re.compile(r"</ix:nonFraction>", re.I)


def _tagged(html):
    for match in _OPEN.finditer(html):
        close = _CLOSE.search(html, match.end())
        if close is not None:
            yield match.group(1), html[match.end():close.start()]
_CONTEXT = re.compile(r"<xbrli:context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</xbrli:context>", re.S | re.I)
_ATTR = re.compile(r"([\w:-]+)=\"([^\"]*)\"")


def displayed(html: str):
    """{(concept, start, end, dimensions): set of displayed values} from the inline document."""
    contexts = {}
    for name, body in _CONTEXT.findall(html):
        instant = re.search(r"<xbrli:instant>([^<]+)<", body)
        start, end = re.search(r"<xbrli:startDate>([^<]+)<", body), re.search(r"<xbrli:endDate>([^<]+)<", body)
        members = tuple(sorted(re.findall(r"<xbrldi:explicitMember[^>]*dimension=\"([^\"]+)\"[^>]*>([^<]+)<", body)))
        typed = bool(re.search(r"<xbrldi:typedMember", body))
        contexts[name] = ((None, instant.group(1).strip()) if instant else (start.group(1).strip(), end.group(1).strip()),
                          members + ((("typed", "typed"),) if typed else ()))
    values = {}
    for attributes, inner in _tagged(html):
        attrs = dict(_ATTR.findall(attributes))
        if attrs.get("contextRef") not in contexts or "usd" not in (attrs.get("unitRef") or "").lower():
            continue
        text = re.sub(r"<[^>]+>", "", inner).strip()
        style = attrs.get("format", "")
        if "zerodash" in style or "fixed-zero" in style or text in ("—", "-", "–"):
            number = Decimal(0)
        else:
            digits = text.replace("\xa0", "").replace(" ", "")
            digits = digits.replace(".", "").replace(",", ".") if "comma-decimal" in style else digits.replace(",", "")
            try:
                number = Decimal(digits.strip("()$"))
            except Exception:  # noqa: BLE001 - a figure this tool cannot read is simply not compared
                continue
        number *= Decimal(10) ** int(attrs.get("scale") or 0)
        if attrs.get("sign") == "-":
            number = -number
        (start, end), dimensions = contexts[attrs["contextRef"]]
        values.setdefault((attrs.get("name"), start, end, dimensions), set()).add(number)
    return values


def one(values, concept, start, end, dimensions=()):
    """The displayed figure, or the sum of one axis's members when the line is shown only split that way."""
    found = values.get((concept, start, end, dimensions))
    if found:
        return max(found, key=lambda v: len(str(v.normalize())))       # the least rounded repeat
    split = {}
    for (name, s, e, dims), figures in values.items():
        if (name, s, e) == (concept, start, end) and len(dims) == 1:
            split.setdefault(dims[0][0], []).append(max(figures, key=lambda v: len(str(v.normalize()))))
    return sum(next(iter(split.values())), Decimal(0)) if len(split) == 1 else None


def main(store_dir, as_of, tickers):
    import requests

    spec = importlib.util.spec_from_file_location("scorer", REPO / "scripts" / "large_filer_score.py")
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    from tradingagents.agents.evidence_validation import create_source_acquisition
    from tradingagents.dataflows.config import get_config, set_config

    store = scorer.Store(store_dir)
    requests.get = scorer.Transport(store)
    out = []
    with tempfile.TemporaryDirectory() as scratch:
        set_config({**get_config(), "data_cache_dir": scratch})
        for ticker in tickers:
            update = create_source_acquisition(["fundamentals"])(
                {"company_of_interest": ticker, "trade_date": as_of, "asset_type": "stock"})
            package = update["financial_evidence"]
            facts, sources = package["facts"], {s["source_id"]: s for s in package["sources"]}
            filed = next((s for s in sources.values() if s["source_id"].startswith("sec-instance-")), None)
            row = {"ticker": ticker}
            if filed is None:
                out.append({**row, "note": "no filed-instance facts were used"})
                continue
            primary = filed["url"].replace("_htm.xml", ".htm")
            html = store.get(primary).content.decode("utf-8", "replace")
            row["document"] = primary.rsplit("/", 2)[-2] + "/" + primary.rsplit("/", 1)[-1]
            row["sha256"] = hashlib.sha256(store.get(primary).content).hexdigest()[:16]
            shown = displayed(html)
            end = max(f["period_end"] for f in facts if f["metric"] == "Total Assets" and f["value"] is not None)

            def held(prefix, facts=facts):
                return [f for f in facts if f["metric"].startswith(prefix) and f["value"] is not None]

            # liabilities
            lines = [f for f in held("Balance Sheet Liability [") if f["period_end"] == end]
            if lines:
                def shown_or_nan(value):
                    return Decimal("NaN") if value is None else value

                total = sum(shown_or_nan(one(shown, f["metric"][25:-1], None, end)) for f in lines)
                stated = next((Decimal(str(f["value"])) for f in facts if f["metric"] == "Total Liabilities"
                               and f["period_end"] == end and f["value"] is not None), None)
                borrow = next((f for f in facts if f["metric"].startswith("Total Borrowings") and f.get("formula_id") == "face_borrowings_v1"), None)
                by_id = {f["fact_id"]: f for f in facts}
                from tradingagents.dataflows.face_liabilities import classify
                debt = sum(shown_or_nan(one(shown, by_id[i]["metric"][25:-1], None, end)) for i in (borrow or {}).get("input_fact_ids", ())[1:]
                           if classify(by_id[i]["metric"][25:-1]).startswith("borrowing")) if borrow else None
                missing = [f["metric"][25:-1] for f in lines if one(shown, f["metric"][25:-1], None, end) is None]
                row["liabilities"] = {"lines": len(lines), "not_displayed": missing,
                                      "displayed_lines": {f["metric"][25:-1]: str(one(shown, f["metric"][25:-1], None, end))
                                                          for f in lines},
                                      "displayed_sum": str(total), "total_liabilities": str(stated),
                                      "adds_up": total == stated, "displayed_borrowings": str(debt),
                                      "borrowings_used": str(Decimal(str(borrow["value"]))) if borrow else None,
                                      "borrowings_agree": debt == Decimal(str(borrow["value"])) if borrow else None}
            # equity
            closings = [f for f in held("Equity Closing [") if f["period_end"] == end]
            moves = [f for f in held("Equity Movement [") if f["period_end"] == end]
            if closings and moves:
                start = moves[0]["period_start"]
                rounding = next(Decimal(str(f["value"])) for f in facts if f["metric"] == "Equity Reconciliation Rounding")
                ok, detail = True, []
                for closing in closings:
                    label = closing["metric"][16:-1]
                    opening = next(f for f in facts if f["metric"] == f"Equity Opening [{label}]")
                    dims = () if label == "total" else (("us-gaap:StatementEquityComponentsAxis", label),)
                    concept_open, concept_close = opening["locator"].split(" at ")[0], closing["locator"].split(" at ")[0]
                    first = one(shown, concept_open, None, opening["period_end"], dims)
                    last = one(shown, concept_close, None, end, dims)
                    total, count = first if first is not None else Decimal("NaN"), 0
                    for move in moves:
                        concept, member, where = move["metric"][17:-1].split(" | ")
                        if member != label:
                            continue
                        sign = 1 if "adds to" in move["locator"] else -1
                        mdims = dims if where == "total column" or label != "total" else None
                        figure = None
                        if mdims is None:      # split along another axis: find the one displayed fact with that member
                            for (name, s, e, d), figures in shown.items():
                                if (name, s, e) == (concept, start, end) and len(d) == 1 and d[0][1] == where:
                                    figure = max(figures, key=lambda v: len(str(v.normalize())))
                        else:
                            figure = one(shown, concept, start, end, mdims)
                        total += sign * (figure if figure is not None else Decimal("NaN"))
                        count += 1
                    closes = last is not None and total.is_finite() and abs(total - last) <= rounding * (count + 2) / 2
                    ok &= closes
                    detail.append({"component": label.split(":")[-1], "opening": str(first), "movements": count,
                                   "computed_closing": str(total), "displayed_closing": str(last), "closes": closes})
                row["equity"] = {"period": f"{start} to {end}", "closes": ok, "components": detail}
            # financing
            flows = [f for f in held("Cash Flow Financing Line [") if f["period_end"] == end]
            if flows:
                start = flows[0]["period_start"]
                # each line's displayed magnitude takes the sign the package recorded for it as cash
                total = Decimal(0)
                for f in flows:
                    figure = one(shown, f["metric"][26:-1], start, end)
                    signed = Decimal(str(f["value"]))
                    total += (abs(figure) if signed >= 0 else -abs(figure)) if figure is not None else Decimal("NaN")
                    if figure is not None and abs(figure) != abs(signed):
                        total = Decimal("NaN")
                stated = one(shown, "us-gaap:NetCashProvidedByUsedInFinancingActivities", start, end)
                if stated is None:
                    stated = one(shown, "us-gaap:NetCashProvidedByUsedInFinancingActivitiesContinuingOperations", start, end)
                row["financing"] = {"period": f"{start} to {end}", "lines": len(flows),
                                    "signed_lines": {f["metric"][26:-1]: str(f["value"]) for f in flows},
                                    "displayed_sum": str(total),
                                    "displayed_total": str(stated), "adds_up": total == stated}
            out.append(row)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
