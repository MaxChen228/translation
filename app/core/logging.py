from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from app.core.settings import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        # include extras except default attributes
        for k, v in record.__dict__.items():
            if k in ("msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process"):
                continue
            if k.startswith("_"):
                continue
            if k not in base:
                try:
                    json.dumps(v)
                    base[k] = v
                except Exception:
                    base[k] = str(v)
        return json.dumps(base, ensure_ascii=False)


def get_logger(name: str = "app") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        settings = get_settings()
        level = getattr(logging, (settings.LOG_LEVEL or "INFO").upper(), logging.INFO)
        logger.setLevel(level)
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger

logger = get_logger("app")

