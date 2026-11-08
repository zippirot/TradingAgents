"""Run-scoped replay of recorded external inputs, never derived graph decisions."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Lock

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)

_SESSION = ContextVar("source_replay_session", default=None)
_LIVE_CLOCK = ContextVar("live_source_clock", default=False)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _pack(value):
    import numpy as np

    if isinstance(value, np.generic) and value.dtype.kind in "iufb" and value.dtype.itemsize <= 8:
        return {"__tradingagents_replay_numpy__": {"dtype": value.dtype.name, "value": _pack(value.item())}}
    if isinstance(value, datetime):
        try:
            datetime.fromisoformat(value.isoformat())
        except ValueError:
            return value  # e.g. pandas NaT remains explicitly unreplayable
        return {"__tradingagents_replay_datetime__": value.isoformat()}
    if isinstance(value, date):
        return {"__tradingagents_replay_date__": value.isoformat()}
    if isinstance(value, float) and not math.isfinite(value):
        return {"__tradingagents_replay_float__": str(value)}
    if isinstance(value, dict):
        return {key: _pack(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_pack(item) for item in value]
    return value


def _unpack(value):
    if isinstance(value, dict):
        if set(value) == {"__tradingagents_replay_numpy__"}:
            import numpy as np

            scalar = value["__tradingagents_replay_numpy__"]
            dtype = np.dtype(scalar["dtype"])
            if dtype.kind not in "iufb" or dtype.itemsize > 8:
                raise ValueError("Unsupported replay scalar dtype")
            return dtype.type(_unpack(scalar["value"]))
        if set(value) == {"__tradingagents_replay_datetime__"}:
            return datetime.fromisoformat(value["__tradingagents_replay_datetime__"])
        if set(value) == {"__tradingagents_replay_date__"}:
            return date.fromisoformat(value["__tradingagents_replay_date__"])
        if set(value) == {"__tradingagents_replay_float__"}:
            return float(value["__tradingagents_replay_float__"])
        return {key: _unpack(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_unpack(item) for item in value]
    return value


@contextmanager
def session_context(session):
    token = _SESSION.set(session)
    try:
        yield
    finally:
        _SESSION.reset(token)


def set_session(session):
    _SESSION.set(session)


def current_session():
    return _SESSION.get()


def source_now(tz=UTC):
    session = _SESSION.get()
    return session.observed_at.astimezone(tz) if session and not _LIVE_CLOCK.get() else datetime.now(tz)


def source_today():
    session = _SESSION.get()
    return session.local_date if session and not _LIVE_CLOCK.get() else date.today()


def external_input(name, arguments, live):
    session = _SESSION.get()
    if session is None:
        return live()
    return session.input(name, arguments, live)


class ReplaySession:
    """The finite source boundaries share one attempt's private trace journal."""

    def __init__(self, recorder, scope, *, baseline=None):
        self.recorder, self.scope = recorder, dict(scope)
        self.baseline = Path(baseline) if baseline is not None else None
        self.records = defaultdict(dict)
        self.occurrences = Counter()
        self.misses = []
        self.lock = Lock()
        self.observed_at = datetime.now(UTC)
        self.local_date = date.today()
        if self.baseline is not None:
            self._load()
        self.recorder.emit("Source Inputs", {}, "source_session_start", scope=self.scope,
                           observed_at=self.observed_at.isoformat(), local_date=self.local_date.isoformat())

    @property
    def status(self):
        return "mixed_input" if self.misses else "replayed" if self.baseline is not None else "recorded"

    def _load(self):
        rows = []
        try:
            for path in (self.baseline / "trace").glob("*.jsonl"):
                rows.extend(json.loads(line) for line in path.read_text().splitlines())
            rows.sort(key=lambda row: row["sequence"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError("Replay trace is incomplete or unreadable") from exc
        starts = [r for r in rows if r.get("event") == "source_session_start"]
        ends = [r for r in rows if r.get("event") == "source_session_end"]
        if len(starts) != 1 or len(ends) != 1 or ends[0].get("incomplete") is not False:
            raise ValueError("Replay trace is incomplete")
        if any(row.get("incomplete") is True for row in rows):
            raise ValueError("Replay trace contains incomplete stages")
        if starts[0].get("scope") != self.scope:
            raise ValueError("Replay source scope differs from ticker/date/clock")
        self.observed_at = datetime.fromisoformat(starts[0]["observed_at"])
        self.local_date = date.fromisoformat(starts[0]["local_date"])
        if self.observed_at.utcoffset() is None:
            raise ValueError("Replay observation clock lacks a timezone")
        if [row["sequence"] for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError("Replay trace is incomplete or has duplicate sequence numbers")
        for row in rows:
            if row.get("event") != "source_input":
                continue
            payload = row.get("payload")
            if row.get("payload_sha256") != _digest(payload):
                raise ValueError("Replay source payload integrity mismatch")
            if _digest(row.get("input_identity")) != row.get("input_key"):
                raise ValueError("Replay source identity integrity mismatch")
            if row.get("replayable") is True:
                self.records[row["input_key"]][row["occurrence"]] = row
            else:
                self.records[row["input_key"]][row["occurrence"]] = None

    def finish(self, success):
        self.recorder.emit("Source Inputs", {}, "source_session_end",
                           incomplete=not success or self.recorder.failed, status=self.status,
                           replay_misses=len(self.misses))

    def input(self, name, arguments, live):
        from tradingagents.operational_capture import current_operation_scope, record_operation

        state, stage = current_operation_scope()
        identity = {"scope": self.scope, "stage": stage, "name": name, "arguments": arguments}
        key = _digest(identity)
        with self.lock:
            occurrence = self.occurrences[key]
            self.occurrences[key] += 1
            found = self.records.get(key, {}).get(occurrence)
        if found is not None:
            payload = deepcopy(found["payload"])
            self.recorder.emit("Source Inputs", state, "source_replayed", name=name,
                               input_key=key, occurrence=occurrence)
            self._record(identity, key, occurrence, payload, state)
            return self._value(payload)
        if self.baseline is not None:
            with self.lock:
                self.misses.append({"name": name, "stage": stage, "input_key": key})
            self.recorder.emit("Source Inputs", state, "replay_miss", name=name,
                               input_key=key, occurrence=occurrence, status="mixed_input")
            record_operation("replay_miss", scope=name)
        try:
            clock_token = _LIVE_CLOCK.set(True)
            try:
                value = live()
            finally:
                _LIVE_CLOCK.reset(clock_token)
            payload = {"value": value}
        except (VendorUnavailableError, VendorNotConfiguredError, NoMarketDataError) as exc:
            payload = {"error": type(exc).__name__,
                       "symbol": getattr(exc, "symbol", None),
                       "canonical": getattr(exc, "canonical", None),
                       "detail": getattr(exc, "detail", ""),
                       "reason_code": getattr(exc, "reason_code", None)}
            self._record(identity, key, occurrence, payload, state)
            raise
        except Exception as exc:
            # Unsupported provider exceptions remain visible but cannot be replayed
            # from an invented replacement payload or raw private diagnostics.
            self._record(identity, key, occurrence, {"unreplayable_error": type(exc).__name__}, state)
            raise
        self._record(identity, key, occurrence, payload, state)
        return value

    def _record(self, identity, key, occurrence, payload, state):
        # A scrubbed source is safe to retain but cannot prove identical input.
        packed = _pack(payload)
        cleaned = self.recorder.clean(packed)
        self.recorder.emit("Source Inputs", state, "source_input", input_identity=identity,
                           input_key=key, occurrence=occurrence, payload=cleaned,
                           payload_sha256=_digest(cleaned),
                           replayable=cleaned == packed and "unreplayable_error" not in payload)

    @staticmethod
    def _value(payload):
        payload = _unpack(payload)
        if "error" not in payload:
            return payload["value"]
        kind = payload["error"]
        if kind == "NoMarketDataError":
            raise NoMarketDataError(payload["symbol"], payload["canonical"], payload["detail"])
        if kind == "VendorNotConfiguredError":
            raise VendorNotConfiguredError("Recorded vendor was not configured")
        if kind == "VendorUnavailableError":
            raise VendorUnavailableError("Recorded vendor was unavailable", reason_code=payload.get("reason_code"))
        raise ValueError("Unsupported recorded source failure")
