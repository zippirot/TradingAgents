"""Small execution observations scoped to one actual graph node invocation."""
from collections.abc import Mapping
from contextvars import ContextVar
from threading import Lock

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda

from tradingagents.operational_audit import observation

_active = ContextVar('operational_node', default=None)
_last_structured_raw = ContextVar('last_structured_raw', default=None)

TRUNCATION_NOTE = "[Model output truncated by provider; this narrative may be incomplete.]"


def output_was_truncated(raw):
    """Use the bounded provider finish status while its raw response is available."""
    metadata = getattr(raw, 'response_metadata', None)
    info = getattr(raw, 'generation_info', None)
    metadata = metadata if isinstance(metadata, Mapping) else {}
    info = info if isinstance(info, Mapping) else {}
    stop = metadata.get('finish_reason') or metadata.get('stop_reason') or info.get('finish_reason') or info.get('stop_reason')
    return stop in {'length', 'max_tokens', 'MAX_TOKENS'}


def delivered_narrative(text, raw=None):
    """Label only the response actually presented to a later agent."""
    if raw is None:
        raw = _last_structured_raw.get()
    return f"{text}\n\n{TRUNCATION_NOTE}" if output_was_truncated(raw) else text


def remember_structured_raw(raw):
    _last_structured_raw.set(raw)


def record_operation(code, *, scope=None):
    """Record a bounded reason code without provider payloads or exceptions."""
    active = _active.get()
    if active is None:
        return
    state, stage, events, lock = active
    with lock:
        key = (code, scope)
        if key in events:
            previous = events[key]
            events[key] = observation(state, stage, code=code, scope=scope,
                                      count=previous.get('count', 1) + 1)
        elif len(events) < 128:
            events[key] = observation(state, stage, code=code, scope=scope)
        else:
            events[('incomplete_history', None)] = observation(
                state, stage, code='incomplete_history', scope='observation limit')


class _Outcomes(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, 'message', None)
                metadata = getattr(message, 'response_metadata', None)
                info = getattr(generation, 'generation_info', None)
                if (message is not None and isinstance(metadata, Mapping)
                        and not (metadata.get('finish_reason') or metadata.get('stop_reason'))
                        and isinstance(info, Mapping)):
                    stop = info.get('finish_reason') or info.get('stop_reason')
                    if stop in {'length', 'max_tokens', 'MAX_TOKENS'}:
                        message.response_metadata = {**metadata, 'finish_reason': stop}
                if output_was_truncated(message) or output_was_truncated(generation):
                    record_operation('model_output_truncated')

    def on_tool_error(self, error, **kwargs):
        record_operation('tool_error')

    def on_tool_end(self, output, **kwargs):
        if getattr(output, 'status', None) == 'error':
            record_operation('tool_error')


def current_operation_scope():
    active = _active.get()
    return (active[0], active[1]) if active is not None else ({}, "Invocation")


def observed_node(node, stage, *, report_key=None, expected_stages=None):
    """Wrap a node while retaining LangGraph config and subgraph execution."""
    runnable = node if hasattr(node, 'invoke') else RunnableLambda(node)

    def invoke(state, config):
        if not state.get('run_id'):
            return runnable.invoke(state, config)
        events = {}
        token = _active.set((state, stage, events, Lock()))
        from tradingagents.attempt_trace import recorder_from_config

        recorder = recorder_from_config(config)
        capture = recorder.stage(stage, state) if recorder else None
        callbacks = [_Outcomes()]
        if capture:
            callbacks.append(capture)
            capture.emit('stage_start', state_keys=sorted(state))
        try:
            from langchain_core.runnables.config import merge_configs
            result = runnable.invoke(state, merge_configs(config, {'callbacks': callbacks}))
        except BaseException as exc:
            if capture:
                capture.emit('stage_error', incomplete=True, error_class=type(exc).__name__)
                recorder.transcript(stage, state, [], failed=True)
            raise
        finally:
            _active.reset(token)
        if capture:
            capture.emit('stage_end', incomplete=False, state_keys=sorted(result))
            recorder.transcript(stage, state, result)
            if capture.calls:
                result = {**result, 'model_call_metadata': capture.calls}
        code = 'empty_output' if report_key and not result.get(report_key) else 'completed'
        extra = {}
        if expected_stages is not None:
            extra['expected_stages'] = expected_stages
        if stage == 'Evidence Check':
            extra['route'] = 'review' if result.get('evidence_quality', {}).get('status') == 'insufficient' else 'full'
        if stage == 'Advisory Audit' and result.get('advisory_audit', {}).get('status') == 'unavailable':
            code = 'empty_output'
        row = observation(state, stage, code=code, **extra)
        rows = {row['event_id']: row}
        for event in events.values():
            rows[event['event_id']] = event
        return {**result, 'operational_observations': rows}

    return invoke
