"""Offline audit failure boundaries: no attribution or retry-budget relaxation."""
from langchain_core.messages import AIMessage

from tests.test_advisory_audit import finding, state
from tradingagents.agents.audit_pass import create_advisory_audit


class SequenceModel:
    def __init__(self, *outputs):
        self.outputs = iter(outputs)
        self.calls = 0

    def with_structured_output(self, schema, *, include_raw):
        assert include_raw is True
        return self

    def invoke(self, prompt):
        self.calls += 1
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return output


def run(model, **kwargs):
    return create_advisory_audit(model, deep_model_id="d", quick_model_id="q", **kwargs)(state())["advisory_audit"]


def response(parsed=None, error=None, finish="stop"):
    return {"raw": AIMessage(content="private content", response_metadata={"finish_reason": finish}),
            "parsed": parsed, "parsing_error": error}


def test_retry_parsing_failure_preserves_finish_and_safe_diagnostics():
    model = SequenceModel(response(error=ValueError("private parse"), finish="length"),
                          response({"findings": [finding()]}))
    record = run(model, sdk_retries_disabled=True)
    assert record["status"] == "completed with findings"
    assert model.calls == 2
    assert [a["error_category"] for a in record["attempts"]] == ["response_parsing", None]
    assert [a["finish_status"] for a in record["attempts"]] == ["length", "stop"]
    assert record["request_size"]["utf8_bytes"] >= record["request_size"]["characters"] > 0
    assert "private" not in str(record)


def test_retry_is_disabled_without_sdk_boundary_and_bounded_with_it():
    for disabled, calls in ((False, 1), (True, 2)):
        model = SequenceModel(TimeoutError("private"), TimeoutError("private"))
        record = run(model, sdk_retries_disabled=disabled)
        assert model.calls == calls
        assert record["status"] == "unavailable"
        assert record["error_category"] == "timeout"
        assert len(record["attempts"]) == calls


def test_all_invalid_quotes_remain_unavailable_without_retry():
    model = SequenceModel(response({"findings": [finding(quote="not present")]}))
    record = run(model, sdk_retries_disabled=True)
    assert model.calls == 1
    assert record["status"] == "unavailable"
    assert record["rejected_count"] == 1


def test_malformed_findings_retries_once_and_no_unknown_finish_leaks():
    model = SequenceModel(response({"findings": "bad"}, finish="private provider data"),
                          response({"findings": []}))
    record = run(model, sdk_retries_disabled=True)
    assert model.calls == 2
    assert record["status"] == "completed with zero findings"
    assert record["attempts"][0]["finish_status"] == "unknown"
    assert record["attempts"][0]["error_category"] == "malformed_findings"


def test_json_parse_exception_is_separate_from_invocation():
    model = SequenceModel("not json", response({"findings": []}))
    record = run(model, sdk_retries_disabled=True)
    assert record["attempts"][0]["error_category"] == "response_parsing"
    assert record["status"] == "completed with zero findings"


def test_budget_stop_never_triggers_application_retry():
    class BudgetStoppedError(RuntimeError):
        pass
    model = SequenceModel(BudgetStoppedError("private budget details"))
    record = run(model, sdk_retries_disabled=True)
    assert model.calls == 1
    assert record["error_category"] == "budget_stopped"
    assert record["status"] == "unavailable"
