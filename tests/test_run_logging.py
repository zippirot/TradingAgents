"""One warning log per analysis attempt, without provider exception text."""

import logging

import pytest

from cli.run_logging import cleanup_run_logging, configure_run_logging


@pytest.fixture(autouse=True)
def clean_run_logging():
    cleanup_run_logging()
    yield
    cleanup_run_logging()


@pytest.mark.unit
def test_warnings_reach_run_log(tmp_path):
    path = configure_run_logging(tmp_path)
    logging.getLogger("cli.run").warning("Report save failed")

    assert path == tmp_path / "run.log"
    assert "WARNING cli.run: Report save failed" in path.read_text()


@pytest.mark.unit
def test_reconfigure_replaces_previous_handler(tmp_path):
    old_path = configure_run_logging(tmp_path / "first")
    new_path = configure_run_logging(tmp_path / "second")
    logging.getLogger("tradingagents.graph").warning("second attempt")

    assert "second attempt" not in old_path.read_text()
    assert "second attempt" in new_path.read_text()


@pytest.mark.unit
def test_exception_and_external_diagnostics_do_not_reach_run_log(tmp_path):
    path = configure_run_logging(tmp_path)
    try:
        raise RuntimeError("secret-provider-token")
    except RuntimeError as exc:
        logging.getLogger("cli.run").warning("Report save failed: %s", exc, exc_info=True)
    logging.getLogger("openai.sdk").warning("raw external secret-provider-token")
    logging.getLogger("tradingagents.dataflows").warning("Vendor failed: %s", "secret-provider-token")

    contents = path.read_text()
    assert "Report save failed" in contents
    assert "RuntimeError" in contents
    assert "test_exception_and_external_diagnostics_do_not_reach_run_log" in contents
    assert "secret-provider-token" not in contents
    assert "raw external" not in contents


@pytest.mark.unit
def test_cleanup_restores_root_level_and_other_handlers(tmp_path):
    root = logging.getLogger()
    old_level = root.level
    other = logging.NullHandler()
    root.addHandler(other)
    try:
        configure_run_logging(tmp_path)
        assert root.level <= logging.WARNING
        cleanup_run_logging()
        assert root.level == old_level
        assert other in root.handlers
    finally:
        root.removeHandler(other)


@pytest.mark.unit
def test_structured_fallback_warning_names_agent_and_exception_class(tmp_path):
    from tradingagents.agents.structured import invoke_structured

    class BrokenProvider:
        def invoke(self, prompt):
            raise TimeoutError("secret-provider-token")

    path = configure_run_logging(tmp_path)
    assert invoke_structured(BrokenProvider(), "private prompt", "Trader") is None
    contents = path.read_text()
    assert "Trader" in contents
    assert "TimeoutError" in contents
    assert "secret-provider-token" not in contents
    assert "private prompt" not in contents
