"""
Supervision service layer.

Handles business logic for exam supervision: logging incidents,
enforcing violation limits, and managing recovery flows.
"""

from django.utils import timezone

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from apps.exams.models import ExamAttempt, ExamSupervisionConfig, SupervisionIncident


def _notify_student_via_ws(attempt_id: int, event_data: dict) -> None:
    """
    Send a real-time supervision event to the student via WebSocket.
    Silently fails if channel layer is unavailable.
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        group_name = f"exam_supervision_{attempt_id}"
        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "supervision_event", "data": event_data},
        )
    except Exception:
        pass

# Event types that count as violations for limit enforcement.
#
# Clipboard / right-click / text-selection attempts are intentionally NOT
# counted: they are blocked outright on the client (the action never
# succeeds), but we still log them for the teacher's audit trail without
# burning a violation point.  Only events that indicate the student left the
# exam surface or tried to open developer tools / view source still count.
VIOLATION_EVENT_TYPES = frozenset(
    {
        "fullscreen_exited",
        "tab_switched",
        "window_blurred",
        "keyboard_shortcut",
        "grace_period_expired",
    }
)

# Events that are blocked on the client and logged for audit, but must never
# increment the violation count.  Kept explicit so the intent is documented
# and so the API can flag them to the frontend.
NON_COUNTING_EVENT_TYPES = frozenset(
    {
        "copy_attempt",
        "paste_attempt",
        "cut_attempt",
        "right_click_attempt",
        "text_select_attempt",
    }
)

# Severity mapping for automatic assignment
EVENT_SEVERITY_MAP = {
    "fullscreen_exited": "high",
    "fullscreen_restored": "info",
    "tab_switched": "high",
    "window_blurred": "medium",
    "window_focused": "info",
    "copy_attempt": "medium",
    "paste_attempt": "medium",
    "cut_attempt": "medium",
    "right_click_attempt": "low",
    "keyboard_shortcut": "medium",
    "text_select_attempt": "low",
    "suspicious_repeated": "high",
    "grace_period_expired": "critical",
    "auto_locked": "critical",
    "auto_submitted": "critical",
    "resume_window_expired": "critical",
    "teacher_resumed": "info",
    "teacher_granted_chance": "info",
    "exam_started_supervised": "info",
    "student_acknowledged": "info",
}


def get_supervision_config(exam):
    """Get supervision config for an exam, or None if not enabled."""
    try:
        config = exam.supervision_config
        if config.enabled:
            return config
    except ExamSupervisionConfig.DoesNotExist:
        pass
    return None


def log_supervision_incident(attempt, event_type, metadata=None):
    """
    Log a supervision incident and return the result with status info.

    Returns a dict with:
      - incident: the created SupervisionIncident
      - violation_count: current total violations for this attempt
      - limit_exceeded: whether the violation limit has been exceeded
      - action_taken: what action was taken (if any)
      - supervision_status: current supervision status of the attempt
    """
    exam = attempt.exam
    config = get_supervision_config(exam)

    if config is None:
        return None

    is_violation = event_type in VIOLATION_EVENT_TYPES
    severity = EVENT_SEVERITY_MAP.get(event_type, "medium")
    violation_count = attempt.supervision_violation_count

    if is_violation:
        violation_count += 1
        attempt.supervision_violation_count = violation_count
        attempt.save(update_fields=["supervision_violation_count"])

    incident = SupervisionIncident.objects.create(
        organization=exam.organization,
        exam=exam,
        attempt=attempt,
        student=attempt.user,
        event_type=event_type,
        severity=severity,
        metadata=metadata or {},
        violation_count_at_time=violation_count,
    )

    # Check if violation limit exceeded
    max_violations = config.get_max_total_violations()
    limit_exceeded = is_violation and violation_count >= max_violations
    action_taken = ""

    if limit_exceeded and attempt.supervision_status not in ("locked", "removed"):
        action_taken = _apply_violation_action(attempt, config, violation_count)

    return {
        "incident_id": incident.id,
        "violation_count": violation_count,
        "max_violations": max_violations,
        "limit_exceeded": limit_exceeded,
        "action_taken": action_taken,
        "supervision_status": attempt.supervision_status,
    }


def _apply_violation_action(attempt, config, violation_count):
    """Apply the configured violation action when limit is exceeded."""
    action = config.violation_action

    if action == "auto_submit":
        attempt.supervision_status = "removed"
        attempt.mark_finished(status="submitted", extra_update_fields=["supervision_status"])
        _log_system_incident(
            attempt,
            "auto_submitted",
            {
                "reason": "violation_limit_exceeded",
                "violation_count": violation_count,
            },
        )
        return "auto_submitted"

    elif action == "lock_exam":
        attempt.supervision_status = "locked"
        # Start the teacher resume window from this moment.
        attempt.supervision_locked_at = timezone.now()
        attempt.save(update_fields=["supervision_status", "supervision_locked_at"])
        _log_system_incident(
            attempt,
            "auto_locked",
            {
                "reason": "violation_limit_exceeded",
                "violation_count": violation_count,
            },
        )
        return "locked"

    elif action == "remove_student":
        attempt.supervision_status = "removed"
        attempt.save(update_fields=["supervision_status"])
        _log_system_incident(
            attempt,
            "auto_locked",
            {
                "reason": "student_removed",
                "violation_count": violation_count,
            },
        )
        return "removed"

    elif action == "mark_suspicious":
        attempt.supervision_status = "warned"
        attempt.save(update_fields=["supervision_status"])
        _log_system_incident(
            attempt,
            "suspicious_repeated",
            {
                "reason": "marked_suspicious",
                "violation_count": violation_count,
            },
        )
        return "marked_suspicious"

    return ""


def _log_system_incident(attempt, event_type, metadata):
    """Log a system-generated incident (auto-lock, auto-submit, etc.)."""
    SupervisionIncident.objects.create(
        organization=attempt.exam.organization,
        exam=attempt.exam,
        attempt=attempt,
        student=attempt.user,
        event_type=event_type,
        severity=EVENT_SEVERITY_MAP.get(event_type, "critical"),
        metadata=metadata,
        violation_count_at_time=attempt.supervision_violation_count,
    )


def teacher_resume_attempt(attempt, teacher, grant_extra_chance=False):
    """
    Teacher resumes a locked/removed attempt.

    Returns True on success, raises ValueError on invalid state.
    """
    if attempt.supervision_status not in ("locked", "removed", "warned"):
        raise ValueError("Attempt is not in a locked/removed/warned state.")

    if attempt.expire_if_time_limit_reached():
        raise ValueError("Attempt time limit has expired and cannot be resumed.")

    if attempt.is_finished:
        raise ValueError("Attempt is already finished and cannot be resumed.")

    config = get_supervision_config(attempt.exam)
    if config is None:
        raise ValueError("No active supervision config for this exam.")

    # Check recovery policy
    if config.recovery_policy == "no_second_chance":
        raise ValueError("Recovery policy does not allow resumption.")

    if config.recovery_policy == "one_extra_chance" and attempt.supervision_extra_chances >= 1:
        raise ValueError("Student has already used their extra chance.")

    old_status = attempt.supervision_status
    attempt.supervision_status = "resumed"
    attempt.supervision_resumed_at = timezone.now()
    # Teacher acted in time → stop the lock countdown so the sweep can no
    # longer auto-finish this attempt.
    attempt.supervision_locked_at = None

    if grant_extra_chance:
        attempt.supervision_extra_chances += 1
        # Reset violation count to give student a fresh start
        attempt.supervision_violation_count = max(0, attempt.supervision_violation_count - 1)

    attempt.status = "in_progress"
    attempt.save(
        update_fields=[
            "supervision_status",
            "supervision_resumed_at",
            "supervision_locked_at",
            "supervision_extra_chances",
            "supervision_violation_count",
            "status",
        ]
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

    _notify_student_via_ws(attempt.id, {
        "action": "resumed",
        "supervision_status": "resumed",
        "violation_count": attempt.supervision_violation_count,
        "max_violations": config.max_violations if config else 3,
    })

    return True


def teacher_lock_attempt(attempt, teacher):
    """
    Teacher temporarily locks a supervised attempt.

    The student's screen is locked (frozen) but the exam is NOT submitted.
    The teacher can later resume or permanently remove the student.

    Returns True on success, raises ValueError on invalid state.
    """
    if attempt.is_finished:
        raise ValueError("Attempt is already finished.")

    if attempt.supervision_status == "locked":
        raise ValueError("Attempt is already locked.")

    old_status = attempt.supervision_status
    attempt.supervision_status = "locked"
    attempt.supervision_locked_at = timezone.now()
    attempt.save(update_fields=["supervision_status", "supervision_locked_at"])

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
        },
        violation_count_at_time=attempt.supervision_violation_count,
        teacher_action="teacher_temporary_lock",
    )

    _notify_student_via_ws(attempt.id, {
        "action": "locked",
        "supervision_status": "locked",
        "reason": "teacher_temporary_lock",
    })

    return True


def teacher_stop_attempt(attempt, teacher):
    """
    Teacher force-stops a supervised attempt, submitting it immediately.

    Returns True on success, raises ValueError on invalid state.
    """
    if attempt.is_finished:
        raise ValueError("Attempt is already finished.")

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
        },
        violation_count_at_time=attempt.supervision_violation_count,
        teacher_action="teacher_force_stopped",
    )

    _notify_student_via_ws(attempt.id, {
        "action": "stopped",
        "supervision_status": "removed",
        "is_finished": True,
        "reason": "teacher_force_stopped",
    })

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


def get_attempt_supervision_status(attempt):
    """Get current supervision status and details for an attempt."""
    config = get_supervision_config(attempt.exam)
    if config is None:
        return {"supervised": False}

    # Resume window countdown: how long the student still has to actually
    # return after a resume before the backend auto-finishes the attempt.
    resume_deadline = attempt.supervision_resume_deadline
    resume_seconds_remaining = None
    if resume_deadline is not None:
        resume_seconds_remaining = max(0, int((resume_deadline - timezone.now()).total_seconds()))

    return {
        "supervised": True,
        "supervision_status": attempt.supervision_status,
        "violation_count": attempt.supervision_violation_count,
        "max_violations": config.get_max_total_violations(),
        "extra_chances_used": attempt.supervision_extra_chances,
        "resume_window_seconds": config.resume_window_seconds,
        "resume_seconds_remaining": resume_seconds_remaining,
        "resume_deadline": resume_deadline.isoformat() if resume_deadline else None,
        "config": {
            "force_fullscreen": config.force_fullscreen,
            "grace_period_seconds": config.grace_period_seconds,
            "detect_tab_switch": config.detect_tab_switch,
            "block_copy_paste": config.block_copy_paste,
            "disable_right_click": config.disable_right_click,
            "disable_text_selection": config.disable_text_selection,
            "restrict_keyboard_shortcuts": config.restrict_keyboard_shortcuts,
            "violation_action": config.violation_action,
            "recovery_policy": config.recovery_policy,
        },
    }


def get_flagged_students_for_exam(exam, organization):
    """Get summary of flagged students for a specific exam."""
    attempts = (
        ExamAttempt.objects.filter(
            exam=exam,
            exam__organization=organization,
            supervision_violation_count__gt=0,
        )
        .select_related("user", "exam")
        .order_by("-supervision_violation_count")
    )

    return [
        {
            "attempt_id": a.id,
            "student_id": a.user_id,
            "student_name": a.user.get_full_name() or a.user.username,
            "student_username": a.user.username,
            "violation_count": a.supervision_violation_count,
            "supervision_status": a.supervision_status,
            "started_at": a.started_at,
            "status": a.status,
        }
        for a in attempts
    ]


def get_supervision_monitor_data(organization, exam_id=None, exam_queryset=None):
    """
    Get supervision monitor data for the teacher dashboard.
    Returns flagged students across all supervised exams.
    """
    # Lazily finish any stale "resumed" attempts (student never returned within
    # the resume window) before building the view, scoped to this org so the
    # monitor never shows phantom open rows for exams that ended long ago.
    sweep_qs = ExamAttempt.objects.filter(exam__organization=organization)
    if exam_queryset is not None:
        sweep_qs = sweep_qs.filter(exam__in=exam_queryset)
    if exam_id:
        sweep_qs = sweep_qs.filter(exam_id=exam_id)
    sweep_expired_resume_windows(sweep_qs)

    incidents_qs = SupervisionIncident.objects.filter(
        organization=organization,
    ).select_related("exam", "student", "attempt")
    if exam_queryset is not None:
        incidents_qs = incidents_qs.filter(exam__in=exam_queryset)

    if exam_id:
        incidents_qs = incidents_qs.filter(exam_id=exam_id)

    # Get unique flagged attempts.  ``exam__supervision_config`` is selected so
    # the per-row ``supervision_resume_deadline`` countdown does not trigger an
    # extra query for every resumed attempt.
    flagged_attempts = (
        ExamAttempt.objects.filter(
            exam__organization=organization,
            supervision_violation_count__gt=0,
        )
        .select_related("user", "exam", "exam__course", "exam__supervision_config")
        .order_by("-supervision_violation_count")
    )
    if exam_queryset is not None:
        flagged_attempts = flagged_attempts.filter(exam__in=exam_queryset)

    if exam_id:
        flagged_attempts = flagged_attempts.filter(exam_id=exam_id)

    # Get supervised exams list
    supervised_exams = (
        ExamSupervisionConfig.objects.filter(
            exam__organization=organization,
            enabled=True,
        )
        .select_related("exam")
        .values_list("exam__id", "exam__title")
    )
    if exam_queryset is not None:
        supervised_exams = supervised_exams.filter(exam__in=exam_queryset)

    # Summary stats
    total_incidents = incidents_qs.filter(
        event_type__in=VIOLATION_EVENT_TYPES,
    ).count()

    return {
        "flagged_attempts": flagged_attempts,
        "supervised_exams": list(supervised_exams),
        "total_incidents": total_incidents,
        "incidents_qs": incidents_qs,
    }


def get_exam_question_total(exam):
    """
    Total number of questions a student is shown for this exam.

    Honours the project rule that a test may draw N random questions from a
    larger bank: when ``random_question_count`` is set we use it, otherwise we
    fall back to the number of questions actually attached to the exam.
    """
    random_count = getattr(exam, "random_question_count", 0) or 0
    if random_count > 0:
        return random_count
    return exam.questions.count()


def _attempt_live_state(attempt):
    """
    Map an attempt to a coarse live state used by the monitor map / stats.

    Returns one of: ``finished`` (submitted/expired), ``flagged`` (locked or
    removed by supervision), ``in_progress`` (actively taking the exam).
    Students who never started have no attempt row, so they are handled by the
    caller (``not_entered``) rather than here.
    """
    if attempt.is_finished:
        return "finished"
    if attempt.supervision_status in ("locked", "removed"):
        return "flagged"
    return "in_progress"


def get_exam_live_monitor_data(exam, date_value=None):
    """
    Live monitoring snapshot for a single exam session.

    Scope note: ``exam`` MUST already be tenant/permission scoped by the caller
    (the view resolves it through ``_supervision_exam_queryset``). This function
    never widens scope — it only reads attempts/incidents for the given exam.

    ``date_value`` optionally filters to attempts started on that calendar day
    (the "today" button / date picker), since one exam can be run on several
    dates. When ``None`` all sessions are included.

    Returns a JSON-serialisable dict consumed by both the initial page render
    and the polling endpoint, so the two never drift apart.
    """
    from django.db.models import Count

    # ``answered_count`` is annotated so each student's progress is read in the
    # single attempts query instead of one COUNT per row (avoids N+1).
    attempts_qs = (
        ExamAttempt.objects.filter(exam=exam)
        .select_related("user", "exam", "exam__supervision_config")
        .annotate(answered_count=Count("answers", distinct=True))
        .order_by("started_at")
    )
    if date_value is not None:
        attempts_qs = attempts_qs.filter(started_at__date=date_value)

    total_questions = get_exam_question_total(exam)

    students = []
    counts = {"entered": 0, "in_progress": 0, "finished": 0, "flagged": 0, "not_entered": 0}
    status_dist = {"active": 0, "warned": 0, "locked": 0, "removed": 0, "resumed": 0}
    progress_sum = 0
    progress_n = 0

    for a in attempts_qs:
        counts["entered"] += 1
        state = _attempt_live_state(a)
        counts[state] = counts.get(state, 0) + 1
        if a.supervision_status in status_dist:
            status_dist[a.supervision_status] += 1

        answered = a.answered_count
        progress_pct = int(round((answered / total_questions) * 100)) if total_questions else 0
        if not a.is_finished:
            progress_sum += progress_pct
            progress_n += 1

        # Coarse violation severity tier drives the map cell colour. Kept here
        # (not the client) so the rule stays in one place and matches the feed.
        vio = a.supervision_violation_count
        if a.supervision_status == "removed":
            vio_level = "removed"
        elif vio >= 6:
            vio_level = "critical"
        elif vio >= 3:
            vio_level = "high"
        elif vio >= 1:
            vio_level = "low"
        else:
            vio_level = "none"

        # Lightweight raw score (correct vs answered) — only meaningful once the
        # attempt is finished. We avoid the heavier per-test result calculation
        # here to keep the monitor query cheap; the modal shows the precise score.
        graded = a.correct_count + a.wrong_count
        raw_score = int(round(a.correct_count * 100 / graded)) if graded else None

        students.append(
            {
                "attempt_id": a.id,
                "student_id": a.user_id,
                "name": a.user.get_full_name() or a.user.username,
                "username": a.user.username,
                "state": state,
                "supervision_status": a.supervision_status,
                "violation_count": vio,
                "violation_level": vio_level,
                "answered": answered,
                "total_questions": total_questions,
                "progress_pct": progress_pct,
                "correct_count": a.correct_count,
                "wrong_count": a.wrong_count,
                "score_percent": raw_score if a.is_finished else None,
                "checked_by_teacher": a.checked_by_teacher,
                "teacher_score": a.teacher_score,
                "started_at": a.started_at.isoformat() if a.started_at else None,
                "finished_at": a.finished_at.isoformat() if a.finished_at else None,
                "is_finished": a.is_finished,
            }
        )

    # Recent suspicious events for the live feed (most recent first).
    incidents_qs = (
        SupervisionIncident.objects.filter(exam=exam, event_type__in=VIOLATION_EVENT_TYPES)
        .select_related("student")
        .order_by("-timestamp")
    )
    if date_value is not None:
        incidents_qs = incidents_qs.filter(timestamp__date=date_value)

    recent_incidents = [
        {
            "student_name": inc.student.get_full_name() or inc.student.username,
            "event_type": inc.event_type,
            "severity": inc.severity,
            "timestamp": inc.timestamp.isoformat(),
        }
        for inc in incidents_qs[:25]
    ]

    # Violation-type distribution for the chart (single aggregation query).
    from django.db.models import Count as _Count

    vtype_dist = dict(incidents_qs.values("event_type").annotate(c=_Count("id")).values_list("event_type", "c"))

    avg_progress = int(round(progress_sum / progress_n)) if progress_n else 0

    return {
        "exam_id": exam.id,
        "exam_title": exam.title,
        "total_questions": total_questions,
        "counts": counts,
        "status_dist": status_dist,
        "violation_type_dist": vtype_dist,
        "avg_progress": avg_progress,
        "total_violations": incidents_qs.count(),
        "students": students,
        "recent_incidents": recent_incidents,
    }


def get_exam_session_dates(exam):
    """
    Distinct calendar dates on which this exam has been attempted, newest first.

    Used to populate the date filter so a teacher can isolate one sitting of an
    exam that is run on multiple days.
    """
    from django.db.models.functions import TruncDate

    return list(
        ExamAttempt.objects.filter(exam=exam)
        .annotate(day=TruncDate("started_at"))
        .values_list("day", flat=True)
        .distinct()
        .order_by("-day")
    )


def get_attempt_live_snapshot(attempt):
    """
    Detailed live snapshot of a single student's in-progress (or finished)
    attempt — what they have answered so far and every supervision event.

    This is read-only monitoring: it never mutates the attempt, so a teacher can
    "look over the shoulder" without blocking the student. Scope MUST be enforced
    by the caller (exam already tenant/permission scoped).
    """
    answers = attempt.answers.select_related("question").prefetch_related("selected_options").order_by("question_id")

    total_questions = get_exam_question_total(attempt.exam)
    answer_rows = []
    for ans in answers:
        selected = [opt.text for opt in ans.selected_options.all()] if hasattr(ans, "selected_options") else []
        question_type = ""
        if ans.question:
            question_type = getattr(ans.question, "question_type", "") or ""
        answer_rows.append(
            {
                "question_text": (ans.question.text or "")[:300] if ans.question else "",
                "question_type": question_type,
                "selected_options": selected,
                "text_answer": (ans.text_answer or "")[:1000],
                "has_paint": bool(getattr(ans, "has_paint", False)),
                "updated_at": ans.updated_at.isoformat() if ans.updated_at else None,
            }
        )

    incidents = SupervisionIncident.objects.filter(attempt=attempt).order_by("-timestamp")[:50]
    incident_rows = [
        {
            "event_type": inc.event_type,
            "event_display": inc.get_event_type_display(),
            "severity": inc.severity,
            "timestamp": inc.timestamp.isoformat(),
            "violation_count_at_time": inc.violation_count_at_time,
        }
        for inc in incidents
    ]

    # Precise score for a single attempt — safe to compute here (one attempt,
    # not the whole list). Only surfaced once the attempt is finished.
    score_percent = None
    if attempt.is_finished:
        try:
            score_percent = round(float(attempt.score_percent), 1)
        except Exception:
            graded = attempt.correct_count + attempt.wrong_count
            score_percent = round(attempt.correct_count * 100 / graded, 1) if graded else None

    return {
        "attempt_id": attempt.id,
        "student_name": attempt.user.get_full_name() or attempt.user.username,
        "student_username": attempt.user.username,
        "supervision_status": attempt.supervision_status,
        "violation_count": attempt.supervision_violation_count,
        "answered": len(answer_rows),
        "total_questions": total_questions,
        "correct_count": attempt.correct_count,
        "wrong_count": attempt.wrong_count,
        "score_percent": score_percent,
        "checked_by_teacher": attempt.checked_by_teacher,
        "teacher_score": attempt.teacher_score,
        "is_finished": attempt.is_finished,
        "status": attempt.status,
        "exam_title": attempt.exam.title,
        "exam_type": getattr(attempt.exam, "exam_type", "") or "",
        "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
        "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
        "answers": answer_rows,
        "incidents": incident_rows,
    }


def save_supervision_config_from_form(exam, form_data):
    """
    Create or update supervision config from form data.
    Called when teacher saves exam with supervision settings.
    """
    enabled = form_data.get("supervision_enabled") == "on"

    config, created = ExamSupervisionConfig.objects.get_or_create(
        exam=exam,
        defaults={"enabled": enabled},
    )

    config.enabled = enabled

    if not enabled:
        config.save(update_fields=["enabled", "updated_at"])
        return config

    # Apply template if selected
    template = form_data.get("supervision_template", "custom")
    config.template = template

    if template != "custom":
        defaults = ExamSupervisionConfig.get_template_defaults(template)
        for key, value in defaults.items():
            setattr(config, key, value)
    else:
        # Read individual settings
        config.force_fullscreen = form_data.get("supervision_force_fullscreen") == "on"
        config.detect_tab_switch = form_data.get("supervision_detect_tab_switch") == "on"
        config.block_copy_paste = form_data.get("supervision_block_copy_paste") == "on"
        config.disable_right_click = form_data.get("supervision_disable_right_click") == "on"
        config.disable_text_selection = form_data.get("supervision_disable_text_selection") == "on"
        config.restrict_keyboard_shortcuts = form_data.get("supervision_restrict_shortcuts") == "on"

        try:
            grace_val = int(form_data.get("supervision_grace_period", "15"))
        except (ValueError, TypeError):
            grace_val = 15
        config.grace_period_seconds = max(5, min(60, grace_val))

        try:
            max_val = int(form_data.get("supervision_max_violations", "3"))
        except (ValueError, TypeError):
            max_val = 3
        config.max_fullscreen_violations = max(1, min(20, max_val))

        config.violation_action = form_data.get("supervision_violation_action", "lock_exam")
        config.recovery_policy = form_data.get("supervision_recovery_policy", "teacher_controlled")

    # Resume window is teacher-configurable regardless of template: minutes in
    # the form, stored as seconds.  Clamp to 1–30 min (0 disables auto-finish).
    resume_raw = form_data.get("supervision_resume_window_minutes")
    if resume_raw not in (None, ""):
        try:
            resume_minutes = int(resume_raw)
        except (ValueError, TypeError):
            resume_minutes = 10
        if resume_minutes <= 0:
            config.resume_window_seconds = 0  # disables the auto-finish window
        else:
            config.resume_window_seconds = max(60, min(1800, resume_minutes * 60))

    config.save()
    return config
