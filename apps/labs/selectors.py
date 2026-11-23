"""
Database query layer for labs app.
This module contains selector functions that handle database queries.
"""

from django.db.models import Exists, OuterRef

from apps.labs.models import Lab


def labs_with_student_target(labs, user, *, include_any=False):
    students = Lab.allowed_students.through.objects.filter(lab_id=OuterRef("pk"))
    labs = labs.annotate(_direct=Exists(students.filter(user_id=user.pk)))
    if include_any:
        labs = labs.annotate(_has_targets=Exists(students))
    return labs
