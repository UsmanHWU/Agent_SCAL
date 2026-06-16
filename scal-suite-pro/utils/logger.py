"""
utils/logger.py
---------------
Structured logging setup for SCAL Suite.
Outputs JSON-compatible structured logs for observability pipelines.
"""

import logging
import sys
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """Formats log records as structured key=value pairs."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        level = record.levelname
        module = record.module
        msg = record.getMessage()
        base = f"ts={ts} level={level} module={module} msg=\"{msg}\""
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            base += f" exception=\"{exc_text.strip()}\""
        return base


def get_logger(name: str = "scal_suite") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
