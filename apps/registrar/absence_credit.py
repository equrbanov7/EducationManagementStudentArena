"""Yalnız seçilmiş fənnin qayıb saatına auditli güzəşt; xanalar dəyişmir."""

import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from . import corrections
from .absence_credit_read import credit_hours_map, effective_hours
from .models import AbsenceCredit, AttendanceStatus, CourseOffering, Enrollment, LessonMark


class CreditConflict(ValidationError):
    pass


def _check_request(request, offering):
    if (
        not corrections.can_correct_journal(request)
        or getattr(request, "organization", None) != offering.organization
        or not offering.is_active
    ):
        raise PermissionError("absence_credit_denied")


def raw_hours(enrollment):
    from .guest_merge import carried_absence_hours

    own = (
        LessonMark.objects.filter(enrollment=enrollment, status=AttendanceStatus.ABSENT).aggregate(
            total=Sum("lesson__hours")
        )["total"]
        or 0
    )
    return own + carried_absence_hours(enrollment)


def _token(raw):
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(pgettext("registrar.absence_credit", "Sorğu açarı düzgün deyil.")) from None


@transaction.atomic
def adjust(*, request, offering, enrollment_id, hours=None, reason, request_token, reverses_id=None):
    _check_request(request, offering)
    token = _token(request_token)
    reason = str(reason or "").strip()
    if not 10 <= len(reason) <= 1000:
        raise ValidationError(pgettext("registrar.absence_credit", "Səbəb 10–1000 simvol olmalıdır."))
    # Mark yazısı da açılışı əvvəl kilidləyir. Mənbə güzəşti köçürülmüş hədəfi də yenidən hesablayır.
    candidate = Enrollment.objects.filter(
        pk=enrollment_id, offering=offering, organization=offering.organization
    ).first()
    if candidate is None:
        raise ValidationError(pgettext("registrar.absence_credit", "Bu fənnin tələbə qeydiyyatı tapılmadı."))

    def neighbors(row):
        ids = set(
            Enrollment.objects.filter(superseded_by=row, organization=offering.organization).values_list(
                "offering_id", flat=True
            )
        )
        if row.superseded_by_id:
            ids.update(
                Enrollment.objects.filter(pk=row.superseded_by_id, organization=offering.organization).values_list(
                    "offering_id", flat=True
                )
            )
        return ids

    target_ids = neighbors(candidate)
    list(
        CourseOffering.objects.select_for_update()
        .filter(pk__in=[offering.pk, *target_ids], organization=offering.organization)
        .order_by("pk")
    )
    offering.refresh_from_db(fields=["is_active"])
    _check_request(request, offering)
    try:
        enrollment = Enrollment.objects.select_for_update().get(
            pk=enrollment_id, offering=offering, organization=offering.organization
        )
    except (Enrollment.DoesNotExist, ValueError, ValidationError):
        raise ValidationError(pgettext("registrar.absence_credit", "Bu fənnin tələbə qeydiyyatı tapılmadı.")) from None
    # A concurrent transfer must not silently introduce an unlocked neighboring journal.
    if enrollment.superseded_by_id != candidate.superseded_by_id or neighbors(enrollment) != target_ids:
        raise CreditConflict(pgettext("registrar.absence_credit", "Qeydiyyat dəyişib. Səhifəni yeniləyib təkrar edin."))
    reversal = None
    if reverses_id:
        reversal = AbsenceCredit.objects.filter(
            pk=_token(reverses_id), enrollment=enrollment, organization=offering.organization, reverses=None
        ).first()
        if reversal is None:
            raise ValidationError(pgettext("registrar.absence_credit", "Geri alınacaq düzəliş tapılmadı."))
        value = reversal.hours
    else:
        try:
            value = int(str(hours))
        except (ValueError, TypeError):
            raise ValidationError(pgettext("registrar.absence_credit", "Saat müsbət tam ədəd olmalıdır.")) from None
        if not 1 <= value <= 32767:
            raise ValidationError(pgettext("registrar.absence_credit", "Saat müsbət tam ədəd olmalıdır."))
    existing = AbsenceCredit.objects.filter(organization=offering.organization, request_token=token).first()
    if existing:
        if (existing.enrollment_id, existing.hours, existing.reason, existing.actor_id, existing.reverses_id) != (
            enrollment.pk,
            value,
            reason,
            request.user.pk,
            getattr(reversal, "pk", None),
        ):
            raise CreditConflict(
                pgettext("registrar.absence_credit", "Bu sorğu açarı başqa düzəlişdə istifadə olunub.")
            )
        return existing
    if reversal and AbsenceCredit.objects.filter(reverses=reversal).exists():
        raise CreditConflict(pgettext("registrar.absence_credit", "Bu düzəliş artıq geri alınıb."))
    raw = raw_hours(enrollment)
    current = credit_hours_map([enrollment.pk]).get(enrollment.pk, 0)
    old = effective_hours(raw, current)
    if not reversal and value > old:
        raise ValidationError(
            pgettext("registrar.absence_credit", "Güzəşt mövcud üzrsüz qayıb saatından çox ola bilməz.")
        )
    new = effective_hours(raw, current - value if reversal else current + value)
    try:
        with transaction.atomic():
            entry = AbsenceCredit.objects.create(
                organization=offering.organization,
                enrollment=enrollment,
                hours=value,
                reason=reason,
                actor=request.user,
                request_token=token,
                reverses=reversal,
                old_absence_hours=old,
                new_absence_hours=new,
            )
    except IntegrityError as exc:
        if AbsenceCredit.objects.filter(organization=offering.organization, request_token=token).exists():
            raise CreditConflict(
                pgettext("registrar.absence_credit", "Bu sorğu açarı başqa düzəlişdə istifadə olunub.")
            ) from exc
        raise
    from .gradebook_marks import recompute_absence_hours_many

    touched = [enrollment]
    if enrollment.superseded_by_id:
        touched += list(Enrollment.objects.filter(pk=enrollment.superseded_by_id))
    recompute_absence_hours_many(touched)
    log_action(
        AuditAction.UPDATE,
        user=request.user,
        organization=offering.organization,
        request=request,
        resource_type="registrar.AbsenceCredit",
        resource_id=str(entry.pk),
        changes={
            "enrollment": str(enrollment.pk),
            "hours": value,
            "reverses": str(reverses_id or ""),
            "absence_hours": [old, new],
        },
        reason=reason,
    )
    return entry
