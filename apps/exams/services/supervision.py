"""
Supervision service layer.

Handles business logic for exam supervision: logging incidents,
enforcing violation limits, and managing recovery flows.
"""

from django.utils import timezone

from apps.exams.models import ExamAttempt, ExamSupervisionConfig, SupervisionIncident

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
