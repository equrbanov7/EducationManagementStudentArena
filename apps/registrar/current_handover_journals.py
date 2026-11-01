"""A recorded canonical handover can expose its populated current legacy journal.

This only covers journals with no official workload row. An owner or manual share
alone is not a current assignment. Existing draft/cancelled/zero/other-teacher
workload is never overridden, and historical lesson authors/hours stay unchanged.
"""

from django.apps import apps as django_apps
from django.db.models import CharField, Exists, OuterRef, Q
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from django.utils import timezone

from .models import CourseOffering, Lesson, TeachingHandover


def kind_filters(user, organization):
    try:
        task_row = django_apps.get_model("workload", "TeachingTaskRow")
    except LookupError:
        return {kind: Q(pk__in=[]) for kind in ("lecture", "seminar", "lab")}
    rows = task_row.objects.filter(
        organization_id=OuterRef("organization_id"),
        subject_id=OuterRef("subject_id"),
        period_id=OuterRef("period_id"),
    ).annotate(_group_text=Cast("groups__pk", output_field=CharField()))
    rows = rows.filter(Q(groups=OuterRef("group_id")) | Q(_group_text=OuterRef("_handover_parent_group")))
    handovers = TeachingHandover.objects.filter(
        organization_id=OuterRef("organization_id"),
        offering_id=OuterRef("pk"),
        to_instructor=user,
        reverted_at__isnull=True,
    )
    courses = (
        CourseOffering.objects.filter(
            organization=organization,
            instructor=user,
            is_active=True,
            course_format="regular",
            group__isnull=False,
            group__is_active=True,
            group__organization=organization,
            period__is_active=True,
            period__is_current=True,
            period__organization=organization,
            period__start_date__lte=timezone.localdate(),
            period__end_date__gte=timezone.localdate(),
        )
        .annotate(_handover_parent_group=KeyTextTransform("parent_group", "group__settings"))
        .annotate(_current_handover=Exists(handovers), _has_official_row=Exists(rows))
        .filter(_current_handover=True, _has_official_row=False)
    )
    lessons = Lesson.objects.filter(
        organization_id=OuterRef("organization_id"),
        offering_id=OuterRef("pk"),
        date__lte=timezone.localdate(),
        hours__gt=0,
    )
    return {
        kind: Q(pk__in=courses.annotate(_recorded_kind=Exists(lessons.filter(kind=kind))).filter(_recorded_kind=True))
        for kind in ("lecture", "seminar", "lab")
    }
