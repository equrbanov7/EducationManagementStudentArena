"""Dərs cədvəli .docx idxalı — plan, toqquşma yoxlaması, yazı və hesabat (sahib 2026-10-12).

Axın: ``schedule_docx_parse`` (hüceyrələr) → ``schedule_docx_match`` (açılış/müəllim/növ) → burada:

* İDEMPOTENTLİK: eyni açılış + gün + başlama saatı + həftə növü + dərs növü olan canlı (silinməmiş,
  parklanmış da daxil) slot varsa — ``exists`` (yenisi yaradılmır). Təkrar işə salma 0 yaradır.
* TOQQUŞMA (``schedule_conflicts`` / ``schedule_publish`` ilə EYNİ qaydalar): gün + vaxt aralığı +
  həftə növü kəsişirsə (üst↔alt kəsişmir) eyni QRUP → həmişə toqquşma; eyni effektiv MÜƏLLİM və ya eyni
  OTAQ → toqquşma, BİRGƏ DƏRS istisna olmaqla (eyni fənn + eyni növ + eyni müəllim + eyni/boş otaq —
  cədvəldə bir neçə qrup bir otaqda birlikdə oturur; dərcin «stream» qaydası). Toqquşan sətir YAZILMIR.
  Yoxlama həm canlı semestr slotları, həm də bu idxalın əvvəlki sətirləri ilə aparılır.
* ``replace_group_slots``: fayldakı qrupların həmin semestrdəki canlı slotları (fayl sətri ilə tam üst-üstə
  düşənlər xaric) YUMŞAQ silinir — ``schedule_publish`` ilə eyni üsul (``is_deleted``; bərpa mümkündür).
* YAZI: ``apply=True`` olanda hamısı bir tranzaksiyada, semestr cədvəl kilidi
  (``schedule_lock.lock_schedule``) altında; plan kilid ALTINDA yenidən qurulur. Slot ``save()`` ilə
  (referans-kimlik yoxlaması) yaranır; slot müəllimi jurnal sahibi ilə eynidirsə NULL yazılır
  (``schedule.stored_instructor_id``). Bir audit sətri (saylar + slot id-ləri).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.registrar import schedule_conflicts, schedule_lock
from apps.registrar.models import ScheduleSlot
from apps.registrar.schedule import effective_instructor_id, stored_instructor_id
from apps.registrar.schedule_docx_match import Resolver
from apps.registrar.schedule_docx_parse import ParseResult, fold

CREATE = "create"
EXISTS = "exists"
UNMATCHED = "unmatched"
AMBIGUOUS = "ambiguous"
CLASH = "clash"
SKIPPED = "skipped"
ACTIONS = (CREATE, EXISTS, UNMATCHED, AMBIGUOUS, CLASH, SKIPPED)

REPORT_HEADER = (
    "table",
    "row",
    "group",
    "weekday",
    "time",
    "week_type",
    "room",
    "raw_subject",
    "kind",
    "kind_source",
    "teacher_token",
    "offering",
    "offering_group",
    "instructor",
    "action",
    "reason",
)
_AMBIGUOUS_REASONS = {"group_ambiguous", "subject_ambiguous", "subject_partial", "kind_unknown"}


@dataclass
class PlanRow:
    entry: object
    action: str
    reasons: list[str] = field(default_factory=list)
    offering: object = None
    instructor: object = None
    kind: str = ""
    kind_source: str = ""
    detail: str = ""

    def csv_row(self) -> list:
        entry = self.entry
        offering = self.offering
        return [
            entry.table,
            entry.row,
            entry.group.display,
            entry.weekday,
            "%s-%s" % (entry.start.strftime("%H:%M"), entry.end.strftime("%H:%M")),
            entry.week_type,
            entry.room,
            entry.text.raw,
            self.kind,
            self.kind_source,
            entry.text.teacher,
            getattr(getattr(offering, "subject", None), "code", "") if offering else "",
            getattr(getattr(offering, "group", None), "name", "") if offering else "",
            getattr(self.instructor, "username", "") if self.instructor else "",
            self.action,
            ";".join(self.reasons) + (f" vs {self.detail}" if self.detail else ""),
        ]


@dataclass
class Plan:
    rows: list[PlanRow] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    replaced_ids: list = field(default_factory=list)
    created_ids: list = field(default_factory=list)
    invisible_offerings: int = 0
    groups: dict = field(default_factory=dict)

    @property
    def counts(self) -> Counter:
        return Counter(row.action for row in self.rows)

    def reason_counts(self, action=None) -> Counter:
        counter: Counter = Counter()
        for row in self.rows:
            if action is None or row.action == action:
                for reason in row.reasons:
                    counter[reason.split(":")[0]] += 1
        return counter


def _live_row(slot) -> dict:
    return {
        "slot_id": slot.pk,
        "offering_id": slot.offering_id,
        "group_id": slot.offering.group_id,
        "subject_id": slot.offering.subject_id,
        "subject": fold(slot.offering.subject.name),
        "weekday": slot.weekday,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "week_type": slot.week_type,
        "kind": slot.kind,
        "room": (slot.room or "").strip().lower(),
        "teacher_id": effective_instructor_id(slot),
        "group_name": getattr(slot.offering.group, "name", ""),
        "subject_code": slot.offering.subject.code,
    }


def _overlap(a: dict, b: dict) -> bool:
    return (
        a["weekday"] == b["weekday"]
        and schedule_conflicts.time_ranges_overlap(a["start_time"], a["end_time"], b["start_time"], b["end_time"])
        and schedule_conflicts.week_types_overlap(a["week_type"], b["week_type"])
    )


def _joint(a: dict, b: dict) -> bool:
    """Birgə dərs: eyni fənn + növ + müəllim + eyni/boş otaq.

    Müəllim: eyni effektiv müəllim id-si (ikisində də boş daxil) və ya — bu idxalın iki sətri üçün —
    fayldakı EYNİ müəllim nişanı (müəllim tapılmayanda açılışların jurnal sahibləri fərqli ola bilər)."""
    same_subject = a["subject_id"] == b["subject_id"] or (a["subject"] and a["subject"] == b["subject"])
    token = a.get("teacher_token") or ""
    same_teacher = str(a["teacher_id"] or "") == str(b["teacher_id"] or "") or (
        token and token == (b.get("teacher_token") or "")
    )
    rooms_ok = not a["room"] or not b["room"] or a["room"] == b["room"]
    return bool(same_subject and a["kind"] == b["kind"] and same_teacher and rooms_ok)


def _label(row: dict) -> str:
    return "%s/%s" % (row.get("group_name", ""), row.get("subject_code", ""))


def _clash(new: dict, others: list[dict]) -> tuple[str, str]:
    """→ (toqquşma növü, qarşı slotun «qrup/fənn kodu» etiketi) və ya ("", "")."""
    for other in others:
        if not _overlap(new, other):
            continue
        if new["group_id"] and new["group_id"] == other["group_id"]:
            return schedule_conflicts.KIND_GROUP, _label(other)
        if _joint(new, other):
            continue
        if new["teacher_id"] and str(new["teacher_id"]) == str(other["teacher_id"] or ""):
            return schedule_conflicts.KIND_TEACHER, _label(other)
        if new["room"] and new["room"] == other["room"]:
            return schedule_conflicts.KIND_ROOM, _label(other)
    return "", ""


def _identity(row: dict) -> tuple:
    return (str(row["offering_id"]), row["weekday"], row["start_time"], row["week_type"], row["kind"])


def _same_content(slot_row: dict, new: dict) -> bool:
    return (
        slot_row["end_time"] == new["end_time"]
        and slot_row["room"] == new["room"]
        and str(slot_row["teacher_id"] or "") == str(new["teacher_id"] or "")
    )


def _resolve_entry(resolver: Resolver, entry) -> list[PlanRow]:
    text = entry.text
    if text.special:
        return [PlanRow(entry=entry, action=SKIPPED, reasons=[text.special])]
    resolution = resolver.resolve(entry.group, text.subject)
    if not resolution.targets:
        action = AMBIGUOUS if resolution.reason in _AMBIGUOUS_REASONS else UNMATCHED
        return [PlanRow(entry=entry, action=action, reasons=[resolution.reason])]
    rows = []
    for target in resolution.targets:
        offering = target.offering
        reasons = list(resolution.notes) + list(entry.notes)
        if target.score < 1.0:
            reasons.append(f"subject_fuzzy:{target.score}")
        teacher, teacher_reason = resolver.teacher(offering, text.teacher)
        if teacher_reason:
            reasons.append(teacher_reason)
        kind, kind_source = text.kind, "cell"
        if text.kind_note:
            reasons.append(f"kind_note:{text.kind_note.replace(' ', '+')}")
        if not kind:
            # Magistratura hüceyrəsi («(N saat)» / tam ad) növsüzdür — bölgüdən çıxmırsa mühazirə.
            default = "lecture" if (text.hours or text.teacher_full) else ""
            kind, kind_source = resolver.infer_kind(offering, teacher, default=default)
        row = PlanRow(
            entry=entry,
            action=CREATE,
            reasons=reasons,
            offering=offering,
            instructor=teacher,
            kind=kind,
            kind_source=kind_source,
        )
        if not kind:
            row.action = AMBIGUOUS
            row.reasons.append("kind_unknown")
        rows.append(row)
    return rows


def _new_row(row: PlanRow) -> dict:
    offering, entry = row.offering, row.entry
    stored = stored_instructor_id(offering, getattr(row.instructor, "pk", None))
    return {
        "offering_id": offering.pk,
        "group_id": offering.group_id,
        "subject_id": offering.subject_id,
        "subject": fold(offering.subject.name),
        "group_name": offering.group.name,
        "subject_code": offering.subject.code,
        "weekday": entry.weekday,
        "start_time": entry.start,
        "end_time": entry.end,
        "week_type": entry.week_type,
        "kind": row.kind,
        "room": (entry.room or "").strip().lower(),
        "teacher_id": stored or offering.instructor_id,
        "stored_instructor_id": stored,
        "teacher_token": fold(entry.text.teacher).replace(".", "").replace(" ", ""),
    }


def build_plan(*, organization, period, parsed: ParseResult, replace_group_slots: bool = False) -> Plan:
    """Heç nə yazmadan planı qurur (``apply`` da bunu kilid altında çağırır)."""
    resolver = Resolver(organization, period)
    plan = Plan(skipped=list(parsed.skipped))
    resolved: list[PlanRow] = []
    for entry in parsed.entries:
        resolved.extend(_resolve_entry(resolver, entry))
    plan.groups = dict(resolver.group_seen)

    candidates = [row for row in resolved if row.action == CREATE]
    live_qs = (
        ScheduleSlot.objects.filter(organization=organization, offering__period=period)
        .select_related("offering", "offering__subject", "offering__group")
        .order_by("created_at")
    )
    live = [_live_row(slot) | {"is_parked": slot.is_parked} for slot in live_qs]
    by_identity = {}
    for slot_row in live:
        by_identity.setdefault(_identity(slot_row), []).append(slot_row)

    keep_ids = set()
    new_rows = {id(row): _new_row(row) for row in candidates}
    if replace_group_slots:
        group_ids = {row.offering.group_id for row in candidates}
        for row in candidates:
            for slot_row in by_identity.get(_identity(new_rows[id(row)]), []):
                if _same_content(slot_row, new_rows[id(row)]):
                    keep_ids.add(slot_row["slot_id"])
                    break
        plan.replaced_ids = [
            slot_row["slot_id"]
            for slot_row in live
            if slot_row["group_id"] in group_ids and slot_row["slot_id"] not in keep_ids
        ]
    replaced = set(plan.replaced_ids)
    remaining = [slot_row for slot_row in live if slot_row["slot_id"] not in replaced]
    remaining_identity = {}
    for slot_row in remaining:
        remaining_identity.setdefault(_identity(slot_row), []).append(slot_row)
    others = [slot_row for slot_row in remaining if not slot_row["is_parked"]]

    accepted_keys = set()
    seen_offerings = set()
    for row in resolved:
        if row.action != CREATE:
            plan.rows.append(row)
            continue
        new = new_rows[id(row)]
        ident = _identity(new)
        existing = remaining_identity.get(ident)
        if existing:
            row.action = EXISTS
            if existing[0]["is_parked"]:
                row.reasons.append("exists_parked")
            elif not _same_content(existing[0], new):
                row.reasons.append("exists_differs")
        elif ident in accepted_keys:
            row.action = SKIPPED
            row.reasons.append("duplicate_in_file")
        else:
            clash, other = _clash(new, others)
            if clash:
                row.action = CLASH
                row.reasons.append(f"clash_{clash}")
                row.detail = other
            else:
                accepted_keys.add(ident)
                others.append(new)
                if not new["teacher_id"]:  # heç bir müəllimin cədvəlinə düşməyəcək
                    row.reasons.append("no_effective_teacher")
                if row.offering.pk not in seen_offerings:
                    seen_offerings.add(row.offering.pk)
                    if resolver.visible_students(row.offering) == 0:
                        plan.invisible_offerings += 1
                        row.reasons.append("no_visible_students")
        plan.rows.append(row)
    return plan


def _write(plan: Plan, *, organization, period, actor, source: str) -> None:
    from core.audit import log_action
    from core.constants import AuditAction

    now = timezone.now()
    if plan.replaced_ids:
        ScheduleSlot.all_objects.filter(pk__in=plan.replaced_ids, is_deleted=False).update(
            is_deleted=True, deleted_at=now, is_parked=False, updated_at=now
        )
    for row in plan.rows:
        if row.action != CREATE:
            continue
        new = _new_row(row)
        slot = ScheduleSlot(
            organization=organization,
            offering=row.offering,
            weekday=new["weekday"],
            start_time=new["start_time"],
            end_time=new["end_time"],
            room=row.entry.room,
            week_type=new["week_type"],
            kind=new["kind"],
            created_by=actor if getattr(actor, "pk", None) else None,
            instructor_id=new["stored_instructor_id"],
        )
        slot.save()
        plan.created_ids.append(str(slot.pk))
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={
            "source": source,
            "period_id": str(period.pk),
            "created": len(plan.created_ids),
            "removed": len(plan.replaced_ids),
            "counts": dict(plan.counts),
            "created_ids": plan.created_ids,
            "removed_ids": [str(pk) for pk in plan.replaced_ids],
        },
        reason="Dərs cədvəli .docx idxalı",
        resource_type="registrar.ScheduleSlot",
        resource_id=source or str(period.pk),
        resource_repr="Dərs cədvəli idxalı (docx)",
    )


def run_import(
    *, organization, period, parsed: ParseResult, actor=None, apply=False, replace_group_slots=False, source=""
) -> Plan:
    """Dry-run (defolt) və ya yazı. Yazıda plan semestr kilidi ALTINDA yenidən qurulur."""
    if not apply:
        return build_plan(
            organization=organization, period=period, parsed=parsed, replace_group_slots=replace_group_slots
        )
    with transaction.atomic():
        schedule_lock.lock_schedule(organization.pk, period.pk)
        plan = build_plan(
            organization=organization, period=period, parsed=parsed, replace_group_slots=replace_group_slots
        )
        _write(plan, organization=organization, period=period, actor=actor, source=source)
    return plan


__all__ = ["ACTIONS", "REPORT_HEADER", "Plan", "PlanRow", "build_plan", "run_import"]
