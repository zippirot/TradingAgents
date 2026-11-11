"""Recompute newly passing checks from the filing as a person reads it, without the readers' inputs or choices.

The readers under test use SEC's extracted instance (``*_htm.xml``) and SEC's resolved structure file
(``MetaLinks.json``), their own table of borrowing tags, and each tag's balance type for signs. This tool
uses none of those:

  figures      the primary filing document: each tagged number as printed (text and scale), negative when it
               is printed in parentheses or with a minus sign;
  structure    the filing's own linkbase files (``*_cal.xml`` / ``*_pre.xml``, or the schema that embeds
               them), read with this file's parser;
  borrowings   this file's own name rule, stated below.

It then redoes three sums:

  liabilities  the leaves of the filer's declared liabilities sum, at printed figures, add up to printed
               total liabilities; the lines this tool calls borrowings add up to the borrowings the reader used;
  equity       printed opening equity plus each printed movement equals printed closing equity, for every
               component the reader reconciled, using only printed signs; every movement the reader used is
               listed in the filing's statement of equity;
  financing    the leaves of the declared financing sum, at printed signed figures, add up to the printed
               total; this tool's own name rule finds no equipment-financing line where the reader said none.

What it still takes from the reader: which components and movements were reconciled for equity (it checks
their membership and arithmetic, it does not search for a reconciliation itself).

Usage: PYTHONPATH=<repo> python recheck.py <store> <as-of> TICKER [TICKER ...]
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
_OPEN = re.compile(r"<ix:nonFraction\b([^>]*)>", re.I)
_CLOSE = re.compile(r"</ix:nonFraction>", re.I)
_CONTEXT = re.compile(r"<xbrli:context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</xbrli:context>", re.S | re.I)
_ATTR = re.compile(r"([\w:-]+)=\"([^\"]*)\"")
_TAGS = re.compile(r"<[^>]+>")
# This tool's own rule for a borrowing line, by name. Not the readers' table.
_BORROWING = re.compile(r"Debt|Borrowings|CommercialPaper|NotesPayable|NotesAndLoans|LineOfCredit|LinesOfCredit|"
                        r"ConvertibleNotes|SeniorNotes|LoansPayable", re.I)
_NOT_BORROWING = re.compile(r"OperatingLease|^FinanceLeaseLiabilit|Deferred|Interest|Tax|Derivative|Securities", re.I)
_EQUIPMENT = re.compile(r"Equipment|FinancingObligation|FinancingArrangement|VendorFinanc|SupplierFinanc", re.I)
_EQUITY_SIDE = re.compile(r"StockholdersEquity|MinorityInterest|PartnersCapital|MembersEquity|Commitments|"
                          r"TemporaryEquity|Redeemable|Mezzanine", re.I)


def printed(html: str):
    """{(concept, start, end, dimensions): printed value}: magnitude from the text, sign from how it is printed."""
    contexts = {}
    for name, body in _CONTEXT.findall(html):
        instant = re.search(r"<xbrli:instant>([^<]+)<", body)
        start, end = re.search(r"<xbrli:startDate>([^<]+)<", body), re.search(r"<xbrli:endDate>([^<]+)<", body)
        members = tuple(sorted(re.findall(r"<xbrldi:explicitMember[^>]*dimension=\"([^\"]+)\"[^>]*>([^<]+)<", body)))
        typed = bool(re.search(r"<xbrldi:typedMember", body))
        contexts[name] = ((None, instant.group(1).strip()) if instant else (start.group(1).strip(), end.group(1).strip()),
                          members + ((("typed", "typed"),) if typed else ()))
    values = {}
    for match in _OPEN.finditer(html):
        close = _CLOSE.search(html, match.end())
        attrs = dict(_ATTR.findall(match.group(1)))
        if close is None or attrs.get("contextRef") not in contexts or "usd" not in (attrs.get("unitRef") or "").lower():
            continue
        text = _TAGS.sub("", html[match.end():close.start()]).strip()
        style = attrs.get("format", "")
        if "zerodash" in style or "fixed-zero" in style or text in ("—", "-", "–", ""):
            number = Decimal(0)
        else:
            digits = text.replace("\xa0", "").replace(" ", "")
            digits = digits.replace(".", "").replace(",", ".") if "comma-decimal" in style else digits.replace(",", "")
            try:
                number = Decimal(digits.strip("()$-−"))
            except Exception:  # noqa: BLE001 - a figure this tool cannot read is simply not compared
                continue
        number *= Decimal(10) ** int(attrs.get("scale") or 0)
        # Printed sign: what stands just before the number once markup is removed.
        before = _TAGS.sub("", html[max(0, match.start() - 400):match.start()]).replace("\xa0", " ").replace("$", "").rstrip()
        if before.endswith(("(", "-", "−", "–")) or text.startswith(("(", "-", "−")):
            number = -number
        (start, end), dimensions = contexts[attrs["contextRef"]]
        key = (attrs.get("name"), start, end, dimensions)
        known = values.get(key)
        # A figure repeated in running text at coarser rounding: keep the one with more significant digits.
        if known is None or len(str(abs(number).normalize().as_tuple().digits)) > len(str(abs(known).normalize().as_tuple().digits)):
            values[key] = number
    return values


def figure(values, concept, start, end, dimensions=()):
    """The printed figure, or the sum of one axis's members when the line is printed only split that way."""
    if (concept, start, end, dimensions) in values:
        return values[(concept, start, end, dimensions)]
    if dimensions:
        return None
    split = {}
    for (name, s, e, dims), number in values.items():
        if (name, s, e) == (concept, start, end) and len(dims) == 1:
            split.setdefault(dims[0][0], []).append(number)
    return sum(next(iter(split.values())), Decimal(0)) if len(split) == 1 else None


