"""Sahib 2026-11-24: «praktiki məşğələ» jurnallarında əvvəl «Laboratoriya» kimi yazılmış dərslər (``fix_practical_lab_lessons_20261124``).

Bir çox fənndə seminar sonradan «Praktiki məşğələ» edildi (``CourseOffering.seminar_is_practical`` — yalnız görünüş,
saxlanan növ ``seminar``). Ondan ƏVVƏL müəllimlər praktiki dərsləri «Laboratoriya» növü ilə yazıblar; planda lab
yoxdur, ona görə həmin saatlar «Praktiki məşğələ · 32 / 60 saat» başlığına düşmür (634 İnteryer «Rəngkarlıq-3»: 32
praktiki + 8 lab). Əvvəl «Xüsusi rəsm»-də (c341f38e) əl ilə düzəldilmişdi — indi bütün təşkilat üzrə.

Qayda (biri pozulsa dərsə / açılışa toxunulmur, səbəb sayılır):

* açılış aktivdir və jurnalda seminar «Praktiki məşğələ» görünür (:func:`practical_label.offering_is_practical`);
* açılışın planında lab YOXDUR — həm qrupun rəsmi bölgüsündə (:func:`plan_hours.plan_hours_for_offering`), həm yük
  sətirlərində (:func:`plan_hours_load.workload_hours_for_offering`); lab payı (``JournalShare.kinds`` ∋ lab) yoxdur;
* dərs ``lab`` növüdür və laboratoriya alt qrupuna bağlı DEYİL (``lab_group`` boş) — alt qruplu dərs bütün qrupun
  praktiki dərsi deyil;
* eyni tarix + başlama saatında artıq seminar dərsi yoxdur (təkrar sütun yaranmasın).

Dəyişən yalnız ``Lesson.kind`` (``lab`` → ``seminar``) — xanalar, bal, saat, müəllim eynidir. Qayıb saatı növdən
asılı deyil, yenə də təhlükəsizlik üçün təsirlənən qeydiyyatlarda yenidən hesablanır. Köhnə növlər auditdədir
(``batch``); ``undo`` onları qaytarır. Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.practical_lab_lessons_20261124"
REASON = (
    "Sahib 2026-11-24: «Praktiki məşğələ» jurnalında əvvəl «Laboratoriya» kimi yazılmış dərslər praktiki dərsə çevrildi"
)
UNDO_REASON = "«Laboratoriya» → «Praktiki məşğələ» çevrilməsinin geri qaytarılması"
LAB, SEMINAR = "lab", "seminar"
#: Sahibin göstərdiyi jurnal (634 İnteryer «Rəngkarlıq-3») — yalnız sayda yoxlama üçün.
PROBE_OFFERING = "3b15b28d-1bd2-4d9b-9ad6-5fd9d9fddfba"


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"praclab-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _planned_lab(offering) -> int:
    from .plan_hours import plan_hours_for_offering
    from .plan_hours_load import workload_hours_for_offering

    official = plan_hours_for_offering(offering) or {}
    load = workload_hours_for_offering(offering) or {}
    return max(int(official.get(LAB) or 0), int(load.get(LAB) or 0))


def _has_lab_share(offering) -> bool:
    shares = _model("JournalShare").objects.filter(offering=offering, is_active=True).values_list("kinds", flat=True)
    return any(LAB in (kinds or []) for kinds in shares)


def _offering_skip_reason(offering) -> str:
    from .practical_label import offering_is_practical

    if not offering_is_practical(offering):
        return "skipped_not_practical"
    if _planned_lab(offering) > 0:
        return "skipped_lab_planned"
    if _has_lab_share(offering):
        return "skipped_lab_share"
    return ""


def run(*, organization, actor, counts: Counter, batch: str, offering_ids=None) -> str:
    from .gradebook_marks import recompute_absence_hours_many

    batch = batch or new_batch()
    CourseOffering = _model("CourseOffering")
    Lesson = _model("Lesson")
    Enrollment = _model("Enrollment")
    candidates = CourseOffering.objects.filter(
        organization=organization, is_active=True, lessons__kind=LAB
    ).select_related("subject__chair_unit", "group")
    if offering_ids is not None:
        candidates = candidates.filter(pk__in=list(offering_ids))
    for offering in candidates.distinct().order_by("pk"):
        probe = str(offering.pk) == PROBE_OFFERING
        reason = _offering_skip_reason(offering)
        if reason:
            counts[reason] += 1
            if probe:
                counts[f"probe_{reason}"] += 1
            continue
        lessons = list(Lesson.objects.select_for_update().filter(offering=offering, kind=LAB).order_by("date"))
        seminar_slots = set(Lesson.objects.filter(offering=offering, kind=SEMINAR).values_list("date", "start_time"))
        changed = []
        for lesson in lessons:
            if lesson.lab_group is not None:
                counts["lessons_skipped_lab_group"] += 1
                continue
            if (lesson.date, lesson.start_time) in seminar_slots:
                counts["lessons_skipped_duplicate"] += 1
                continue
            changed.append(lesson)
            seminar_slots.add((lesson.date, lesson.start_time))
        if not changed:
            counts["offerings_nothing_to_change"] += 1
            continue
        Lesson.objects.filter(pk__in=[lesson.pk for lesson in changed]).update(kind=SEMINAR, updated_at=timezone.now())
        recompute_absence_hours_many(list(Enrollment.objects.filter(offering=offering)))
        counts["offerings_fixed"] += 1
        counts["lessons_changed"] += len(changed)
        counts["hours_changed"] += sum(int(lesson.hours or 0) for lesson in changed)
        if probe:
            counts["probe_lessons_changed"] += len(changed)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(offering.pk),
            resource_repr="Laboratoriya kimi yazılmış dərslər praktiki məşğələyə",
            old_values={"kind": LAB, "lessons": [str(lesson.pk) for lesson in changed]},
            new_values={"batch": batch, "kind": SEMINAR},
        )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    from .gradebook_marks import recompute_absence_hours_many

    AuditLog = _model("AuditLog", "audit")
    Lesson = _model("Lesson")
    Enrollment = _model("Enrollment")
    rows = list(AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch))
    if not rows:
        counts["undo_batch_unknown"] += 1
        return
    for row in rows:
        ids = (row.old_values or {}).get("lessons") or []
        restored = Lesson.objects.filter(pk__in=ids, kind=SEMINAR).update(kind=LAB, updated_at=timezone.now())
        counts["undo_lessons_restored"] += restored
        recompute_absence_hours_many(list(Enrollment.objects.filter(offering_id=row.resource_id)))
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=UNDO_REASON,
            resource_type=f"{RESOURCE}.undo",
            resource_id=row.resource_id,
            resource_repr="Praktiki məşğələdən yenidən laboratoriyaya",
            old_values={"batch": batch},
        )


__all__ = ["PROBE_OFFERING", "new_batch", "run", "undo"]
