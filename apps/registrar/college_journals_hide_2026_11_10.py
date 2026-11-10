"""Kollec jurnalları gizlədilir (sahib 2026-11-10: «gizlət hamısından, onlar köhnə sistemi istifadə edirlər»).

Kollec qruplarının dərsləri bu sistemdə YAZILMIR — jurnallardakı bütün dərslər köhnə sistemdən köçürülmüş
sentyabr–oktyabr qeydləridir, amma jurnallar müəllimlərin siyahısında görünürdü. Kollec qrupu: əcdad bölmənin adında
«Kollec» və ya ``settings.legacy.kollec_or_uni = Kollec`` (``organizations.group_education_form`` ilə eyni əlamət).

Hər aktiv kollec jurnalı (bütün semestrlər): açılış passiv, aktiv qeydiyyatlar «dropped» («Jurnal təmizliyi»ndə
«ləğv edilmiş jurnalda qeydiyyat» bayrağı yaranmasın), cədvəl slotları park (:mod:`applications_repair_2026_11_07`
nümunəsi). Dərslər, qiymətlər, paylar SİLİNMİR. İmtahana bağlı jurnal toxunulmur (sayılır). Hər jurnal üçün audit
sətri yazılır — ``undo`` məhz həmin izlə geri qaytarır. Təkrar qaçış idempotentdir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

HIDDEN = "registrar.college_journals_hide_2026_11_10.hidden"
REASON = "Sahib 2026-11-10: Kollec bu sistemdə yazılmır (köhnə sistem) — jurnal heç kimə göstərilmir"
PARK_REASON = "Sahib 2026-11-10: Kollec jurnalı gizlədilib (köhnə sistemdə aparılır)"
_MARKERS = ("kollec", "kolec", "college")


def _model(app, name):
    return django_apps.get_model(app, name)


def college_group_ids(organization) -> set:
    """Kollec qruplarının id-ləri — əcdad adında marker və ya legacy ``kollec_or_uni`` işarəsi."""
    OrgUnit = _model("organizations", "OrgUnit")
    units = {
        str(pk): (name, unit_type, path, settings)
        for pk, name, unit_type, path, settings in OrgUnit.objects.filter(organization=organization).values_list(
            "pk", "name", "unit_type", "path", "settings"
        )
    }
    found = set()
    for pk, (_name, unit_type, path, settings) in units.items():
        if unit_type != "group":
            continue
        legacy = (
            settings.get("legacy") if isinstance(settings, dict) and isinstance(settings.get("legacy"), dict) else {}
        )
        if str(legacy.get("kollec_or_uni") or "").strip().casefold() in _MARKERS:
            found.add(pk)
            continue
        ancestors = [segment for segment in str(path or "").strip("/").split("/") if segment and segment != pk]
        names = [units[segment][0] for segment in ancestors if segment in units]
        if any(marker in str(name or "").casefold() for name in names for marker in _MARKERS):
            found.add(pk)
    return found


def _exam_linked(offering) -> bool:
    return (
        _model("exams", "Exam").objects.filter(journal_offerings=offering).exists()
        or _model("registrar", "ExamScoreSheet").objects.filter(offering=offering).exists()
    )


def run(*, organization, actor, counts, apply=False) -> None:
    Offering, Enrollment = _model("registrar", "CourseOffering"), _model("registrar", "Enrollment")
    Slot = _model("registrar", "ScheduleSlot")
    groups = college_group_ids(organization)
    counts["college_groups"] += len(groups)
    offerings = (
        Offering.objects.select_for_update(of=("self",))
        .filter(organization=organization, group_id__in=groups, is_active=True)
        .order_by("pk")
    )
    for offering in offerings:
        if _exam_linked(offering):
            counts["exam_linked_skipped"] += 1
            continue
        now = timezone.now()
        enrollments = list(
            Enrollment.objects.filter(offering=offering, status="enrolled").order_by("pk").values_list("pk", flat=True)
        )
        Enrollment.objects.filter(pk__in=enrollments).update(status="dropped", updated_at=now)
        slots = list(
            Slot.objects.filter(offering=offering, is_parked=False).order_by("pk").values_list("pk", flat=True)
        )
        Slot.objects.filter(pk__in=slots).update(
            is_parked=True, parked_at=now, parked_by=actor, park_reason=PARK_REASON, updated_at=now
        )
        Offering.objects.filter(pk=offering.pk).update(is_active=False, updated_at=now)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=offering,
            old_values={"is_active": True},
            new_values={
                "is_active": False,
                "dropped_enrollments": [str(pk) for pk in enrollments],
                "parked_slots": [str(pk) for pk in slots],
            },
            reason=REASON,
            resource_type=HIDDEN,
            resource_id=str(offering.pk),
        )
        counts["offerings_hidden"] += 1
        counts["with_teacher"] += 1 if offering.instructor_id else 0
        counts["enrollments_dropped"] += len(enrollments)
        counts["slots_parked"] += len(slots)


def undo(*, organization, actor, counts, apply=False) -> None:
    """Bu əmrin gizlətdiyi jurnallar audit izinə görə bərpa olunur (sonradan aktivləşdirilən toxunulmur)."""
    Offering, Enrollment = _model("registrar", "CourseOffering"), _model("registrar", "Enrollment")
    Slot, AuditLog = _model("registrar", "ScheduleSlot"), _model("audit", "AuditLog")
    for entry in AuditLog.objects.filter(organization=organization, resource_type=HIDDEN).order_by("created_at"):
        offering = Offering.objects.filter(organization=organization, pk=entry.resource_id, is_active=False).first()
        if offering is None:
            counts["undo_already"] += 1
            continue
        values = entry.new_values or {}
        now = timezone.now()
        counts["undo_enrollments_restored"] += Enrollment.objects.filter(
            offering=offering, pk__in=values.get("dropped_enrollments") or [], status="dropped"
        ).update(status="enrolled", updated_at=now)
        counts["undo_slots_unparked"] += Slot.objects.filter(
            offering=offering, pk__in=values.get("parked_slots") or [], is_parked=True, park_reason=PARK_REASON
        ).update(is_parked=False, parked_at=None, parked_by=None, park_reason="", updated_at=now)
        Offering.objects.filter(pk=offering.pk).update(is_active=True, updated_at=now)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=offering,
            old_values={"is_active": False},
            new_values={"is_active": True, "undo_of": str(entry.pk)},
            reason="Sahib 2026-11-10: Kollec jurnalının gizlədilməsi geri qaytarıldı",
        )
        counts["undo_offerings_reactivated"] += 1


__all__ = ["HIDDEN", "college_group_ids", "run", "undo"]
