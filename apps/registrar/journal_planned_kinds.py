"""Jurnalın növləri: keçirilmiş/cədvəl dərsləri və dəqiq qrupun dərs yükü planı."""

from collections import defaultdict

from django.apps import apps
from django.db.models import Exists, OuterRef, Q

from .models import Lesson, ScheduleSlot
from .plan_hours_load import workload_hours_by_offering, workload_hours_for_offering

KINDS = ("lecture", "seminar", "lab")


def planned_kinds_by_offering(offerings):
    """Hər tenantın səhifə diliminə iki sorğu; qrupsuz açılış başqa qrupların yükünü almır."""
    by_org = defaultdict(list)
    for offering in offerings:
        if offering.group_id:
            by_org[offering.organization_id].append(offering)
    result = {}
    for batch in by_org.values():
        result.update({key: set(hours) for key, hours in workload_hours_by_offering(batch).items()})
    return result


def available_kinds(offering):
    """Yazılmamış, amma planlaşdırılmış növ də seçilə bilər; heç bir dərs yaradılmır."""
    kinds = set(Lesson.objects.filter(offering=offering).values_list("kind", flat=True))
    kinds.update(ScheduleSlot.objects.filter(offering=offering).values_list("kind", flat=True))
    if offering.group_id:
        kinds.update(workload_hours_for_offering(offering))
    return kinds.intersection(KINDS)


def apply_kind_filter(queryset, kind):
    """Exact organization/subject/period/group korrelyasiyası; join fan-out yoxdur."""
    if kind not in KINDS:
        return queryset.none()
    TaskRow = apps.get_model("workload", "TeachingTaskRow")
    planned = (
        TaskRow.objects.filter(
            organization_id=OuterRef("organization_id"),
            subject_id=OuterRef("subject_id"),
            period_id=OuterRef("period_id"),
            groups=OuterRef("group_id"),
        )
        .exclude(task__status="cancelled")
        .filter(Q(**{f"{kind}_plan__gt": 0}) | Q(**{f"{kind}_total__gt": 0}))
    )
    return queryset.alias(_journal_planned_kind=Exists(planned)).filter(
        Q(pk__in=ScheduleSlot.objects.filter(kind=kind).values("offering_id"))
        | Q(pk__in=Lesson.objects.filter(kind=kind).values("offering_id"))
        | Q(_journal_planned_kind=True)
    )
