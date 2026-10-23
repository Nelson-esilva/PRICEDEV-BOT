from __future__ import annotations

import logging
import re
import sys

import structlog


class _RedactFeedKey(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = re.sub(r"(/apikey/)[^/\s\"']+", r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    for handler in logging.getLogger().handlers:
        if not any(isinstance(item, _RedactFeedKey) for item in handler.filters):
            handler.addFilter(_RedactFeedKey())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
