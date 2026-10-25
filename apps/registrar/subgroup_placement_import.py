"""Köçürmə ilə yaranmış «alt qrupdan əlavə» qeydiyyatını RƏSMİ tarixçəyə yazmaq (sahib 2026-10-25).

Sahib: «Alt qrup tələbələrini tapsan işarələ — yeni sistemdə işarələyərək göndər, görünsün ki alt qrupdur.»

Köhnə sistemdən (myedu) gələn delta tələbəni alt qrupun jurnalına ``source_group`` provenansı ilə yazır
(:func:`guest_roster.add_guest_student`-in formasında) — jurnal çipi onu görür, amma «Alt qrupa yerləşdir»
alətinin tarixçəsi və tələbə reyestrinin kartı (:class:`SubgroupPlacementEvent`) boş qalırdı. Bu modul
YENİ YAZI YOLU İCAD ETMİR: mövcud canlı qeydiyyata modal yolunun (:func:`subgroup_placement.
record_journal_placement`) eyni formalı ``place`` sətrini yazır — qeydiyyatın özünə, bala, davamiyyətə
toxunmur, bildiriş göndərmir (köçürmədir, yeni qərar deyil). Sətir alətin rəsmi «geri götür» axını ilə
idarə olunur (``undo_placement``).

İdempotentdir: qeydiyyatın artıq ``place`` sətri varsa (geri götürülmüş olsa belə) yenisi yazılmır.
"""

from __future__ import annotations

from core.constants import AuditAction

from . import credit_load
from .models import Enrollment, SubgroupPlacementEvent, SubgroupPlacementKind
from .subgroup_placement import MIN_REASON_LENGTH, _audit, _clean_reason


def has_placement(enrollment_id) -> bool:
    return SubgroupPlacementEvent.objects.filter(enrollment_id=enrollment_id, kind=SubgroupPlacementKind.PLACE).exists()


def record_imported_placement(*, enrollment, actor, reason, details=None, load=None):
    """Canlı «alt qrupdan əlavə» qeydiyyatına ``place`` sətri. Qaytarır: sətir və ya ``None`` (uyğun deyil/var).

    *load* — tələbənin həmin dövr üzrə :func:`credit_load.credit_load` nəticəsi (çağıran tələbə üzrə
    keşləyə bilər); verilməsə hesablanır. Kredit «əvvəl/sonra» qeyd anındakı yükdür (qeydiyyat artıq var).
    """
    reason = _clean_reason(reason)
    if len(reason) < MIN_REASON_LENGTH:
        raise ValueError("subgroup_import_reason_too_short")
    offering = enrollment.offering
    if (
        enrollment.status != Enrollment.Status.ENROLLED
        or enrollment.source_group_id is None
        or offering.group_id is None
        or enrollment.source_group_id == offering.group_id
    ):
        return None
    if has_placement(enrollment.pk):
        return None
    if load is None:
        load = credit_load.credit_load(enrollment.student, offering.period, organization=offering.organization)
    credits = next(
        (item["credits"] for item in load.get("items") or () if item.get("enrollment_id") == str(enrollment.pk)), 0
    )
    total = int(load.get("total") or 0)
    event = SubgroupPlacementEvent.objects.create(
        organization_id=enrollment.organization_id,
        kind=SubgroupPlacementKind.PLACE,
        enrollment=enrollment,
        student_id=enrollment.student_id,
        offering=offering,
        source_group_id=enrollment.source_group_id,
        target_group_id=offering.group_id,
        reason=reason,
        credits_before=max(0, total - int(credits or 0)),
        credits_after=total,
        credit_limit=int(load.get("limit") or 0),
        details={"via": "import", **(details or {})},
        actor=actor,
    )
    _audit(event=event, actor=actor, request=None, action=AuditAction.CREATE, verb="place_import")
    return event


__all__ = ["has_placement", "record_imported_placement"]
