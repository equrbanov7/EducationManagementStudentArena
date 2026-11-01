"""Atomic level placement: retain old grades; never forge cross-subject succession."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from . import guest_merge, guest_roster, language_cohorts
from .language_levels import level_family, level_of
from .models import (
    AcademicStatus,
    CourseOffering,
    Enrollment,
    EnrollmentKind,
    LanguageLevelCohort,
    LanguageLevelPlacement,
    StudentAcademicRecord,
)


def _cohort(cohort):
    cohort = LanguageLevelCohort.objects.select_related(
        "organization",
        "department",
        "group",
        "period",
        "offering__subject",
        "offering__period",
        "offering__organization",
    ).get(organization_id=cohort.organization_id, pk=cohort.pk)
    offering = cohort.offering
    if (
        offering.group_id != cohort.group_id
        or offering.period_id != cohort.period_id
        or offering.organization_id != cohort.organization_id
        or cohort.group.organization_id != cohort.organization_id
        or cohort.department.organization_id != cohort.organization_id
        or cohort.group.parent_id != cohort.department_id
        or level_of(offering.subject.name) != cohort.level
        or level_family(offering.subject.name) != cohort.family
        or offering.course_format != "regular"
        or not offering.subject.is_active
        or (cohort.group.settings or {}).get("language_level_cohort") is not True
        or not cohort.group.is_active
        or not cohort.department.is_active
        or not offering.is_active
    ):
        raise ValidationError(_("Səviyyə qrupunun əlaqələri dəyişib; inzibati yoxlama tələb olunur."))
    guest_roster.assert_roster_open(offering)
    return cohort


def _record(cohort, record_id):
    record = (
        StudentAcademicRecord.objects.select_for_update(of=("self",))
        .filter(
            pk=record_id,
            organization_id=cohort.organization_id,
            group__organization_id=cohort.organization_id,
            group__is_active=True,
            group__language_cohort__isnull=True,
            is_active=True,
            status=AcademicStatus.ENROLLED,
            student__is_active=True,
        )
        .select_related("group", "student")
        .first()
    )
    if record is None:
        raise ValidationError(_("Tələbənin uyğun aktiv akademik qeydi yoxdur."))
    profiles = apps.get_model("accounts", "UserProfile").objects.filter(
        user_id=record.student_id, organization_id=cohort.organization_id, access_state="active"
    )
    membership = apps.get_model("organizations", "Membership").objects.filter(
        user_id=record.student_id,
        organization_id=cohort.organization_id,
        is_active=True,
        role__organization_id=cohort.organization_id,
        role__is_active=True,
    )
    if not profiles.exists() or not membership.exists():
        raise ValidationError(_("Tələbənin aktiv təşkilat profili və üzvlüyü yoxdur."))
    return record


def _authorize_record(actor, cohort, record, sources):
    if not language_cohorts.can_manage(actor, cohort):
        raise PermissionDenied
    if guest_roster.unit_in_scope(actor, cohort.organization, record.group_id):
        return
    if any(language_cohorts.source_access(actor, source) for source in sources):
        return
    removed = (
        Enrollment.objects.filter(
            organization=cohort.organization,
            offering=cohort.offering,
            student_id=record.student_id,
            status=Enrollment.Status.DROPPED,
            level_departures__cohort=cohort,
            level_departures__action="remove",
        )
        .select_related("offering__organization")
        .distinct()
    )
    if any(language_cohorts.source_access(actor, row) for row in removed):
        return
    raise PermissionDenied


def _event(*, cohort, record, actor, action, source=None, target=None, reason):
    event = LanguageLevelPlacement.objects.create(
        organization=cohort.organization,
        cohort=cohort,
        student=record.student,
        home_group=record.group,
        actor=actor,
        action=action,
        source_enrollment=source,
        target_enrollment=target,
        reason=reason,
    )
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=cohort.organization,
        obj=cohort,
        changes={
            "placement_event_id": str(event.pk),
            "action": action,
            "source_enrollment": str(source.pk) if source else None,
            "target_enrollment": str(target.pk) if target else None,
        },
        reason=reason,
    )
    return event


def _reason(value):
    value = str(value or "").strip()
    if not 10 <= len(value) <= 500:
        raise ValidationError(_("Səbəb 10–500 simvol olmalıdır."))
    return value


@transaction.atomic
def place_student(*, cohort, record_id, actor, reason, source_enrollment_id=None):
    reason = _reason(reason)
    cohort = _cohort(cohort)
    record = _record(cohort, record_id)
    from .subject_exempt import is_exempt_from_subject

    if is_exempt_from_subject(record, cohort.period, cohort.offering.subject_id):
        raise ValidationError(pgettext("registrar.intensive", "Tələbə bu semestrdə bu fəndən azad edilib."))
    get_user_model().objects.select_for_update().only("pk").get(pk=record.student_id)
    sources = language_cohorts.eligible_family_enrollments(cohort=cohort, student_id=record.student_id)
    _authorize_record(actor, cohort, record, sources)
    # SAR serializes concurrent placements of this academic record; lock every
    # involved offering in canonical order before any enrollment/mark writer.
    list(
        CourseOffering.objects.select_for_update()
        .filter(organization=cohort.organization, pk__in=[cohort.offering_id, *[row.offering_id for row in sources]])
        .order_by("pk")
    )
    cohort = _cohort(cohort)
    sources = language_cohorts.eligible_family_enrollments(cohort=cohort, student_id=record.student_id, lock=True)
    _authorize_record(actor, cohort, record, sources)
    if len(sources) > 1:
        raise ValidationError(
            _("Tələbənin bu dil ailəsində birdən çox aktiv jurnalı var; inzibati yoxlama tələb olunur.")
        )
    source = sources[0] if sources else None
    if (source is None and source_enrollment_id) or (source and str(source.pk) != str(source_enrollment_id)):
        raise ValidationError(_("Cari səviyyədən keçid ayrıca təsdiqlənməlidir; mənbə qeydiyyatı dəyişib."))
    if source:
        if (
            source.kind == EnrollmentKind.RETAKE
            or source.offering.course_format != "regular"
            or source.superseded_by_id
        ):
            raise ValidationError(_("Təkrar/intensiv və əvəzlənmiş qeydiyyat üçün ayrıca inzibati qərar tələb olunur."))
        if not (
            guest_roster.can_manage_offering_roster(actor, source.offering)
            or language_cohorts.source_access(actor, source)
        ):
            raise PermissionDenied
        guest_roster.assert_roster_open(source.offering)
        guest_merge.assert_releasable(source)
    target = (
        Enrollment.objects.select_for_update()
        .filter(organization=cohort.organization, offering=cohort.offering, student=record.student)
        .first()
    )
    if target:
        if (
            target.status != Enrollment.Status.DROPPED
            or target.superseded_by_id
            or target.source_group_id != record.group_id
        ):
            raise ValidationError(_("Hədəf qeydiyyatı artıq aktivdir və ya tarixçəsi ayrıca yoxlanmalıdır."))
        guest_merge.assert_releasable(target)
        target.status = Enrollment.Status.ENROLLED
        target.save(update_fields=["status", "updated_at"])
    else:
        target = Enrollment.objects.create(
            organization=cohort.organization,
            offering=cohort.offering,
            student=record.student,
            kind=source.kind if source else EnrollmentKind.MANDATORY,
            source_group=record.group,
            added_by=actor,
            added_at=timezone.now(),
        )
    if source:
        # Subject identity can differ across levels. No superseded_by, grade
        # copying, absence carry-over, membership or academic-group mutation.
        source.status = Enrollment.Status.DROPPED
        source.save(update_fields=["status", "updated_at"])
    _event(
        cohort=cohort,
        record=record,
        actor=actor,
        action="move" if source else "add",
        source=source,
        target=target,
        reason=reason,
    )
    return target


@transaction.atomic
def remove_student(*, cohort, enrollment_id, actor, reason):
    reason = _reason(reason)
    cohort = _cohort(cohort)
    if not language_cohorts.can_manage(actor, cohort):
        raise PermissionDenied
    enrollment = Enrollment.objects.get(
        organization=cohort.organization, offering=cohort.offering, pk=enrollment_id, status=Enrollment.Status.ENROLLED
    )
    records = list(
        StudentAcademicRecord.objects.filter(
            organization=cohort.organization,
            student_id=enrollment.student_id,
            is_active=True,
            status=AcademicStatus.ENROLLED,
        ).values_list("pk", flat=True)[:2]
    )
    if len(records) != 1:
        raise ValidationError(_("Tələbənin cari əsas qrupu ayrıca yoxlanmalıdır."))
    record = _record(cohort, records[0])
    get_user_model().objects.select_for_update().only("pk").get(pk=record.student_id)
    CourseOffering.objects.select_for_update().get(organization=cohort.organization, pk=cohort.offering_id)
    cohort = _cohort(cohort)
    if not language_cohorts.can_manage(actor, cohort):
        raise PermissionDenied
    enrollment = (
        Enrollment.objects.select_for_update(of=("self",))
        .select_related("offering")
        .get(
            organization=cohort.organization,
            offering=cohort.offering,
            pk=enrollment_id,
            status=Enrollment.Status.ENROLLED,
        )
    )
    guest_merge.assert_releasable(enrollment)
    enrollment.status = Enrollment.Status.DROPPED
    enrollment.save(update_fields=["status", "updated_at"])
    _event(cohort=cohort, record=record, actor=actor, action="remove", source=enrollment, reason=reason)
    return enrollment
