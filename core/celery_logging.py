"""Keep Celery's message diagnostics useful without logging mail content."""

import logging
from collections.abc import Mapping
from uuid import UUID

from core.logging_filters import SensitiveDataFilter

_MAIL_PREFIX = "core.email_tasks."


def protect_mail_headers(sender=None, headers=None, **kwargs):
    # Protocol v2 uses these display fields for events, inspection and trace logs.
    # The worker still receives the original arguments in the message body.
    if isinstance(sender, str) and sender.startswith(_MAIL_PREFIX) and headers is not None:
        headers["argsrepr"] = "[redacted]"
        headers["kwargsrepr"] = "[redacted]"


def _correlation_id(value):
    try:
        return str(UUID(str(value)))
    except ValueError:
        return "-"


class WorkerMessageFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        from celery.worker.consumer import consumer

        # These Celery diagnostics render the raw body before task dispatch.
        # Task display headers alone cannot protect an unregistered task here.
        self.rejections = {
            consumer.UNKNOWN_TASK_ERROR: "unregistered task",
            consumer.UNKNOWN_FORMAT: "unknown message format",
            consumer.INVALID_TASK_ERROR: "invalid task",
            consumer.MESSAGE_DECODE_ERROR: "undecodable message",
        }

    def filter(self, record):
        message = record.msg
        if not isinstance(message, str):
            return True
        reason = self.rejections.get(message)
        if reason:
            args = record.args
            headers = args[2] if isinstance(args, tuple) and len(args) > 2 else None
            task_id = headers.get("id") if isinstance(headers, Mapping) else None
            record.msg = "Celery discarded a message (%s, task id %s)"
            record.args = (reason, _correlation_id(task_id))
        elif record.name == "celery.concurrency.base" and message.startswith("TaskPool: Apply "):
            # Celery DEBUG logs include the serialized transport payload for every job.
            record.msg, record.args = "Task dispatched to the pool", ()
        elif isinstance(record.args, Mapping) and str(record.args.get("name", "")).startswith(_MAIL_PREFIX):
            # An SMTP exception can contain the recipient, subject or even message text.
            # Old queued messages can also contain unmasked argsrepr/kwargsrepr.
            context = record.args
            safe = {"name": context["name"], "id": _correlation_id(context.get("id"))}
            for key in ("description", "runtime"):
                if key in context:
                    safe[key] = context[key]
            for key in ("exc", "args", "kwargs", "return_value", "traceback"):
                if key in context:
                    safe[key] = "[redacted]"
            record.args = safe
            if hasattr(record, "data"):
                record.data = safe
        else:
            return True
        record.exc_info = record.exc_text = record.stack_info = None
        return True


def install_worker_filters(logger=None, **kwargs):
    # The worker can replace Django's console handler at startup.
    for handler in logger.handlers:
        if not any(isinstance(f, SensitiveDataFilter) for f in handler.filters):
            handler.addFilter(SensitiveDataFilter())
    for name in (
        "celery.worker.consumer.consumer",
        "celery.concurrency.base",
        "celery.worker.strategy",
        "celery.app.trace",
    ):
        source = logging.getLogger(name)
        if not any(isinstance(f, WorkerMessageFilter) for f in source.filters):
            source.addFilter(WorkerMessageFilter())
