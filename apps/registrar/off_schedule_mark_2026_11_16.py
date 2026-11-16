"""«Cədvəldən kənar» işarəsi cədvələ uyğun olmayan dərslərə bərpa olunur (sahib 2026-11-16).

Sahib: «dərsdən kənar yazısını dərs cədvəlinə uyğun olmayanda bərpa et; sistemdən yandırıb-söndürmək olsun». Kod
tərəfi ``journal.off_schedule_flag`` tənzimləməsidir; 14.11-də təmizlənən 650 dərs ``offsched-…`` paketinin geri
qaytarılması ilə öz səbəbini alır. Bu modul QALANLARDIR — CARİ semestrin aktiv jurnallarında işarəsiz, amma cədvələ
UYĞUN OLMAYAN dərslər (əsasən işarə söndürülü ikən 14.11-dən sonra açılanlar) sabit avtomatik səbəb alır
(:data:`AUTO_REASON`).

Qayda yaradılma və ``clear_stale_off_schedule_flags`` ilə EYNİDİR (:func:`off_schedule_flags.unflagged_off_schedule`
— :func:`off_schedule_flags.is_on_schedule`-in tərsi). Ötürülür (sayılır):

* passiv dərs (``check_manual_lesson`` kimi — cədvəl dərsi deyil);
* cədvəldə DURAN slotu olmayan jurnal (müqayisə ediləcək cədvəl yoxdur);
* 14.11 təmizləməsinin hələ geri qaytarılmamış dərsi — onun öz səbəbini ``offsched-…`` undo-su bərpa edir.

Hər jurnalın «Dəyişiklik tarixçəsi»nə bir sətir + bir ``AuditLog`` sətri (``resource_type`` = :data:`MARKED`, paket
id-si ``batch`` + dərs id-ləri) — ``undo`` məhz bu izlə yalnız SƏBƏBİ HƏLƏ :data:`AUTO_REASON` OLAN dərsləri
təmizləyir. Dərs, xana, tələbə, slot toxunulmur. Təkrar qaçış idempotentdir.
"""

from __future__ import annotations

import datetime as _dt
import secrets

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import grade_audit, off_schedule_flags
from .off_schedule_disable_2026_11_14 import CLEARED as OFFSCHED_CLEARED

SOURCE = "off_schedule_marked_20261116"
MARKED = "registrar.off_schedule_mark_2026_11_16.marked"
AUTO_REASON = "Dərs cədvəlinə uyğun deyil (avtomatik işarə)"
REASON = "Sahib 2026-11-16: cədvələ uyğun olmayan dərsə «cədvəldən kənar» işarəsi bərpa olundu"
UNDO_REASON = "Sahib 2026-11-16: avtomatik «cədvəldən kənar» işarəsi geri alındı"
UNDO_NOTE = "avtomatik «cədvəldən kənar» işarəsi geri alındı"
BATCH_PREFIX = "offmark-"
#: İşarə söndürülən gün (``clear_off_schedule_flags_20261114``) — bu gündən sonra açılan dərslər ayrıca sayılır.
FLAG_OFF_SINCE = _dt.date(2026, 11, 14)
_FIELDS = ("id", "offering", "date", "start_time", "kind", "off_schedule_reason", "is_passive", "created_at")


def new_batch_id() -> str:
    return f"{BATCH_PREFIX}{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _models():
    return django_apps.get_model("registrar", "CourseOffering"), django_apps.get_model("registrar", "Lesson")


def current_period(organization):
    from .exam_bridge import _current_period

    return _current_period(organization)


def awaiting_offsched_undo(organization) -> set:
    """14.11 təmizləməsinin dərsləri — paketi hələ geri qaytarılmayıbsa (``.undo`` sətri yoxdur)."""
    AuditLog = django_apps.get_model("audit", "AuditLog")
    undone = {
        str((values or {}).get("undo_of") or "")
        for values in AuditLog.objects.filter(
            organization=organization, resource_type=f"{OFFSCHED_CLEARED}.undo"
        ).values_list("new_values", flat=True)
    }
    pending = set()
    for pk, values in AuditLog.objects.filter(organization=organization, resource_type=OFFSCHED_CLEARED).values_list(
        "pk", "new_values"
    ):
        lessons = (values or {}).get("lessons")
        if str(pk) not in undone and isinstance(lessons, dict):
            pending.update(str(key) for key in lessons)
    return pending


