"""MR-000714 (2026-11-24): təkrar boş jurnala yazılmış Midterm balları əsl jurnala (``copy_dup_journal_midterms_20261124``).

Magistratura qruplarında «Biologiyanın müasir problemləri» fənninin iki jurnalı var: əsl jurnal (dərs yükü, Sevinc
Rəcəbova, dərslər keçirilir) və köhnə tədris planından açılmış dərssiz təkrar — «Biologiyanın müasir problemləri və
perspektivləri». İmtahan Mərkəzi 23.11-də Midterm ballarını səhvən TƏKRAR jurnala yazıb (709/6 SBİO: 9 tələbə);
əsl jurnalda Midterm boşdur, tələbə kabinetində bal görünmür (Nuray Süleymanova, MR-000714).

Qayda (sabit cütlər, «yalnız boşluğu doldur»):

* mənbə — təkrar jurnalın hər qeydiyyatının (statusundan asılı olmayaraq) Midterm balı;
* hədəf — eyni tələbənin əsl jurnaldakı ``enrolled`` qeydiyyatı; əsl jurnalın Midterm komponenti
  :func:`interim_components.ensure_kollokviums` ilə (yoxdursa yaradılır, adi qayda);
* hədəfdə bal yoxdursa yaradılır (``exam_source`` ilə); varsa — sayılır, toxunulmur; əsl jurnalda qeydiyyatı
  olmayan tələbə sayılır (``no_target_enrollment``). Mənbəyə toxunulmur.

``undo`` — yalnız həmin ``batch``-ın yaratdığı balları silir. Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.dup_journal_midterms_20261124"
REASON = "MR-000714: təkrar boş jurnala yazılmış Midterm balı əsl «Biologiyanın müasir problemləri» jurnalına köçürüldü"
UNDO_REASON = "MR-000714: köçürülmüş Midterm ballarının geri götürülməsi"

#: (təkrar jurnal, əsl jurnal)
PAIRS = (
    ("642fd163-bfea-49ea-ad38-ce4c2c104723", "9e5a7ebf-1ea3-4dca-a0b5-d16f0089f82b"),  # 709/6 SBİO
    ("b52f6b59-98bb-4a98-bf6a-e24c14e8c62a", "fa78490b-65ec-482b-9cf4-3601350d6250"),  # 505/6 MB
    ("eb5d43b1-e1c7-4faf-b0d2-05b01b3a987f", "affdce67-67a7-4868-ba80-b61319d03b33"),  # 505/6 G
)


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"dupmid-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def run(*, organization, actor, counts: Counter, batch: str, pairs=None) -> str:
    from .interim_components import ensure_kollokviums

    batch = batch or new_batch()
    CourseOffering = _model("CourseOffering")
    Enrollment = _model("Enrollment")
    ComponentScore = _model("ComponentScore")
    created = []
    for source_id, target_id in pairs or PAIRS:
        source = CourseOffering.objects.filter(organization=organization, pk=source_id).first()
        target = CourseOffering.objects.filter(organization=organization, pk=target_id).first()
        if source is None or target is None or source.subject_id == target.subject_id:
            counts["pair_invalid"] += 1
            continue
        if source.group_id != target.group_id or source.period_id != target.period_id:
            counts["pair_invalid"] += 1
            continue
        scores = list(
            ComponentScore.objects.filter(enrollment__offering=source, component__kind="kollokvium").select_related(
                "enrollment", "component"
            )
        )
        if not scores:
            counts["pair_no_scores"] += 1
            continue
        components = ensure_kollokviums(target)
        component = components[0] if components else None
        if component is None:
            counts["target_no_component"] += 1
            continue
        targets = {
            e.student_id: e
            for e in Enrollment.objects.filter(offering=target, status=Enrollment.Status.ENROLLED).only(
                "id", "student_id"
            )
        }
        for score in scores:
            dst = targets.get(score.enrollment.student_id)
            if dst is None:
                counts["no_target_enrollment"] += 1
                continue
            if ComponentScore.objects.filter(component=component, enrollment=dst).exists():
                counts["target_filled"] += 1
                continue
            new = ComponentScore.objects.create(
                organization=organization,
                component=component,
                enrollment=dst,
                score=score.score,
                entered_by=score.entered_by,
                exam_source=score.exam_source,
            )
            created.append(str(new.pk))
        counts["pairs_done"] += 1
    counts["scores_copied"] += len(created)
    if created:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr="Təkrar jurnaldan Midterm balları əsl jurnala",
            new_values={"batch": batch, "scores": created},
        )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("AuditLog", "audit")
    rows = list(AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch))
    if not rows:
        counts["undo_batch_unknown"] += 1
        return
    for row in rows:
        removed, _ = _model("ComponentScore").objects.filter(pk__in=(row.new_values or {}).get("scores") or []).delete()
        counts["undo_scores_removed"] += removed
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=UNDO_REASON,
            resource_type=f"{RESOURCE}.undo",
            resource_id=batch,
            resource_repr="Köçürülmüş Midterm balları geri götürüldü",
            old_values={"batch": batch},
        )


__all__ = ["PAIRS", "new_batch", "run", "undo"]
