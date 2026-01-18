from django.db import transaction
from django.db.models.signals import m2m_changed, pre_save, post_save
from django.dispatch import receiver

from blog.models import StudentGroup
from courses.models import CourseMembership


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

        qs = CourseMembership.objects.filter(group_name=old_name)
        if teacher is not None:
            qs = qs.filter(course__owner=teacher)

        qs.update(group_name=instance.name)


# Qrupun tələbələri dəyişəndə -> kurs membership qrupunu sync elə
@receiver(m2m_changed, sender=StudentGroup.students.through)
def sync_group_students_to_course_memberships(sender, instance: StudentGroup, action, pk_set, **kwargs):

    def do_sync():
        teacher = getattr(instance, "teacher", None)

        if action == "post_add":
            qs = CourseMembership.objects.filter(user_id__in=pk_set)
            if teacher is not None:
                qs = qs.filter(course__owner=teacher)
            qs.update(group_name=instance.name)

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