def _mark(offering, lessons, *, actor, counts) -> list:
    _, Lesson = _models()
    marked, changes = [], []
    for lesson in lessons:
        if not Lesson.objects.filter(pk=lesson.pk, off_schedule_reason="").update(off_schedule_reason=AUTO_REASON):
            counts["race_skipped"] += 1
            continue
        lesson.off_schedule_reason = AUTO_REASON
        marked.append(str(lesson.pk))
        changes.append(
            {
                "student": "—",
                "item": f"{lesson.date} · {lesson.get_kind_display()}",
                "old": "—",
                "new": f"cədvəldən kənar dərs — {AUTO_REASON}",
            }
        )
    if changes:
        grade_audit.log_grade_changes(
            offering=offering, by_user=actor, kind="mark", changes=changes, reason=f"off_schedule_marked:{SOURCE}"
        )
    return marked


def run(*, organization, actor, counts, batch) -> None:
    Offering, Lesson = _models()
    period = current_period(organization)
    if period is None:
        counts["no_period"] += 1
        return
    pending = awaiting_offsched_undo(organization)
    rows = Lesson.objects.filter(
        organization=organization, offering__period=period, offering__is_active=True, off_schedule_reason=""
    ).only(*_FIELDS)
    by_offering: dict = {}
    for lesson in rows.order_by("offering_id", "date", "start_time", "pk"):
        if lesson.is_passive:
            counts["passive_skipped"] += 1
        elif str(lesson.pk) in pending:
            counts["awaiting_offsched_undo"] += 1
        else:
            by_offering.setdefault(lesson.offering_id, []).append(lesson)
    offerings = Offering.objects.filter(pk__in=list(by_offering)).select_related("period", "organization", "subject")
    for offering in offerings.order_by("pk"):
        lessons = by_offering[offering.pk]
        if not off_schedule_flags.has_timetable(offering):
            counts["no_slots_offerings"] += 1
            counts["no_slots_lessons"] += len(lessons)
            continue
        counts["offerings"] += 1
        counts["lessons"] += len(lessons)
        targets = off_schedule_flags.unflagged_off_schedule(offering, lessons)
        counts["on_schedule"] += len(lessons) - len(targets)
        counts["off_schedule"] += len(targets)
        counts["off_no_time"] += sum(1 for lesson in targets if lesson.start_time is None)
        counts["off_created_since_nov_fourteen"] += sum(
            1 for lesson in targets if lesson.created_at and timezone.localdate(lesson.created_at) >= FLAG_OFF_SINCE
        )
        if not targets:
            continue
        counts["offerings_marked"] += 1
        marked = _mark(offering, targets, actor=actor, counts=counts)
        counts["marked"] += len(marked)
        if not marked:
            continue
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            old_values={"off_schedule_reason": {pk: "" for pk in marked}},
            new_values={"batch": batch, "period_id": str(period.pk), "reason": AUTO_REASON, "lessons": marked},
            reason=REASON,
            resource_type=MARKED,
            resource_id=str(offering.pk),
            resource_repr="Cədvəldən kənar işarəsi (bərpa)",
        )


def undo(*, organization, actor, counts, batch) -> None:
    """Paketin audit izinə görə — yalnız səbəbi HƏLƏ :data:`AUTO_REASON` olan dərslərin işarəsi təmizlənir."""
    Offering, Lesson = _models()
    AuditLog = django_apps.get_model("audit", "AuditLog")
    entries = AuditLog.objects.filter(
        organization=organization, resource_type=MARKED, new_values__batch=batch
    ).order_by("created_at", "pk")
    for entry in entries:
        counts["undo_entries"] += 1
        offering = (
            Offering.objects.filter(organization=organization, pk=entry.resource_id)
            .select_related("period", "organization", "subject")
            .first()
        )
        saved = (entry.new_values or {}).get("lessons") or []
        if offering is None or not isinstance(saved, list):
            counts["undo_offering_missing"] += 1
            continue
        lessons = list(Lesson.objects.filter(offering=offering, pk__in=saved).order_by("date", "start_time", "pk"))
        counts["undo_lessons_missing"] += len(saved) - len(lessons)
        auto = [lesson for lesson in lessons if lesson.off_schedule_reason == AUTO_REASON]
        counts["undo_changed"] += len(lessons) - len(auto)
        done = off_schedule_flags.clear(offering, auto, by_user=actor, source=SOURCE, note=UNDO_NOTE) if auto else 0
        cleared = [str(lesson.pk) for lesson in auto if not lesson.off_schedule_reason]
        counts["undo_cleared"] += done
        counts["undo_changed"] += len(auto) - done
        if not cleared:
            continue
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            old_values={"off_schedule_reason": {pk: AUTO_REASON for pk in cleared}},
            new_values={"undo_of": str(entry.pk), "batch": batch, "lessons": cleared},
            reason=UNDO_REASON,
            resource_type=f"{MARKED}.undo",
            resource_id=str(offering.pk),
        )


__all__ = ["AUTO_REASON", "BATCH_PREFIX", "MARKED", "SOURCE", "awaiting_offsched_undo", "new_batch_id", "run", "undo"]
