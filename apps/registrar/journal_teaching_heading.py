"""Read-only heading projection: current teaching share and retained journal history."""

from django.utils import timezone
from django.utils.translation import gettext

from core.group_identity import canonical_aliases

from .journal_assignment_sources import teacher_journal_plan_hours
from .models import Lesson
from .practical_label import kind_choices


def current_plan(offering, user):
    from .language_cohort_journal import hours_for_offering, teacher_assignments

    if (None, None, offering.pk) in teacher_assignments(organization=offering.organization, teacher_id=user.pk):
        return hours_for_offering(offering)
    plans = teacher_journal_plan_hours(organization=offering.organization, teacher_id=user.pk)
    intensive = plans.get((None, None, offering.pk))
    if intensive is not None:
        return intensive
    group = offering.group if offering.group_id else None
    group_id = canonical_aliases([group]).get(group.pk, group).pk if group is not None else None
    return plans.get((offering.subject_id, offering.period_id, group_id), {})


def summarize(offering, *, personal_actor=None, scope=None):
    lessons = list(
        Lesson.objects.filter(organization_id=offering.organization_id, offering=offering)
        .select_related("instructor")
        .only(
            "kind",
            "hours",
            "date",
            "lab_group",
            "seminar_group",
            "instructor__first_name",
            "instructor__last_name",
            "instructor__username",
        )
    )
    plan = current_plan(offering, personal_actor) if personal_actor is not None else None
    allowed = set(plan) if plan else (getattr(scope, "kinds", None) if personal_actor is not None else None)
    permitted = [lesson for lesson in lessons if scope is None or scope.allows_lesson(lesson)]
    visible = [lesson for lesson in permitted if allowed is None or lesson.kind in allowed]
    result = _summary(
        offering,
        visible,
        total=sum(plan.values()) if plan else (None if personal_actor else offering.lesson_hours),
        # Fənnin (tələbə başına) saatı: Lab-1 və Lab-2 toplanmır; müəllimin şəxsi planı isə hər iki qrupu sayır.
        per_student=personal_actor is None,
    )
    result["personal"] = personal_actor is not None
    if plan:
        by_kind = {row["kind"]: row for row in result["kinds"]}
        for kind, hours in plan.items():
            row = by_kind.get(kind)
            if row is None:
                row = {"kind": kind, "label": dict(kind_choices(offering)).get(kind, kind), "held": 0, "teachers": []}
                result["kinds"].append(row)
            row["planned"] = hours
        result["kinds"].sort(key=lambda row: ("lecture", "seminar", "lab").index(row["kind"]))
    if personal_actor is not None:
        result["history"] = _summary(offering, permitted, total=None)
    if personal_actor is not None and not result["held_total"]:
        from .journal_prior_history_badge import available

        result["prior_history_available"] = offering.pk in available(
            personal_actor,
            [offering],
            organization=offering.organization,
            kinds={offering.pk: allowed},
            enrollment_ids={offering.pk: getattr(scope, "enrollment_ids", None)},
        )
    return result


def _summary(offering, lessons, *, total, per_student=False):
    from .lab_groups import is_split, per_student_hours

    today = timezone.localdate()
    labels = dict(kind_choices(offering))
    by_kind, scheduled_total = {}, 0
    for lesson in lessons:
        row = by_kind.setdefault(lesson.kind, {"held": 0, "teachers": {}})
        hours = int(lesson.hours or 0)
        scheduled_total += hours
        if lesson.date is None or lesson.date <= today:
            row["held"] += hours
        # Ownership and data-entry authorship never prove who actually taught an anonymous lesson.
        teacher = lesson.instructor
        name = (
            (teacher.get_full_name().strip() or teacher.username)
            if teacher
            else gettext("Müəllifi göstərilməyən tarixçə")
        )
        row["teachers"][teacher.pk if teacher else None] = name
    kinds = [
        {
            "kind": kind,
            "label": labels.get(kind, kind),
            "held": data["held"],
            "teachers": list(data["teachers"].values()),
        }
        for kind, data in by_kind.items()
    ]
    kinds.sort(key=lambda row: {"lecture": 0, "seminar": 1, "lab": 2}.get(row["kind"], 9))
    held_total = sum(row["held"] for row in kinds)
    if per_student and any(is_split(lesson) for lesson in lessons):
        # Lab qrupları / seminar alt qrupları (sahib 2026-11-06/07): tələbə yalnız öz qrupunun dərsindədir.
        held_lessons = [lesson for lesson in lessons if lesson.date is None or lesson.date <= today]
        scheduled_total = per_student_hours(lessons)
        held_total = per_student_hours(held_lessons)
        for row in kinds:
            row["held"] = per_student_hours([lesson for lesson in held_lessons if lesson.kind == row["kind"]])
    total = int(total or 0)
    return {
        "kinds": kinds,
        "held_total": held_total,
        "scheduled_total": scheduled_total,
        "total": total,
        "remaining": max(0, total - scheduled_total) if total else None,
        "over": bool(total and scheduled_total > total),
        "completed": bool(total and held_total >= total),
    }
