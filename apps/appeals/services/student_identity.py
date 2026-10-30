"""Current student groups within the appeal tenant; shared by screen and notifications."""

from django.apps import apps as django_apps


def student_group_map(queryset):
    try:
        record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    except LookupError:
        return {}
    rows = (
        record_model.objects.filter(
            organization_id__in=queryset.order_by().values("organization_id"),
            student_id__in=queryset.order_by().values("student_id"),
            is_active=True,
            group__isnull=False,
        )
        .order_by("student_id", "-created_at")
        .values_list("student_id", "group__name")
    )
    result = {}
    for student_id, name in rows:
        if name:
            result.setdefault(student_id, name)
    return result
