"""
core/tasks.py
─────────────
Lightweight background-task foundation for EMS Arena.

Architecture
------------
The current implementation uses ``concurrent.futures.ThreadPoolExecutor`` to
run heavy work in a daemon thread so that HTTP responses are not blocked.
This is appropriate for the current project maturity where adding a full
broker (Celery/Redis-Queue) would be over-engineering.

Migration path to Celery
------------------------
When the project is ready to add a broker:

1. ``pip install celery[redis]``
2. Create ``config/celery.py`` and wire it into ``config/__init__.py``
3. Replace each ``defer(fn, *args, **kwargs)`` call with
   ``fn.delay(*args, **kwargs)`` after decorating the function with
   ``@shared_task``.

The thin API exposed here (``defer``) makes that migration a grep-and-replace.

Usage
-----
::

    from core.tasks import defer

    # Fire and forget – does not block the HTTP response
    defer(send_notification_email, user_id=user.pk, message="…")

Notes
-----
* Tasks run in a **daemon thread** – they are *not* persisted across process
  restarts.  Use this only for best-effort work (email notifications, cache
  warm-ups, audit log flushes) that can be safely dropped on restart.
* For mission-critical work that must not be lost, prefer a transactional
  outbox pattern or a proper task broker.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger(__name__)

# A single process-wide pool with a conservative size.  Keeps memory footprint
# small and avoids saturating the database connection pool.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="emsarena_task")

# Make pool available for shutdown during tests / graceful teardown
_pool_lock = threading.Lock()


def defer(fn: Callable, *args: Any, **kwargs: Any) -> None:
    """
    Submit *fn* to the background thread pool and return immediately.

    The caller should **not** rely on the return value of *fn*.  Any exception
    raised inside *fn* is caught, logged, and suppressed so that a failing
    background task never crashes the request that triggered it.

    Parameters
    ----------
    fn:
        A plain callable (function, bound method, lambda).
    *args, **kwargs:
        Positional and keyword arguments forwarded to *fn*.
    """

    def _run() -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("Background task %s raised an unhandled exception", getattr(fn, "__qualname__", fn))

    with _pool_lock:
        _pool.submit(_run)


# ──────────────────────────────────────────────────────────────────────────────
# Built-in heavy tasks
# ──────────────────────────────────────────────────────────────────────────────


def send_audit_log_async(*, action, user=None, organization=None, obj=None, **kwargs) -> None:
    """
    Write an audit log entry in a background thread.

    This avoids adding database latency to the critical request path for
    high-frequency operations (e.g. per-question scoring in live exams).

    Example::

        defer(send_audit_log_async,
              action=AuditAction.UPDATE, user=request.user, obj=session)
    """
    from core.audit import log_action

    log_action(action=action, user=user, organization=organization, obj=obj, **kwargs)


def export_exam_results_csv(*, exam_pk: int, recipient_email: str) -> None:
    """
    Placeholder for a heavy CSV export task.

    In production this would generate a CSV of exam results and email it to
    *recipient_email*.  The actual implementation is left for the feature
    branch that introduces result export.
    """
    logger.info(
        "export_exam_results_csv: exam_pk=%s recipient=%s  (not yet implemented)",
        exam_pk,
        recipient_email,
    )
