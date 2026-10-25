"""Jurnal dərslərindən cədvəl — plan, toqquşma, yazı və hesabat (``infer_timetable_from_lessons``).

Analiz (faktlar → vahidlər): :mod:`apps.registrar.timetable_inference`. Burada vahidlər canlı cədvəllə
tutuşdurulur:

* İDEMPOTENTLİK: eyni açılış (= qrup + fənn) + gün + başlama saatı + növ + EFFEKTİV müəllim olan canlı
  (silinməmiş, parklanmış da daxil) slot, həftə növləri kəsişirsə — ``exists`` (yenisi yaradılmır, mövcud
  slota TOXUNULMUR: həftə növü / otaq / bitmə fərqli olsa da üstündən yazılmır, səbəbdə qeyd olunur).
  Təkrar işə salma 0 yaradır. Heç bir slot silinmir və dəyişdirilmir.
* TOQQUŞMA: redaktorun avtoritet mühərriki ``schedule_conflicts.detect`` (semestr süzgəci, üst↔alt
  kəsişməmə, axın qaydası, paralel alt qrup) — həm canlı slotlarla, həm də bu planın əvvəl qəbul
  olunmuş vahidləri ilə. Qrup / müəllim toqquşması → vahid ``conflict`` (yazılmır). Yalnız OTAQ
  toqquşmasında vahid otaqsız yazılır (``room_dropped``).
* AXIN atomikdir: qruplarından biri toqquşursa bütün axın yazılmır (yarımçıq axın yaranmasın). Axının
  artıq cədvəldə olan qrupu varsa, onun otağı götürülür (birgə mühazirə eyni otaqdadır).
* MÜƏLLİM: slot müəllimi jurnal sahibi ilə eynidirsə NULL (``schedule.stored_instructor_id``); fərqlidirsə
  həmin müəllimin təşkilatda AKTİV ``grade.input`` üzvlüyü olmalıdır (DB qoruyucusu ilə eyni şərt) —
  yoxdursa ``teacher_not_authorized``.
* OTAQ DOLDURMA (2026-10-25, defolt): bu əmrin əvvəl yaratdığı (audit ``created_ids``) və otağı BOŞ olan slot
  mövcud vahidə uyğun gəlirsə ona vahidin otağı yazılır (``room_filled``); otaq eyni vaxt başqa slotda tutulubsa
  yazılmır (``room_fill_clash``). Rəsmi docx / əl ilə qoyulmuş slotlara toxunulmur. İdempotent.
* YAZI: ``apply=True`` — bir tranzaksiya, semestr cədvəl kilidi (``schedule_lock.lock_schedule``) altında,
  plan kilid ALTINDA yenidən qurulur; slot ``save()`` ilə (referans-kimlik yoxlaması); bir audit sətri
  (saylar + slot id-ləri) — ``schedule_docx_import`` ilə eyni üsul. Bildiriş göndərilmir.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.db import transaction

from apps.registrar import schedule, schedule_conflicts, schedule_lock, schedule_slot_teachers
from apps.registrar.models import CourseOffering, ScheduleSlot
from apps.registrar.timetable_inference import (
    AMBIGUOUS,
    BELOW_THRESHOLD,
    READY,
    ROOM_FROM_LESSONS,
    ROOM_FROM_TEACHER,
    ROOM_FROM_TEACHER_SLOT,
    SUPERSEDED,
    Rules,
    build_units,
    load_facts,
)

#: Axının artıq cədvəldə olan qrupunun otağı (birgə dərs eyni otaqdadır).
ROOM_FROM_EXISTING = "existing"

CREATE = "create"
EXISTS = "exists"
CONFLICT = "conflict"
SKIPPED = "skipped"
ACTIONS = (CREATE, EXISTS, CONFLICT, SUPERSEDED, BELOW_THRESHOLD, AMBIGUOUS, SKIPPED)

REPORT_HEADER = (
    "teacher",
    "subject_code",
    "subject",
    "group",
    "weekday",
    "time",
    "kind",
    "week_type",
    "room",
    "unit_dates",
    "group_dates",
    "odd_dates",
    "even_dates",
    "stream_size",
    "first_date",
    "last_date",
    "action",
    "reason",
    "room_source",
)


@dataclass
class MemberRow:
    """Vahidin bir qrupu (açılışı) üçün qərar — cədvəldə bir slot sətri."""

    unit: object
    offering: object
    action: str
    reason: str = ""
    slot: object = None
    fill_room: str = ""
    room_source: str = ""

    def csv_row(self, usernames: dict) -> list:
        unit, offering = self.unit, self.offering
        dates = sorted(unit.members.get(offering.pk, ()))
        slot = self.slot
        return [
            usernames.get(unit.teacher_id, ""),
            offering.subject.code,
            offering.subject.name,
            offering.group.name if offering.group_id else "",
            unit.weekday,
            "%s-%s" % (unit.start.strftime("%H:%M"), unit.end.strftime("%H:%M") if unit.end else ""),
            unit.kind,
            unit.week_type,
            slot.room if slot is not None else unit.room,
            len(unit.dates),
            len(dates),
            unit.odd,
            unit.even,
            len(unit.members),
            dates[0].isoformat() if dates else "",
            dates[-1].isoformat() if dates else "",
            self.action,
            self.reason,
            self.room_source if (slot.room if slot is not None else unit.room) else "",
        ]


@dataclass
class Plan:
    facts: Counter = field(default_factory=Counter)
    units: list = field(default_factory=list)
    rows: list[MemberRow] = field(default_factory=list)
    created_ids: list = field(default_factory=list)
    filled_ids: list = field(default_factory=list)

    @property
    def counts(self) -> Counter:
        counter = Counter({action: 0 for action in ACTIONS})
        counter.update(row.action for row in self.rows)
        return counter

    def reason_counts(self) -> Counter:
        return Counter(row.reason.split(":")[0] for row in self.rows if row.reason)

    def unit_counts(self) -> Counter:
        streams = [unit for unit in self.units if unit.is_stream]
        return Counter(
            units=len(self.units),
            singles=len(self.units) - len(streams),
            streams=len(streams),
            stream_groups=sum(len(unit.members) for unit in streams),
        )

    def created_counts(self) -> Counter:
        created_rows = [row for row in self.rows if row.action == CREATE]
        created = [row.slot for row in created_rows]
        counter = Counter({f"week_{value}": 0 for value in ("all", "odd", "even")})
        counter.update(f"week_{slot.week_type}" for slot in created)
        counter["room_set"] = sum(1 for slot in created if slot.room)
        for source in (ROOM_FROM_EXISTING, ROOM_FROM_LESSONS, ROOM_FROM_TEACHER_SLOT, ROOM_FROM_TEACHER):
            counter[f"room_from_{source}"] = sum(
                1 for row in created_rows if row.slot.room and row.room_source == source
            )
        counter["room_filled"] = sum(1 for row in self.rows if row.fill_room)
        counter["room_empty"] = sum(1 for slot in created if not slot.room)
        counter["lecture"] = sum(1 for slot in created if slot.kind == "lecture")
        counter["seminar"] = sum(1 for slot in created if slot.kind == "seminar")
        counter["lab"] = sum(1 for slot in created if slot.kind == "lab")
        return counter


def _identity(offering_id, weekday, start, teacher_id) -> tuple:
    """Mövcud slotun tanınması: açılış + gün + başlama + effektiv müəllim. NÖV daxil DEYİL (2026-10-25): rəsmi
    cədvəldə «mühazirə», jurnalda «seminar» yazılan eyni saat yeni slot / toqquşma deyil — ``exists_other_kind``."""
    return (str(offering_id), weekday, start, str(teacher_id or ""))


class _Planner:
    """Canlı cədvəl (bir dəfə yüklənir) + bu planın qəbul etdiyi slotlar üzərində qərar."""

    def __init__(self, *, organization, period, units, actor=None, fill_rooms=False, source=""):
        self.organization, self.period, self.actor = organization, period, actor
        self.inferred_ids = inferred_slot_ids(organization, source) if fill_rooms else set()
        ids = {pk for unit in units for pk in unit.members}
        self.offerings = {
            offering.pk: offering
            for offering in CourseOffering.objects.filter(organization=organization, pk__in=ids).select_related(
                "organization", "period", "subject", "group", "instructor"
            )
        }
        live = ScheduleSlot.objects.filter(organization=organization, offering__period=period).select_related(
            "offering", "offering__subject", "offering__group", "offering__instructor", "instructor"
        )
        self.identity: dict = defaultdict(list)
        self.by_day: dict = defaultdict(list)
        for slot in live:
            key = _identity(slot.offering_id, slot.weekday, slot.start_time, schedule.effective_instructor_id(slot))
            self.identity[key].append(slot)
            if not slot.is_parked:
                self.by_day[slot.weekday].append(slot)
        foreign = {
            unit.teacher_id
            for unit in units
            for pk in unit.members
            if pk in self.offerings and schedule.stored_instructor_id(self.offerings[pk], unit.teacher_id)
        }
        self.authorized = schedule_slot_teachers.authorized_teacher_ids(organization.pk, foreign)

    def _detect(self, unit, offering, room, extra) -> list:
        return schedule_conflicts.detect(
            organization=self.organization,
            weekday=unit.weekday,
            start_time=unit.start,
            end_time=unit.end,
            week_type=unit.week_type,
            room=room,
            group_id=offering.group_id,
            instructor_id=unit.teacher_id,
            candidates=self.by_day[unit.weekday] + extra,
            period_id=self.period.pk,
            subject_id=offering.subject_id,
            kind=unit.kind,
            offering_id=offering.pk,
        )

    def _new_slot(self, unit, offering, stored, room):
        return ScheduleSlot(
            organization=self.organization,
            offering=offering,
            weekday=unit.weekday,
            start_time=unit.start,
            end_time=unit.end,
            room=room,
            week_type=unit.week_type,
            kind=unit.kind,
            created_by=self.actor if getattr(self.actor, "pk", None) else None,
            instructor_id=stored,
        )

    def _check(self, unit, pending, room) -> tuple[set, list]:
        """Axının bütün qruplarını ardıcıl yoxla → (toqquşma növləri, yaradılacaq slotlar)."""
        extra = []
        for offering, stored, _row in pending:
            conflicts = self._detect(unit, offering, room, extra)
            if conflicts:
                return {conflict["kind"] for conflict in conflicts}, []
            extra.append(self._new_slot(unit, offering, stored, room))
        return set(), extra

    def plan_unit(self, unit) -> list[MemberRow]:
        members = [(pk, self.offerings.get(pk)) for pk in unit.offering_ids]
        rows = []
        if unit.status != READY:
            return [MemberRow(unit, offering, unit.status, unit.reason) for _pk, offering in members if offering]
        pending, existing_rooms, fills = [], [], []
        for pk, offering in members:
            if offering is None:
                continue
            if pk in unit.dropped:
                rows.append(MemberRow(unit, offering, BELOW_THRESHOLD, unit.dropped[pk]))
                continue
            stored = schedule.stored_instructor_id(offering, unit.teacher_id)
            if stored and stored not in self.authorized:
                rows.append(MemberRow(unit, offering, SKIPPED, "teacher_not_authorized"))
                continue
            key = _identity(pk, unit.weekday, unit.start, unit.teacher_id)
            hits = [
                slot
                for slot in self.identity.get(key, [])
                if schedule_conflicts.week_types_overlap(slot.week_type, unit.week_type)
            ]
            if hits:
                existing_rooms.append(hits[0].room or "")
                row = MemberRow(unit, offering, EXISTS, _exists_reason(hits[0], unit), slot=hits[0])
                rows.append(row)
                if not hits[0].room and str(hits[0].pk) in self.inferred_ids:
                    fills.append(row)
                continue
            row = MemberRow(unit, offering, CREATE)
            pending.append((offering, stored, row))
            rows.append(row)
        existing_room = next((value for value in existing_rooms if value), "")
        room = existing_room or unit.room
        for row in rows:
            row.room_source = ROOM_FROM_EXISTING if existing_room else unit.room_source
        if pending:
            self._create(unit, pending, room)
        if room:
            self._fill(fills, room)
        return rows

    def _create(self, unit, pending, room) -> None:
        kinds, slots = self._check(unit, pending, room)
        dropped_room = False
        if kinds == {schedule_conflicts.KIND_ROOM} and room:
            kinds, slots = self._check(unit, pending, "")
            dropped_room = True
        if kinds:
            reason = "clash_" + next(kind for kind in schedule_conflicts.KIND_ORDER if kind in kinds)
            for _offering, _stored, row in pending:
                row.action, row.reason = CONFLICT, reason
            return
        for (offering, _stored, row), slot in zip(pending, slots):
            row.slot = slot
            row.reason = "room_dropped" if dropped_room else unit.reason
            self.by_day[unit.weekday].append(slot)
            key = _identity(offering.pk, unit.weekday, unit.start, unit.teacher_id)
            self.identity[key].append(slot)

    def _fill(self, fills, room) -> None:
        """Bu əmrin ƏVVƏL yazdığı, otağı BOŞ slota otaq (rəsmi / əl ilə qoyulmuş slotlara toxunulmur).

        Otaq eyni vaxtda başqa slotda tutulubsa (``schedule_conflicts.detect`` — otaq növü) doldurulmur."""
        for row in fills:
            slot = row.slot
            clashes = schedule_conflicts.detect(
                organization=self.organization,
                weekday=slot.weekday,
                start_time=slot.start_time,
                end_time=slot.end_time,
                week_type=slot.week_type,
                room=room,
                group_id=slot.offering.group_id,
                instructor_id=schedule.effective_instructor_id(slot),
                exclude_ids=[slot.pk],
                candidates=self.by_day[slot.weekday],
                period_id=self.period.pk,
                subject_id=slot.offering.subject_id,
                kind=slot.kind,
                offering_id=slot.offering_id,
            )
            if any(clash["kind"] == schedule_conflicts.KIND_ROOM for clash in clashes):
                row.reason = "room_fill_clash"
                continue
            slot.room = room
            row.fill_room, row.reason = room, "room_filled"


def _exists_reason(slot, unit) -> str:
    if slot.is_parked:
        return "exists_parked"
    if slot.kind != unit.kind:
        return "exists_other_kind"
    if slot.week_type != unit.week_type:
        return "exists_other_week_type"
    if slot.end_time != unit.end:
        return "exists_other_end"
    return ""


def inferred_slot_ids(organization, source: str) -> set:
    """Bu əmrin (``source``) əvvəlki işlərində yaratdığı slotların id-ləri — audit sətirlərinin ``created_ids``-i.

    Otaq doldurma YALNIZ bunlara toxunur: rəsmi docx idxalı və redaktorda əl ilə qoyulmuş slotlar dəyişmir."""
    if not source:
        return set()
    audit_log = django_apps.get_model("audit", "AuditLog")
    ids = set()
    rows = audit_log.objects.filter(
        organization=organization, resource_type="registrar.ScheduleSlot", resource_id=source
    ).values_list("new_values", flat=True)
    for values in rows:
        ids.update(str(pk) for pk in (values or {}).get("created_ids") or ())
    return ids


def build_plan(
    *, organization, period, units, facts=None, actor=None, fill_rooms=False, source="infer_timetable_from_lessons"
) -> Plan:
    """Heç nə yazmadan plan (``apply`` da bunu kilid altında çağırır)."""
    plan = Plan(facts=Counter(facts or {}), units=list(units))
    planner = _Planner(
        organization=organization,
        period=period,
        units=plan.units,
        actor=actor,
        fill_rooms=fill_rooms,
        source=source,
    )
    for unit in plan.units:
        plan.rows.extend(planner.plan_unit(unit))
    return plan


def _write(plan: Plan, *, organization, period, actor, source: str) -> None:
    from core.audit import log_action
    from core.constants import AuditAction

    for row in plan.rows:
        if row.fill_room:
            row.slot.save(update_fields=["room", "updated_at"])
            plan.filled_ids.append(str(row.slot.pk))
        if row.action != CREATE:
            continue
        row.slot.save()
        plan.created_ids.append(str(row.slot.pk))
    if not (plan.created_ids or plan.filled_ids):
        return
    log_action(
        AuditAction.UPDATE,
        user=actor if getattr(actor, "pk", None) else None,
        organization=organization,
        new_values={
            "source": source,
            "period_id": str(period.pk),
            "created": len(plan.created_ids),
            "counts": dict(plan.counts),
            "units": dict(plan.unit_counts()),
            "created_ids": plan.created_ids,
            "room_filled_ids": plan.filled_ids,
        },
        reason="Dərs cədvəli jurnalın keçirilmiş dərslərindən çıxarıldı",
        resource_type="registrar.ScheduleSlot",
        resource_id=source or str(period.pk),
        resource_repr="Dərs cədvəli (jurnal dərslərindən)",
    )


def weekly_budgets(offering_ids) -> dict:
    """``{(açılış id, növ): həftəlik slot}`` — açılışın plan / kafedra yükü saatından (``plan_hours``).

    1 dərs = 2 akademik saat, semestr = ``EFFECTIVE_WEEKS`` (15) həftə: 30 saat → 1 (hər həftə), 15 → 0.5 (üst
    və ya alt), 45 → 1.5; ən yaxın 0.5-ə yuvarlanır. Saatı məlum olmayan açılış lüğətdə yoxdur (məhdudiyyət yox).
    """
    from apps.registrar.models.curriculum_meta import EFFECTIVE_WEEKS
    from apps.registrar.plan_hours import plan_hours_for_offering

    budgets = {}
    offerings = CourseOffering.objects.filter(pk__in=list(offering_ids)).select_related(
        "organization", "subject", "group", "period"
    )
    for offering in offerings:
        for kind, hours in (plan_hours_for_offering(offering) or {}).items():
            weekly = round(float(hours) / 2 / EFFECTIVE_WEEKS * 2) / 2
            if hours and kind in ("lecture", "seminar", "lab"):
                budgets[(str(offering.pk), kind)] = max(weekly, 0.5)
    return budgets


def run_inference(
    *,
    organization,
    period,
    date_from,
    date_to,
    teacher=None,
    rules: Rules | None = None,
    actor=None,
    apply: bool = False,
    source: str = "infer_timetable_from_lessons",
) -> Plan:
    """Dry-run (defolt — heç nə yazılmır) və ya yazı (kilid altında yenidən qurulan plan)."""
    rules = rules or Rules()
    facts, stats = load_facts(
        organization=organization,
        period=period,
        date_from=date_from,
        date_to=date_to,
        teacher=teacher,
        snap_minutes=rules.snap_minutes,
    )
    budgets = weekly_budgets({fact.offering_id for fact in facts}) if rules.hours_cap else None
    units = build_units(
        facts,
        period=period,
        min_occurrences=rules.min_occurrences,
        parity_tolerance=rules.parity_tolerance,
        budgets=budgets,
        recent_since=date_to - dt.timedelta(days=rules.recent_days - 1) if rules.recent_days > 0 else None,
    )
    options = {"facts": stats, "actor": actor, "fill_rooms": rules.fill_rooms, "source": source}
    if not apply:
        return build_plan(organization=organization, period=period, units=units, **options)
    with transaction.atomic():
        schedule_lock.lock_schedule(organization.pk, period.pk)
        plan = build_plan(organization=organization, period=period, units=units, **options)
        _write(plan, organization=organization, period=period, actor=actor, source=source)
    return plan


def usernames_for(plan: Plan) -> dict:
    """Hesabat üçün ``{müəllim id → istifadəçi adı}`` (bir sorğu; stdout-a düşmür)."""
    ids = {unit.teacher_id for unit in plan.units}
    user_model = django_apps.get_model("auth", "User")
    return dict(user_model._default_manager.filter(pk__in=ids).values_list("pk", "username"))


__all__ = [
    "ACTIONS",
    "CONFLICT",
    "CREATE",
    "EXISTS",
    "REPORT_HEADER",
    "SKIPPED",
    "MemberRow",
    "Plan",
    "build_plan",
    "inferred_slot_ids",
    "run_inference",
    "usernames_for",
    "weekly_budgets",
]
