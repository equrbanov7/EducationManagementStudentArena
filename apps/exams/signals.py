"""Signals for keeping exam assignment side effects in sync."""

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from apps.exams.models import Exam, StudentGroup
from apps.exams.services.student_pins import provision_exam_student_pins
from core.rls_pooling import rls_worker_atomic

_SYNC_ACTIONS = {"post_add", "post_remove", "post_clear"}


def _sync_pin_assignments_for_group_ids(group_ids):
    if not group_ids:
        return
    exams = Exam.objects.filter(allowed_groups__id__in=group_ids, is_deleted=False).distinct()
    for exam in exams:
        provision_exam_student_pins(exam)


@receiver(m2m_changed, sender=StudentGroup.students.through)
def sync_student_pins_when_group_students_change(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in _SYNC_ACTIONS:
        return

    with rls_worker_atomic():
        if reverse:
            # Reverse updates are User.student_groups_as_student.add/remove(...).
            # post_clear cannot provide the previous group ids, so normal forward
            # StudentGroup.students.clear() is the reliable path for pruning.
            if action == "post_clear":
                return
            group_ids = set(pk_set or ())
        else:
            group_ids = {instance.pk}

        _sync_pin_assignments_for_group_ids(group_ids)


@receiver(m2m_changed, sender=Exam.allowed_groups.through)
@receiver(m2m_changed, sender=Exam.allowed_users.through)
@receiver(m2m_changed, sender=Exam.excluded_users.through)
def sync_student_pins_when_exam_assignments_change(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in _SYNC_ACTIONS:
        return

    with rls_worker_atomic():
        if reverse:
            if action == "post_clear":
                return
            for exam in Exam.objects.filter(pk__in=pk_set or (), is_deleted=False):
                provision_exam_student_pins(exam)
        else:
            provision_exam_student_pins(instance)
