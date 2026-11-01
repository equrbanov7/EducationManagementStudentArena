"""Scoped language-level cohort registry and explicit creation, without SAR writes."""

import uuid

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from core.audit import log_action
from core.constants import AuditAction

from . import guest_roster
from .integrity import is_authorized_instructor, validate_same_organization
from .journal_access import can_edit_journal
from .journal_shares import journal_scope
from .language_levels import level_family, level_of
from .models import CourseOffering, LanguageLevelCohort


def department_choices(user, organization):
    units = apps.get_model("organizations", "OrgUnit").objects.filter(
        organization=organization, unit_type__in=["chair", "department"], is_active=True
    )
    if (
        not user
        or not user.is_authenticated
        or not user.is_active
        or not organization.is_active
        or getattr(getattr(user, "profile", None), "access_state", None) != "active"
    ):
        return units.none()
    scope = apps.get_model("organizations", "OrgUnit").user_permission_scope(user, organization, "journal.roster")
    if not scope.has_structure_access:
        return units.none()
    if not scope.is_org_wide:
        units = units.filter(scope.unit_subtree_q())
    return units.order_by("name", "id")


def can_manage(user, cohort):
    if (
        not user
        or not user.is_authenticated
        or not user.is_active
        or getattr(getattr(user, "profile", None), "access_state", None) != "active"
    ):
        return False
    if guest_roster.unit_in_scope(user, cohort.organization, cohort.department_id):
        return True
    offering = cohort.offering
    return offering.instructor_id == user.pk and is_authorized_instructor(
        organization=cohort.organization, instructor=user
    )


def authorized_cohorts(user, organization):
    """``can_manage`` ilə eyni qayda, toplu: əhatə BİR dəfə hesablanır (N×exists əvəzinə 1 sorğu)."""
    rows = list(
        LanguageLevelCohort.objects.filter(organization=organization)
        .select_related("organization", "department", "group", "period", "offering__subject", "offering__instructor")
        .order_by("-period__start_date", "department__name", "name")
    )
    if not rows or not _active_actor(user):
        return []
    managed = guest_roster.units_in_scope(user, organization, {row.department_id for row in rows})
    instructor_ok = None
    result = []
    for row in rows:
        if row.department_id in managed:
            result.append(row)
            continue
        if row.offering.instructor_id == user.pk:
            if instructor_ok is None:
                instructor_ok = is_authorized_instructor(organization=organization, instructor=user)
            if instructor_ok:
                result.append(row)
    return result


def _active_actor(user):
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and getattr(getattr(user, "profile", None), "access_state", None) == "active"
    )


def source_access(user, enrollment):
    """Course-scope access must include this student's row, not only the journal."""
    return can_edit_journal(user, enrollment.offering) and journal_scope(user, enrollment.offering).allows_enrollment(
        enrollment.pk
    )


def eligible_family_enrollments(*, cohort, student_id, lock=False):
    from .models import Enrollment

    rows = Enrollment.objects.filter(
        organization=cohort.organization,
        student_id=student_id,
        offering__organization=cohort.organization,
        offering__period_id=cohort.period_id,
        status=Enrollment.Status.ENROLLED,
    ).exclude(offering_id=cohort.offering_id)
    if lock:
        rows = rows.select_for_update(of=("self",))
    return [
        row
        for row in rows.select_related(
            "offering__subject", "offering__period", "offering__group", "offering__organization"
        ).order_by("pk")
        if level_of(row.offering.subject.name) and level_family(row.offering.subject.name) == cohort.family
    ]


@transaction.atomic
def create_cohort(
    *,
    organization,
    actor,
    department,
    period,
    subject,
    instructor,
    name,
    hours=None,
    lecture_hours=None,
    seminar_hours=None,
    lab_hours=None,
    source_offering=None,
    entry_score_max=None,
    pass_threshold=None,
    min_final_exam_score=None,
    confirm_separate=False,
):
    validate_same_organization(organization=organization, department=department, period=period, subject=subject)
    if not department_choices(actor, organization).filter(pk=department.pk).exists():
        raise PermissionDenied
    if not period.is_active or not period.is_current or not subject.is_active:
        raise ValidationError(_("Yalnız cari aktiv semestr və aktiv səviyyə fənni seçilə bilər."))
    level = level_of(subject.name)
    if (
        not level
        or not is_authorized_instructor(organization=organization, instructor=instructor)
        or getattr(getattr(instructor, "profile", None), "access_state", None) != "active"
    ):
        raise ValidationError(_("Səviyyə fənni və aktiv müəllim seçilməlidir."))
    contacts = dict(lecture_hours=lecture_hours, seminar_hours=seminar_hours, lab_hours=lab_hours)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 300 for value in contacts.values()
    ):
        raise ValidationError(_("Mühazirə, seminar və laboratoriya saatlarını açıq daxil edin."))
    total = sum(contacts.values())
    if hours is not None and hours != total:
        raise ValidationError(_("Növlər üzrə saatlar ümumi dərs saatına bərabər olmalıdır."))
    hours = total
    name = " ".join(str(name or "").split())
    if not 2 <= len(name) <= 100 or isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 300:
        raise ValidationError(_("Qrup adı və 1–300 arası dərs saatı tələb olunur."))
    if (
        CourseOffering.objects.filter(
            organization=organization, subject=subject, period=period, instructor=instructor, is_active=True
        ).exists()
        and not confirm_separate
    ):
        raise ValidationError(
            _(
                "Bu müəllim, fənn və semestr üçün jurnal artıq mövcuddur. Mövcud jurnalı açın və ya ayrıca yeni qrup yaratmağı təsdiqləyin."
            )
        )
    group = apps.get_model("organizations", "OrgUnit").objects.create(
        organization=organization,
        parent=department,
        unit_type="group",
        name=f"{name} · {level}",
        slug=f"language-level-{uuid.uuid4().hex}",
        settings={"language_level_cohort": True},
    )
    offering = CourseOffering.objects.create(
        organization=organization,
        group=group,
        subject=subject,
        period=period,
        instructor=instructor,
        lesson_hours=hours,
    )
    from .language_cohort_assessment import configure

    configure(
        offering=offering,
        actor=actor,
        source_offering=source_offering,
        entry_score_max=entry_score_max,
        pass_threshold=pass_threshold,
        min_final_exam_score=min_final_exam_score,
    )
    cohort = LanguageLevelCohort.objects.create(
        organization=organization,
        department=department,
        group=group,
        offering=offering,
        period=period,
        name=name,
        source_offering=source_offering,
        **contacts,
        family=level_family(subject.name),
        level=level,
        created_by=actor,
    )
    log_action(
        AuditAction.CREATE,
        user=actor,
        organization=organization,
        obj=cohort,
        new_values={"offering_id": str(offering.pk), "level": level},
        reason="Language level cohort created",
    )
    return cohort
