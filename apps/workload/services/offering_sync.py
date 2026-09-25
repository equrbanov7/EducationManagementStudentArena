"""Tapşırıq sətirləri → qrup açılışları (``registrar.CourseOffering``) — YEGANƏ yazı yolu (2026-09-25).

KİM ÇAĞIRIR
-----------
* ``workflow.recompute_task_status`` — plan kafedraya çatanda (təsdiq): bütün sənəd;
* ``assignments.assign_teacher`` / ``unassign`` — sətrin açılışlarının müəllimi DƏRHAL;
* ``tasks.save_row`` — çatmış sənəddə sətir dəyişəndə (yeni qrup → yeni açılış);
* ``distribution.sync_offerings`` (``confirm_distribution``) və ``sync_plan_offerings`` əmri.

Vaxt, saat, jurnal sahibi və müəllim provenansı qaydaları :mod:`.offering_rules`-dadır.
Burada əlavə olaraq:

* SEÇMƏ FƏNN: (qrup, fənn) cütü qrupun ixtisasının təsdiqlənmiş aktiv planında
  YALNIZ seçmə kimi keçirsə qrup açılışı YARADILMIR — seçim qrup səviyyəsindədir:
  ``registrar.services.choose_group_elective`` açılışı yaradır və qrupu ELECTIVE
  kimi yazır. Açılış artıq varsa (qərar verilib) sinxron yalnız müəllim/saatı
  yeniləyir, qeydiyyata toxunmur. Planda izi olmayan fənn məcburi sayılır.
* LƏĞV edilmiş (``is_active=False``) açılışa və KİLİDLİ semestrə toxunulmur;
  bağlı jurnalın saatı dəyişmir.
* QEYDİYYAT: yeni və ya hələ BOŞ açılışa qrupun aktiv tələbələri
  ``registrar.services.enroll_group_students`` ilə (tarixçə/alt qrup qaydaları orada).
* HEÇ NƏ SİLİNMİR: sətir silinsə/dəyişsə köhnə açılış qalır (jurnal tarixçəsi).

Sorğu sayı sətir sayından asılı DEYİL: toplu SELECT-lər + yalnız dəyişən açılışa YAZI.
"""

from __future__ import annotations

import logging

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.db.models import Prefetch

from core.audit import log_action
from core.constants import AuditAction

from ..models import TeacherAssignment, TeachingTaskRow
from .offering_rules import (
    OUTCOME_COUNTERS,
    UNKNOWN,
    decide_instructor,
    merge_hours,
    owner_for_rows,
    plan_reached_chair,
)
from .plan_calendar import PeriodResolver, ensure_row_periods

logger = logging.getLogger(__name__)

#: ``registrar.integrity.INSTRUCTOR_PERMISSION`` — açılış müəllimi bal yaza bilməlidir.
INSTRUCTOR_PERMISSION = "grade.input"

COUNTER_KEYS = (
    "rows",
    "rows_skipped",
    "period_set",
    "period_missing",
    "period_locked",
    "created",
    "updated",
    "skipped",
    "not_created",
    "inactive_skipped",
    "elective_pending",
    "hours_updated",
    "instructor_set",
    "instructor_replaced",
    "instructor_cleared",
    "instructor_blocked",
    "preserved_handover",
    "preserved_foreign",
    "enrolled",
    "enroll_existing",
    "enroll_conflict",
    "enroll_not_member",
    "guest_added",
    "guest_present",
    "guest_deferred",
    "guest_failed",
)

#: ``registrar.services.enroll_group_students`` hesabatı → bu modulun sayğacları.
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


def assignments_prefetch() -> Prefetch:
    """Təyinatlar BİR sorğu ilə, müəllim ``select_related``, sıra: fəaliyyət + yaradılma."""
    return Prefetch(
        "assignments",
        queryset=TeacherAssignment.objects.select_related("teacher").order_by("activity", "created_at"),
    )


def rows_queryset(task):
    return (
        TeachingTaskRow.objects.filter(task=task)
        .select_related("period")
        .prefetch_related("groups", assignments_prefetch())
        .order_by("season", "order", "created_at")
    )


def compact(report) -> dict:
    """Audit / JSON üçün yalnız tam ədəd sayğaclar (id siyahıları yox)."""
    return {key: value for key, value in (report or {}).items() if isinstance(value, int) and value}


