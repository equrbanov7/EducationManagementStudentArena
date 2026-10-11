"""«Jurnal təmizliyi» — ÖNLƏMƏ qatı: yeni «ayrılmış» və «boş» qeydiyyat yaranmasın (sahib 2026-10-10).

Qaydalar (hamısı :func:`prevention_enabled` açarı ilə; söndürüləndə köhnə davranış OLDUĞU KİMİ qayıdır):

* **Yazılış qapısı** — arxiv hesabı (``access_state=archived``) və ya ``enrolled``/aktiv olmayan akademik qeydi
  olan tələbə üçün YENİ qeydiyyat yaradılmır (:func:`record_is_enrollable`, :func:`archived_student_ids`).
  Mövcud sətir olduğu kimi qaytarılır — tarixçə yenidən aktivləşdirilmir.
* **Seçmə fənn dəyişəndə** köhnə seçimin BOŞ qeydiyyatları ``dropped`` olur (:func:`drop_replaced_elective`);
  qrup həmin fənnə QAYIDANDA bu qərarlar geri qaytarılır (:func:`restore_replaced_elective`).
* **Açılış ləğv olunanda** onun BOŞ qeydiyyatları ``dropped`` olur (:func:`drop_cancelled_offering`).
* Məlumatı (bal, davamiyyət, sənəd…) olan sətrə HEÇ VAXT toxunulmur; hər dəyişiklik qərar jurnalına
  (``JournalHygieneDecision``) və audit-ə yazılır, yəni «Jurnal təmizliyi» → «Tarixçə»-dən geri qaytarılır.

Açar: ``core.runtime_settings``-də ``journal.hygiene_prevention`` qeydə alınıbsa oradan («Sistem
tənzimləmələri»), yoxsa Django ``JOURNAL_HYGIENE_PREVENTION`` ayarından (defolt ``True``) oxunur.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.conf import settings
from django.db import transaction
from django.utils.translation import pgettext

from . import journal_hygiene as hygiene
from .models import AcademicStatus, Enrollment, EnrollmentKind

_CTX = "registrar.journal_hygiene"
RUNTIME_KEY = "journal.hygiene_prevention"


def prevention_enabled() -> bool:
    from core import runtime_settings

    if RUNTIME_KEY in runtime_settings.SPECS:
        return runtime_settings.get_bool(RUNTIME_KEY)
    return bool(getattr(settings, "JOURNAL_HYGIENE_PREVENTION", True))


def archived_student_ids(student_ids) -> set:
    """Hesabı arxivdə olan (məzun/xaric — giriş bağlı) tələbələr; açar söndürülüdə boş dəst."""
    ids = {pk for pk in student_ids if pk}
    if not ids or not prevention_enabled():
        return set()
    profile = django_apps.get_model("accounts", "UserProfile")
    return set(profile.objects.filter(user_id__in=ids, access_state="archived").values_list("user_id", flat=True))


def enrollable_records(queryset):
    """``StudentAcademicRecord`` querysetini YENİ qeydiyyat ala bilənlərə daraldır (açar söndürülüdə olduğu kimi)."""
    if not prevention_enabled():
        return queryset
    return queryset.filter(status=AcademicStatus.ENROLLED, is_active=True).exclude(
        student__profile__access_state="archived"
    )


def record_is_enrollable(record) -> bool:
    """Bu akademik qeyd üçün YENİ qeydiyyat yaradıla bilərmi."""
    if not prevention_enabled():
        return True
    if record.status != AcademicStatus.ENROLLED or not record.is_active:
        return False
    return not archived_student_ids([record.student_id])


def existing_enrollment(record, *, subject, period):
    """Qeydin qrup açılışındakı mövcud sətri (yaradılmır) — qapı bağlıdırsa çağıranlara qaytarılır."""
    return (
        Enrollment.objects.filter(
            organization_id=record.organization_id,
            student_id=record.student_id,
            offering__subject=subject,
            offering__period=period,
            offering__group_id=record.group_id,
        )
        .order_by("created_at")
        .first()
    )


def drop_empty_enrollments(queryset, *, organization, reason_code, reason, actor=None, request=None) -> int:
    """``queryset``-in BOŞ (alt-qrup əlavəsi olmayan) qeydiyyatlarını ``dropped`` edir — jurnal + audit ilə."""
    from . import journal_hygiene_actions as actions
    from . import journal_hygiene_rows as rows_service

    with transaction.atomic():
        found = list(
            queryset.filter(organization=organization, source_group__isnull=True, absence_hours=0)
            .exclude(status=Enrollment.Status.DROPPED)
            .filter(*hygiene.no_evidence_filters())
            .select_for_update(of=("self",))
            .order_by("pk")
            .values_list("pk", "status")
        )
        if not found:
            return 0
        counts = rows_service.evidence_counts([pk for pk, _status in found])
        rows = []
        for pk, status in found:
            row = {"id": str(pk), "status": status, "reason": reason_code, "strong": False, "absence_hours": 0}
            row["tags"] = [{"code": reason_code}]
            row["evidence"] = actions.row_evidence(row, hygiene.EMPTY, counts.get(str(pk)))
            rows.append(row)
        result = actions.record_decisions(
            organization=organization,
            category=hygiene.EMPTY,
            rows=rows,
            to_status=Enrollment.Status.DROPPED,
            reason=reason,
            actor=actor,
            request=request,
        )
    return int(result["changed"])


def drop_replaced_elective(*, organization, group, period, old_subject_id, new_subject, actor=None) -> int:
    """Qrup seçmə blokunu dəyişdi: köhnə seçimin BOŞ (``elective``) qeydiyyatları nəticələrdən çıxır."""
    if not prevention_enabled() or not old_subject_id or old_subject_id == getattr(new_subject, "pk", None):
        return 0
    queryset = Enrollment.objects.filter(
        offering__group=group,
        offering__period=period,
        offering__subject_id=old_subject_id,
        kind=EnrollmentKind.ELECTIVE,
    )
    reason = pgettext(
        _CTX, "Qrupun seçmə fənni dəyişdirildi (%(group)s → %(subject)s): köhnə seçimin boş qeydiyyatı çıxarıldı."
    ) % {"group": getattr(group, "name", ""), "subject": getattr(new_subject, "code", "")}
    return drop_empty_enrollments(
        queryset, organization=organization, reason_code=hygiene.SOURCE_REPLACED, reason=reason, actor=actor
    )


def restore_replaced_elective(*, organization, offering, student_ids=None, actor=None) -> int:
    """Qrup əvvəl dəyişdirdiyi seçmə fənnə QAYIDIR: :func:`drop_replaced_elective`-in bu açılışdakı qərarları
    geri qaytarılır (status əvvəlkinə; qərar jurnalında «geri qaytarıldı»).

    Əks halda ``get_or_create`` köhnə ``dropped`` sətri tapıb onu olduğu kimi saxlayardı və qrup həmin fənndən
    kənarda qalardı. Açardan asılı deyil: alətin ÖZ qərarını geri almaq həmişə doğrudur. ``student_ids``
    verilibsə yalnız o tələbələr (qrupun hazırda yazıla bilən üzvləri) bərpa olunur; statusu o vaxtdan
    dəyişmiş və ya tələbəsi həmin fənn üzrə başqa jurnalda aktiv olan sətir toxunulmur.
    """
    from . import journal_hygiene_actions as actions
    from .models import JournalHygieneDecision

    queryset = JournalHygieneDecision.objects.filter(
        organization=organization,
        enrollment__offering=offering,
        category=hygiene.EMPTY,
        reason_code=hygiene.SOURCE_REPLACED,
        reverted_at__isnull=True,
    )
    if student_ids is not None:
        queryset = queryset.filter(enrollment__student_id__in=list(student_ids))
    with transaction.atomic():
        decisions = list(queryset.select_for_update(of=("self",)).order_by("pk"))
        if not decisions:
            return 0
        enrollments = {
            item.pk: item
            for item in Enrollment.objects.select_for_update(of=("self",))
            .filter(organization=organization, pk__in={item.enrollment_id for item in decisions})
            .select_related("offering")
        }
        decisions = [item for item in decisions if enrollments[item.enrollment_id].status == item.to_status]
        restoring = [
            enrollments[item.enrollment_id] for item in decisions if item.from_status == Enrollment.Status.ENROLLED
        ]
        clashes = actions.active_elsewhere(organization, restoring)
        decisions = [
            item
            for item in decisions
            if (
                enrollments[item.enrollment_id].student_id,
                offering.subject_id,
                offering.period_id,
            )
            not in clashes
        ]
        if not decisions:
            return 0
        reason = pgettext(_CTX, "Qrup bu seçmə fənni yenidən seçdi — əvvəl çıxarılmış boş qeydiyyat bərpa olundu.")
        result = actions.revert_locked(
            organization=organization, decisions=decisions, enrollments=enrollments, reason=reason, actor=actor
        )
    return int(result["reverted"])


def drop_cancelled_offering(offering, *, reason, actor=None, request=None) -> int:
    """Açılış ləğv olundu: onun BOŞ qeydiyyatları nəticələrdən çıxır (məlumatı olan qalır)."""
    if not prevention_enabled():
        return 0
    text = pgettext(_CTX, "Açılış ləğv olundu: %(reason)s") % {"reason": reason}
    return drop_empty_enrollments(
        Enrollment.objects.filter(offering=offering),
        organization=offering.organization,
        reason_code=hygiene.SOURCE_CANCELLED,
        reason=text,
        actor=actor,
        request=request,
    )


__all__ = [
    "RUNTIME_KEY",
    "archived_student_ids",
    "drop_cancelled_offering",
    "drop_empty_enrollments",
    "drop_replaced_elective",
    "enrollable_records",
    "existing_enrollment",
    "prevention_enabled",
    "record_is_enrollable",
    "restore_replaced_elective",
]
