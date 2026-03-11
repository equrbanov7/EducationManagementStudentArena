from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import LabAssignment

User = get_user_model()


@transaction.atomic
def create_lab_assignments_for_students(lab, student_ids):
    users = User.objects.filter(id__in=student_ids)
    created_count = 0
    existing_count = 0

    for user in users:
        assignment, created = LabAssignment.objects.get_or_create(
            lab=lab,
            student=user,
            defaults={"assigned_at": timezone.now()},
        )

        if created:
            created_count += 1
        else:
            existing_count += 1

    return created_count, existing_count


def get_lab_assignment_for_student(lab, student):
    return LabAssignment.get_or_create_for_student(lab, student)


__all__ = [
    "create_lab_assignments_for_students",
    "get_lab_assignment_for_student",
]
