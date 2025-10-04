import json
import logging

import pytest

from app.core.logging import JsonFormatter, get_logger


@pytest.fixture
def formatter_pretty():
    return JsonFormatter(pretty=True)


@pytest.fixture
def formatter_compact():
    return JsonFormatter(pretty=False)


def _make_record(msg: str, level=logging.INFO, **extra):
    record = logging.LogRecord(
        name="test",
        level=level,
        pathname=__file__,
        lineno=10,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_format_non_llm_includes_extra_json(formatter_compact):
    record = _make_record("hello")
    record.custom = {"foo": "bar"}
    record.unserializable = object()
    formatted = formatter_compact.format(record)
    payload = json.loads(formatted)
    assert payload["message"] == "hello"
    assert payload["custom"] == {"foo": "bar"}
    assert "object at" in payload["unserializable"]


def test_format_includes_exception_trace(formatter_compact):
    try:
        raise ValueError("boom")
    except ValueError as exc:  # pragma: no cover - exercised by test
        record = _make_record("failure")
        record.exc_info = (exc.__class__, exc, exc.__traceback__)
    formatted = formatter_compact.format(record)
    payload = json.loads(formatted)
    assert "exception" in payload
    assert "ValueError" in payload["exception"]


def test_format_llm_input_with_pretty(formatter_pretty):
    record = _make_record("ignored", event="llm_request")
    record.direction = "input"
    record.model = "gemini-test"
    record.endpoint = "https://example.com"
    record.state = "draft"
    record.checklist = {"valid": True}
    record.payload = {"prompt": "line1\nline2"}

    rendered = formatter_pretty.format(record)
    assert "====== LLM INPUT ======" in rendered
    assert "gemini-test" in rendered
    assert "draft" in rendered
    assert "checklist" in rendered
    assert "line1\n  line2" in rendered  # pretty formatter keeps newline and indent


def test_llm_output_uses_response_field(formatter_pretty):
    record = _make_record("ignored", event="llm_response")
    record.direction = "output"
    record.response = {"text": "hello"}
    rendered = formatter_pretty.format(record)
    assert "====== LLM OUTPUT ======" in rendered
    assert "hello" in rendered


def test_render_structure_fallback_to_string(formatter_pretty):
    class NotSerializable:
        def __str__(self):
            return "<not-json>"

    rendered = formatter_pretty._render_structure(NotSerializable())
    assert rendered == "<not-json>"


def test_get_logger_installs_single_handler(monkeypatch):
    class DummySettings:
        LOG_LEVEL = "DEBUG"
        LLM_LOG_PRETTY = False

    monkeypatch.setattr("app.core.logging.get_settings", lambda: DummySettings())

    logger = get_logger("test-logger")
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1

    same = get_logger("test-logger")
    assert same is logger
    assert len(logger.handlers) == 1

    # cleanup handlers to avoid leaking into root configuration
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
