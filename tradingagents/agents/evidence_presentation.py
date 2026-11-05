"""Presentation-only separation of readable evidence and exact reference IDs."""

import re

REFERENCE_START = "\n\n<!-- evidence-references:start -->\n"
REFERENCE_END = "\n<!-- evidence-references:end -->"
_REFERENCE_BLOCK = re.compile(re.escape(REFERENCE_START) + r"(.*?)" + re.escape(REFERENCE_END), re.S)


def analyst_prose(text: str) -> str:
    """Keep research prose; structured extraction stays in raw diagnostics."""
    return re.sub(
        r"```(?:financial_claims|disclosures|valuation_scenarios)\b[^\n]*\n.*?(?:```|\Z)",
        "", text, flags=re.S,
    ).strip()


def readable_evidence(text: str) -> str:
    """Keep values and limitations; exact references remain in canonical state."""
    return _REFERENCE_BLOCK.sub("", text).strip()


def evidence_references(text: str) -> str:
    return "\n\n".join(match.group(1) for match in _REFERENCE_BLOCK.finditer(text))


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
