from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.assignments.models import Submission as AssignmentSubmission
from apps.exams.models import ExamAttempt
from apps.labs.models import LabSubmission
from apps.projects.models import ProjectSubmission
from apps.notifications.services import notify_student_about_feedback, notify_teacher_about_submission


def _cache_previous_state(sender, instance, field_names):
    if not instance.pk:
        instance._notification_previous_state = {}
        return

    instance._notification_previous_state = sender.objects.filter(pk=instance.pk).values(*field_names).first() or {}


def _graded_payload_changed(previous_state, instance, *, score_field="grade", feedback_field="feedback"):
    previous_status = previous_state.get("status")
    previous_score = previous_state.get(score_field)
    previous_feedback = previous_state.get(feedback_field) or ""
    current_feedback = getattr(instance, feedback_field, "") or ""

    return (
        previous_status != getattr(instance, "status", None)
        or previous_score != getattr(instance, score_field, None)
        or previous_feedback != current_feedback
    )


@receiver(pre_save, sender=AssignmentSubmission)
def _cache_assignment_submission_state(sender, instance, **kwargs):
    _cache_previous_state(sender, instance, ("status", "grade", "feedback"))


@receiver(post_save, sender=AssignmentSubmission)
def _notify_assignment_submission_events(sender, instance, created, **kwargs):
    previous_state = getattr(instance, "_notification_previous_state", {})

    if created and instance.status == "submitted":
        notify_teacher_about_submission(task=instance.assignment, student=instance.user, task_kind="assignment")
        return

    if instance.status == "graded" and _graded_payload_changed(previous_state, instance):
        notify_student_about_feedback(task=instance.assignment, student=instance.user, task_kind="assignment")


@receiver(pre_save, sender=ProjectSubmission)
def _cache_project_submission_state(sender, instance, **kwargs):
    _cache_previous_state(sender, instance, ("status", "grade", "feedback"))


@receiver(post_save, sender=ProjectSubmission)
def _notify_project_submission_events(sender, instance, created, **kwargs):
    previous_state = getattr(instance, "_notification_previous_state", {})

    if created and instance.status == "pending":
        notify_teacher_about_submission(task=instance.project, student=instance.student, task_kind="project")
        return

    if instance.status == "graded" and _graded_payload_changed(previous_state, instance):
        notify_student_about_feedback(task=instance.project, student=instance.student, task_kind="project")


@receiver(pre_save, sender=LabSubmission)
def _cache_lab_submission_state(sender, instance, **kwargs):
    _cache_previous_state(sender, instance, ("status", "score", "feedback"))


@receiver(post_save, sender=LabSubmission)
def _notify_lab_submission_events(sender, instance, created, **kwargs):
    previous_state = getattr(instance, "_notification_previous_state", {})

    if created and instance.status in {"submitted", "late"}:
        notify_teacher_about_submission(task=instance.assignment.lab, student=instance.assignment.student, task_kind="lab")
        return

    if instance.status == "graded" and _graded_payload_changed(
        previous_state,
        instance,
        score_field="score",
        feedback_field="feedback",
    ):
        notify_student_about_feedback(task=instance.assignment.lab, student=instance.assignment.student, task_kind="lab")


@receiver(pre_save, sender=ExamAttempt)
def _cache_exam_attempt_state(sender, instance, **kwargs):
    _cache_previous_state(sender, instance, ("status",))


@receiver(post_save, sender=ExamAttempt)
def _notify_exam_attempt_events(sender, instance, created, **kwargs):
    if created:
        return

    previous_state = getattr(instance, "_notification_previous_state", {})
    previous_status = previous_state.get("status")
    current_status = instance.status

    if previous_status != current_status and current_status in {"submitted", "expired"}:
        notify_teacher_about_submission(task=instance.exam, student=instance.user, task_kind="exam")
