"""Vakant saatı jurnal sübutu ilə müəllimə yazmaq + paketi geri qaytarmaq (sahib 2026-10-25).

Qərarlar :mod:`.vacant_fill`-dədir; burada yalnız ``fill`` qərarlı cütlər yazılır — RƏSMİ yolla:

* sətir üçün ``amendments.open_amendment`` (səbəb «Texniki səhvin düzəlişi», qeyd
  «Jurnal datası: dərsi keçən müəllim — sahibin 2026-10-25 qərarı [paket]», ``new_values``-da hər vakant
  bölgünün id-si, saatı, yeni müəllim və sübut) → tapşırıq ``amended``;
* :class:`~.task_load_reassign.RowPlanApplier` — blokerlər (jurnal sahibi «Fənn təhvili» ilə başqasıdırsa,
  jurnal bağlıdır, dövr bitib, müəllim bal yaza bilmir …), ``assignments.assign_teacher`` vakant bölgünün
  ÖZÜNÜ yeniləyir (id dəyişmir), açılışın müəllim sinxronu; sətir öz savepoint-indədir;
* müəllim kafedranın üzvü deyilsə — əvvəl ``people.join_chair_as_teacher`` (ƏLAVƏ üzvlük, audit) və bölgü
  saathesabı (``is_hourly_paid``); yaradılan üzvlük id-si qeydə düşür (geri qaytarmada deaktiv olur);
* tapşırığın sonunda ``confirm_distribution`` — bildiriş («Dərs yükü təyin edildi») yalnız yükü DƏYİŞƏN
  müəllimə, bir dəfə (``loads_before``); ``notify=False`` — heç kimə.

GERİ QAYTARMA (:func:`undo_batch`): paketin qeydlərindəki hər bölgü yenə rəsmi yolla «Vakant»a qaytarılır
(yalnız hələ də həmin müəllimdədirsə), paketin yaratdığı üzvlük — müəllimin həmin kafedrada başqa bölgüsü
qalmayıbsa — deaktiv olur; hər addım ``[undo:paket]`` qeydi ilə. İdempotentdir.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, AmendmentTarget, TaskStatus
from ..models import TeacherAssignment, TeachingTask, WorkloadAmendment
from .amendments import open_amendment
from .assignments import assign_teacher
from .distribution import confirm_distribution, distribution_readiness, teacher_loads
from .people import join_chair_as_teacher
from .scoping import WorkloadDenied
from .task_load_reassign import ASSIGNED, REASSIGNED, RowPlanApplier
from .vacant_fill import FILL

NOTE = "Jurnal datası: dərsi keçən müəllim — sahibin 2026-10-25 qərarı"
ACTION_FILL = "vacant_fill"
ACTION_UNDO = "vacant_fill_undo"
AMENDABLE = (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED)
_JOIN_REASON = "workload.vacant_fill: jurnalda dərsi keçən müəllim bu kafedranın vakant saatını alır (sahib 2026-10-25)"


class _FillApplier(RowPlanApplier):
    """Düzəlişi HƏMİŞƏ öz qeydimizlə açır (paket id-si + bölgü snapshot-u — geri qaytarma üçün)."""

    def __init__(self, *, batch: str, **kwargs):
        super().__init__(**kwargs)
        self.batch = batch
        self.payload: dict = {}

    def _write(self, row, changed: dict) -> None:
        open_amendment(
            task=row.task,
            actor=self.actor,
            target_kind=AmendmentTarget.ROW,
            target_id=row.pk,
            reason=AmendmentReason.CORRECTION,
            note=self.note,
            new_values=self.payload.get(row.pk) or {},
        )
        self.counters["amendment_opened"] += 1
        super()._write(row, changed)


class VacantFiller:
    def __init__(self, *, organization, actor, batch: str, notify: bool):
        self.organization = organization
        self.actor = actor
        self.batch = batch
        self.notify = notify
        self.counts: Counter = Counter()
        self.applier = _FillApplier(
            batch=batch,
            organization=organization,
            actor=actor,
            apply=True,
            reassign=True,
            note=f"{NOTE} [{batch}]",
        )

    def run(self, items) -> None:
        by_task: dict = {}
        for item in items:
            if item.decision == FILL:
                by_task.setdefault(item.row.task_id, []).append(item)
        for task_id, task_items in by_task.items():
            task = TeachingTask.objects.select_for_update().get(pk=task_id)
            if task.status not in AMENDABLE:
                for item in task_items:
                    item.result = f"blocked:task_{task.status}"
                    self.counts["pairs_blocked"] += 1
                continue
            was_distributed = task.status == TaskStatus.DISTRIBUTED
            loads_before = teacher_loads(task)
            rows: dict = {}
            for item in task_items:
                rows.setdefault(item.row.pk, []).append(item)
            for row_items in rows.values():
                self._fill_row(row_items)
            self._reconfirm(task, was_distributed, loads_before)

    def _fill_row(self, items) -> None:
        row = items[0].row
        row.task.refresh_from_db(fields=["status", "distributed_at"])
        joined = []
        desired = {}
        before = {}
        for item in items:
            current = list(TeacherAssignment.objects.filter(row=row, activity=item.activity).order_by("created_at"))
            if not current or any(a.teacher_id for a in current) or sum(a.hours for a in current) != item.hours:
                item.result = "skipped:changed"
                self.counts["pairs_changed_meanwhile"] += 1
                continue
            # Vakant bölgü(lər)in HƏR BİRİ eyni saatla müəllimə keçir (id-lər qalır — geri qaytarma üçün).
            desired[item.activity] = [(item.teacher_id, a.hours, bool(item.outside)) for a in current]
            before[item.activity] = [_assignment_state(a) for a in current]
        if not desired:
            return
        try:
            with transaction.atomic():
                for item in items:
                    if item.activity in desired and item.outside:
                        joined += self._join(row.task.chair, item.teacher_id)
                self.applier.payload[row.pk] = {
                    "action": ACTION_FILL,
                    "batch": self.batch,
                    "fills": [_fill_record(item, before[item.activity]) for item in items if item.activity in desired],
                    "joined_memberships": joined,
                    # Açılışın müəllimi (köhnə jurnaldan gəlmiş ola bilər) — geri qaytarmada bərpa üçün.
                    "offerings": {str(o.pk): o.instructor_id for o in self.applier._offerings(row)},
                }
                action, detail = self.applier.apply_plan(row, desired)
                if action not in (ASSIGNED, REASSIGNED):
                    raise _RowBlocked(detail or action)
        except _RowBlocked as exc:
            for item in items:
                if item.activity in desired:
                    item.result = f"blocked:{exc.code}"
                    self.counts["pairs_blocked"] += 1
            return
        for item in items:
            if item.activity in desired:
                item.result = "assigned"
                self.counts["pairs_filled"] += 1
                self.counts["hours_filled"] += item.hours
                self.counts["pairs_filled_outside_chair"] += int(item.outside)
        self.counts["memberships_added"] += len(joined)

    def _join(self, chair, teacher_id) -> list:
        user = get_user_model().objects.get(pk=teacher_id)
        if not join_chair_as_teacher(
            organization=self.organization,
            user=user,
            chair=chair,
            actor_user=getattr(self.actor, "user", None),
            reason=_JOIN_REASON,
        ):
            return []
        Membership = django_apps.get_model("organizations", "Membership")
        membership = Membership.objects.filter(
            organization=self.organization, user=user, role__name="teacher", scope_unit=chair, is_active=True
        ).first()
        return [str(membership.pk)] if membership else []

    def _reconfirm(self, task, was_distributed: bool, loads_before: dict) -> None:
        task.refresh_from_db()
        if task.status != TaskStatus.AMENDED or not was_distributed:
            return
        if not distribution_readiness(task)["is_ready"]:
            self.counts["tasks_left_amended"] += 1
            return
        confirm_distribution(
            task=task, actor=self.actor, allow_vacant=True, notify=self.notify, loads_before=loads_before
        )
        self.counts["tasks_reconfirmed"] += 1


class _RowBlocked(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _assignment_state(assignment) -> dict:
    return {
        "id": str(assignment.pk),
        "hours": int(assignment.hours),
        "hourly": bool(assignment.is_hourly_paid),
        "note": assignment.note or "",
    }


def _fill_record(item, before: list) -> dict:
    return {
        "activity": item.activity,
        "assignments": before,
        "hours": item.hours,
        "teacher_id": item.teacher_id,
        "hourly": bool(item.outside),
        "evidence": {
            "source": item.source,
            "pooled": item.pooled,
            "weight": item.evidence.get(item.teacher_id, 0),
            "weight_total": item.weight,
            "share": round(item.share, 3),
        },
    }


# ── geri qaytarma ──────────────────────────────────────────────────────────
def undo_batch(*, organization, batch: str, actor, notify: bool = True) -> Counter:
    counts: Counter = Counter()
    amendments = list(
        WorkloadAmendment.objects.filter(
            organization=organization,
            note__contains=f"[{batch}]",
            target_kind=AmendmentTarget.ROW,
            new_values__action=ACTION_FILL,
        ).order_by("-created_at")
    )
    done = set(
        WorkloadAmendment.objects.filter(
            organization=organization, note__contains=f"[undo:{batch}]", new_values__action=ACTION_UNDO
        ).values_list("new_values__undone", flat=True)
    )
    loads_before, was_distributed = {}, set()
    for amendment in amendments:
        if str(amendment.pk) in done:
            counts["already_undone"] += 1
            continue
        task = TeachingTask.objects.select_for_update().get(pk=amendment.task_id)
        if task.pk not in loads_before:
            loads_before[task.pk] = teacher_loads(task)
            if task.status == TaskStatus.DISTRIBUTED:
                was_distributed.add(task.pk)
        values = amendment.new_values or {}
        pending = [fill for fill in values.get("fills") or [] if _still_filled(fill)]
        if not pending:
            counts["rows_not_restorable"] += 1
            continue
        try:
            with transaction.atomic():
                open_amendment(
                    task=task,
                    actor=actor,
                    target_kind=AmendmentTarget.ROW,
                    target_id=amendment.target_id,
                    reason=AmendmentReason.CORRECTION,
                    note=f"{NOTE} [undo:{batch}]: vakanta qaytarıldı",
                    new_values={"action": ACTION_UNDO, "batch": batch, "undone": str(amendment.pk)},
                )
                for fill in pending:
                    for state in fill["assignments"]:
                        assignment = TeacherAssignment.objects.select_related("row__task").get(pk=state["id"])
                        assign_teacher(
                            row=assignment.row, actor=actor, activity=assignment.activity, teacher_id=None,
                            hours=state["hours"], is_hourly_paid=state["hourly"], note=state["note"],
                            assignment=assignment,
                        )  # fmt: skip
                    counts["pairs_restored"] += 1
                    counts["hours_restored"] += int(fill.get("hours") or 0)
        except WorkloadDenied as exc:
            counts[f"blocked_{getattr(exc, 'code', '') or 'workload_denied'}"] += 1
            continue
        counts["offerings_restored"] += _restore_offerings(
            organization, values.get("offerings") or {}, {fill.get("teacher_id") for fill in pending}, actor
        )
        counts["memberships_deactivated"] += _deactivate(organization, task, values.get("joined_memberships"), actor)
    for task in TeachingTask.objects.filter(pk__in=list(loads_before)):
        if (
            task.status == TaskStatus.AMENDED
            and task.pk in was_distributed
            and distribution_readiness(task)["is_ready"]
        ):
            confirm_distribution(
                task=task, actor=actor, allow_vacant=True, notify=notify, loads_before=loads_before[task.pk]
            )
            counts["tasks_reconfirmed"] += 1
    return counts


def _still_filled(fill: dict) -> bool:
    ids = [state["id"] for state in fill.get("assignments") or []]
    found = TeacherAssignment.objects.filter(pk__in=ids, teacher_id=fill.get("teacher_id"))
    return bool(ids) and found.count() == len(ids)


def _restore_offerings(organization, snapshot: dict, filled: set, actor) -> int:
    """Bölgü vakanta qayıdanda sinxron açılışın müəllimini SİLİR (yük sahibi yoxdur) — halbuki o, doldurmadan
    ƏVVƏL (köhnə jurnaldan) var idi. Snapshot-dakı müəllim yalnız açılış hələ də boşdursa və ya paketin yazdığı
    müəllimdədirsə qaytarılır (sonradan «Fənn təhvili» / əl ilə qoyulan müəllimə toxunulmur)."""
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    restored = 0
    for offering in CourseOffering.objects.filter(organization=organization, pk__in=list(snapshot)):
        wanted = snapshot.get(str(offering.pk))
        current = offering.instructor_id
        if current == wanted or (current is not None and current not in filled):
            continue
        offering.instructor_id = wanted
        try:
            with transaction.atomic():
                offering.save(update_fields=["instructor", "updated_at"])
        except IntegrityError:  # registrar qoruyucusu (müəllim artıq bal yaza bilmir) — toxunulmur
            continue
        log_action(
            AuditAction.UPDATE,
            user=getattr(actor, "user", None),
            organization=organization,
            obj=offering,
            old_values={"instructor": str(current or "")},
            new_values={"instructor": str(wanted or "")},
            reason="workload.vacant_fill_undo: açılışın doldurmadan əvvəlki müəllimi bərpa olundu",
            resource_type="registrar.CourseOffering",
            resource_id=str(offering.pk),
        )
        restored += 1
    return restored


def _deactivate(organization, task, membership_ids, actor) -> int:
    """Paketin yaratdığı üzvlük — müəllimin bu kafedrada başqa bölgüsü qalmayıbsa deaktiv olur."""
    Membership = django_apps.get_model("organizations", "Membership")
    changed = 0
    for membership in Membership.objects.filter(pk__in=membership_ids or [], organization=organization, is_active=True):
        busy = TeacherAssignment.objects.filter(
            row__task__chair_id=membership.scope_unit_id, teacher_id=membership.user_id
        ).exists()
        if busy:
            continue
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        log_action(
            AuditAction.UPDATE,
            user=getattr(actor, "user", None),
            organization=organization,
            obj=membership,
            reason="workload.vacant_fill: geri qaytarma — paketin verdiyi əlavə kafedra üzvlüyü deaktiv",
            new_values={"is_active": False, "task": str(task.pk)},
        )
        changed += 1
    return changed


__all__ = ["ACTION_FILL", "ACTION_UNDO", "NOTE", "VacantFiller", "undo_batch"]
