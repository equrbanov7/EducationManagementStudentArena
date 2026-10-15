"""Müəllim cədvəli slotları — ``backfill_teacher_lessons`` (sahib 2026-10-15), bax :mod:`lesson_backfill`.

* CANLI rejim: müəllimin semestrdəki cədvəldə duran (silinməmiş, parklanmamış) slotları — effektiv müəllim
  qaydası ilə (``schedule.taught_by_q``); eyni açılış + gün + başlama + həftə növü təkrarı bir dəfə sayılır.
* SPESİFİKASİYA rejimi (JSON): hər sətir müəllimin ÖZ açılışına (``instructor``) TƏK uyğunluqla bağlanır
  (qrup adı tam — ``fold`` müqayisəsi, fənn adı alt-sətir; bir neçə uyğunluqda fənn adı tam bərabər olan
  seçilir); tapılmayan / çox mənalı sətir hesabata düşür və ötürülür. Mövcud eyni slot saxlanılır,
  çatışmayan ``schedule.create_slot`` ilə yaranır (semestr kilidi + qrup/müəllim/otaq toqquşma qaydası).
* ``replace``: müəllimin bu semestrdəki DİGƏR slotları (parklanmışlar da) yumşaq silinir (``is_deleted`` —
  ``schedule_docx_import`` ilə eyni üsul, bərpa olunur). Dəyişiklik varsa bir audit sətri.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.registrar import schedule
from apps.registrar.models import CourseOffering, ScheduleSlot, SlotKind, WeekType
from apps.registrar.schedule_docx_parse import fold

MAX_SPEC_ROWS = 200

# Slot sətrinin əməlləri
SLOT_USED = "used"
SLOT_CREATED = "created"
SLOT_KEPT = "kept"
SLOT_SOFT_DELETED = "soft_deleted"
SLOT_DUPLICATE = "duplicate"
SLOT_UNMATCHED = "unmatched"
SLOT_AMBIGUOUS = "ambiguous"
SLOT_CLASH = "clash"
SLOT_ACTIONS = (
    SLOT_USED,
    SLOT_KEPT,
    SLOT_CREATED,
    SLOT_SOFT_DELETED,
    SLOT_DUPLICATE,
    SLOT_UNMATCHED,
    SLOT_AMBIGUOUS,
    SLOT_CLASH,
)
SLOT_REPORT_HEADER = (
    "source",
    "subject_code",
    "subject",
    "group",
    "weekday",
    "time",
    "kind",
    "week_type",
    "room",
    "action",
    "reason",
)


class SpecError(ValueError):
    """Slot spesifikasiyası (JSON) yararsızdır — mesaj sətir nömrəsi ilə."""


@dataclass(frozen=True)
class SlotSpec:
    group: str
    subject_contains: str
    weekday: int
    start: dt.time
    end: dt.time
    kind: str
    week_type: str
    room: str = ""


@dataclass
class SlotRow:
    source: str  # "spec" | "live"
    action: str
    weekday: int
    start: dt.time
    end: dt.time
    kind: str
    week_type: str
    room: str = ""
    offering: object = None
    group_label: str = ""
    reason: str = ""

    def csv_row(self) -> list:
        subject = getattr(self.offering, "subject", None)
        group = getattr(getattr(self.offering, "group", None), "name", "") or self.group_label
        return [
            self.source,
            getattr(subject, "code", ""),
            getattr(subject, "name", ""),
            group,
            self.weekday,
            f"{self.start:%H:%M}-{self.end:%H:%M}",
            self.kind,
            self.week_type,
            self.room,
            self.action,
            self.reason,
        ]


# ── Spesifikasiya ────────────────────────────────────────────────────────────


def _parse_time(value, where: str) -> dt.time:
    try:
        return dt.time.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        raise SpecError(f"{where}: saat «HH:MM» formatında olmalıdır") from None


def load_slot_spec(text: str) -> list[SlotSpec]:
    """JSON → ``SlotSpec`` siyahısı: ``[{group, subject_contains, weekday, start, end, kind, week_type, room}]``
    (və ya ``{"slots": [...]}``). Yararsız sətir bütün faylı rədd edir (yarımçıq cədvəl yazılmasın)."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise SpecError("slots_file JSON deyil") from None
    if isinstance(data, dict):
        data = data.get("slots")
    if not isinstance(data, list) or not data:
        raise SpecError("slots_file boş siyahı və ya yanlış quruluşdur")
    if len(data) > MAX_SPEC_ROWS:
        raise SpecError(f"slots_file ən çox {MAX_SPEC_ROWS} sətir ola bilər")
    specs = []
    for index, raw in enumerate(data, start=1):
        where = f"sətir {index}"
        if not isinstance(raw, dict):
            raise SpecError(f"{where}: obyekt olmalıdır")
        group = " ".join(str(raw.get("group") or "").split())
        subject = " ".join(str(raw.get("subject_contains") or "").split())
        if not group or len(group) > 64 or len(subject) > 120:
            raise SpecError(f"{where}: group boşdur və ya uzundur")
        try:
            weekday = int(raw.get("weekday"))
        except (TypeError, ValueError):
            weekday = 0
        if not 1 <= weekday <= 7:
            raise SpecError(f"{where}: weekday 1..7 olmalıdır")
        start, end = _parse_time(raw.get("start"), where), _parse_time(raw.get("end"), where)
        if start >= end:
            raise SpecError(f"{where}: start end-dən əvvəl olmalıdır")
        kind = str(raw.get("kind") or "").strip()
        week_type = str(raw.get("week_type") or WeekType.ALL).strip()
        if kind not in SlotKind.values or week_type not in WeekType.values:
            raise SpecError(f"{where}: kind ({'/'.join(SlotKind.values)}) və ya week_type yanlışdır")
        room = " ".join(str(raw.get("room") or "").split())[:64]
        specs.append(SlotSpec(group, subject, weekday, start, end, kind, week_type, room))
    return specs


