"""Opted-in factual audit around the existing publication finalizer."""
import time
from copy import deepcopy

from tradingagents.ground_truth import (
    DEFAULT_MAX_REQUESTS,
    DEFAULT_MAX_SECONDS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_OUTPUT_TOKEN_RESERVATION,
    _positive,
)


def _remaining_config(state, config):
    progress = state.setdefault('ground_truth_execution', {'requests': 0, 'elapsed_seconds': 0.0})
    progress.setdefault('budget_tokens', 0)
    return {**config,
            'ground_truth_max_requests': max(0, _positive(config, 'ground_truth_max_requests', DEFAULT_MAX_REQUESTS, 512) - progress['requests']),
            'ground_truth_max_seconds': max(0, _positive(config, 'ground_truth_max_seconds', DEFAULT_MAX_SECONDS, 7200) - progress['elapsed_seconds']),
            'ground_truth_max_tokens': max(0, _positive(config, 'ground_truth_max_tokens', DEFAULT_MAX_TOKENS, 20_000_000) - progress['budget_tokens'])}


def _audit_pass(state, llm, config):
    from tradingagents.ground_truth import run_audit
    from tradingagents.ground_truth_display import build_report_inventory

    remaining = _remaining_config(state, config)
    progress = state['ground_truth_execution']
    started = time.monotonic()
    try:
        inventory = build_report_inventory(state)
        result = run_audit(state, llm, remaining, inventory=inventory)
    except Exception:
        # Model payloads and provider exceptions can contain confidential data.
        result = {'schema_version': 1, 'status': 'unavailable', 'claims': [],
                  'reason': 'Audit preparation or provider failed.'}
    progress['requests'] += result.get('usage', {}).get('requests', 0)
    progress['budget_tokens'] += result.get('usage', {}).get('budget_tokens', 0)
    progress['elapsed_seconds'] += time.monotonic() - started
    return result


def _material_correction(claim):
    """Only dated source-backed corrections can prompt an independent PM review."""
    correction = claim.get('correction')
    if (claim.get('outcome') != 'contradicted' or claim.get('decision_material') is not True
            or not isinstance(correction, str) or not correction.strip()):
        return False
    if claim.get('code_verified') is True:
        return True
    if (claim.get('verification') or {}).get('source_quotes_validated') is not True:
        return False
    return any(evidence.get('kind') in {'filing passage', 'canonical financial fields'}
               and isinstance(evidence.get('quote'), str) and correction in evidence['quote']
               for evidence in claim.get('evidence') or [])