def eligible_instructor_ids(organization_id, user_ids) -> set:
    """``registrar.integrity.eligible_instructor_user_ids``-in NAMİZƏDLƏ məhdud güzgüsü (bir sorğu).

    Tam siyahı təşkilatın BÜTÜN üzvlüklərini oxuyur (QKU-da ~8 400 sətir) — sətir
    başına təyinatda bu ağırdır; qayda (aktiv təşkilat/istifadəçi/üzvlük/eyni
    tenantın aktiv rolu + ``grade.input``) eynidir.
    """
    from core.permissions import has_permission

    ids = {user_id for user_id in user_ids if user_id}
    if not ids:
        return set()
    memberships = (
        django_apps.get_model("organizations", "Membership")
        .objects.filter(
            organization_id=organization_id,
            organization__is_active=True,
            user_id__in=ids,
            user__is_active=True,
            is_active=True,
            role__is_active=True,
            role__organization_id=organization_id,
        )
        .select_related("role")
    )
    return {m.user_id for m in memberships if has_permission(list(m.role.permissions or []), INSTRUCTOR_PERMISSION)}


def group_targets(rows, *, only_groups=None, only_period=None, counters=None) -> dict:
    """``{(fənn, semestr, qrup): {"group", "rows"}}`` — sinxrona düşən (sətir × qrup) cütləri."""
    targets: dict = {}
    for row in rows:
        groups = list(row.groups.all())
        if not (row.subject_id and row.period_id and groups):
            if counters is not None:
                counters["rows_skipped"] += 1
            continue
        if only_period is not None and row.period_id != only_period:
            continue
        if getattr(row.period, "locked_at", None) is not None:
            if counters is not None:
                counters["period_locked"] += 1
            continue
        for group in groups:
            if only_groups is not None and group.pk not in only_groups:
                continue
            entry = targets.setdefault((row.subject_id, row.period_id, group.pk), {"group": group, "rows": []})
            entry["rows"].append(row)
    return targets


def _anchor_scope(rows, anchor_id):
    anchor = next((row for row in rows if row.pk == anchor_id), None)
    if anchor is None or not anchor.period_id:
        return None, None
    return {group.pk for group in anchor.groups.all()}, anchor.period_id


def _sibling_rows(row) -> list:
    """Sətirlə eyni açılışları paylaşa bilən sənəd sətirləri (eyni fənn)."""
    if not row.subject_id:
        return list(rows_queryset(row.task).filter(pk=row.pk))
    return list(rows_queryset(row.task).filter(subject_id=row.subject_id))


def owner_snapshot(row) -> dict:
    """``assign``/``unassign``-dən ƏVVƏL: sətrin açılışlarının yük sahibi — ``{açar: user_id|None}``."""
    rows = _sibling_rows(row)
    ensure_row_periods(rows, task=row.task, apply=False)
    only_groups, only_period = _anchor_scope(rows, row.pk)
    if only_period is None:
        return {}
    targets = group_targets(rows, only_groups=only_groups, only_period=only_period)
    return {key: getattr(owner_for_rows(entry["rows"]), "pk", None) for key, entry in targets.items()}


