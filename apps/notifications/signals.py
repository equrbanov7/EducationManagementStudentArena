"""Consumer-app submission hadisələrinə bildiriş reciverləri.

M2 (2026-07-02): sender-lər lazy "app_label.Model" string-ləri ilə verilir —
notifications artıq istehlakçı app-ların modellərini İMPORT ETMİR (4 dövri
modul asılılığı əridildi; bax scripts/module_deps.py). Django receiver-in
string-sender dəstəyi rəsmi API-dir; davranış birə-birdir.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.notifications.services import notify_student_about_feedback, notify_teacher_about_submission
from core.rls import set_rls_tenant
from core.rls_pooling import rls_worker_atomic


def _submission_organization_id(instance):
    assignment = getattr(instance, "assignment", None)
    if assignment is not None:
        lab = getattr(assignment, "lab", None)
        if lab is not None:
            course = getattr(lab, "course", None)
            if course is not None:
                return getattr(course, "organization_id", None)

        course = getattr(assignment, "course", None)
        if course is not None:
            return getattr(course, "organization_id", None)

    project = getattr(instance, "project", None)
    if project is not None:
        course = getattr(project, "course", None)
        if course is not None:
            return getattr(course, "organization_id", None)

    exam = getattr(instance, "exam", None)
    if exam is not None:
        return getattr(exam, "organization_id", None)

    return None


def _set_tenant_for_instance(instance):
    org_id = _submission_organization_id(instance)
    if org_id:
        set_rls_tenant(org_id)


def _cache_previous_state(sender, instance, field_names):
    with rls_worker_atomic():
        _set_tenant_for_instance(instance)
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


@receiver(pre_save, sender="assignments.Submission")
def _cache_assignment_submission_state(sender, instance, **kwargs):
    _cache_previous_state(sender, instance, ("status", "grade", "feedback"))


@receiver(post_save, sender="assignments.Submission")
def _notify_assignment_submission_events(sender, instance, created, **kwargs):
    with rls_worker_atomic():
        _set_tenant_for_instance(instance)
        previous_state = getattr(instance, "_notification_previous_state", {})

        if created and instance.status == "submitted":
            notify_teacher_about_submission(task=instance.assignment, student=instance.user, task_kind="assignment")
            return

        if instance.status == "graded" and _graded_payload_changed(previous_state, instance):
            notify_student_about_feedback(task=instance.assignment, student=instance.user, task_kind="assignment")


@receiver(pre_save, sender="projects.ProjectSubmission")
def _cache_project_submission_state(sender, instance, **kwargs):
    _cache_previous_state(sender, instance, ("status", "grade", "feedback"))


@receiver(post_save, sender="projects.ProjectSubmission")
def _notify_project_submission_events(sender, instance, created, **kwargs):
    with rls_worker_atomic():
        _set_tenant_for_instance(instance)
        previous_state = getattr(instance, "_notification_previous_state", {})

        if created and instance.status == "pending":
            notify_teacher_about_submission(task=instance.project, student=instance.student, task_kind="project")
            return

        if instance.status == "graded" and _graded_payload_changed(previous_state, instance):
            notify_student_about_feedback(task=instance.project, student=instance.student, task_kind="project")


@receiver(pre_save, sender="labs.LabSubmission")
def _cache_lab_submission_state(sender, instance, **kwargs):
    _cache_previous_state(sender, instance, ("status", "score", "feedback"))


@receiver(post_save, sender="labs.LabSubmission")
def _notify_lab_submission_events(sender, instance, created, **kwargs):
    with rls_worker_atomic():
        _set_tenant_for_instance(instance)
        previous_state = getattr(instance, "_notification_previous_state", {})

        if created and instance.status in {"submitted", "late"}:
            notify_teacher_about_submission(
                task=instance.assignment.lab, student=instance.assignment.student, task_kind="lab"
            )
            return

        if instance.status == "graded" and _graded_payload_changed(
            previous_state,
            instance,
            score_field="score",
            feedback_field="feedback",
        ):
            notify_student_about_feedback(
                task=instance.assignment.lab, student=instance.assignment.student, task_kind="lab"
            )


@receiver(pre_save, sender="exams.ExamAttempt")
def _cache_exam_attempt_state(sender, instance, **kwargs):
    _cache_previous_state(sender, instance, ("status",))


@receiver(post_save, sender="exams.ExamAttempt")
def _notify_exam_attempt_events(sender, instance, created, **kwargs):
    with rls_worker_atomic():
        _set_tenant_for_instance(instance)
        if created:
            return

        previous_state = getattr(instance, "_notification_previous_state", {})
        previous_status = previous_state.get("status")
        current_status = instance.status

        if previous_status != current_status and current_status in {"submitted", "expired"}:
            notify_teacher_about_submission(task=instance.exam, student=instance.user, task_kind="exam")
