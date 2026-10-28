"""Recorded teaching hours: explicit lesson author, never current ownership inference.

This read surface grants no journal/student access. Self-history is independent of
current ownership; a report caller must cover the offering's official chair.
"""

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import CourseOffering, Lesson, TeachingHandover


def _name(user):
    return (user.get_full_name() or user.username) if user else ""


def recorded_teaching_hours(*, actor, teacher_id=None, academic_year="", as_of=None):
    """Return each canonical offering once, with per-activity own and unknown hours.

    Marks, enrollments, shares and workload rows are deliberately not joined: a
    lesson's hours cannot multiply by student/group/assignment counts. NULL
    instructor remains unknown, even after a handover or an administrative entry.
    """
    organization = actor.organization
    user = actor.user
    if organization is None or not user or not user.is_active or not user.is_authenticated:
        raise PermissionDenied("teaching_hours_denied")
    teacher_id = teacher_id if teacher_id is not None else user.pk
    own = str(teacher_id) == str(user.pk)
    if not actor.has("workload.view" if own else "workload.report"):
        raise PermissionDenied("teaching_hours_denied")
    base = CourseOffering.objects.filter(organization=organization)
    if not own:
        scope = actor.scope_for("workload.report")
        base = base.filter(
            scope.unit_subtree_q(path_field="subject__chair_unit__path", id_field="subject__chair_unit_id")
        )
    lessons = Lesson.objects.filter(organization=organization, instructor_id=teacher_id)
    handovers = TeachingHandover.objects.filter(organization=organization).filter(
        Q(from_instructor_id=teacher_id) | Q(to_instructor_id=teacher_id)
    )
    base = base.filter(
        Q(instructor_id=teacher_id)
        | Q(pk__in=lessons.values("offering_id"))
        | Q(pk__in=handovers.values("offering_id"))
    )
    if academic_year:
        base = base.filter(period__academic_year=academic_year)
    offerings = list(
        base.select_related("subject__chair_unit", "group", "period", "instructor").order_by(
            "subject__name", "group__name", "pk"
        )
    )
    ids = [row.pk for row in offerings]
    cutoff = min(as_of or timezone.localdate(), timezone.localdate())
    cells = (
        Lesson.objects.filter(organization=organization, offering_id__in=ids, date__lte=cutoff)
        .filter(Q(instructor_id=teacher_id) | Q(instructor_id__isnull=True))
        .values("offering_id", "kind", "instructor_id")
        .annotate(recorded_hours=Sum("hours"), recorded_lessons=Count("pk"))
    )
    totals = {}
    for cell in cells:
        bucket = totals.setdefault(cell["offering_id"], {"hours": {}, "unknown_hours": 0, "lessons": 0})
        if cell["instructor_id"] is None:
            bucket["unknown_hours"] += int(cell["recorded_hours"] or 0)
        else:
            bucket["hours"][cell["kind"]] = int(cell["recorded_hours"] or 0)
            bucket["lessons"] += cell["recorded_lessons"]
    history = {}
    for record in TeachingHandover.objects.filter(organization=organization, offering_id__in=ids).order_by(
        "created_at"
    ):
        history.setdefault(record.offering_id, []).append(
            {
                "from_name": record.from_instructor_name,
                "to_name": record.to_instructor_name,
                "reverted": record.reverted_at is not None,
            }
        )
    result = []
    for offering in offerings:
        bucket = totals.get(offering.pk, {"hours": {}, "unknown_hours": 0, "lessons": 0})
        result.append(
            {
                "offering_id": str(offering.pk),
                "subject": offering.subject.name,
                "group": offering.group.name if offering.group_id else "",
                "chair": offering.subject.chair_unit.name if offering.subject.chair_unit_id else "",
                "academic_year": offering.period.academic_year,
                "period_start": offering.period.start_date,
                "period": offering.period.name,
                "current_teacher": _name(offering.instructor),
                "history": history.get(offering.pk, []),
                "hours": bucket["hours"],
                "total_hours": sum(bucket["hours"].values()),
                "unknown_hours": bucket["unknown_hours"],
                "lessons": bucket["lessons"],
            }
        )
    return result