class _Sync:
    """Bir keçid: sətirlər → hədəflər → açılış yaz/yenilə → qeydiyyat → hesabat."""

    def __init__(self, task, *, actor, request, create, previous):
        self.task = task
        self.org_id = task.organization_id
        self.actor_user = getattr(actor, "user", None)
        self.request = request
        self.create = create
        self.previous = previous
        self.counters = dict.fromkeys(COUNTER_KEYS, 0)
        self.offering_ids: list[str] = []
        self.missing_seasons: dict = {}
        self._closed = None

    def run(self, rows, *, anchor_id=None) -> dict:
        rows = list(rows)
        self.counters["rows"] = len(rows)
        periods = ensure_row_periods(rows, task=self.task, resolver=PeriodResolver(self.org_id))
        self.counters["period_set"] = periods["period_set"]
        self.counters["period_missing"] = periods["period_missing"]
        self.missing_seasons = periods["missing_seasons"]
        only_groups = only_period = None
        if anchor_id is not None:
            only_groups, only_period = _anchor_scope(rows, anchor_id)
            if only_period is None:
                self.counters["rows_skipped"] += 1
                return self.report()
        targets = group_targets(rows, only_groups=only_groups, only_period=only_period, counters=self.counters)
        if targets:
            self._apply(targets)
        return self.report()

    def report(self) -> dict:
        return {**self.counters, "offering_ids": self.offering_ids, "missing_seasons": self.missing_seasons}

    # ── toplu oxu ─────────────────────────────────────────────────────────
    def _existing(self, keys) -> dict:
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        found = CourseOffering.objects.filter(
            organization_id=self.org_id,
            subject_id__in={key[0] for key in keys},
            period_id__in={key[1] for key in keys},
            group_id__in={key[2] for key in keys},
        )
        return {(o.subject_id, o.period_id, o.group_id): o for o in found}

    def _foreign_rows(self, keys) -> dict:
        """Eyni açılışları əhatə edən BAŞQA sənədlərin sətirləri — yalnız saat üçün (bir sorğu)."""
        found: dict = {}
        rows = (
            TeachingTaskRow.objects.filter(
                organization_id=self.org_id,
                subject_id__in={key[0] for key in keys},
                period_id__in={key[1] for key in keys},
            )
            .exclude(task_id=self.task.pk)
            .exclude(task__status="cancelled")
            .prefetch_related("groups")
        )
        wanted = set(keys)
        for row in rows:
            for group in row.groups.all():
                key = (row.subject_id, row.period_id, group.pk)
                if key in wanted:
                    found.setdefault(key, []).append(row)
        return found

    def _elective_pairs(self, targets) -> set:
        """(ixtisas, fənn) — təsdiqlənmiş aktiv planda YALNIZ seçmə kimi keçən cütlər."""
        CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
        specialty_ids = {entry["group"].parent_id for entry in targets.values() if entry["group"].parent_id}
        if not specialty_ids:
            return set()
        mandatory, elective = set(), set()
        for specialty_id, subject_id, is_elective in CurriculumSubject.objects.filter(
            organization_id=self.org_id,
            curriculum__status="approved",
            curriculum__is_active=True,
            curriculum__program__specialty_unit_id__in=specialty_ids,
            subject_id__in={key[0] for key in targets},
        ).values_list("curriculum__program__specialty_unit_id", "subject_id", "is_elective"):
            (elective if is_elective else mandatory).add((specialty_id, subject_id))
        return elective - mandatory

    def _handover_pairs(self, offerings) -> set:
        if not offerings:
            return set()
        TeachingHandover = django_apps.get_model("registrar", "TeachingHandover")
        return set(
            TeachingHandover.objects.filter(
                offering_id__in=[o.pk for o in offerings], reverted_at__isnull=True, to_instructor_id__isnull=False
            ).values_list("offering_id", "to_instructor_id")
        )

    def _populated(self, offerings) -> set:
        if not offerings:
            return set()
        # «Boş» = AKTİV qeydiyyatı yoxdur; yalnız tarixçə (``dropped``) sətirləri olan
        # açılış da boş sayılır — həmin tələbələr ``enroll_group_students``-da ötürülür.
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        return set(
            Enrollment.objects.filter(offering_id__in=[o.pk for o in offerings], status=Enrollment.Status.ENROLLED)
            .values_list("offering_id", flat=True)
            .distinct()
        )

    def _is_closed(self, offering, existing) -> bool:
        if self._closed is None:
            from apps.registrar.public import handover

            self._closed = handover.closed_offering_ids([o.pk for o in existing.values()])
        return offering.pk in self._closed

    # ── yazı ──────────────────────────────────────────────────────────────
    def _apply(self, targets) -> None:
        existing = self._existing(list(targets))
        foreign_rows = self._foreign_rows(list(targets))
        electives = self._elective_pairs(targets)
        owners = {key: owner_for_rows(entry["rows"]) for key, entry in targets.items()}
        eligible = eligible_instructor_ids(self.org_id, {getattr(owner, "pk", None) for owner in owners.values()})
        differing = [
            existing[key]
            for key in targets
            if key in existing
            and existing[key].instructor_id
            and existing[key].instructor_id != getattr(owners[key], "pk", None)
        ]
        handover_pairs = self._handover_pairs(differing)
        populated = self._populated([offering for key, offering in existing.items() if key in targets])
        to_enroll = []
        for key, entry in targets.items():
            offering = existing.get(key)
            is_elective = (entry["group"].parent_id, key[0]) in electives
            lesson_hours = sum(merge_hours(entry["rows"] + foreign_rows.get(key, [])).values())
            desired_id = getattr(owners[key], "pk", None)
            decision = {"desired_id": desired_id, "eligible": desired_id in eligible}
            if offering is None:
                if is_elective:
                    self.counters["elective_pending"] += 1
                elif not self.create:
                    self.counters["not_created"] += 1
                else:
                    created = self._create(key, lesson_hours=lesson_hours, **decision)
                    to_enroll += [created] if created is not None else []
                continue
            if not offering.is_active:
                self.counters["inactive_skipped"] += 1
                continue
            self.offering_ids.append(str(offering.pk))
            previous_id = UNKNOWN if self.previous is UNKNOWN else self.previous.get(key)
            handover_owned = (offering.pk, offering.instructor_id) in handover_pairs
            self._update(
                offering,
                entry,
                existing=existing,
                lesson_hours=lesson_hours,
                previous_id=previous_id,
                handover_owned=handover_owned,
                **decision,
            )
            if not is_elective and offering.pk not in populated:
                to_enroll.append(offering)
        if to_enroll:
            self._enroll(to_enroll)

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
        old_id = offering.instructor_id
        outcome, new_id = decide_instructor(
            old_id, desired_id=desired_id, eligible=eligible, previous_id=previous_id, handover_owned=handover_owned
        )
        fields = ["instructor"] if new_id != old_id else []
        if lesson_hours and offering.lesson_hours != lesson_hours and not self._is_closed(offering, existing):
            offering.lesson_hours = lesson_hours
            fields.append("lesson_hours")
        if not fields:
            self.counters["skipped"] += 1
            self._count(outcome)
            return
        offering.instructor_id = new_id
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
        if not fields:
            return
        self.counters["updated"] += 1
        self.counters["hours_updated"] += int("lesson_hours" in fields)
        if "instructor" in fields:
            self._audit_instructor(offering, old_id, new_id, outcome, entry["rows"])

    def _audit_instructor(self, offering, old_id, new_id, outcome, rows) -> None:
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
            },
            reason="workload.offering_instructor_synced",
            request=self.request,
            resource_type="registrar.CourseOffering",
            resource_id=str(offering.pk),
            resource_repr=f"{offering.subject_id} · {offering.group_id}",
        )

    def _enroll(self, offerings) -> None:
        from apps.registrar.public import services as registrar_services

        report = registrar_services.enroll_group_students(
            offerings=offerings,
            by_user=self.actor_user,
            reason=f"Tədris tapşırığı {self.task.academic_year}: plan qruplara düşdü — birləşik qrupun açılışı",
        )
        for key, value in report.items():
            self.counters[_ENROLL_KEYS[key]] += int(value)


