"""supervision paketi — cəhdin nəzarət statusu.

Köhnə müəllim monitor UI-ı 2026-07-29-da silindiyi üçün onun data qatı
(flagged students, monitor data, live monitor, sessiya tarixləri) də
götürüldü. Burada yalnız hələ də istifadə olunan status funksiyası qalır:
tələbənin imtahan səhifəsi və `supervision_status_api` onu çağırır.
"""

from django.utils import timezone

from apps.exams.features import disabled_supervision_status, exam_supervision_enabled

from ._shared import get_supervision_config
from .interventions import get_attempt_intervention


def get_attempt_supervision_status(attempt):
    """Get current supervision status and details for an attempt."""
    if not exam_supervision_enabled():
        return disabled_supervision_status(attempt)

    config = get_supervision_config(attempt.exam)
    # Resume window countdown: how long the student still has to actually
    # return after a resume before the backend auto-finishes the attempt.
    resume_deadline = attempt.supervision_resume_deadline
    resume_seconds_remaining = None
    if resume_deadline is not None:
        resume_seconds_remaining = max(0, int((resume_deadline - timezone.now()).total_seconds()))

    config_payload = {}
    max_violations = 3
    resume_window_seconds = 0
    if config is not None:
        max_violations = config.get_max_total_violations()
        resume_window_seconds = config.resume_window_seconds
        config_payload = {
            "force_fullscreen": config.force_fullscreen,
            "grace_period_seconds": config.grace_period_seconds,
            "detect_tab_switch": config.detect_tab_switch,
            "block_copy_paste": config.block_copy_paste,
            "disable_right_click": config.disable_right_click,
            "disable_text_selection": config.disable_text_selection,
            "restrict_keyboard_shortcuts": config.restrict_keyboard_shortcuts,
            "violation_action": config.violation_action,
            "recovery_policy": config.recovery_policy,
        }

    intervention = get_attempt_intervention(attempt)
    return {
        "supervised": config is not None,
        "supervision_status": attempt.supervision_status,
        "manual_lock": bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked"),
        "violation_count": attempt.supervision_violation_count,
        "max_violations": max_violations,
        "extra_chances_used": attempt.supervision_extra_chances,
        "resume_window_seconds": resume_window_seconds,
        "resume_seconds_remaining": resume_seconds_remaining,
        "resume_deadline": resume_deadline.isoformat() if resume_deadline else None,
        "intervention_action": intervention["action"],
        "intervention_reason": intervention["reason"],
        "config": config_payload,
    }


def get_exam_question_total(exam):
    """
    Total number of questions a student is shown for this exam.

    Honours the project rule that a test may draw N random questions from a
    larger bank: when ``random_question_count`` is set we use it, otherwise we
    fall back to the number of questions actually attached to the exam.

    QEYD: köhnə monitor UI-ı silinsə də bu hesablama CANLIDIR — `snapshot.py`
    (yeni imtahan mərkəzi monitorunun snapshot-u) onu işlədir.
    """
    random_count = getattr(exam, "random_question_count", 0) or 0
    if random_count > 0:
        return random_count
    return exam.questions.count()
