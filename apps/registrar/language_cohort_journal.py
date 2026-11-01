"""Explicit staff-assigned cohort contact hours, independent of imported workload."""

from django.utils.translation import gettext as _

from .integrity import is_authorized_instructor
from .models import LanguageLevelCohort

KINDS = ("lecture", "seminar", "lab")


def _hours(cohort):
    return {kind: getattr(cohort, f"{kind}_hours") for kind in KINDS if getattr(cohort, f"{kind}_hours")}


def hours_for_offering(offering):
    if offering is None or not getattr(offering, "pk", None) or not getattr(offering, "organization_id", None):
        return {}
    cohort = LanguageLevelCohort.objects.filter(
        organization_id=offering.organization_id,
        offering_id=offering.pk,
        group_id=offering.group_id,
        period_id=offering.period_id,
    ).first()
    return _hours(cohort) if cohort else {}


def hours_by_offering(offerings):
    by_id = {offering.pk: offering for offering in offerings}
    rows = LanguageLevelCohort.objects.filter(offering_id__in=by_id)
    return {
        row.offering_id: _hours(row)
        for row in rows
        if row.organization_id == by_id[row.offering_id].organization_id
        and row.group_id == by_id[row.offering_id].group_id
        and row.period_id == by_id[row.offering_id].period_id
    }


def teacher_assignments(*, organization, teacher_id):
    from django.contrib.auth import get_user_model

    rows = list(
        LanguageLevelCohort.objects.filter(
            organization=organization,
            offering__organization=organization,
            offering__instructor_id=teacher_id,
            offering__is_active=True,
            period__is_current=True,
            period__is_active=True,
            group__is_active=True,
        )
    )
    if not rows:
        return {}
    teacher = get_user_model().objects.only("pk", "is_active").filter(pk=teacher_id, is_active=True).first()
    if (
        not teacher
        or not is_authorized_instructor(organization=organization, instructor=teacher)
        or getattr(getattr(teacher, "profile", None), "access_state", None) != "active"
    ):
        return {}
    return {(None, None, row.offering_id): set(_hours(row)) for row in rows}


def validate_lesson(*, offering, kind, hours, exclude_id=None):
    from django.db.models import Sum

    from .gradebook import LessonRuleError
    from .models import Lesson

    budgets = hours_for_offering(offering)
    if not budgets:
        return
    if kind not in budgets:
        raise LessonRuleError(_("Bu səviyyə qrupunda seçilmiş dərs növü təyin edilməyib."))
    used = Lesson.objects.filter(organization_id=offering.organization_id, offering=offering, kind=kind)
    if exclude_id:
        used = used.exclude(pk=exclude_id)
    total = used.aggregate(total=Sum("hours"))["total"] or 0
    if total + hours > budgets[kind]:
        raise LessonRuleError(_("Bu dərs növü üzrə səviyyə qrupunun saat həddi aşılır."))


def require_cohort_placement_surface(offering):
    from django.core.exceptions import ValidationError

    if LanguageLevelCohort.objects.filter(organization_id=offering.organization_id, offering_id=offering.pk).exists():
        raise ValidationError(_("Səviyyə qrupunun siyahısını səviyyə idarəetməsindən dəyişin."))
