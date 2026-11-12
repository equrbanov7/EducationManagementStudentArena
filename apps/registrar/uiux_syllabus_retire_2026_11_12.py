"""Səbinə Mustafayevanın «QKU-2703 İnsan-kompüter interfeysi (UI/UX)» sillabusu gizlədilir (sahib 2026-11-12).

Müəllimin müraciəti: «İnsan və kompüter interfeysi fənnindən 2 jurnal açılır. UI/UX yazılan açılmamalıdır».
233 K az jurnalı (fənn QKU-269 «İnsan-kompüter interfeysləri») öz təsdiqli sillabusunu göstərir; QKU-2703
dosyesi eyni proqram (Kompüter Mühəndisliyi) üçün ikinci, artıq nüsxədir və müəllimin siyahısında yanaşı
görünür. Dosye SİLİNMİR — yalnız ``is_active=False`` (``syllabus.services.queries.list_syllabi`` passiv dosyeni
göstərmir); versiyalar, bölmələr, təsdiq tarixçəsi olduğu kimi qalır. ``undo`` audit izinə görə geri açır.

Qoruyucular (biri pozulsa heç nə yazılmır): dosye bu təşkilatdadır, müəllifi və fənn kodu gözlənilən kimidir,
aktiv jurnala bağlı deyil, paylaşılmayıb / təkrar istifadə olunmayıb, və müəllifin eyni proqram üçün QKU-269
üzrə AKTİV sillabusu var (müəllim sillabussuz qalmır).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import CommandError
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RETIRED = "registrar.uiux_syllabus_retire_2026_11_12.retired"
REASON = "Sahib 2026-11-12: müəllimin müraciəti — «UI/UX» sillabusu artıq nüsxədir, QKU-269 sillabusu qalır"
TARGET = {
    "syllabus": "ab3f3977-26b1-45e0-af4c-7234325a2000",
    "author": 7750,
    "subject_code": "QKU-2703",
    "keeper_subject_code": "QKU-269",
}


def _model(app, name):
    return django_apps.get_model(app, name)


def _guard(organization, syllabus, target) -> None:
    Syllabus, Share = _model("syllabus", "Syllabus"), _model("syllabus", "SyllabusShare")
    if syllabus.author_id != target["author"] or syllabus.subject.code != target["subject_code"]:
        raise CommandError("syllabus_retire_scope_changed")
    if syllabus.offering_id and syllabus.offering.is_active:
        raise CommandError("syllabus_retire_bound_to_active_journal")
    if (
        Share.objects.filter(syllabus=syllabus).exists()
        or Syllabus.objects.filter(organization=organization, reused_from=syllabus).exists()
    ):
        raise CommandError("syllabus_retire_shared")
    keeper = Syllabus.objects.filter(
        organization=organization,
        author_id=target["author"],
        subject__code=target["keeper_subject_code"],
        program_id=syllabus.program_id,
        is_active=True,
        approved_version__status="approved",
    )
    if not keeper.exists():
        raise CommandError("syllabus_retire_keeper_missing")


def run(*, organization, actor, counts, apply=False, target=None) -> None:
    target = target or TARGET
    Syllabus = _model("syllabus", "Syllabus")
    syllabus = (
        Syllabus.objects.select_for_update(of=("self",))
        .select_related("subject", "offering")
        .filter(organization=organization, pk=target["syllabus"])
        .first()
    )
    if syllabus is None:
        raise CommandError("syllabus_retire_not_found")
    if not syllabus.is_active:
        counts["already_retired"] += 1
        return
    _guard(organization, syllabus, target)
    Syllabus.objects.filter(pk=syllabus.pk).update(is_active=False, updated_at=timezone.now())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=syllabus,
        old_values={"is_active": True},
        new_values={"is_active": False, "subject_code": target["subject_code"]},
        reason=REASON,
        resource_type=RETIRED,
        resource_id=str(syllabus.pk),
    )
    counts["syllabi_retired"] += 1


def undo(*, organization, actor, counts, apply=False, target=None) -> None:
    """Bu əmrin söndürdüyü dosye audit izinə görə yenidən aktiv olur."""
    Syllabus, AuditLog = _model("syllabus", "Syllabus"), _model("audit", "AuditLog")
    for entry in AuditLog.objects.filter(organization=organization, resource_type=RETIRED).order_by("created_at"):
        syllabus = Syllabus.objects.filter(organization=organization, pk=entry.resource_id, is_active=False).first()
        if syllabus is None:
            counts["undo_already"] += 1
            continue
        Syllabus.objects.filter(pk=syllabus.pk).update(is_active=True, updated_at=timezone.now())
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=syllabus,
            old_values={"is_active": False},
            new_values={"is_active": True, "undo_of": str(entry.pk)},
            reason="Sahib 2026-11-12: «UI/UX» sillabusunun gizlədilməsi geri qaytarıldı",
        )
        counts["undo_syllabi_reactivated"] += 1


__all__ = ["RETIRED", "TARGET", "run", "undo"]