def linkbase(raw: str, kind: str):
    """{role: {parent: [(child, weight)]}} from a calculation or presentation linkbase, by this file's own reading."""
    roles = {}
    for role, body in re.findall(rf"<link:{kind}Link\b[^>]*xlink:role=\"([^\"]+)\"[^>]*>(.*?)</link:{kind}Link>", raw, re.S):
        labels = {}
        for attributes in re.findall(r"<link:loc\b([^>]*)/?>", body):
            attrs = dict(_ATTR.findall(attributes))
            fragment = attrs.get("xlink:href", "").rsplit("#", 1)[-1]
            prefix, _, name = fragment.partition("_")
            labels[attrs.get("xlink:label")] = f"{prefix}:{name}"
        tree = roles.setdefault(role, {})
        for attributes in re.findall(rf"<link:{kind}Arc\b([^>]*)/?>", body):
            attrs = dict(_ATTR.findall(attributes))
            parent, child = labels.get(attrs.get("xlink:from")), labels.get(attrs.get("xlink:to"))
            if parent and child:
                tree.setdefault(parent, []).append((child, Decimal(attrs.get("weight", "1"))))
    return roles


def leaves(tree, values, root, start, end):
    """Declared leaves under ``root`` with a printed figure, each with its accumulated weight."""
    out = []

    def walk(concept, weight):
        children = [(c, w) for c, w in tree.get(concept, ()) if figure(values, c, start, end) is not None or c in tree]
        if tree.get(concept) and figure(values, concept, start, end) is not None and children:
            for child, w in tree[concept]:
                walk(child, weight * w)
        elif figure(values, concept, start, end) is not None:
            out.append((concept, weight, figure(values, concept, start, end)))

    walk(root, Decimal(1))
    return out


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
            facts = package["facts"]
            filed = next((s for s in package["sources"] if s["source_id"].startswith("sec-instance-")), None)
            row = {"ticker": ticker}
            if filed is None:
                out.append({**row, "note": "no filed-instance facts were used"})
                continue
            base, instance_name = filed["url"].rsplit("/", 1)
            stem = instance_name[:-len("_htm.xml")]
            names = [item["name"] for item in json.loads(store.get(f"{base}/index.json").content)["directory"]["item"]]
            html = store.get(f"{base}/{stem}.htm").content.decode("utf-8", "replace")
            row["document"] = base.rsplit("/", 1)[-1] + "/" + stem + ".htm"
            row["sha256"] = hashlib.sha256(store.get(f"{base}/{stem}.htm").content).hexdigest()[:16]

            def linkbase_text(suffix, names=names, base=base):
                name = next((n for n in names if n.endswith(suffix)), None) or next(n for n in names if n.endswith(".xsd"))
                return store.get(f"{base}/{name}").content.decode("utf-8", "replace")

            calc, shown_in = linkbase(linkbase_text("_cal.xml"), "calculation"), linkbase(linkbase_text("_pre.xml"), "presentation")
            row["structure_from"] = next((n for n in names if n.endswith("_cal.xml")), "schema with embedded linkbases")
            values = printed(html)
            end = max(f["period_end"] for f in facts if f["metric"] == "Total Assets" and f["value"] is not None)

            # ---- liabilities
            tree = next((t for t in calc.values() if "us-gaap:Liabilities" in t and figure(values, "us-gaap:Liabilities", None, end) is not None), None)
            if tree is not None:
                lines, total = leaves(tree, values, "us-gaap:Liabilities", None, end), figure(values, "us-gaap:Liabilities", None, end)
                how = "printed total liabilities"
            else:
                tree = next(t for t in calc.values() if "us-gaap:LiabilitiesAndStockholdersEquity" in t)
                lines = [leaf for child, _ in tree["us-gaap:LiabilitiesAndStockholdersEquity"]
                         if not _EQUITY_SIDE.search(child.split(":")[1]) for leaf in leaves(tree, values, child, None, end)]
                equity_side = sum((figure(values, child, None, end) or Decimal(0)) for child, _ in tree["us-gaap:LiabilitiesAndStockholdersEquity"]
                                  if _EQUITY_SIDE.search(child.split(":")[1]))
                total = figure(values, "us-gaap:LiabilitiesAndStockholdersEquity", None, end) - equity_side
                how = "printed liabilities-and-equity total less the printed equity-side lines"
            summed = sum((weight * number for _, weight, number in lines), Decimal(0))
            mine = sum((weight * number for concept, weight, number in lines
                        if _BORROWING.search(concept.split(":")[1]) and not _NOT_BORROWING.search(concept.split(":")[1])), Decimal(0))
            used = next((Decimal(str(f["value"])) for f in facts if f["metric"].startswith("Total Borrowings")
                         and f.get("formula_id") == "face_borrowings_v1"), None)
            reader_total = next((Decimal(str(f["value"])) for f in facts if f["metric"] == "Total Liabilities"
                                 and f["period_end"] == end and f["value"] is not None), None)
            row["liabilities"] = {"total_is": how, "printed_lines": {c: str(w * n) for c, w, n in lines},
                                  "printed_sum": str(summed), "printed_total": str(total), "adds_up": summed == total,
                                  "equals_reader_total": total == reader_total,
                                  "borrowings_by_this_tool": str(mine), "borrowings_reader_used": str(used),
                                  "borrowings_agree": used is None or mine == used}

            # ---- equity
            closings = [f for f in facts if f["metric"].startswith("Equity Closing [") and f["period_end"] == end]
            moves = [f for f in facts if f["metric"].startswith("Equity Movement [") and f["period_end"] == end]
            if closings and moves:
                start = moves[0]["period_start"]
                rounding = next(Decimal(str(f["value"])) for f in facts if f["metric"] == "Equity Reconciliation Rounding")
                listed = {child for role, t in shown_in.items() if re.search(r"equity|deficit|capital", role, re.I)
                          and not re.search(r"balancesheet|financialposition|parenthetical", role, re.I)
                          for children in t.values() for child, _ in children}
                ok, detail, unlisted = True, [], set()
                for closing in closings:
                    label = closing["metric"][16:-1]
                    opening = next(f for f in facts if f["metric"] == f"Equity Opening [{label}]")
                    dims = () if label == "total" else (("us-gaap:StatementEquityComponentsAxis", label),)
                    first = figure(values, opening["locator"].split(" at ")[0], None, opening["period_end"], dims)
                    last = figure(values, closing["locator"].split(" at ")[0], None, end, dims)
                    total, count = first if first is not None else Decimal("NaN"), 0
                    for move in moves:
                        concept, member, where = move["metric"][17:-1].split(" | ")
                        if member != label:
                            continue
                        if concept not in listed:
                            unlisted.add(concept)
                        number = None
                        if label == "total" and where != "total column":
                            for (name, s, e, d), candidate in values.items():
                                if (name, s, e) == (concept, start, end) and len(d) == 1 and d[0][1] == where:
                                    number = candidate
                        else:
                            number = values.get((concept, start, end, dims))
                        total += number if number is not None else Decimal("NaN")       # printed sign only
                        count += 1
                    closes = last is not None and total.is_finite() and abs(total - last) <= rounding * (count + 2) / 2
                    ok &= closes
                    detail.append({"component": label.split(":")[-1], "printed_opening": str(first), "movements": count,
                                   "opening_plus_printed_movements": str(total), "printed_closing": str(last), "closes": closes})
                row["equity"] = {"period": f"{start} to {end}", "closes_on_printed_signs": ok,
                                 "movements_not_listed_in_the_statement": sorted(unlisted), "components": detail}

            # ---- financing
            flows = [f for f in facts if f["metric"].startswith("Cash Flow Financing Line [") and f["period_end"] == end]
            if flows:
                start = flows[0]["period_start"]
                root = next((c for c in ("us-gaap:NetCashProvidedByUsedInFinancingActivities",
                                         "us-gaap:NetCashProvidedByUsedInFinancingActivitiesContinuingOperations")
                             if figure(values, c, start, end) is not None and any(c in t for t in calc.values())), None)
                tree = next(t for t in calc.values() if root in t)
                lines = leaves(tree, values, root, start, end)
                # Printed figures already carry the cash sign a reader sees, so they are added as printed.
                summed, total = sum((number for _, _, number in lines), Decimal(0)), figure(values, root, start, end)
                equipment = sorted(c for c, _, _ in lines if _EQUIPMENT.search(c.split(":")[1]))
                row["financing"] = {"period": f"{start} to {end}", "printed_lines": {c: str(n) for c, _, n in lines},
                                    "printed_sum": str(summed), "printed_total": str(total), "adds_up": summed == total,
                                    "equipment_like_lines_by_this_tool": equipment}
            out.append(row)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
