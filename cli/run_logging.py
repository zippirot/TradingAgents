"""A replaceable, sanitized warning log for one analysis attempt."""

import logging
import re
import traceback
from pathlib import Path

_owned_handler: logging.FileHandler | None = None
_previous_root_level: int | None = None


class _RunLogFilter(logging.Filter):
    """Keep third-party SDK diagnostics out of the run log."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == "root" or record.name == "cli" or record.name.startswith(
            "cli."
        ) or record.name == "tradingagents" or record.name.startswith("tradingagents.")


class _SafeRunFormatter(logging.Formatter):
    """Retain event text and stack location, never exception details or values."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.msg if isinstance(record.msg, str) else type(record.msg).__name__
        if record.args:
            # Log templates are app-owned; arguments may contain provider payloads.
            # Keep their types for diagnosis without evaluating __str__/__repr__.
            args = record.args.values() if isinstance(record.args, dict) else record.args
            message += " [arg types: " + ", ".join(type(arg).__name__ for arg in args) + "]"
        if record.name == "tradingagents.agents.structured":
            agent = getattr(record, "diagnostic_agent", None)
            error = getattr(record, "diagnostic_error_class", None)
            if agent in {"Trader", "Portfolio Manager", "Research Manager", "Sentiment Analyst"}:
                message += f" [agent: {agent}]"
            if isinstance(error, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", error):
                message += f" [exception class: {error}]"
        timestamp = self.formatTime(record, self.datefmt)
        rendered = f"{timestamp} {record.levelname} {record.name}: {message}"
        if record.exc_info:
            exc_type, _, tb = record.exc_info
            rendered += "\nTraceback (most recent call last):"
            for frame in traceback.extract_tb(tb):
                rendered += f'\n  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
            rendered += f"\n{exc_type.__name__ if exc_type else 'Exception'}"
        return rendered


def cleanup_run_logging() -> None:
    """Remove only this module's file handler and restore the root level."""
    global _owned_handler, _previous_root_level
    root = logging.getLogger()
    if _owned_handler is not None:
        root.removeHandler(_owned_handler)
        _owned_handler.close()
        _owned_handler = None
    if _previous_root_level is not None:
        root.setLevel(_previous_root_level)
        _previous_root_level = None


def configure_run_logging(results_dir: Path) -> Path:
    """Install a WARNING log at ``results_dir/run.log`` for the current run."""
    global _owned_handler, _previous_root_level
    cleanup_run_logging()
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "run.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.WARNING)
    handler.addFilter(_RunLogFilter())
    handler.setFormatter(_SafeRunFormatter())
    root = logging.getLogger()
    _previous_root_level = root.level
    if root.level > logging.WARNING:
        root.setLevel(logging.WARNING)
    root.addHandler(handler)
    _owned_handler = handler
    return path
