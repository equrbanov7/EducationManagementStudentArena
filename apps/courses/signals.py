from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from apps.courses.models import CourseMembership
from apps.exams.models import StudentGroup


# Qrup adının əvvəlki dəyərini yadda saxla
@receiver(pre_save, sender=StudentGroup)
def remember_old_group_name(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_name = StudentGroup.objects.get(pk=instance.pk).name
        except StudentGroup.DoesNotExist:
            instance._old_name = None
    else:
        instance._old_name = None


# Qrup adı dəyişibsə -> kurslarda da group_name update olunsun
@receiver(post_save, sender=StudentGroup)
def sync_group_rename_to_course_memberships(sender, instance, created, **kwargs):
    old_name = getattr(instance, "_old_name", None)
    if old_name and old_name != instance.name:
        # yalnız həmin müəllimin kursları üçün (əgər teacher field-i varsa)
        teacher = getattr(instance, "teacher", None)
        student_ids = list(instance.students.values_list("id", flat=True))

        qs = CourseMembership.objects.filter(group_name=old_name)
        if teacher is not None:
            qs = qs.filter(course__owner=teacher)
        if student_ids:
            qs = qs.filter(user_id__in=student_ids)

        qs.update(group_name=instance.name)


def _propagate_new_members_to_courses(instance, new_student_ids):
    """
    When new students join a StudentGroup, enrol them in every course
    where that group is already linked (i.e. existing CourseMembership rows
    carry group_name == instance.name) and propagate any group-based
    task membership to them as well.

    This ensures idempotent behaviour: students already enrolled are
    ignored, and each student gets exactly one membership per course.

    NOTE: This function is intentionally called inside ``transaction.on_commit``
    so the M2M rows are fully committed before any DB reads here.
    """
    from apps.assignments.models import Assignment
    from apps.projects.models import Project

    teacher = getattr(instance, "teacher", None)

    # Find all courses that already have this group linked.
    membership_qs = CourseMembership.objects.filter(group_name=instance.name)
    if teacher is not None:
        membership_qs = membership_qs.filter(course__owner=teacher)

    linked_course_ids = list(membership_qs.values_list("course_id", flat=True).distinct())
    if not linked_course_ids:
        return

    for course_id in linked_course_ids:
        # Determine which of the new students are not yet enrolled.
        existing_user_ids = set(
            CourseMembership.objects.filter(
                course_id=course_id,
                user_id__in=new_student_ids,
            ).values_list("user_id", flat=True)
        )
        to_create = [
            CourseMembership(
                course_id=course_id,
                user_id=uid,
                role="student",
                group_name=instance.name,
            )
            for uid in new_student_ids
            if uid not in existing_user_ids
        ]
        if to_create:
            CourseMembership.objects.bulk_create(to_create, ignore_conflicts=True)

        _propagate_group_task_assignments(
            task_model=Assignment,
            course_id=course_id,
            group_name=instance.name,
            new_student_ids=new_student_ids,
        )
        _propagate_group_task_assignments(
            task_model=Project,
            course_id=course_id,
            group_name=instance.name,
            new_student_ids=new_student_ids,
        )


def _propagate_group_task_assignments(*, task_model, course_id, group_name, new_student_ids):
    """
    Copy existing group-based M2M task assignments to newly added students.

    The app stores course assignments/projects as explicit user relations, so
    when a teacher originally targets a whole group we infer that intent from
    existing assignees whose course membership currently carries ``group_name``.
    """
    task_fk_name = f"{task_model._meta.model_name}_id"
    group_task_ids = list(
        task_model.objects.filter(
            course_id=course_id,
            assigned_students__course_memberships__course_id=course_id,
            assigned_students__course_memberships__group_name=group_name,
        )
        .distinct()
        .values_list("id", flat=True)
    )
    if not group_task_ids:
        return

    through_model = task_model.assigned_students.through
    already_assigned = set(
        through_model.objects.filter(
            **{
                f"{task_fk_name}__in": group_task_ids,
                "user_id__in": new_student_ids,
            }
        ).values_list(task_fk_name, "user_id")
    )
    new_relations = [
        through_model(**{task_fk_name: task_id, "user_id": user_id})
        for task_id in group_task_ids
        for user_id in new_student_ids
        if (task_id, user_id) not in already_assigned
    ]
    if new_relations:
        through_model.objects.bulk_create(new_relations, ignore_conflicts=True)


# Qrupun tələbələri dəyişəndə -> kurs membership qrupunu sync elə
@receiver(m2m_changed, sender=StudentGroup.students.through)
def sync_group_students_to_course_memberships(sender, instance: StudentGroup, action, pk_set, **kwargs):

    def do_sync():
        teacher = getattr(instance, "teacher", None)

        if action == "post_add":
            # Update group_name for students already enrolled in the teacher's courses.
            qs = CourseMembership.objects.filter(user_id__in=pk_set)
            if teacher is not None:
                qs = qs.filter(course__owner=teacher)
            qs.update(group_name=instance.name)

            # Enrol newly added students in all courses linked to this group
            # and propagate group-based assignment membership.
            _propagate_new_members_to_courses(instance, list(pk_set))

        elif action == "post_remove":
            qs = CourseMembership.objects.filter(user_id__in=pk_set, group_name=instance.name)
            if teacher is not None:
                qs = qs.filter(course__owner=teacher)
            qs.update(group_name="")

        elif action == "post_clear":
            qs = CourseMembership.objects.filter(group_name=instance.name)
            if teacher is not None:
                qs = qs.filter(course__owner=teacher)
            qs.update(group_name="")

    transaction.on_commit(do_sync)
