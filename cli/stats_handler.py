import threading
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult


class StatsCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks LLM calls, tool calls, and token usage."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.token_usage_calls = 0
        self.token_usage_missing = 0

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when an LLM starts."""
        with self._lock:
            self.llm_calls += 1

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when a chat model starts."""
        with self._lock:
            self.llm_calls += 1

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract token usage from LLM response."""
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return

        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata

        valid = (isinstance(usage_metadata, dict) and
                 all(type(usage_metadata.get(key)) is int and usage_metadata[key] >= 0
                     for key in ("input_tokens", "output_tokens")))
        with self._lock:
            if valid:
                self.tokens_in += usage_metadata["input_tokens"]
                self.tokens_out += usage_metadata["output_tokens"]
                self.token_usage_calls += 1
            else:
                self.token_usage_missing += 1

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Increment tool call counter when a tool starts."""
        with self._lock:
            self.tool_calls += 1

    def get_stats(self) -> dict[str, Any]:
        """Return current statistics."""
        with self._lock:
            scope = ("complete_observed" if self.token_usage_calls > 0
                     and self.token_usage_calls == self.llm_calls and self.token_usage_missing == 0
                     else "partial_observed" if self.token_usage_calls > 0 else "unavailable")
            return {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "token_usage_calls": self.token_usage_calls,
                "token_usage_missing": self.token_usage_missing,
                "token_usage_scope": scope,
            }


def _valid_price(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return price if price.is_finite() and price >= 0 else None


def render_usage_cost(stats: dict, config: dict) -> str:
    """One CLI usage line, with an optional estimate for observed tokens only."""
    scope = stats.get("token_usage_scope")
    count_in, count_out = stats.get("tokens_in"), stats.get("tokens_out")
    if scope not in {"complete_observed", "partial_observed"} or any(
        type(value) is not int or value < 0 for value in (count_in, count_out)
    ):
        return "Tokens: unavailable (usage was not observed)"

    coverage = "complete observed" if scope == "complete_observed" else "partial observed"
    line = f"Tokens: {count_in:,} in / {count_out:,} out ({coverage})"
    input_price = _valid_price(config.get("input_cost_per_million"))
    output_price = _valid_price(config.get("output_cost_per_million"))
    if input_price is None or output_price is None:
        return line
    try:
        cost = (Decimal(count_in) * input_price + Decimal(count_out) * output_price) / 1_000_000
    except DecimalException:
        return line
    scope_note = "observed tokens only; not the whole run or a billing total" if scope == "partial_observed" else (
        "observed tokens only; not a billing total"
    )
    return f"{line}\nEstimated cost at configured prices: ${cost:.6f} ({scope_note})"
