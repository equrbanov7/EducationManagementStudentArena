"""supervision paketi — actions."""

from django.utils import timezone

from apps.exams.features import exam_supervision_enabled, supervision_disabled_message
from apps.exams.models import ExamAttempt, SupervisionIncident

from ._shared import (
    _notify_student_via_ws,
    get_supervision_config,
)


def teacher_resume_attempt(attempt, teacher, grant_extra_chance=False):
    """
    Teacher resumes a locked/removed attempt.

    Returns True on success, raises ValueError on invalid state.
    """
    if not exam_supervision_enabled():
        raise ValueError(supervision_disabled_message())

    if attempt.supervision_status not in ("locked", "removed", "warned"):
        raise ValueError("Attempt is not in a locked/removed/warned state.")

    if attempt.is_finished:
        raise ValueError("Attempt is already finished and cannot be resumed.")

    # A manual teacher pause ("Müvəqqəti blokla") is the teacher's own decision,
    # not a student violation, so it is ALWAYS resumable — independent of the
    # exam clock, the recovery_policy, or even whether a supervision config is
    # still attached.  The teacher froze the screen, the teacher unfreezes it.
    is_manual_lock = bool(attempt.supervision_manual_lock)
    config = get_supervision_config(attempt.exam)

    if not is_manual_lock:
        # Auto-lock path: the exam clock still governs, and the recovery policy
        # decides whether a violation-locked attempt may be resumed at all.
        if attempt.expire_if_time_limit_reached():
            raise ValueError("Attempt time limit has expired and cannot be resumed.")

        if config is None:
            raise ValueError("No active supervision config for this exam.")

        if config.recovery_policy == "no_second_chance":
            raise ValueError("Recovery policy does not allow resumption.")

        if config.recovery_policy == "one_extra_chance" and attempt.supervision_extra_chances >= 1:
            raise ValueError("Student has already used their extra chance.")

    old_status = attempt.supervision_status
    attempt.supervision_status = "resumed"
    attempt.supervision_resumed_at = timezone.now()
    # Teacher acted → stop any lock countdown and clear the manual-pause flag so
    # the sweep can no longer auto-finish this attempt and a later auto-lock is
    # handled on its own terms.
    attempt.supervision_locked_at = None
    attempt.supervision_manual_lock = False

    # Granting an extra chance only makes sense for an auto-lock (a real
    # violation).  For a manual pause we keep the violation count untouched —
    # the teacher simply lets the student carry on.
    if grant_extra_chance and not is_manual_lock:
        attempt.supervision_extra_chances += 1
        # Reset violation count to give student a fresh start
        attempt.supervision_violation_count = max(0, attempt.supervision_violation_count - 1)

    attempt.status = "in_progress"
    attempt.save(
        update_fields=[
            "supervision_status",
            "supervision_resumed_at",
            "supervision_locked_at",
            "supervision_manual_lock",
            "supervision_extra_chances",
            "supervision_violation_count",
            "status",
        ]
    )
    # Final imtahan mərkəzində müvəqqəti dayandırma üçün saxlanmış cari səbəb
    # bərpadan sonra artıq aktiv müdaxilə deyil. Hadisənin özü incident tarixçəsində
    # qalır, tələbəyə göstərilən cari status isə təmizlənir.
    attempt.final_tickets.filter(removal_action="suspended").update(
        removal_action="",
        removal_reason="",
        removed_at=None,
        removed_by=None,
    )

    action_type = "teacher_granted_chance" if grant_extra_chance else "teacher_resumed"
    SupervisionIncident.objects.create(
        organization=attempt.exam.organization,
        exam=attempt.exam,
        attempt=attempt,
        student=attempt.user,
        event_type=action_type,
        severity="info",
        metadata={
            "teacher_id": teacher.id,
            "teacher_username": teacher.username,
            "previous_status": old_status,
            "extra_chance_granted": grant_extra_chance,
        },
        violation_count_at_time=attempt.supervision_violation_count,
        teacher_action=action_type,
    )

    _notify_student_via_ws(
        attempt.id,
        {
            "action": "resumed",
            "supervision_status": "resumed",
            "violation_count": attempt.supervision_violation_count,
            "max_violations": config.get_max_total_violations() if config else 3,
        },
    )

    return True


