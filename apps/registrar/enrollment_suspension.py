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

TOXUNULMAYANLAR: keçmiş dövrlər, ``completed`` / ``dropped`` sətirlər,
jurnalı BAĞLI (``assessment_scheme.is_published``) açılışlar — yekunlaşmış
jurnalın tərkibi sonradan dəyişmir. Məzuniyyət (graduated) qeydiyyatları
dondurmur: məzun tələbənin son semestr jurnalı olduğu kimi qalmalıdır.

Hər dəyişiklik bir audit sətri yazır (fail-closed, çağıranın tranzaksiyasında).
"""

from __future__ import annotations

from django.utils import timezone

from apps.registrar.models import AcademicStatus, Enrollment
from core import audit as audit_service
from core.constants import AuditAction

#: Qeydiyyatı DONDURAN akademik statuslar (məzun QƏSDƏN yoxdur — modul şərhi).
SUSPENDING_STATUSES = frozenset({AcademicStatus.ACADEMIC_LEAVE, AcademicStatus.EXPELLED})

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
    """Tələbənin CARİ (aktiv) dövrdə, jurnalı açıq açılışlardakı ``status`` qeydiyyatları."""
    return Enrollment.objects.filter(
        organization_id=record.organization_id,
        student_id=record.student_id,
        status=status,
        offering__period__is_current=True,
        offering__period__is_active=True,
    ).exclude(offering__assessment_scheme__is_published=True)


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
    "sync_enrollments_for_status",
]
