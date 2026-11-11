"""İmtahan vermiş, amma fənnin jurnalında OLMAYAN tələbənin jurnala əlavəsi (sahib 2026-11-11).

Sahib: «Fənnin jurnalında olmayan tələbə: 35 / 35 … hər kəs nəticəsini görsün. Jurnalda yoxdursa çox güman alt qrup
tələbəsidir — heç bir sənəd olmadan əlavə et, sənədlər sonradan yüklənəcək.» YENİ YAZI YOLU İCAD OLUNMUR:

* tələbənin öz qrupunun jurnalıdırsa — adi qeydiyyat sətri (DB qapıları işləyir);
* başqa qrupun jurnalıdırsa — rəsmi :func:`.subgroup_placement.place_in_subgroup` (kredit həddi, tutum, cədvəl,
  «artıq keçib» və s. yoxlamaları EYNİDİR; imtina kodu sayılır, tələbə əlavə olunmur). Sənəd tələbi superadmin
  aktorun sənədsiz keçidi ilə (``core.superadmin_waiver`` — avtomatik «SA-…» sərəncamı) ödənilir; səbəb mətnində
  sahibin göstərişi və «sənəd sonradan yüklənəcək» qeydi tarixçədə qalır (``SubgroupPlacementEvent`` + audit).

Hədəf jurnal: imtahanın bağlı jurnallarından tələbənin qrup ailəsinə aid TƏK jurnal; ailədə yoxdursa və imtahanın
TƏK bağlı jurnalı varsa o (alt qrup tələbəsi); əks halda qeyri-müəyyəndir — heç nə yazılmır, sayılır. Bütöv bir qrupun
səhvən yad jurnala yazılmasının qarşısını çağıran alır (imtahan başına hədd — ``journal_missing_takers``).

Hər qaçışın yerləşdirmələri paket id-si ilə audit-ə yazılır (:func:`receipt`); :func:`undo` YALNIZ toxunulmamış
yerləşdirməni azad edir (dərs xanası və ya əl ilə yazılmış bal varsa sətir qalır — ``takers_undo_blocked_touched``).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import credit_load, exam_journal_scope
from .models import CourseOffering, Enrollment
from .subgroup_placement import place_in_subgroup, undo_placement
from .subgroup_placement_errors import SubgroupPlacementError

REASON = (
    "Sahib 2026-11-11: tələbə imtahanda iştirak edib, nəticəsi var, amma fənnin jurnalında yox idi — alt qrup "
    "tələbəsi kimi əlavə olundu. Sahibin göstərişi ilə sənədsiz; sənəd sonradan yüklənəcək."
)
UNDO_REASON = (
    "Sahib 2026-11-11 əlavəsinin geri qaytarılması: imtahan iştirakçısı jurnaldan çıxarıldı (toxunulmamış sətir)"
)
RESOURCE = "registrar.exam_taker_placement"
KIND = "exam_taker_placement"


def _slug(code) -> str:
    return "".join(ch if ch.isalpha() else "_" for ch in str(code).lower())


def is_retake_attempt(*, student, subject_id, organization, attempt) -> bool:
    """Cəhd 25% müraciətinə bağlıdırmı (bağlanmış müraciət də) — belə cəhdin hədəfi jurnal qeydiyyatı deyil."""
    from .retake_results import application_for_attempt

    found = application_for_attempt(student=student, subject_id=subject_id, organization=organization, attempt=attempt)
    return found is not None


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
    """``(kod, Enrollment | None, qəbz | None)`` — kod yalnız ``[a-z_]``; qəbz yalnız YENİ yaranan sətir üçün."""
    record = credit_load.active_record(student, organization)
    if record is None or record.group_id is None:
        return "taker_no_active_record", None, None
    offering, how = choose_offering(organization, record, offering_ids)
    if offering is None:
        return how, None, None
    existing = Enrollment.objects.filter(organization=organization, student=student, offering=offering).first()
    if existing is not None:
        enrolled = existing.status == Enrollment.Status.ENROLLED
        return (
            ("taker_already_in_journal" if enrolled else "taker_left_journal"),
            (existing if enrolled else None),
            None,
        )
    if offering.group_id == record.group_id:
        try:
            with transaction.atomic():
                row = Enrollment.objects.create(organization=organization, student=student, offering=offering)
        except IntegrityError:
            return "taker_own_group_enroll_blocked", None, None
        return "taker_enrolled_own_group", row, {"enrollment": str(row.pk), "event": "", "offering": str(offering.pk)}
    try:
        with transaction.atomic():
            result = place_in_subgroup(student=student, offering=offering, document=None, actor=actor, reason=REASON)
    except SubgroupPlacementError as exc:
        return f"taker_refused_{_slug(exc.code)}", None, None
    row = result["enrollment"]
    receipt_row = {"enrollment": str(row.pk), "event": str(result["event"].pk), "offering": str(offering.pk)}
    return "taker_placed_as_subgroup", row, receipt_row


def receipt(*, organization, actor, batch, placements) -> None:
    if not placements:
        return
    log_action(
        AuditAction.CREATE,
        user=actor,
        organization=organization,
        new_values={"placements": len(placements)},
        changes={"kind": KIND, "batch": batch, "placements": placements},
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=batch,
    )


def _touched(row) -> bool:
    """Yerləşdirmədən sonra müəllim sətirlə işləyib: dərs xanası və ya imtahandan GƏLMƏYƏN komponent balı."""
    return row.lesson_marks.exists() or row.component_scores.filter(exam_source__isnull=True).exists()


def undo(*, organization, actor, counts, batch) -> bool:
    """Paketin toxunulmamış yerləşdirmələrini azad edir. ``False`` — bu paketdə yerləşdirmə qəbzi yoxdur."""
    AuditLog = django_apps.get_model("audit", "AuditLog")
    entries = AuditLog.objects.filter(
        organization=organization, resource_type=RESOURCE, resource_id=batch, changes__kind=KIND
    )
    placements = [item for entry in entries.order_by("created_at") for item in (entry.changes or {})["placements"]]
    if not placements:
        return False
    released = []
    for item in placements:
        row = Enrollment.objects.select_for_update().filter(organization=organization, pk=item["enrollment"]).first()
        if row is None or row.status != Enrollment.Status.ENROLLED:
            counts["takers_undo_already_released"] += 1
            continue
        if _touched(row):
            counts["takers_undo_blocked_touched"] += 1
            continue
        if item.get("event"):
            try:
                with transaction.atomic():
                    undo_placement(event_id=item["event"], actor=actor, reason=UNDO_REASON, organization=organization)
            except SubgroupPlacementError as exc:
                counts[f"takers_undo_refused_{_slug(exc.code)}"] += 1
                continue
        else:
            Enrollment.objects.filter(pk=row.pk).update(status=Enrollment.Status.DROPPED, updated_at=timezone.now())
        released.append(item["enrollment"])
        counts["takers_undo_released"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes={"kind": f"{KIND}_undo", "batch": batch, "released": released},
        reason=UNDO_REASON,
        resource_type=RESOURCE,
        resource_id=batch,
    )
    return True


__all__ = ["KIND", "REASON", "RESOURCE", "choose_offering", "is_retake_attempt", "place", "receipt", "undo"]
