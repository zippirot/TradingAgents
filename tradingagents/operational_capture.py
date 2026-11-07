"""Small execution observations scoped to one actual graph node invocation."""
from contextvars import ContextVar
from threading import Lock

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda

from tradingagents.operational_audit import observation

_active = ContextVar('operational_node', default=None)


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
                metadata = getattr(getattr(generation, 'message', None), 'response_metadata', {})
                info = generation.generation_info or {}
                stop = metadata.get('finish_reason') or metadata.get('stop_reason') or info.get('finish_reason')
                if stop in {'length', 'max_tokens', 'MAX_TOKENS'}:
                    record_operation('model_output_truncated')

    def on_tool_error(self, error, **kwargs):
        record_operation('tool_error')

    def on_tool_end(self, output, **kwargs):
        if getattr(output, 'status', None) == 'error':
            record_operation('tool_error')


def observed_node(node, stage, *, report_key=None, expected_stages=None):
    """Wrap a node while retaining LangGraph config and subgraph execution."""
    runnable = node if hasattr(node, 'invoke') else RunnableLambda(node)

    def invoke(state, config):
        if not state.get('run_id'):
            return runnable.invoke(state, config)
        events = {}
        token = _active.set((state, stage, events, Lock()))
        try:
            from langchain_core.runnables.config import merge_configs
            result = runnable.invoke(state, merge_configs(config, {'callbacks': [_Outcomes()]}))
        finally:
            _active.reset(token)
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
