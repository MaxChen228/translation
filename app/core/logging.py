from __future__ import annotations

import json
import logging
import textwrap
from typing import Any, Dict

from app.core.settings import get_settings


class JsonFormatter(logging.Formatter):
    def __init__(self, *, pretty: bool = False) -> None:
        super().__init__()
        self.pretty = bool(pretty)

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        if event in {"llm_request", "llm_response"}:
            return self._format_llm(record)

        base: Dict[str, Any] = {
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)

        for k, v in record.__dict__.items():
            if k in (
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            ):
                continue
            if k.startswith("_"):
                continue
            if k not in base:
                try:
                    json.dumps(v)
                    base[k] = v
                except Exception:
                    base[k] = str(v)

        indent = 2 if self.pretty else None
        return json.dumps(base, ensure_ascii=False, indent=indent)

    def _format_llm(self, record: logging.LogRecord) -> str:
        direction = getattr(record, "direction", "").lower() or "unknown"
        tag = "INPUT" if direction == "input" else "OUTPUT" if direction == "output" else direction.upper()
        model = getattr(record, "model", "-")
        endpoint = getattr(record, "endpoint", "-")
        header = f"====== LLM {tag} ======"

        lines = [
            header,
            f"level: {record.levelname}",
            f"model: {model}",
            f"endpoint: {endpoint}",
        ]
        state = getattr(record, "state", None)
        if state:
            lines.append(f"state: {state}")
        checklist = getattr(record, "checklist", None)
        if checklist:
            rendered_checklist = json.dumps(checklist, ensure_ascii=False)
            lines.append(f"checklist: {rendered_checklist}")

        body_key = "payload" if direction == "input" else "response"
        body = getattr(record, body_key, None)
        if body is None:
            body = getattr(record, "payload", None) or getattr(record, "response", None)

        if body is not None:
            rendered_body = self._render_structure(body)
            lines.append("body:")
            lines.append(textwrap.indent(rendered_body, "  "))

        lines.append("=" * len(header))
        return "\n".join(lines)

    def _render_structure(self, data: Any) -> str:
        try:
            indent = 2 if self.pretty else None
            rendered = json.dumps(data, ensure_ascii=False, indent=indent)
        except TypeError:
            return str(data)

        if not self.pretty:
            return rendered

        # 展示時將 \\n 還原為真正的換行，提升可讀性
        return rendered.replace("\\n", "\n")


def get_logger(name: str = "app") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        settings = get_settings()
        level = getattr(logging, (settings.LOG_LEVEL or "INFO").upper(), logging.INFO)
        logger.setLevel(level)
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter(pretty=bool(settings.LLM_LOG_PRETTY)))
        logger.addHandler(handler)
        logger.propagate = False
    return logger


logger = get_logger("app")

