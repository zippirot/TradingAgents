"""Private, opt-in per-stage traces and bounded call provenance for one CLI attempt."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)
_SECRET_NAME = re.compile(r"api.?key|(?:^|_)token$|password|secret|authorization|headers", re.I)
_SECRET_ENV = re.compile(r"(?:API_?KEY|_TOKEN|_PASSWORD|_SECRET|AUTHORIZATION)$", re.I)


def merge_call_metadata(left, right):
    return {**(left or {}), **(right or {})}


def _model_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"[\w./:@+~-]{1,256}", value) else None


class AttemptRecorder(BaseCallbackHandler):
    """One callback marker shared by stage wrappers; never store credentials/config."""

    def __init__(self, directory, attempt_id):
        self.directory = Path(directory)
        self.attempt_id = str(attempt_id)
        self.enabled = os.getenv("TRADINGAGENTS_TRACE") == "1" or bool(os.getenv("TRADINGAGENTS_REPLAY_TRACE"))
        self.lock = Lock()
        self.sequence = 0
        self.stages = {}
        self.failed = False
        self.secrets = sorted({value for key, value in os.environ.items()
                               if _SECRET_ENV.search(key) and len(value) >= 4}, key=len, reverse=True)

    def clean(self, value):
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, BaseMessage):
            return self.clean({"type": value.type, "content": value.content,
                               "id": value.id, "name": value.name,
                               "tool_calls": getattr(value, "tool_calls", None),
                               "tool_call_id": getattr(value, "tool_call_id", None)})
        if isinstance(value, Mapping):
            return {str(key): "[REDACTED]" if _SECRET_NAME.search(str(key))
                    else self.clean(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(item) for item in value]
        if value is None or isinstance(value, (int, float, bool)):
            return value
        # Command updates contain graph effects as well as ToolMessages.
        if type(value).__name__ == "Command" and hasattr(value, "update"):
            return {"command_update": self.clean(value.update)}
        return {"type": type(value).__name__}

    def emit(self, stage, state, event, **data):
        if not self.enabled:
            return
        try:
            with self.lock:
                if stage not in self.stages:
                    self.stages[stage] = len(self.stages) + 1
                self.sequence += 1
                slug = re.sub(r"[^a-z0-9-]", "-", stage.lower()).strip("-")[:80]
                folder = self.directory / "trace"
                folder.mkdir(mode=0o700, parents=True, exist_ok=True)
                path = folder / f"{self.stages[stage]:02d}-{slug}.jsonl"
                row = {"schema_version": 1, "attempt_id": self.attempt_id,
                       "run_id": state.get("run_id"), "ticker": state.get("company_of_interest"),
                       "analysis_date": state.get("trade_date"), "stage": stage,
                       "sequence": self.sequence, "recorded_at": datetime.now(UTC).isoformat(),
                       "event": event, **data}
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(self.clean(row), ensure_ascii=False, allow_nan=False) + "\n")
        except (OSError, ValueError, TypeError):
            if not self.failed:
                logger.warning("Attempt trace incomplete: a trace event could not be written")
            self.failed = True

    def stage(self, stage, state):
        return _StageCapture(self, stage, state)

    def transcript(self, stage, state, fields, *, failed=False):
        row = {"attempt_id": self.attempt_id, "run_id": state.get("run_id"),
               "stage": stage, "status": "failed" if failed else "completed",
               "state_keys": sorted(fields)}
        try:
            with self.lock:
                self.directory.mkdir(parents=True, exist_ok=True)
                with (self.directory / "message_tool.log").open("a", encoding="utf-8") as handle:
                    handle.write("[Node] " + json.dumps(self.clean(row), sort_keys=True) + "\n")
        except OSError:
            logger.warning("Node transcript incomplete: a stage pointer could not be written")


def recorder_from_config(config):
    callbacks = config.get("callbacks")
    handlers = callbacks if isinstance(callbacks, (list, tuple)) else getattr(callbacks, "handlers", [])
    return next((handler for handler in handlers if isinstance(handler, AttemptRecorder)), None)


class _StageCapture(BaseCallbackHandler):
    """Callbacks inherit this stage even through private analyst subgraphs."""

    def __init__(self, owner, stage, state):
        self.owner, self.stage, self.state = owner, stage, state
        self.calls = {}
        self.lock = Lock()

    def emit(self, event, **data):
        self.owner.emit(self.stage, self.state, event, **data)

    def _start(self, prompts, run_id, kwargs):
        params = kwargs.get("invocation_params") or {}
        requested = _model_id(params.get("model") or params.get("model_name"))
        with self.lock:
            if len(self.calls) < 512:
                self.calls[str(run_id)] = {"stage": self.stage, "attempt_id": self.owner.attempt_id,
                                           "requested_model": requested, "actual_model": None,
                                           "status": "started"}
        self.emit("model_start", call_id=str(run_id), requested_model=requested, prompts=prompts)

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._start(messages, run_id, kwargs)

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        self._start(prompts, run_id, kwargs)

    def on_llm_end(self, response, *, run_id, **kwargs):
        outputs = []
        actual = None
        for group in response.generations:
            for generation in group:
                message = getattr(generation, "message", None)
                metadata = getattr(message, "response_metadata", None) or {}
                actual = actual or _model_id(metadata.get("model_name") or metadata.get("model"))
                outputs.append(message if message is not None else generation.text)
        provider = response.llm_output or {}
        actual = actual or _model_id(provider.get("model_name") or provider.get("model"))
        with self.lock:
            if str(run_id) in self.calls:
                self.calls[str(run_id)].update(actual_model=actual, status="completed")
        self.emit("model_end", call_id=str(run_id), actual_model=actual, outputs=outputs)

    def on_llm_error(self, error, *, run_id, **kwargs):
        with self.lock:
            if str(run_id) in self.calls:
                self.calls[str(run_id)]["status"] = "failed"
        self.emit("model_error", call_id=str(run_id), error_class=type(error).__name__)

    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kwargs):
        # Injected state belongs to the graph, not the model's requested arguments.
        args = {key: value for key, value in (inputs or {}).items()
                if key not in {"run_state", "tool_call_id", "runtime"}}
        self.emit("tool_start", call_id=str(run_id), tool=(serialized or {}).get("name"), arguments=args)

    def on_tool_end(self, output, *, run_id, **kwargs):
        self.emit("tool_end", call_id=str(run_id), output=output)

    def on_tool_error(self, error, *, run_id, **kwargs):
        self.emit("tool_error", call_id=str(run_id), error_class=type(error).__name__)
