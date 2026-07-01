"""supervision paketi — incidents."""

from django.utils import timezone

from apps.exams.features import exam_supervision_enabled
from apps.exams.models import SupervisionIncident

from ._shared import (
    get_supervision_config,
)
from .constants import (
    EVENT_SEVERITY_MAP,
    VIOLATION_EVENT_TYPES,
)


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
    if not exam_supervision_enabled():
        return None

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
