"""Akademik status ↔ CARİ dövr qeydiyyatları (Audit 2026-09-28 S1).

PROBLEM: xaric edilmiş / akademik məzuniyyətə çıxmış tələbənin cari dövr
qeydiyyatları ``enrolled`` qalırdı — jurnalda, imtahan cədvəlində, LMS kursuna
əlavədə aktiv tələbə kimi görünür, qiymət/davamiyyət yazıla bilirdi.

QAYDA (sahib, tövsiyə olunan variant):

* ``enrolled → academic_leave | expelled`` — tələbənin CARİ dövrdəki
  ``enrolled`` qeydiyyatları ``suspended`` olur. Aktiv siyahılar (jurnal,
  imtahan cədvəli, LMS) yalnız ``enrolled`` süzdüyü üçün onları avtomatik
  görmür; ``dropped`` süzgəcləri (transkript, statistika) isə dondurulmuşu
  «tərk edilmiş» saymır — tarixçə itmir.
* ``academic_leave | expelled → enrolled`` (bərpa əmri) — cari dövrün
  ``suspended`` qeydiyyatları yenidən ``enrolled`` olur. Bərpa əmri qrupu da
  dəyişirsə, köçürmə xidməti (``transfer_student_group``) bundan SONRA işləyir
  və bərpa olunmuş qeydiyyatları yeni qrupa aparır.

GƏLƏCƏK DÖVRLƏR (sahib 2026-10-10, «Jurnal təmizliyi»): əvvəlcədən açılmış gələcək semestrin (aktiv,
``start_date`` > bu gün) jurnalı açıq qeydiyyatları da eyni qaydaya düşür — əks halda xaric olunmuş
tələbə növbəti semestrin jurnalında qalırdı. Açar: ``journal_hygiene_guard.prevention_enabled``.

TOXUNULMAYANLAR: keçmiş dövrlər, ``completed`` / ``dropped`` sətirlər,
jurnalı BAĞLI (``assessment_scheme.is_published``) açılışlar — yekunlaşmış
jurnalın tərkibi sonradan dəyişmir.

MƏZUN (sahib 2026-10-25, «Məzun etmə» əmri): xaric etmə kimi cari/gələcək dövrün AÇIQ
qeydiyyatlarını dondurur. Son semestrin jurnalı adətən artıq bağlıdır (yuxarıdakı istisna) —
yəni məzunun yekun jurnalı olduğu kimi qalır; açıq qalan (məs. əvvəlcədən açılmış növbəti
semestr) qeydiyyatlar isə aktiv siyahılardan çıxır. Bərpa əmri onları geri qaytarır.

BAŞQA AKTİV QEYD: qeydiyyat tələbəyə bağlıdır, akademik qeydə yox. Eyni adamın başqa ``enrolled``
qeydi varsa (bakalavr bağlanır, magistrdə oxuyur) dondurma EDİLMİR — əks halda aktiv proqramın
jurnalı da donardı.

Hər dəyişiklik bir audit sətri yazır (fail-closed, çağıranın tranzaksiyasında).
"""

from __future__ import annotations

from django.utils import timezone

from apps.registrar.models import AcademicStatus, Enrollment
from core import audit as audit_service
from core.constants import AuditAction

#: Qeydiyyatı DONDURAN akademik statuslar (modul şərhi; məzun 2026-10-25-dən daxildir).
SUSPENDING_STATUSES = frozenset({AcademicStatus.ACADEMIC_LEAVE, AcademicStatus.EXPELLED, AcademicStatus.GRADUATED})

AUDIT_RESOURCE = "registrar.enrollment_suspension"


def _direction(previous, to_status):
    """``(mənbə, hədəf)`` status cütü və ya ``None`` (qeydiyyata toxunulmur)."""
    from apps.registrar import status as academic_status

    if not previous or previous == to_status:
        return None
    if to_status in SUSPENDING_STATUSES and previous not in SUSPENDING_STATUSES:
        return Enrollment.Status.ENROLLED, Enrollment.Status.SUSPENDED
    if previous in SUSPENDING_STATUSES and academic_status.is_active_for(to_status):
        return Enrollment.Status.SUSPENDED, Enrollment.Status.ENROLLED
    return None


def current_period_enrollments(record, status):
    """Tələbənin CARİ (aktiv) — açar yanılıdırsa həm də GƏLƏCƏK — dövrdə, jurnalı açıq açılışlardakı qeydiyyatları."""
    from apps.registrar import journal_hygiene, journal_hygiene_guard

    queryset = Enrollment.objects.filter(
        organization_id=record.organization_id, student_id=record.student_id, status=status
    )
    if journal_hygiene_guard.prevention_enabled():
        queryset = queryset.filter(journal_hygiene.open_period_q())
    else:
        queryset = queryset.filter(offering__period__is_current=True, offering__period__is_active=True)
    return queryset.exclude(offering__assessment_scheme__is_published=True)


def has_other_active_record(record) -> bool:
    """Eyni tələbənin bu qeyddən BAŞQA ``enrolled`` akademik qeydi varmı."""
    from apps.registrar.models import StudentAcademicRecord

    return (
        StudentAcademicRecord.objects.filter(
            organization_id=record.organization_id, student_id=record.student_id, status=AcademicStatus.ENROLLED
        )
        .exclude(pk=record.pk)
        .exists()
    )


def sync_enrollments_for_status(*, record, previous, to_status, actor=None, reason="") -> dict:
    """Status keçidinə görə cari dövr qeydiyyatlarını dondurur / bərpa edir.

    Çağıran tranzaksiyanın İÇİNDƏ çağırılmalıdır (status yazısı ilə eyni atomik
    blok). Qaytarır ``{"suspended": n, "restored": n, "enrollment_ids": [...]}``.
    """
    result = {"suspended": 0, "restored": 0, "enrollment_ids": []}
    direction = _direction(previous, to_status)
    if direction is None:
        return result
    source, target = direction
    if target == Enrollment.Status.SUSPENDED and has_other_active_record(record):
        return result
    ids = list(
        current_period_enrollments(record, source)
        .select_for_update(of=("self",))
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if not ids:
        return result
    Enrollment.objects.filter(pk__in=ids, status=source).update(status=target, updated_at=timezone.now())
    key = "suspended" if target == Enrollment.Status.SUSPENDED else "restored"
    result[key] = len(ids)
    result["enrollment_ids"] = [str(pk) for pk in ids]
    audit_service.log_action(
        action=AuditAction.UPDATE,
        user=actor if getattr(actor, "pk", None) else None,
        organization=record.organization,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(record.pk),
        resource_repr=str(record.student_id),
        old_values={"status": source},
        new_values={"status": target},
        changes={
            "enrollment_ids": result["enrollment_ids"],
            "academic_status": {"from": previous, "to": to_status},
        },
        reason=reason or f"Akademik status: {previous} → {to_status} ({len(ids)} qeydiyyat: {source} → {target})",
    )
    return result


__all__ = [
    "AUDIT_RESOURCE",
    "SUSPENDING_STATUSES",
    "current_period_enrollments",
    "has_other_active_record",
    "sync_enrollments_for_status",
]
