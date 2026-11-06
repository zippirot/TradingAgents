"""Retained analyst tool outputs for advisory review, never accepted financial facts."""
import hashlib
import json
import re
from collections.abc import Mapping

AUDIT_TOOL_FIELDS = {
    "market": "audit_market_tool_evidence",
    "social": "audit_social_tool_evidence",
    "news": "audit_news_tool_evidence",
    "fundamentals": "audit_fundamentals_tool_evidence",
}
MAX_RECORDS = 16
MAX_TEXT = 20000


def _text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _excerpt(text, cap):
    if len(text) <= cap:
        return text
    marker = "\n[... middle omitted from advisory review ...]\n"
    remaining = max(0, cap - len(marker))
    first = remaining // 2
    return text[:first] + marker + text[-(remaining-first):] if remaining else marker[:cap]


def retain_tool_outputs(analyst, ticker, trade_date, outputs):
    """Bind excerpts to actual calls/output bytes without claiming provider truth."""
    priority = {"get_verified_market_snapshot": 0, "get_news": 1, "prefetched_news": 1,
                "get_indicators": 2, "get_stock_data": 3}
    indexed = list(enumerate(outputs))
    selected = sorted(indexed, key=lambda pair: (priority.get(pair[1]["name"], 4), pair[0]))[:MAX_RECORDS]
    remaining = MAX_TEXT
    records = []
    for position, (ordinal, item) in enumerate(selected):
        text = _text(item["content"])
        cap = min(6000, remaining if item["name"] == "get_verified_market_snapshot"
                  else remaining // (len(selected)-position))
        excerpt = _excerpt(text, cap)
        remaining -= len(excerpt)
        arguments = _text(item.get("arguments") or {})
        records.append({
            "label": f"TOOL_{analyst.upper()}_{ordinal+1}",
            "tool_name": item["name"], "tool_call_id": str(item.get("tool_call_id") or ""),
            "arguments": arguments[:1000], "arguments_truncated": len(arguments) > 1000,
            "output_sha256": _hash(text), "output_characters": len(text),
            "excerpt": excerpt, "excerpt_sha256": _hash(excerpt),
            "truncated": len(text) != len(excerpt), "status": item.get("status") or "success",
        })
    return {"schema_version": 1, "analyst": analyst, "ticker": ticker, "requested_as_of": trade_date,
            "label": "Recorded analyst tool output, unverified; not accepted financial evidence",
            "records": records, "omitted_outputs": len(outputs)-len(selected),
            "text_cap_characters": MAX_TEXT}


def collect_tool_outputs(state, analyst):
    """Read only model-issued call arguments and matching tool responses."""
    calls, outputs = {}, []
    for message in state.get("messages") or []:
        for call in getattr(message, "tool_calls", None) or []:
            if isinstance(call, Mapping) and isinstance(call.get("id"), str):
                calls[call["id"]] = call
        call_id = getattr(message, "tool_call_id", None)
        if call_id is None:
            continue
        call = calls.get(call_id)
        if call is None:
            continue
        outputs.append({"name": str(call.get("name") or "unknown"), "arguments": call.get("args") or {},
                        "tool_call_id": call_id, "content": message.content,
                        "status": getattr(message, "status", None) or "success"})
    return retain_tool_outputs(analyst, state.get("company_of_interest"), state.get("trade_date"), outputs)


def _validated_rows(state, analyst, field):
    bundle = state.get(field)
    if not isinstance(bundle, Mapping) or (
        bundle.get("schema_version") != 1 or bundle.get("analyst") != analyst
        or bundle.get("ticker") != state.get("company_of_interest")
        or bundle.get("requested_as_of") != state.get("trade_date")
    ):
        return []
    rows = bundle.get("records")
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        return []
    result, labels, used = [], set(), 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        text, label = row.get("excerpt"), row.get("label")
        if (not isinstance(text, str) or len(text) > 6000 or used + len(text) > MAX_TEXT
                or row.get("excerpt_sha256") != _hash(text)
                or not isinstance(label, str) or not re.fullmatch(rf"TOOL_{analyst.upper()}_[0-9]{{1,4}}", label)
                or label in labels):
            continue
        if any(not isinstance(row.get(key), str) or len(row[key]) > cap for key, cap in
               (("tool_name", 128), ("tool_call_id", 128), ("arguments", 1000), ("output_sha256", 64))):
            continue
        if (not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", row["tool_name"])
                or not re.fullmatch(r"[0-9a-f]{64}", row["output_sha256"])
                or row.get("status") not in ("success", "error")
                or type(row.get("output_characters")) is not int
                or not 0 <= row["output_characters"] <= 1000000000
                or type(row.get("truncated")) is not bool
                or type(row.get("arguments_truncated")) is not bool
                or (not row["truncated"] and row["output_sha256"] != row["excerpt_sha256"])):
            continue
        result.append(row)
        used += len(text)
        labels.add(label)
    return result


def known_tool_labels(state):
    """Only code-constructed, valid captured labels; raw feed text adds none."""
    return {row["label"] for analyst, field in AUDIT_TOOL_FIELDS.items()
            for row in _validated_rows(state, analyst, field)}


def render_tool_evidence(state):
    """Bound output text (20k/analyst) and metadata (at most 16 small records)."""
    blocks = []
    for analyst, field in AUDIT_TOOL_FIELDS.items():
        bundle = state.get(field)
        if not isinstance(bundle, Mapping):
            continue
        rows = _validated_rows(state, analyst, field)
        supplied = bundle.get("records")
        supplied_count = len(supplied) if isinstance(supplied, list) else 0
        omitted = bundle.get("omitted_outputs")
        omitted = omitted if type(omitted) is int and 0 <= omitted <= 1000000 else "unknown"
        origin = bundle.get("capture_origin", "Actual analyst messages or prefetched inputs")
        origin = origin[:200] if isinstance(origin, str) else "unknown"
        blocks.append(f"{analyst}: recorded tool outputs, unverified. Origin: {origin}. "
                      f"Omitted outputs: {omitted}; invalid retained records: {supplied_count-len(rows)}. "
                      "Arguments are model-requested or prefetch-requested; tools may clamp dates. "
                      "Served dates/definitions come from the output, not requested arguments. "
                      "Truncated, invalid or missing material is a review limit, not a finding.")
        for row in rows:
            metadata = {key: row[key] for key in
                        ("tool_name", "tool_call_id", "arguments", "arguments_truncated",
                         "output_sha256", "output_characters", "truncated", "status")}
            blocks.append(f"[{row['label']}] " + json.dumps(metadata, ensure_ascii=False) + "\n" + row["excerpt"])
    return "\n\n".join(blocks)


def tool_evidence_coverage(state):
    """Coverage describes inputs, never the truth of an analyst's claims."""
    coverage = {}
    for analyst, field in AUDIT_TOOL_FIELDS.items():
        bundle = state.get(field)
        if not isinstance(bundle, Mapping):
            coverage[analyst] = {"status": "not captured", "records": 0, "truncated": 0, "omitted": 0}
            continue
        rows = _validated_rows(state, analyst, field)
        omitted = bundle.get("omitted_outputs")
        coverage[analyst] = {
            "status": "captured" if rows else "empty or invalid",
            "records": len(rows), "truncated": sum(row["truncated"] for row in rows),
            "omitted": omitted if type(omitted) is int and 0 <= omitted <= 1000000 else 0,
        }
    return coverage
