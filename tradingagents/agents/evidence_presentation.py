"""Presentation-only separation of readable evidence and exact reference IDs."""

import json
import re

REFERENCE_START = "\n\n<!-- evidence-references:start -->\n"
REFERENCE_END = "\n<!-- evidence-references:end -->"
_REFERENCE_BLOCK = re.compile(re.escape(REFERENCE_START) + r"(.*?)" + re.escape(REFERENCE_END), re.S)


def analyst_prose(text: str) -> str:
    """Keep research prose; structured extraction stays in raw diagnostics."""
    return re.sub(
        r"```(?:financial_claims|disclosures|valuation_scenarios|peers)\b[^\n]*\n.*?(?:```|\Z)",
        "", text, flags=re.S,
    ).strip()


def readable_evidence(text: str) -> str:
    """Keep values and limitations; exact references remain in canonical state."""
    rendered = without_reference_appendix(text)
    for label, ident in re.findall(
        r"^- ([SD]\d+): source_id ([^;\n]+);", evidence_references(text), re.M,
    ):
        rendered = rendered.replace(ident, label)
    return rendered


def without_reference_appendix(text: str) -> str:
    """Remove the exact-ID appendix from a display view without changing prose."""
    return _REFERENCE_BLOCK.sub("", text).strip()


def evidence_references(text: str) -> str:
    return "\n\n".join(match.group(1) for match in _REFERENCE_BLOCK.finditer(text))


def fact_reference_labels(text: str) -> dict[str, str]:
    return {
        ident: label
        for label, ident in re.findall(r"^- (F\d+): fact_id (.+)$", evidence_references(text), re.M)
    }


def prompt_reference_map(canonical: str, brief: str, *, fact_ids=(), source_ids=()) -> dict[str, str]:
    """Project exact, retained IDs to prompt labels; canonical references lead."""
    appendix = evidence_references(canonical)
    result = fact_reference_labels(canonical)
    for label, ident in re.findall(r"^- ([SDK]\d+): source_id ([^;\n]+);", appendix, re.M):
        result.setdefault(ident, label)
    allowed_facts, allowed_sources = set(fact_ids), set(source_ids)
    next_fact = max((int(label[1:]) for label in result.values() if re.fullmatch(r"F\d+", label)), default=0)
    next_source = max((int(label[1:]) for label in result.values() if re.fullmatch(r"S\d+", label)), default=0)
    for line in brief.splitlines():
        if line.startswith("{"):
            try:
                item = json.loads(line)
            except ValueError:
                item = None
            if isinstance(item, dict):
                ident = item.get("fact_id")
                if ident in allowed_facts and ident not in result:
                    next_fact += 1
                    result[ident] = f"F{next_fact}"
                identifiers = [*(item.get("source_ids") or ()), item.get("source_id")]
            else:
                identifiers = []
        else:
            identifiers = re.findall(r"\bsource_id[ ;:,]+([A-Za-z0-9_-]+)", line)
        for ident in identifiers:
            if ident in allowed_sources and ident not in result:
                next_source += 1
                result[ident] = f"S{next_source}"
    return result


def prompt_id_view(text: str, references: dict[str, str]) -> str:
    """Substitute exact IDs only in a disposable prompt projection."""
    # Short local IDs may also be ordinary prose (e.g. the s in a possessive).
    # They do not need compaction, and expanding them would alter source words.
    references = {ident: alias for ident, alias in references.items() if len(ident) > len(alias)}
    if not references:
        return text
    pattern = re.compile(r"(?<![A-Za-z0-9_-])(?:" + "|".join(
        re.escape(ident) for ident in sorted(references, key=len, reverse=True)
    ) + r")(?![A-Za-z0-9_-])")
    return pattern.sub(lambda match: references[match.group()], text)


def compact_prior_decision(text: str) -> str:
    """Shorten legacy provenance only in the unvalidated memory prompt view."""
    labels = {}

    def label(match):
        ident = match.group(0)
        if ident not in labels:
            labels[ident] = f"[reference {len(labels) + 1}]"
        return labels[ident]

    rendered = re.sub(r"\b[0-9a-f]{64}\b", label, readable_evidence(text))
    if labels:
        rendered += "\nExact provenance IDs remain in the original memory record; display references are not fact IDs."
    return rendered