def sync_task_offerings(task, *, actor=None, request=None, create=True, previous=UNKNOWN, rows=None) -> dict:
    """Sənədin bütün sətirləri → qrup açılışları (idempotent). Hesabat: :data:`COUNTER_KEYS` + id-lər."""
    rows = rows_queryset(task) if rows is None else rows
    return _Sync(task, actor=actor, request=request, create=create, previous=previous).run(rows)


def sync_row_offerings(row, *, actor=None, request=None, previous=UNKNOWN, create=None) -> dict:
    """Bir sətrin qrup açılışları DƏRHAL (təyinat/sətir dəyişikliyi). ``create`` — plan çatıbsa."""
    task = row.task
    create = plan_reached_chair(task) if create is None else create
    sync = _Sync(task, actor=actor, request=request, create=create, previous=previous)
    return sync.run(_sibling_rows(row), anchor_id=row.pk)


def run_safely(func, *args, **kwargs) -> dict:
    """Hook-lar üçün: sinxron xətası əsas əməli (təsdiq, təyinat, sətir) GERİ QAYTARMIR.

    Savepoint içində icra olunur (DB xətası xarici tranzaksiyanı zəhərləmir);
    xəta loglanır və hesabatda ``error=1`` görünür — ``sync_plan_offerings``
    əmri sonra eyni işi təkrarlaya bilər.
    """
    try:
        with transaction.atomic():
            return func(*args, **kwargs)
    except Exception:  # noqa: BLE001 — əsas əməl dayanmamalıdır
        logger.exception("workload: offering sync failed")
        return {"error": 1}


__all__ = [
    "COUNTER_KEYS",
    "UNKNOWN",
    "assignments_prefetch",
    "compact",
    "eligible_instructor_ids",
    "group_targets",
    "owner_snapshot",
    "plan_reached_chair",
    "rows_queryset",
    "run_safely",
    "sync_row_offerings",
    "sync_task_offerings",
]