def teacher_lock_attempt(attempt, teacher, reason=""):
    """
    Teacher temporarily locks an attempt.

    The student's screen is locked (frozen) but the exam is NOT submitted.
    The teacher can later resume or permanently remove the student.

    Returns True on success, raises ValueError on invalid state.
    """
    if not exam_supervision_enabled():
        raise ValueError(supervision_disabled_message())

    if attempt.is_finished:
        raise ValueError("Attempt is already finished.")

    if attempt.supervision_status == "locked":
        raise ValueError("Attempt is already locked.")

    display_reason = (reason or "").strip()[:1000]
    old_status = attempt.supervision_status
    attempt.supervision_status = "locked"
    # Mark this as a *manual* teacher pause. Unlike an auto-lock we deliberately
    # do NOT set ``supervision_locked_at`` so the resume-window sweep can never
    # auto-finish a teacher-paused attempt — the teacher controls when it ends.
    attempt.supervision_manual_lock = True
    attempt.supervision_locked_at = None
    attempt.save(update_fields=["supervision_status", "supervision_manual_lock", "supervision_locked_at"])

    SupervisionIncident.objects.create(
        organization=attempt.exam.organization,
        exam=attempt.exam,
        attempt=attempt,
        student=attempt.user,
        event_type="auto_locked",
        severity="high",
        metadata={
            "teacher_id": teacher.id,
            "teacher_username": teacher.username,
            "previous_status": old_status,
            "reason": "teacher_temporary_lock",
            "display_reason": display_reason,
        },
        violation_count_at_time=attempt.supervision_violation_count,
        teacher_action="teacher_temporary_lock",
    )

    _notify_student_via_ws(
        attempt.id,
        {
            "action": "locked",
            "supervision_status": "locked",
            "reason": display_reason,
            "reason_code": "teacher_temporary_lock",
            "manual": True,
        },
    )

    return True


def teacher_stop_attempt(attempt, teacher, reason="", action="removed"):
    """
    Teacher force-stops a supervised attempt, submitting it immediately.

    Returns True on success, raises ValueError on invalid state.
    """
    if not exam_supervision_enabled():
        raise ValueError(supervision_disabled_message())

    if attempt.is_finished:
        raise ValueError("Attempt is already finished.")

    display_reason = (reason or "").strip()[:1000]
    old_status = attempt.supervision_status
    attempt.supervision_status = "removed"
    attempt.mark_finished(status="submitted", extra_update_fields=["supervision_status"])

    SupervisionIncident.objects.create(
        organization=attempt.exam.organization,
        exam=attempt.exam,
        attempt=attempt,
        student=attempt.user,
        event_type="auto_submitted",
        severity="critical",
        metadata={
            "teacher_id": teacher.id,
            "teacher_username": teacher.username,
            "previous_status": old_status,
            "reason": "teacher_force_stopped",
            "display_reason": display_reason,
            "intervention_action": action,
        },
        violation_count_at_time=attempt.supervision_violation_count,
        teacher_action="teacher_force_stopped",
    )

    _notify_student_via_ws(
        attempt.id,
        {
            "action": "stopped",
            "supervision_status": "removed",
            "is_finished": True,
            "reason": display_reason,
            "reason_code": "teacher_force_stopped",
            "intervention_action": action,
        },
    )

    # Qovulan tələbə → elektron jurnalda avtomatik F (0 bal). Körpü yuxarıdakı
    # ``mark_finished`` çağırışında planlanır (supervision_status ondan ƏVVƏL
    # "removed" olduğu üçün 0 bal yazılır).

    return True


def mark_student_returned(attempt):
    """
    Called when a student actually re-enters a supervised attempt after a
    teacher resume.  Clears the transient "resumed" state back to "active".

    No-op if the attempt is finished or not in the "resumed" state.
    """
    if attempt.is_finished or attempt.supervision_status != "resumed":
        return False

    attempt.supervision_status = "active"
    attempt.supervision_resumed_at = None
    attempt.save(update_fields=["supervision_status", "supervision_resumed_at"])
    return True


def sweep_expired_resume_windows(queryset=None):
    """
    Finish any LOCKED attempts whose teacher-resume window has elapsed without
    the teacher resuming.  The attempt is submitted with the student's current
    answers.  Safe to call from the periodic Celery task and from lazy monitor
    reads.  Returns the number of attempts auto-finished.

    Tenant isolation: callers pass an org-scoped queryset; the unscoped
    default is only intended for the global periodic sweep, and each finished
    attempt records an incident under its own ``exam.organization``.
    """
    if not exam_supervision_enabled():
        return 0

    if queryset is None:
        queryset = ExamAttempt.objects.all()

    candidates = (
        queryset.filter(
            supervision_status="locked",
            supervision_locked_at__isnull=False,
        )
        .exclude(
            status__in=["submitted", "expired"],
        )
        .select_related("exam", "exam__organization", "exam__supervision_config", "user")
    )

    expired = 0
    for attempt in candidates.iterator():
        if attempt.expire_if_resume_window_expired():
            expired += 1
    return expired