def match_offering(spec: SlotSpec, offerings) -> tuple[object, str]:
    """Spesifikasiya sətrini müəllimin açılışına bağla → ``(açılış, "")`` və ya ``(None, səbəb)``."""
    group_key, subject_key = fold(spec.group), fold(spec.subject_contains)
    found = [
        offering
        for offering in offerings
        if offering.group_id
        and fold(offering.group.name) == group_key
        and (not subject_key or subject_key in fold(offering.subject.name))
    ]
    if len(found) > 1 and subject_key:
        exact = [offering for offering in found if fold(offering.subject.name) == subject_key]
        found = exact if len(exact) == 1 else found
    if not found:
        return None, "offering_not_found"
    if len(found) > 1:
        return None, f"offering_ambiguous:{len(found)}"
    return found[0], ""


# ── Slotlar ─────────────────────────────────────────────────────────────────


def _teacher_slots(organization, period, teacher, *, include_parked: bool):
    queryset = ScheduleSlot.objects.filter(organization=organization, offering__period=period).filter(
        schedule.taught_by_q(teacher)
    )
    if not include_parked:
        queryset = queryset.filter(is_parked=False)
    return list(
        queryset.select_related("offering", "offering__subject", "offering__group", "instructor").order_by(
            "weekday", "start_time", "created_at"
        )
    )


def _slot_row(slot, source, action, reason="") -> SlotRow:
    return SlotRow(
        source=source,
        action=action,
        weekday=slot.weekday,
        start=slot.start_time,
        end=slot.end_time,
        kind=slot.kind,
        week_type=slot.week_type,
        room=slot.room or "",
        offering=slot.offering,
        reason=reason,
    )


def live_slots(organization, period, teacher, rows: list) -> list:
    """Müəllimin cədvəldə duran slotları; açılış + gün + başlama + həftə növü təkrarı bir dəfə."""
    picked, seen = [], set()
    for slot in _teacher_slots(organization, period, teacher, include_parked=False):
        key = (slot.offering_id, slot.weekday, slot.start_time, slot.week_type)
        if key in seen:
            rows.append(_slot_row(slot, "live", SLOT_DUPLICATE))
            continue
        seen.add(key)
        picked.append(slot)
        rows.append(_slot_row(slot, "live", SLOT_USED))
    return picked


def _same_slot(slot, spec: SlotSpec, offering) -> bool:
    return (
        not slot.is_parked
        and slot.offering_id == offering.pk
        and slot.weekday == spec.weekday
        and slot.start_time == spec.start
        and slot.end_time == spec.end
        and slot.week_type == spec.week_type
        and slot.kind == spec.kind
        and (not spec.room or (slot.room or "").strip().lower() == spec.room.lower())
    )


