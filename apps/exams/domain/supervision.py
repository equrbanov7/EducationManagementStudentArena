"""
Exam Supervision / Anti-Cheating domain models.

Provides per-exam supervision configuration and incident tracking
for browser-based proctoring in the LMS platform.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import pgettext_lazy

User = get_user_model()


class ExamSupervisionConfig(models.Model):
    """
    Per-exam supervision configuration.
    Created when a teacher enables supervision mode on an exam.
    """

    VIOLATION_ACTION_CHOICES = (
        ("auto_submit", pgettext_lazy("supervision.config.choice.action", "auto_submit")),
        ("lock_exam", pgettext_lazy("supervision.config.choice.action", "lock_exam")),
        ("remove_student", pgettext_lazy("supervision.config.choice.action", "remove_student")),
        ("mark_suspicious", pgettext_lazy("supervision.config.choice.action", "mark_suspicious")),
    )

    RECOVERY_POLICY_CHOICES = (
        ("no_second_chance", pgettext_lazy("supervision.config.choice.recovery", "no_second_chance")),
        ("one_extra_chance", pgettext_lazy("supervision.config.choice.recovery", "one_extra_chance")),
        ("teacher_controlled", pgettext_lazy("supervision.config.choice.recovery", "teacher_controlled")),
    )

    TEMPLATE_CHOICES = (
        ("custom", pgettext_lazy("supervision.config.choice.template", "custom")),
        ("light", pgettext_lazy("supervision.config.choice.template", "light")),
        ("medium", pgettext_lazy("supervision.config.choice.template", "medium")),
        ("strict", pgettext_lazy("supervision.config.choice.template", "strict")),
    )

    exam = models.OneToOneField(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="supervision_config",
        verbose_name=pgettext_lazy("supervision.config.field", "exam"),
    )

    # Master toggle
    enabled = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("supervision.config.field", "enabled"),
        help_text=pgettext_lazy("supervision.config.help", "enabled"),
    )

    # Template preset
    template = models.CharField(
        max_length=20,
        choices=TEMPLATE_CHOICES,
        default="custom",
        verbose_name=pgettext_lazy("supervision.config.field", "template"),
    )

    # Core settings
    force_fullscreen = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("supervision.config.field", "force_fullscreen"),
        help_text=pgettext_lazy("supervision.config.help", "force_fullscreen"),
    )
    grace_period_seconds = models.PositiveIntegerField(
        default=15,
        verbose_name=pgettext_lazy("supervision.config.field", "grace_period_seconds"),
        help_text=pgettext_lazy("supervision.config.help", "grace_period_seconds"),
    )
    # Time window granted to a student to actually resume the exam after a
    # teacher/auto resume.  If the student does not return within this window,
    # the attempt is automatically finished by the backend.  Default 10 min.
    resume_window_seconds = models.PositiveIntegerField(
        default=600,
        verbose_name=pgettext_lazy("supervision.config.field", "resume_window_seconds"),
        help_text=pgettext_lazy("supervision.config.help", "resume_window_seconds"),
    )
    max_fullscreen_violations = models.PositiveIntegerField(
        default=3,
        verbose_name=pgettext_lazy("supervision.config.field", "max_fullscreen_violations"),
        help_text=pgettext_lazy("supervision.config.help", "max_fullscreen_violations"),
    )
    detect_tab_switch = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("supervision.config.field", "detect_tab_switch"),
        help_text=pgettext_lazy("supervision.config.help", "detect_tab_switch"),
    )
    block_copy_paste = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("supervision.config.field", "block_copy_paste"),
        help_text=pgettext_lazy("supervision.config.help", "block_copy_paste"),
    )
    disable_right_click = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("supervision.config.field", "disable_right_click"),
        help_text=pgettext_lazy("supervision.config.help", "disable_right_click"),
    )
    disable_text_selection = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("supervision.config.field", "disable_text_selection"),
        help_text=pgettext_lazy("supervision.config.help", "disable_text_selection"),
    )
    restrict_keyboard_shortcuts = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("supervision.config.field", "restrict_keyboard_shortcuts"),
        help_text=pgettext_lazy("supervision.config.help", "restrict_keyboard_shortcuts"),
    )

    # Violation action
    violation_action = models.CharField(
        max_length=20,
        choices=VIOLATION_ACTION_CHOICES,
        default="lock_exam",
        verbose_name=pgettext_lazy("supervision.config.field", "violation_action"),
        help_text=pgettext_lazy("supervision.config.help", "violation_action"),
    )

    # Recovery policy
    recovery_policy = models.CharField(
        max_length=20,
        choices=RECOVERY_POLICY_CHOICES,
        default="teacher_controlled",
        verbose_name=pgettext_lazy("supervision.config.field", "recovery_policy"),
        help_text=pgettext_lazy("supervision.config.help", "recovery_policy"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("supervision.config.meta", "singular")
        verbose_name_plural = pgettext_lazy("supervision.config.meta", "plural")

    def __str__(self):
        status = "ON" if self.enabled else "OFF"
        return f"Supervision [{status}] → {self.exam.title}"

    def get_max_total_violations(self):
        return self.max_fullscreen_violations

    @classmethod
    def get_template_defaults(cls, template_name):
        """Return default settings for a supervision template."""
        templates = {
            "light": {
                "force_fullscreen": False,
                "grace_period_seconds": 20,
                "resume_window_seconds": 900,
                "max_fullscreen_violations": 5,
                "detect_tab_switch": True,
                "block_copy_paste": False,
                "disable_right_click": False,
                "disable_text_selection": False,
                "restrict_keyboard_shortcuts": False,
                "violation_action": "mark_suspicious",
                "recovery_policy": "one_extra_chance",
            },
            "medium": {
                "force_fullscreen": True,
                "grace_period_seconds": 15,
                "resume_window_seconds": 600,
                "max_fullscreen_violations": 3,
                "detect_tab_switch": True,
                "block_copy_paste": True,
                "disable_right_click": True,
                "disable_text_selection": False,
                "restrict_keyboard_shortcuts": True,
                "violation_action": "lock_exam",
                "recovery_policy": "teacher_controlled",
            },
            "strict": {
                "force_fullscreen": True,
                "grace_period_seconds": 10,
                "resume_window_seconds": 300,
                "max_fullscreen_violations": 2,
                "detect_tab_switch": True,
                "block_copy_paste": True,
                "disable_right_click": True,
                "disable_text_selection": True,
                "restrict_keyboard_shortcuts": True,
                "violation_action": "auto_submit",
                "recovery_policy": "no_second_chance",
            },
        }
        return templates.get(template_name, {})


class SupervisionIncident(models.Model):
    """
    Records each supervision event during an exam attempt.
    Provides a complete audit trail of all proctoring events.
    """

    EVENT_TYPE_CHOICES = (
        ("fullscreen_exited", pgettext_lazy("supervision.incident.choice.event", "fullscreen_exited")),
        ("fullscreen_restored", pgettext_lazy("supervision.incident.choice.event", "fullscreen_restored")),
        ("tab_switched", pgettext_lazy("supervision.incident.choice.event", "tab_switched")),
        ("window_blurred", pgettext_lazy("supervision.incident.choice.event", "window_blurred")),
        ("window_focused", pgettext_lazy("supervision.incident.choice.event", "window_focused")),
        ("copy_attempt", pgettext_lazy("supervision.incident.choice.event", "copy_attempt")),
        ("paste_attempt", pgettext_lazy("supervision.incident.choice.event", "paste_attempt")),
        ("cut_attempt", pgettext_lazy("supervision.incident.choice.event", "cut_attempt")),
        ("right_click_attempt", pgettext_lazy("supervision.incident.choice.event", "right_click_attempt")),
        ("keyboard_shortcut", pgettext_lazy("supervision.incident.choice.event", "keyboard_shortcut")),
        ("text_select_attempt", pgettext_lazy("supervision.incident.choice.event", "text_select_attempt")),
        ("suspicious_repeated", pgettext_lazy("supervision.incident.choice.event", "suspicious_repeated")),
        ("grace_period_expired", pgettext_lazy("supervision.incident.choice.event", "grace_period_expired")),
        ("auto_locked", pgettext_lazy("supervision.incident.choice.event", "auto_locked")),
        ("auto_submitted", pgettext_lazy("supervision.incident.choice.event", "auto_submitted")),
        (
            "resume_window_expired",
            pgettext_lazy("supervision.incident.choice.event", "resume_window_expired"),
        ),
        ("teacher_resumed", pgettext_lazy("supervision.incident.choice.event", "teacher_resumed")),
        ("teacher_granted_chance", pgettext_lazy("supervision.incident.choice.event", "teacher_granted_chance")),
        ("exam_started_supervised", pgettext_lazy("supervision.incident.choice.event", "exam_started_supervised")),
        ("student_acknowledged", pgettext_lazy("supervision.incident.choice.event", "student_acknowledged")),
    )

    SEVERITY_CHOICES = (
        ("info", pgettext_lazy("supervision.incident.choice.severity", "info")),
        ("low", pgettext_lazy("supervision.incident.choice.severity", "low")),
        ("medium", pgettext_lazy("supervision.incident.choice.severity", "medium")),
        ("high", pgettext_lazy("supervision.incident.choice.severity", "high")),
        ("critical", pgettext_lazy("supervision.incident.choice.severity", "critical")),
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="supervision_incidents",
        verbose_name=pgettext_lazy("supervision.incident.field", "organization"),
    )
    exam = models.ForeignKey(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="supervision_incidents",
        verbose_name=pgettext_lazy("supervision.incident.field", "exam"),
    )
    attempt = models.ForeignKey(
        "exams.ExamAttempt",
        on_delete=models.CASCADE,
        related_name="supervision_incidents",
        verbose_name=pgettext_lazy("supervision.incident.field", "attempt"),
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="supervision_incidents",
        verbose_name=pgettext_lazy("supervision.incident.field", "student"),
    )
    event_type = models.CharField(
        max_length=30,
        choices=EVENT_TYPE_CHOICES,
        verbose_name=pgettext_lazy("supervision.incident.field", "event_type"),
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default="medium",
        verbose_name=pgettext_lazy("supervision.incident.field", "severity"),
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=pgettext_lazy("supervision.incident.field", "timestamp"),
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=pgettext_lazy("supervision.incident.field", "metadata"),
        help_text=pgettext_lazy("supervision.incident.help", "metadata"),
    )
    violation_count_at_time = models.PositiveIntegerField(
        default=0,
        verbose_name=pgettext_lazy("supervision.incident.field", "violation_count_at_time"),
    )
    teacher_action = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=pgettext_lazy("supervision.incident.field", "teacher_action"),
    )

    class Meta:
        verbose_name = pgettext_lazy("supervision.incident.meta", "singular")
        verbose_name_plural = pgettext_lazy("supervision.incident.meta", "plural")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["attempt", "-timestamp"]),
            models.Index(fields=["organization", "-timestamp"]),
            models.Index(fields=["exam", "-timestamp"]),
            models.Index(fields=["student", "-timestamp"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["severity"]),
        ]

    def __str__(self):
        return f"{self.student.username} - {self.get_event_type_display()} @ {self.timestamp}"

    @property
    def is_violation(self):
        """Whether this event counts as a violation."""
        violation_types = {
            "fullscreen_exited",
            "tab_switched",
            "window_blurred",
            "copy_attempt",
            "paste_attempt",
            "cut_attempt",
            "right_click_attempt",
            "keyboard_shortcut",
            "text_select_attempt",
            "suspicious_repeated",
            "grace_period_expired",
        }
        return self.event_type in violation_types


__all__ = [
    "ExamSupervisionConfig",
    "SupervisionIncident",
]