def audit_before_publication(state, llm, config, *, reassess=None, validate=None):
    """Audit the candidate and reconsider once with reproducible corrections."""
    if config.get('ground_truth_audit') is not True:
        return
    if 'ground_truth_prepublication' not in state:
        started = time.monotonic()
        try:
            from tradingagents.ground_truth_sources import acquire_sources
            remaining = _remaining_config(state, config)
            if remaining['ground_truth_max_seconds'] > 0:
                state.update(acquire_sources(state, remaining))
        except Exception:
            state['ground_truth_source_acquisition'] = {
                'status': 'unavailable', 'error_categories': ['source_acquisition_failed']}
        progress = state.setdefault('ground_truth_execution', {'requests': 0, 'elapsed_seconds': 0.0})
        progress['elapsed_seconds'] += time.monotonic() - started
    original = _audit_pass(state, llm, config)
    state['ground_truth_prepublication'] = original
    corrections = [claim for claim in original.get('claims', []) if _material_correction(claim)]
    if not corrections or state.get('final_rating') == 'REVIEW' or (
            state.get('evidence_quality') or {}).get('status') == 'insufficient':
        return
    previous = state.get('ground_truth_reassessment')
    if previous or reassess is None:
        return
    progress = state.setdefault('ground_truth_execution', {'requests': 0, 'elapsed_seconds': 0.0})
    remaining = _remaining_config(state, config)
    if any(remaining[key] <= 0 for key in ('ground_truth_max_requests', 'ground_truth_max_seconds', 'ground_truth_max_tokens')):
        state['ground_truth_reassessment'] = {'status': 'unavailable', 'reason': 'Audit budget exhausted. Recommendation needs review.'}
        return
    saved = deepcopy(state)
    record = {'status': 'unavailable', 'original_rating': saved.get('final_rating'),
              'original_decision': saved.get('final_trade_decision'),
              'corrections': corrections, 'reason': 'Recommendation needs review.'}
    state['ground_truth_reassessment'] = record
    started = time.monotonic()
    try:
        review_input = deepcopy(saved)
        review_input['investment_plan'] = str(review_input.get('investment_plan') or '') + (
            '\nGround Truth review asks you to independently assess each original claim against its '
            'dated primary-source passage and proposed correction. Exact source quotations have been '
            'checked by code. Any semantic relationship remains a model assessment. Determine whether '
            'the evidence changes your reasoning or rating. You may retain the rating. Never infer a '
            'rating change from an unsupported hypothesis, missing source or the auditor alone.\n'
        )
        update = reassess(review_input, corrections, _BudgetedModel(llm, progress, config))
        candidate = {**saved, **update}
        if validate:
            candidate.update(validate(candidate))
        state.update(candidate)
        record['status'] = 'completed'
        record.pop('reason', None)
    except Exception:
        # Preserve the original decision if reassessment or validation fails.
        pass
    progress['elapsed_seconds'] += time.monotonic() - started
    state['ground_truth_execution'] = progress
    state['ground_truth_reassessment'] = record
    if record['status'] == 'completed':
        state.pop('executive_summary', None)
        state['ground_truth_prepublication'] = _audit_pass(state, llm, config)


def audit_after_summary(state, llm, config):
    """Bind a final audit to the complete rendered sections and resolved summary."""
    if config.get('ground_truth_audit') is True:
        state['ground_truth_audit'] = _audit_pass(state, llm, config)


class _BudgetedModel:
    """Share the audit request allowance with PM structured and fallback calls."""
    def __init__(self, model, progress, config, deadline=None):
        self.model = model
        self.progress = progress
        self.config = config
        self.progress.setdefault('budget_tokens', 0)
        self.deadline = deadline if deadline is not None else (time.monotonic() + max(0, _positive(config, 'ground_truth_max_seconds', DEFAULT_MAX_SECONDS, 7200) - progress['elapsed_seconds']))

    def with_structured_output(self, *args, **kwargs):
        return _BudgetedModel(self.model.with_structured_output(*args, **kwargs), self.progress, self.config, self.deadline)

    def invoke(self, *args, **kwargs):
        if self.progress['requests'] >= _positive(self.config, 'ground_truth_max_requests', DEFAULT_MAX_REQUESTS, 512):
            raise RuntimeError('Audit request budget exhausted')
        if time.monotonic() >= self.deadline:
            raise RuntimeError('Audit time budget exhausted')
        prompt = args[0] if args else kwargs
        reservation = len(str(prompt).encode('utf-8')) + 8192 + _positive(
            self.config, 'ground_truth_output_token_reservation', DEFAULT_OUTPUT_TOKEN_RESERVATION, 100000)
        token_limit = _positive(self.config, 'ground_truth_max_tokens', DEFAULT_MAX_TOKENS, 20_000_000)
        if self.progress['budget_tokens'] + reservation > token_limit:
            raise RuntimeError('Audit token budget exhausted')
        self.progress['requests'] += 1
        self.progress['budget_tokens'] += reservation
        result = self.model.invoke(*args, **kwargs)
        metadata = getattr(result, 'usage_metadata', None)
        if (isinstance(metadata, dict) and type(metadata.get('input_tokens')) is int
                and type(metadata.get('output_tokens')) is int
                and metadata['input_tokens'] >= 0 and metadata['output_tokens'] >= 0):
            self.progress['budget_tokens'] += metadata['input_tokens'] + metadata['output_tokens'] - reservation
        return result
