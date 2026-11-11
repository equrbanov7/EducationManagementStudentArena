"""İmtahan vermiş, amma fənnin jurnalında OLMAYAN tələbənin jurnala əlavəsi (sahib 2026-11-11).

Sahib: «Fənnin jurnalında olmayan tələbə: 35 / 35 … hər kəs nəticəsini görsün. Jurnalda yoxdursa çox güman alt qrup
tələbəsidir — heç bir sənəd olmadan əlavə et, sənədlər sonradan yüklənəcək.» YENİ YAZI YOLU İCAD OLUNMUR:

* tələbənin öz qrupunun (və ya ana qrupunun ailəsinin) jurnalıdırsa — adi qeydiyyat sətri (DB qapıları işləyir);
* başqa qrupun jurnalıdırsa — rəsmi :func:`.subgroup_placement.place_in_subgroup` (kredit həddi, tutum, cədvəl,
  «artıq keçib» və s. yoxlamaları EYNİDİR; imtina kodu sayılır, tələbə əlavə olunmur). Sənəd tələbi superadmin
  aktorun sənədsiz keçidi ilə (``core.superadmin_waiver`` — avtomatik «SA-…» sərəncamı) ödənilir; səbəb mətnində
  sahibin göstərişi və «sənəd sonradan yüklənəcək» qeydi tarixçədə qalır (``SubgroupPlacementEvent`` + audit).

Hədəf jurnal: imtahanın bağlı jurnallarından tələbənin qrup ailəsinə aid TƏK jurnal; ailədə yoxdursa və imtahanın
TƏK bağlı jurnalı varsa o (alt qrup tələbəsi); əks halda qeyri-müəyyəndir — heç nə yazılmır, sayılır.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from . import credit_load, exam_journal_scope
from .models import CourseOffering, Enrollment
from .subgroup_placement import place_in_subgroup
from .subgroup_placement_errors import SubgroupPlacementError

REASON = (
    "Sahib 2026-11-11: tələbə imtahanda iştirak edib, nəticəsi var, amma fənnin jurnalında yox idi — alt qrup "
    "tələbəsi kimi əlavə olundu. Sahibin göstərişi ilə sənədsiz; sənəd sonradan yüklənəcək."
)


def choose_offering(organization, record, offering_ids):
    """``(açılış | None, kod)`` — kod: ``own`` / ``single`` / ``taker_no_journal`` / ``taker_journal_ambiguous``."""
    offerings = list(
        CourseOffering.objects.filter(organization=organization, pk__in=list(offering_ids), is_active=True)
    )
    if not offerings:
        return None, "taker_no_journal"
    _units, _own, linked = exam_journal_scope.unit_families(organization, [record.group_id])
    family = linked.get(record.group_id, {record.group_id})
    own = [row for row in offerings if row.group_id in family]
    if len(own) == 1:
        return own[0], "own"
    if not own and len(offerings) == 1:
        return offerings[0], "single"
    return None, "taker_journal_ambiguous"


def place(*, organization, student, offering_ids, actor) -> tuple:
    """``(kod, Enrollment | None)`` — kod yalnız ``[a-z_]`` (sayğac açarı)."""
    record = credit_load.active_record(student, organization)
    if record is None or record.group_id is None:
        return "taker_no_active_record", None
    offering, how = choose_offering(organization, record, offering_ids)
    if offering is None:
        return how, None
    existing = Enrollment.objects.filter(organization=organization, student=student, offering=offering).first()
    if existing is not None:
        code = "taker_already_in_journal" if existing.status == Enrollment.Status.ENROLLED else "taker_left_journal"
        return code, existing if existing.status == Enrollment.Status.ENROLLED else None
    if offering.group_id == record.group_id:
        try:
            with transaction.atomic():
                row = Enrollment.objects.create(organization=organization, student=student, offering=offering)
        except IntegrityError:
            return "taker_own_group_enroll_blocked", None
        return "taker_enrolled_own_group", row
    try:
        with transaction.atomic():
            result = place_in_subgroup(student=student, offering=offering, document=None, actor=actor, reason=REASON)
    except SubgroupPlacementError as exc:
        return f"taker_refused_{''.join(ch if ch.isalpha() else '_' for ch in str(exc.code).lower())}", None
    return "taker_placed_as_subgroup", result["enrollment"]


__all__ = ["REASON", "choose_offering", "place"]
