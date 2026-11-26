"""Celery mail registration and log confidentiality for both new and queued messages."""

import logging
from unittest import TestCase
from uuid import uuid4

from celery import signals
from celery.app import trace
from celery.worker.consumer import consumer

from config.celery import app
from core.celery_logging import WorkerMessageFilter

TASK = "core.email_tasks.send_template_email_async"
PRIVATE = "private synthetic mail context"
TASK_ID = str(uuid4())


class CeleryMailLoggingTests(TestCase):
    def test_worker_imports_all_four_mail_tasks_by_name(self):
        # Keep this assertion independent of tasks eagerly imported by other tests.
        self.assertIn("core.email_tasks", app.loader.default_modules)
        app.loader.import_default_modules()
        self.assertEqual(
            {name for name in app.tasks if name.startswith("core.email_tasks.")},
            {
                "core.email_tasks.send_account_otp_email",
                "core.email_tasks.send_verification_otp_email",
                TASK,
                "core.email_tasks.send_new_post_notification_email",
            },
        )

    def test_publish_masks_only_mail_display_headers(self):
        for name, expected in ((TASK, "[redacted]"), ("other.task", PRIVATE)):
            headers = {"argsrepr": PRIVATE, "kwargsrepr": PRIVATE, "id": TASK_ID}
            body = ((), {"context": PRIVATE}, {})
            signals.before_task_publish.send(sender=name, headers=headers, body=body)
            self.assertEqual(headers, {"argsrepr": expected, "kwargsrepr": expected, "id": TASK_ID})
            self.assertEqual(body[1]["context"], PRIVATE)

    def test_worker_discards_raw_payload_diagnostics(self):
        f = WorkerMessageFilter()
        for fmt, args in (
            (consumer.UNKNOWN_TASK_ERROR, (TASK, PRIVATE, {"id": TASK_ID, "kwargsrepr": PRIVATE}, {"detail": PRIVATE})),
            (consumer.UNKNOWN_FORMAT, (PRIVATE,)),
            (consumer.INVALID_TASK_ERROR, (ValueError(PRIVATE), PRIVATE)),
            (consumer.MESSAGE_DECODE_ERROR, (ValueError(PRIVATE), "json", "utf8", PRIVATE, PRIVATE)),
        ):
            with self.subTest(fmt=fmt):
                record = logging.LogRecord(consumer.__name__, logging.ERROR, "", 1, fmt, args, None)
                self.assertTrue(f.filter(record))
                self.assertIn("Celery discarded a message", record.getMessage())
                if fmt == consumer.UNKNOWN_TASK_ERROR:
                    self.assertIn(TASK_ID, record.getMessage())
                self.assertNotIn(PRIVATE, logging.Formatter().format(record))

    def test_older_mail_headers_and_provider_exception_are_hidden_from_trace(self):
        f = WorkerMessageFilter()
        try:
            raise RuntimeError(PRIVATE)
        except RuntimeError as exc:
            context = dict(name=TASK, id=TASK_ID, exc=repr(exc), description="raised unexpected", kwargs=PRIVATE)
            record = logging.LogRecord(
                trace.__name__, logging.ERROR, "", 1, trace.LOG_FAILURE, (context,), (type(exc), exc, exc.__traceback__)
            )
            record.data = context
            self.assertTrue(f.filter(record))
        self.assertIn(TASK_ID, logging.Formatter().format(record))
        self.assertNotIn(PRIVATE, repr((record.data, record.args, record.exc_info, record.exc_text)))
        self.assertNotIn(PRIVATE, logging.Formatter().format(record))

    def test_unrelated_task_diagnostics_are_preserved(self):
        context = {"name": "other.task", "id": TASK_ID, "exc": "ordinary failure", "description": "failed"}
        record = logging.LogRecord(trace.__name__, logging.ERROR, "", 1, trace.LOG_FAILURE, (context,), None)
        self.assertTrue(WorkerMessageFilter().filter(record))
        self.assertIn("ordinary failure", record.getMessage())
