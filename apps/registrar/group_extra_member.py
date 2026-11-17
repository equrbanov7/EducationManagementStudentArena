"""Qrupa ƏLAVƏ üzv — tələbə öz qrupunda qalır, bu qrupun cari jurnallarına düşür (sahib 2026-11-18).

Sahib: «əcnəbi tələbə 2 qrupda ola bilər — biri öz əsas qrupu, biri əcnəbi qrupu; əsas qrupa dəymirik»
(ADİAK kimi dərslər üçün). Ayrıca üzvlük modeli YOXDUR: «qrupda olmaq» = qrupun cari semestr
açılışlarında (jurnallarında) qeydiyyat. Ona görə əməl hər açılış üçün jurnal modalının («Alt qrupdan
tələbə əlavə et») eyni servis zəncirini çağırır — kredit/tutum qapısı (:func:`journal_modal_check`),
:func:`guest_roster.add_guest_student` (mənbə = tələbənin öz qrupu) və yerləşdirmə tarixçəsi.
Öz qrupu (``StudentAcademicRecord.group``) DƏYİŞMİR — rəsmi köçürmə deyil.

Hər jurnal ayrıca savepoint-dədir: biri alınmasa (məs. tələbə həmin fənni öz qrupunda keçir),
o jurnal SƏBƏBİ ilə «buraxıldı» siyahısına düşür, qalanları əlavə olunur.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from .models import CourseOffering, Enrollment

_CTX = "registrar.group_extra_member"


def add_extra_group_member(*, record, group, period, by_user, reason="") -> dict:
    """``record``-un tələbəsini ``group``-un ``period`` jurnallarına əlavə et (öz qrupu qalır).

    Qaytarır: ``{"added": [fənn adı…], "skipped": [{"subject", "message"}…]}``. Qrupun bu semestrdə
    heç bir aktiv jurnalı yoxdursa :class:`ValidationError` (nə ediləcəyi mətndə yazılır).
    """
    from . import guest_roster, subgroup_placement

    if record is None or record.group_id is None:
        raise ValidationError(pgettext(_CTX, "Tələbənin aktiv akademik qeydi (qrupu) yoxdur."))
    if record.group_id == group.pk:
        raise ValidationError(pgettext(_CTX, "Tələbə onsuz da bu qrupdadır."))
    offerings = list(
        CourseOffering.objects.filter(
            organization_id=record.organization_id, group=group, period=period, is_active=True
        ).select_related("subject", "period", "group", "organization")
    )
    if not offerings:
        raise ValidationError(
            pgettext(
                _CTX,
                "Bu qrupun cari semestrdə jurnalı yoxdur. Əvvəl dərs yükündə qrupa fənn yazılsın "
                "(jurnal açılsın), sonra tələbəni əlavə edin.",
            )
        )
    student = record.student
    note = reason or pgettext(_CTX, "Qrup reyestrindən əlavə üzv (öz qrupu: %s)") % record.group.name
    added, skipped = [], []
    for offering in offerings:
        subject = offering.subject.name
        if Enrollment.objects.filter(
            organization_id=offering.organization_id,
            student=student,
            offering=offering,
            status=Enrollment.Status.ENROLLED,
        ).exists():
            skipped.append({"subject": subject, "message": pgettext(_CTX, "onsuz da bu jurnaldadır")})
            continue
        blocked = guest_roster.roster_block_reason(offering)
        if blocked:
            skipped.append({"subject": subject, "message": blocked})
            continue
        try:
            with transaction.atomic():
                plan = subgroup_placement.journal_modal_check(student=student, offering=offering)
                enrollment = guest_roster.add_guest_student(
                    offering=offering, student=student, by_user=by_user, source_group=record.group, reason=note
                )
                subgroup_placement.record_journal_placement(
                    plan=plan, enrollment=enrollment, document=None, actor=by_user, reason=note
                )
        except subgroup_placement.SubgroupPlacementError as exc:
            skipped.append({"subject": subject, "message": str(exc.message)})
            continue
        except ValidationError as exc:
            skipped.append({"subject": subject, "message": " ".join(str(m) for m in exc.messages)})
            continue
        added.append(subject)
    return {"added": added, "skipped": skipped}


def extra_group_members(*, organization, group, period) -> list:
    """Bu qrupun ``period`` jurnallarında olan, amma öz qrupu BAŞQA olan tələbələr (oxu).

    Qaytarır: ``[{"student_id", "subjects": [...]}]`` — çekmecə «Əlavə üzvlər» bölməsi üçün.
    Köhnə sistemdən gələn belə sətirlər (``source_group`` boş) də görünür: meyar tələbənin qeydidir.
    """
    if period is None:
        return []
    from .models import StudentAcademicRecord

    rows = (
        Enrollment.objects.filter(
            organization=organization,
            offering__group=group,
            offering__period=period,
            offering__is_active=True,
            status=Enrollment.Status.ENROLLED,
        )
        .values_list("student_id", "offering__subject__name")
        .order_by("offering__subject__name")
    )
    subjects: dict = {}
    for student_id, subject in rows:
        subjects.setdefault(student_id, [])
        if subject not in subjects[student_id]:
            subjects[student_id].append(subject)
    if not subjects:
        return []
    own = set(
        StudentAcademicRecord.objects.filter(
            organization=organization, student_id__in=list(subjects), group=group
        ).values_list("student_id", flat=True)
    )
    return [{"student_id": sid, "subjects": names} for sid, names in subjects.items() if sid not in own]


__all__ = ["add_extra_group_member", "extra_group_members"]
