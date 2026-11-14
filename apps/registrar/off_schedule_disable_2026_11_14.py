"""«Cədvəldən kənar» işarəsi hamıdan təmizlənir (sahib 2026-11-14, MR-356).

Sahib: «cədvəldən kənar yazısını yığışdır, kimə düşübsə də sil. və onu söndürmək olsun — settings-də söndürüb
yandırmaq». Kod tərəfi ``journal.off_schedule_flag`` tənzimləməsidir (defolt söndürülü); bu modul MÖVCUD datadır:
təşkilatın BÜTÜN dərslərinin ``Lesson.off_schedule_reason``-u boşaldılır.

* Hər açılışın «Dəyişiklik tarixçəsi»nə (``off_schedule_flags.clear`` — köhnə səbəb ilə) bir sətir;
* hər açılış üçün bir ``AuditLog`` sətri (``resource_type`` = :data:`CLEARED`): paket id-si (``batch``) və
  ``{dərs_id: köhnə səbəb}`` — ``undo`` məhz bu izlə həmin paketi geri qaytarır.

Dərs, xana, tələbə, slot toxunulmur. Təkrar qaçış idempotentdir (təmizlənəcək dərs qalmır → 0, yeni sətir yoxdur).
"""

from __future__ import annotations

import secrets

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import grade_audit, off_schedule_flags

SOURCE = "off_schedule_disabled_20261114"
CLEARED = "registrar.off_schedule_disable_2026_11_14.cleared"
REASON = "Sahib 2026-11-14 (MR-356): «cədvəldən kənar» işarəsi yığışdırıldı — bütün dərslərdən təmizləndi"
UNDO_REASON = "Sahib 2026-11-14: «cədvəldən kənar» işarəsinin təmizlənməsi geri qaytarıldı"
NOTE = "«cədvəldən kənar» işarəsi söndürüldü — təmizləndi"
BATCH_PREFIX = "offsched-"


def new_batch_id() -> str:
    return f"{BATCH_PREFIX}{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _models():
    return django_apps.get_model("registrar", "CourseOffering"), django_apps.get_model("registrar", "Lesson")


def run(*, organization, actor, counts, batch) -> None:
    Offering, Lesson = _models()
    flagged = Lesson.objects.filter(organization=organization).exclude(off_schedule_reason="")
    by_offering: dict = {}
    for lesson in flagged.order_by("offering_id", "date", "start_time", "pk"):
        by_offering.setdefault(lesson.offering_id, []).append(lesson)
    offerings = Offering.objects.filter(pk__in=list(by_offering)).select_related("period", "organization", "subject")
    for offering in offerings.order_by("pk"):
        lessons = by_offering[offering.pk]
        old = {str(lesson.pk): lesson.off_schedule_reason for lesson in lessons}
        counts["offerings"] += 1
        counts["flagged"] += len(lessons)
        done = off_schedule_flags.clear(offering, lessons, by_user=actor, source=SOURCE, note=NOTE)
        # ``clear`` boşaltdığı dərsin obyektində də səbəbi boşaldır (yarışda dəyişən dərs qalır).
        cleared = {str(lesson.pk): old[str(lesson.pk)] for lesson in lessons if not lesson.off_schedule_reason}
        counts["cleared"] += done
        counts["race_skipped"] += len(lessons) - done
        if not cleared:
            continue
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            old_values={"off_schedule_reason": cleared},
            new_values={"batch": batch, "lessons": cleared},
            reason=REASON,
            resource_type=CLEARED,
            resource_id=str(offering.pk),
            resource_repr="Cədvəldən kənar işarəsi (söndürüldü)",
        )


def undo(*, organization, actor, counts, batch) -> None:
    """Paketin audit izinə görə səbəblər bərpa olunur — yalnız dərs hələ də işarəsizdirsə (sonra yazılan toxunulmur)."""
    Offering, Lesson = _models()
    AuditLog = django_apps.get_model("audit", "AuditLog")
    entries = AuditLog.objects.filter(
        organization=organization, resource_type=CLEARED, new_values__batch=batch
    ).order_by("created_at", "pk")
    for entry in entries:
        counts["undo_entries"] += 1
        offering = Offering.objects.filter(organization=organization, pk=entry.resource_id).first()
        saved = (entry.new_values or {}).get("lessons") or {}
        if offering is None or not isinstance(saved, dict):
            counts["undo_offering_missing"] += 1
            continue
        restored, changes = {}, []
        lessons = list(Lesson.objects.filter(offering=offering, pk__in=list(saved)).order_by("date", "start_time"))
        counts["undo_lessons_missing"] += len(saved) - len(lessons)
        for lesson in lessons:
            reason = str(saved.get(str(lesson.pk)) or "")[:255]
            if not reason or not Lesson.objects.filter(pk=lesson.pk, off_schedule_reason="").update(
                off_schedule_reason=reason
            ):
                counts["undo_already"] += 1
                continue
            restored[str(lesson.pk)] = reason
            changes.append(
                {
                    "student": "—",
                    "item": f"{lesson.date} · {lesson.get_kind_display()}",
                    "old": "—",
                    "new": f"cədvəldən kənar dərs — {reason} (bərpa)",
                }
            )
        if not changes:
            continue
        grade_audit.log_grade_changes(
            offering=offering, by_user=actor, kind="mark", changes=changes, reason=f"off_schedule_restored:{SOURCE}"
        )
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            old_values={"off_schedule_reason": {pk: "" for pk in restored}},
            new_values={"undo_of": str(entry.pk), "batch": batch, "lessons": restored},
            reason=UNDO_REASON,
            resource_type=f"{CLEARED}.undo",
            resource_id=str(offering.pk),
        )
        counts["undo_restored"] += len(restored)


__all__ = ["BATCH_PREFIX", "CLEARED", "SOURCE", "new_batch_id", "run", "undo"]
