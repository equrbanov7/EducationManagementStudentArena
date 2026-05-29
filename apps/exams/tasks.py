"""
Celery tasks for the exams app.

Currently hosts the supervision resume-window sweep: any attempt that a teacher
(or an automatic recovery flow) put back into the ``resumed`` state, but where
the student never actually returned within the per-exam resume window, is
auto-finished by the backend so it does not linger in the supervision monitor.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="exams.expire_stale_resumed_attempts")
def expire_stale_resumed_attempts():
    """
    Finish supervised attempts whose resume window has elapsed without the
    student returning.  Runs globally across all organizations; tenant
    isolation is preserved because each finished attempt records its incident
    under its own ``exam.organization``.

    Returns the number of attempts that were auto-finished.
    """
    # Imported lazily so the task module stays import-safe even when the app
    # registry is not fully loaded (e.g. during Celery autodiscovery).
    from apps.exams.services.supervision import sweep_expired_resume_windows

    expired = sweep_expired_resume_windows()
    if expired:
        logger.info("expire_stale_resumed_attempts: auto-finished %d attempt(s)", expired)
    return expired
