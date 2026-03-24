"""
Logging filters for masking sensitive values before they are emitted.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping


class SensitiveDataFilter(logging.Filter):
    """Redact common secrets and PII from log records."""

    REDACTED = "[REDACTED]"

    _SENSITIVE_KEY_PART = re.compile(r"(password|pass|pwd|token|authorization|auth|secret)", re.IGNORECASE)
    _EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
    _PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s().-]{7,}\d)(?!\w)")
    _AUTH_RE = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?([^\s,;\"']+)")
    _KEY_VALUE_RE = re.compile(
        r"(?ix)"
        r"([\"']?(?:password|pass|pwd|token|authorization|auth[_-]?token|secret|email|phone)[\"']?\s*[:=]\s*)"
        r"([\"']?[^\"'\s,}\]]+[\"']?)"
    )
    _QUERY_VALUE_RE = re.compile(
        r"(?ix)" r"((?:password|pass|pwd|token|authorization|email|phone)\s*=\s*)" r"([^&\s]+)"
    )

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._sanitize(record.msg)
        if record.args:
            record.args = self._sanitize(record.args)
        return True

    def _sanitize(self, value):
        if isinstance(value, Mapping):
            sanitized: dict = {}
            for key, item in value.items():
                key_text = str(key)
                if self._SENSITIVE_KEY_PART.search(key_text):
                    sanitized[key] = self.REDACTED
                else:
                    sanitized[key] = self._sanitize(item)
            return sanitized

        if isinstance(value, tuple):
            return tuple(self._sanitize(item) for item in value)
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, set):
            return {self._sanitize(item) for item in value}
        if isinstance(value, str):
            return self._sanitize_text(value)
        return value

    def _sanitize_text(self, text: str) -> str:
        text = self._AUTH_RE.sub(r"\1" + self.REDACTED, text)
        text = self._KEY_VALUE_RE.sub(r"\1" + self.REDACTED, text)
        text = self._QUERY_VALUE_RE.sub(r"\1" + self.REDACTED, text)
        text = self._EMAIL_RE.sub(self.REDACTED, text)
        text = self._PHONE_RE.sub(self.REDACTED, text)
        return text


class RequestIdFilter(logging.Filter):
    """Inject the current request's ``request_id`` into every log record.

    Install this filter on any handler where per-request correlation is
    needed.  The filter reads ``request_id`` from Django's thread-local
    request store (set by ``RequestIdMiddleware``) and attaches it to each
    ``LogRecord`` as the string attribute ``request_id``.  When no request is
    active the field is set to ``"-"``.

    Usage in ``LOGGING``::

        "filters": {
            "request_id": {"()": "core.logging_filters.RequestIdFilter"},
        },
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from core.request_context import get_request_id

        record.request_id = get_request_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object.

    Fields emitted
    --------------
    ``timestamp``  ISO-8601 UTC timestamp
    ``level``      Log level name (INFO, WARNING, …)
    ``logger``     Logger name (``record.name``)
    ``message``    Rendered log message
    ``request_id`` Per-request correlation ID (set by ``RequestIdFilter``)
    ``exc_info``   Formatted exception traceback string, if present

    Usage in ``LOGGING``::

        "formatters": {
            "json": {"()": "core.logging_filters.JsonFormatter"},
        },
    """

    def format(self, record: logging.LogRecord) -> str:
        import json
        import traceback
        from datetime import datetime, timezone

        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload: dict = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }

        if record.exc_info:
            payload["exc_info"] = "".join(traceback.format_exception(*record.exc_info))

        return json.dumps(payload, ensure_ascii=False, default=str)
