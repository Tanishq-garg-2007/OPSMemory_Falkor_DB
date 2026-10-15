"""Structured logging with secret redaction and tenant context."""
import logging
import json
import sys
from typing import Any, Dict


REDACTED_KEYS = {"api_key", "x-tenant-key", "authorization", "password", "token", "secret"}


def redact_sensitive(data: Any) -> Any:
    """Recursively redact sensitive keys from dictionary or string."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if any(secret in str(k).lower() for secret in REDACTED_KEYS):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_sensitive(v)
        return redacted
    elif isinstance(data, list):
        return [redact_sensitive(item) for item in data]
    return data


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "tenant_id"):
            payload["tenant_id"] = getattr(record, "tenant_id")
        if hasattr(record, "extra_data"):
            payload["extra"] = redact_sensitive(getattr(record, "extra_data"))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_logger(name: str = "opsmemory") -> logging.Logger:
    """Get or configure logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
