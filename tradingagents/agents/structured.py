"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema)``
   so the model returns a typed Pydantic instance. If the provider does
   not support structured output (rare; mostly older Ollama models), the
   wrap is skipped and the agent uses free-text generation instead.
2. At invocation, run the structured call and render the result back to
   markdown. If the structured call itself fails for any reason
   (malformed JSON from a weak model, transient provider issue), fall
   back to a plain ``llm.invoke`` so the pipeline never blocks.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any, TypeVar

from pydantic import BaseModel

from tradingagents.operational_capture import (
    delivered_narrative,
    record_operation,
    remember_structured_raw,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Schema-only structured output binds exactly one tool (the schema itself), so a
# model that reaches for a search tool emits an unknown tool call and the whole
# structured attempt is discarded for a free-text retry. Agents on this path
# state the constraint explicitly rather than relying on the binding alone
# (#1130).
NO_EXTERNAL_TOOLS = (
    "Use only the evidence provided in this prompt. Do not call external tools "
    "or search the web; if something is missing, say so explicitly."
)


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Any | None:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    try:
        try:
            return llm.with_structured_output(schema, include_raw=True)
        except TypeError:
            return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, type(exc).__name__,
            extra={"diagnostic_agent": agent_name, "diagnostic_error_class": type(exc).__name__},
        )
        return None


_last_failure: ContextVar[tuple[str, str] | None] = ContextVar("structured_failure", default=None)


def provider_error_text(exc: BaseException) -> str:
    """First 500 characters of a provider error, without keys or request content."""
    text = " ".join(str(exc).split())
    text = re.sub(r"(?i)\b(bearer\s+|api[_-]?key[\"'=:\s]+)\S+", r"\1[redacted]", text)
    text = re.sub(r"\b[sprk]{1,2}-[A-Za-z0-9_-]{8,}", "[redacted]", text)
    text = re.sub(r"(?is)(request[_ ]?body|[\"']messages[\"'])\s*[:=].*", r"\1: [omitted]", text)
    return text[:500]


def invoke_structured(structured_llm: Any | None, prompt: Any, agent_name: str) -> T | None:
    """Run the structured call; ``None`` when there is none or it fails.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape), so a caller can forward the same value to its free-text fallback.
    """
    remember_structured_raw(None)
    _last_failure.set(None)
    if structured_llm is None:
        return None
    try:
        result = structured_llm.invoke(prompt)
        if isinstance(result, dict) and "parsed" in result and "raw" in result:
            remember_structured_raw(result["raw"])
            if result.get("parsing_error") is not None:
                raise ValueError("structured output parsing failed")
            result = result["parsed"]
        if result is None:
            # A thinking model can answer in plain text instead of calling
            # the tool, leaving the parser with nothing to return. Treat it
            # as a structured miss and fall back, with a clear reason.
            raise ValueError("structured output returned no parsed result")
        return result
    except Exception as exc:
        message = provider_error_text(exc)
        _last_failure.set((type(exc).__name__, message))
        logger.warning(
            "%s: structured-output invocation failed (%s: %s); retrying once as free text",
            agent_name, type(exc).__name__, message,
            extra={"diagnostic_agent": agent_name, "diagnostic_error_class": type(exc).__name__},
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
    finish_freetext: Callable[[str], str] | None = None,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``finish_freetext`` checks or completes fallback text only, and may raise to fail the stage.
    """
    result = invoke_structured(structured_llm, prompt, agent_name)
    if result is not None:
        return delivered_narrative(render(result))
    failure = _last_failure.get()
    raw = plain_llm.invoke(prompt)
    content = finish_freetext(raw.content) if finish_freetext is not None else raw.content
    text = delivered_narrative(content, raw)
    if structured_llm is not None:
        detail = {"error_class": failure[0], "error_message": failure[1]} if failure else {}
        record_operation('fallback_recovered', **detail)
    return text
