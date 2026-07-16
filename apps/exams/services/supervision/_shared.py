"""supervision paketi — _shared."""

from django.utils import timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.exams.features import exam_supervision_enabled
from apps.exams.models import ExamSupervisionConfig


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


def notify_attempt_student(attempt_id: int, event_data: dict) -> None:
    """İmtahan tələbəsinə təhlükəsiz public WS bildirişi göndər."""
    _notify_student_via_ws(attempt_id, event_data)


def get_supervision_config(exam):
    """Get supervision config for an exam, or None if not enabled."""
    if not exam_supervision_enabled():
        return None
    try:
        config = exam.supervision_config
        if config.enabled:
            return config
    except ExamSupervisionConfig.DoesNotExist:
        pass
    return None


def save_supervision_config_from_form(exam, form_data):
    """
    Create or update supervision config from form data.
    Called when teacher saves exam with supervision settings.
    """
    if not exam_supervision_enabled():
        ExamSupervisionConfig.objects.filter(exam=exam, enabled=True).update(
            enabled=False,
            updated_at=timezone.now(),
        )
        return ExamSupervisionConfig.objects.filter(exam=exam).first()

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
