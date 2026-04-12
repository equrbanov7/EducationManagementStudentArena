"""
Supervision service layer.

Handles business logic for exam supervision: logging incidents,
enforcing violation limits, and managing recovery flows.
"""

from apps.exams.models import ExamAttempt, ExamSupervisionConfig, SupervisionIncident

# Event types that count as violations for limit enforcement
VIOLATION_EVENT_TYPES = frozenset(
    {
        "fullscreen_exited",
        "tab_switched",
        "window_blurred",
        "copy_attempt",
        "paste_attempt",
        "cut_attempt",
        "right_click_attempt",
        "keyboard_shortcut",
        "text_select_attempt",
        "grace_period_expired",
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
        attempt.mark_finished(status="submitted")
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
        attempt.save(update_fields=["supervision_status"])
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

    if grant_extra_chance:
        attempt.supervision_extra_chances += 1
        # Reset violation count to give student a fresh start
        attempt.supervision_violation_count = max(0, attempt.supervision_violation_count - 1)

    attempt.status = "in_progress"
    attempt.save(
        update_fields=[
            "supervision_status",
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


def get_attempt_supervision_status(attempt):
    """Get current supervision status and details for an attempt."""
    config = get_supervision_config(attempt.exam)
    if config is None:
        return {"supervised": False}

    return {
        "supervised": True,
        "supervision_status": attempt.supervision_status,
        "violation_count": attempt.supervision_violation_count,
        "max_violations": config.get_max_total_violations(),
        "extra_chances_used": attempt.supervision_extra_chances,
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


def get_supervision_monitor_data(organization, exam_id=None):
    """
    Get supervision monitor data for the teacher dashboard.
    Returns flagged students across all supervised exams.
    """
    incidents_qs = SupervisionIncident.objects.filter(
        organization=organization,
    ).select_related("exam", "student", "attempt")

    if exam_id:
        incidents_qs = incidents_qs.filter(exam_id=exam_id)

    # Get unique flagged attempts
    flagged_attempts = (
        ExamAttempt.objects.filter(
            exam__organization=organization,
            supervision_violation_count__gt=0,
        )
        .select_related("user", "exam", "exam__course")
        .order_by("-supervision_violation_count")
    )

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

        grace = form_data.get("supervision_grace_period", "15")
        grace_val = int(grace) if grace.isdigit() else 15
        config.grace_period_seconds = max(5, min(60, grace_val))

        max_v = form_data.get("supervision_max_violations", "3")
        max_val = int(max_v) if max_v.isdigit() else 3
        config.max_fullscreen_violations = max(1, min(20, max_val))

        config.violation_action = form_data.get("supervision_violation_action", "lock_exam")
        config.recovery_policy = form_data.get("supervision_recovery_policy", "teacher_controlled")

    config.save()
    return config
