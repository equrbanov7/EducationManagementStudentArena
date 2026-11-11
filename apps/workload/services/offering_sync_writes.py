"""Açılış sinxronunun YAZI addımları (``offering_sync._Sync``-in mixin-i; modul ölçüsü üçün ayrılıb, 2026-11-11).

Müəllim dəyişikliyi: əvvəlki yük sahibi bilinir və kafedra AÇIQ dəyişiklik edibsə (``decide_instructor`` →
``replaced``), sahiblik «Fənn təhvili» ilə EYNİ registrar servisindən keçir (:mod:`.offering_transfer` →
``journal_transfer.transfer``) — təhvil qeydi, slotlar, iki tərəfin payları; yük sinxronu sonra növ paylarını
yenidən qurur (köhnə müəllimin başqa növü varsa jurnal ondan getmir).
"""

from __future__ import annotations

import logging

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction

from core.audit import log_action
from core.constants import AuditAction

from .offering_rules import OUTCOME_COUNTERS, decide_instructor

logger = logging.getLogger("apps.workload.services.offering_sync")

_ENROLL_KEYS = {
    "created": "enrolled",
    "existing": "enroll_existing",
    "conflict": "enroll_conflict",
    "not_member": "enroll_not_member",
    "guest_added": "guest_added",
    "guest_present": "guest_present",
    "guest_deferred": "guest_deferred",
    "guest_failed": "guest_failed",
}


class SyncWrites:
    """``_Sync``-in yazı metodları — ``self.counters``/``self.task``/``self.actor_user`` ``_Sync``-dədir."""

    def _own(self, offering, kind) -> None:
        if offering is not None:
            self.group_offering_ids[kind].append(str(offering.pk))

    def _count(self, outcome) -> None:
        for counter in OUTCOME_COUNTERS[outcome]:
            self.counters[counter] += 1

    def _create(self, key, *, desired_id, eligible, lesson_hours):
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        outcome, instructor_id = decide_instructor(None, desired_id=desired_id, eligible=eligible)
        lookup = {"organization_id": self.org_id, "subject_id": key[0], "period_id": key[1], "group_id": key[2]}
        for candidate in (instructor_id, None) if instructor_id else (None,):
            try:
                with transaction.atomic():
                    offering = CourseOffering.objects.create(
                        **lookup, instructor_id=candidate, lesson_hours=lesson_hours, is_active=True
                    )
                break
            except IntegrityError:
                if candidate is None:
                    # Paralel yaradılma (unikal açar) — növbəti keçid mövcud sətri yeniləyəcək.
                    logger.warning("workload: offering create race %s", lookup)
                    self.counters["skipped"] += 1
                    return None
                logger.warning("workload: instructor %s rejected by registrar guard (%s)", candidate, lookup)
                outcome = "blocked"
        self.counters["created"] += 1
        self._count(outcome)
        self.offering_ids.append(str(offering.pk))
        return offering

    def _update(self, offering, entry, *, existing, lesson_hours, desired_id, eligible, previous_id, handover_owned):
        from .offering_transfer import Snapshot, hand_over_owner

        old_id = offering.instructor_id
        chair_edit = isinstance(self.previous, Snapshot)
        outcome, new_id = decide_instructor(
            old_id,
            desired_id=desired_id,
            eligible=eligible,
            previous_id=previous_id,
            handover_owned=handover_owned,
            chair_edit=chair_edit,
        )
        moved = False
        if chair_edit and outcome == "replaced" and old_id is not None and new_id is not None:
            # Kafedranın açıq dəyişikliyi = «Fənn təhvili» (ortaq servis; sahiblik + qeyd + slot + paylar).
            moved = hand_over_owner(self, offering, new_id)
            if not moved:
                outcome, new_id = "blocked", old_id
        fields = ["instructor"] if new_id != offering.instructor_id else []
        if lesson_hours and offering.lesson_hours != lesson_hours and not self._is_closed(offering, existing):
            offering.lesson_hours = lesson_hours
            fields.append("lesson_hours")
        if not fields and not moved:
            self.counters["skipped"] += 1
            self._count(outcome)
            return
        offering.instructor_id = new_id
        if fields:
            try:
                with transaction.atomic():
                    offering.save(update_fields=fields + ["updated_at"])
            except IntegrityError:
                offering.instructor_id = old_id
                fields = [field for field in fields if field != "instructor"]
                outcome = "blocked"
                if fields:
                    with transaction.atomic():
                        offering.save(update_fields=fields + ["updated_at"])
        self._count(outcome)
        if not fields and not moved:
            return
        self.counters["updated"] += 1
        self.counters["hours_updated"] += int("lesson_hours" in fields)
        if "instructor" in fields or moved:
            conflicts = self._timetable_conflicts(offering, new_id)
            self._audit_instructor(offering, old_id, new_id, outcome, entry["rows"], conflicts=conflicts)

    def _timetable_conflicts(self, offering, new_id) -> list:
        """Audit 2026-09-28 W4: yeni müəllim açılışın slotlarında başqa dərslə toqquşurmu."""
        from .offering_timetable import instructor_change_conflicts

        conflicts = instructor_change_conflicts(offering, new_id)
        self.counters["schedule_conflicts"] += len(conflicts)
        self.schedule_conflicts.extend(conflicts)
        return conflicts

    def _audit_instructor(self, offering, old_id, new_id, outcome, rows, *, conflicts=()) -> None:
        log_action(
            AuditAction.UPDATE,
            user=self.actor_user,
            organization=self.task.organization,
            obj=offering,
            old_values={"instructor": str(old_id or "")},
            new_values={
                "instructor": str(new_id or ""),
                "outcome": outcome,
                "task": str(self.task.pk),
                "rows": [str(row.pk) for row in rows],
                "schedule_conflicts": [item.get("message", "") for item in conflicts],
            },
            reason="workload.offering_instructor_synced",
            request=self.request,
            resource_type="registrar.CourseOffering",
            resource_id=str(offering.pk),
            resource_repr=f"{offering.subject_id} · {offering.group_id}",
        )

    def _enroll(self, offerings, *, kind="mandatory") -> None:
        from apps.registrar.public import services as registrar_services

        report = registrar_services.enroll_group_students(
            offerings=offerings,
            kind=kind,
            by_user=self.actor_user,
            reason=f"Tədris tapşırığı {self.task.academic_year}: plan qruplara düşdü — birləşik qrupun açılışı",
        )
        for key, value in report.items():
            self.counters[_ENROLL_KEYS[key]] += int(value)


__all__ = ["SyncWrites"]