def sync_spec_slots(*, organization, period, teacher, specs, actor, replace: bool, rows: list) -> list:
    """Spesifikasiyanı slotlara çevir (mövcud eyni slot saxlanılır, çatışmayan yaranır); ``replace`` →
    müəllimin bu semestrdəki digər slotları yumşaq silinir. Dərs üçün işlənəcək slotları qaytarır."""
    from apps.registrar import schedule_lock

    schedule_lock.lock_schedule(organization.pk, period.pk)
    offerings = list(
        CourseOffering.objects.filter(organization=organization, period=period, instructor=teacher, is_active=True)
        .select_related("subject", "group")
        .order_by("group__name", "subject__name")
    )
    current = _teacher_slots(organization, period, teacher, include_parked=True)
    resolved, keep_ids = [], set()
    seen = set()
    for spec in specs:
        offering, reason = match_offering(spec, offerings)
        row = SlotRow("spec", "", spec.weekday, spec.start, spec.end, spec.kind, spec.week_type, spec.room)
        row.offering, row.group_label = offering, spec.group
        if offering is None:
            row.action = SLOT_AMBIGUOUS if reason.startswith("offering_ambiguous") else SLOT_UNMATCHED
            row.reason = reason
            rows.append(row)
            continue
        key = (offering.pk, spec.weekday, spec.start, spec.week_type, spec.kind)
        if key in seen:
            row.action, row.reason = SLOT_DUPLICATE, "duplicate_in_spec"
            rows.append(row)
            continue
        seen.add(key)
        existing = next(
            (slot for slot in current if slot.pk not in keep_ids and _same_slot(slot, spec, offering)), None
        )
        if existing is not None:
            keep_ids.add(existing.pk)
        resolved.append((spec, offering, existing, row))

    removed = []
    if replace:
        now = timezone.now()
        removed = [slot for slot in current if slot.pk not in keep_ids]
        if removed:
            ScheduleSlot.all_objects.filter(pk__in=[slot.pk for slot in removed], is_deleted=False).update(
                is_deleted=True, deleted_at=now, is_parked=False, updated_at=now
            )
        for slot in removed:
            rows.append(_slot_row(slot, "live", SLOT_SOFT_DELETED, "parked" if slot.is_parked else ""))

    used, created = [], []
    for spec, offering, existing, row in resolved:
        if existing is not None:
            row.action = SLOT_KEPT
            used.append(existing)
        else:
            try:
                with transaction.atomic():
                    slot = schedule.create_slot(
                        offering=offering,
                        weekday=spec.weekday,
                        start_time=spec.start,
                        end_time=spec.end,
                        room=spec.room,
                        week_type=spec.week_type,
                        kind=spec.kind,
                        created_by=actor,
                    )
            except schedule.ScheduleConflict as exc:
                row.action, row.reason = SLOT_CLASH, f"clash_{_conflict_kind(exc.conflict, offering, teacher)}"
            else:
                row.action = SLOT_CREATED
                created.append(slot)
                used.append(slot)
        rows.append(row)
    if created or removed:
        _audit_slots(organization, period, teacher, actor, created, removed)
    return used


def _conflict_kind(other, offering, teacher) -> str:
    """``find_conflict``-in qaytardığı qarşı slot → toqquşma növü (qrup → müəllim → otaq)."""
    if getattr(other, "offering", None) is not None and other.offering.group_id == offering.group_id:
        return "group"
    if schedule.same_id(schedule.effective_instructor_id(other), teacher.pk):
        return "teacher"
    return "room"


def _audit_slots(organization, period, teacher, actor, created, removed) -> None:
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={
            "source": "backfill_teacher_lessons",
            "period_id": str(period.pk),
            "teacher_id": str(teacher.pk),
            "created": len(created),
            "removed": len(removed),
            "created_ids": [str(slot.pk) for slot in created],
            "removed_ids": [str(slot.pk) for slot in removed],
        },
        reason="Müəllimin cədvəli spesifikasiya ilə eyniləşdirildi (keçmiş dərslərin bərpası)",
        resource_type="registrar.ScheduleSlot",
        resource_id=str(teacher.pk),
        resource_repr="Müəllim cədvəli (backfill_teacher_lessons)",
    )


__all__ = [
    "MAX_SPEC_ROWS",
    "SLOT_ACTIONS",
    "SLOT_REPORT_HEADER",
    "SlotRow",
    "SlotSpec",
    "SpecError",
    "live_slots",
    "load_slot_spec",
    "match_offering",
    "sync_spec_slots",
]
