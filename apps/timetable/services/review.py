"""Qaralamanın BAXIŞ qatı — qrup / müəllim / otaq üzrə həftəlik şəbəkə, siyahılar, KPI.

Axın mühazirəsi (eyni ``event_key``, bir neçə açılış) şəbəkədə BİR element kimi
göstərilir, qrupları birlikdə yazılır. Üst/alt həftə dərsləri eyni xanada iki
yarım kimi görünür (mövcud cədvəl matrisi ilə eyni dil).
"""

from __future__ import annotations

from django.utils.translation import pgettext

from apps.registrar.public import schedule, schedule_grid

from ..constants import RunStatus

_CTX = "timetable.review"

VIEW_GROUP, VIEW_TEACHER, VIEW_ROOM = "group", "teacher", "room"
_WEEK_ORDER = {"all": 0, "odd": 1, "even": 2}


def _name(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def kind_labels() -> dict:
    return {
        "lecture": pgettext(_CTX, "Mühazirə"),
        "seminar": pgettext(_CTX, "Məşğələ"),
        "lab": pgettext(_CTX, "Laboratoriya"),
    }


def draft_rows(run):
    return list(
        run.slots.select_related("offering__subject", "offering__group", "teacher").order_by(
            "weekday", "pair", "event_key", "offering__group__name"
        )
    )


def events_of(rows) -> list:
    """Sətirləri ``event_key`` üzrə birləşdir → hadisə siyahısı (UI müqaviləsi)."""
    events: dict = {}
    labels = kind_labels()
    for row in rows:
        item = events.get(row.event_key)
        group = getattr(row.offering.group, "name", "") or ""
        if item is None:
            subject = row.offering.subject
            item = {
                "key": row.event_key,
                "kind": row.kind,
                "kind_label": labels.get(row.kind, row.kind),
                "weekday": row.weekday,
                "pair": row.pair,
                "week_type": row.week_type,
                "is_biweekly": row.is_biweekly,
                "subject": getattr(subject, "name", "") or "",
                "subject_code": getattr(subject, "code", "") or "",
                "teacher_id": row.teacher_id,
                "teacher": _name(row.teacher),
                "room": row.room,
                "locked": row.locked,
                "is_manual": row.is_manual,
                "reason": row.reason,
                "reason_code": row.reason_code,
                "groups": [],
                "group_ids": [],
                "offering_ids": [],
                "split_teacher": bool(row.teacher_id and row.offering.instructor_id != row.teacher_id),
            }
            events[row.event_key] = item
        if group and group not in item["groups"]:
            item["groups"].append(group)
        if row.offering.group_id:
            item["group_ids"].append(str(row.offering.group_id))
        item["offering_ids"].append(str(row.offering_id))
    return list(events.values())


def options(events) -> dict:
    groups, teachers, rooms = {}, {}, set()
    for event in events:
        for gid, name in zip(event["group_ids"], event["groups"]):
            groups[gid] = name
        if event["teacher_id"]:
            teachers[str(event["teacher_id"])] = event["teacher"]
        if event["room"]:
            rooms.add(event["room"])
    return {
        "groups": [{"value": k, "label": v} for k, v in sorted(groups.items(), key=lambda kv: kv[1])],
        "teachers": [{"value": k, "label": v} for k, v in sorted(teachers.items(), key=lambda kv: kv[1].casefold())],
        "rooms": [{"value": r, "label": r} for r in sorted(rooms)],
    }


def _family(run, group_id) -> set:
    """Qrupun özü + ata/alt qrupları (birləşik qrupun dərsi alt qrupun gününə də düşür)."""
    from django.apps import apps as django_apps

    from ..sources.groups import load_groups

    Unit = django_apps.get_model("organizations", "OrgUnit")
    group = Unit.objects.filter(organization=run.organization, pk=group_id).first()
    if group is None:
        return {str(group_id)}
    siblings = list(Unit.objects.filter(organization=run.organization, parent_id=group.parent_id, is_active=True))
    infos = load_groups(run.organization, siblings or [group])
    info = infos.get(str(group.pk))
    related = {str(group.pk)}
    if info is not None:
        if info.parent:
            related.add(info.parent)
        related.update(info.children)
    return related


def select(events, run, view, key) -> list:
    if not key:
        return []
    if view == VIEW_TEACHER:
        return [e for e in events if str(e["teacher_id"] or "") == str(key)]
    if view == VIEW_ROOM:
        return [e for e in events if e["room"] == key]
    family = _family(run, key)
    return [e for e in events if family & set(e["group_ids"])]


def grid(run, events, weekdays) -> dict:
    """Günlər × dərs saatları matrisi; hər hüceyrə üst/alt sıralı elementlər daşıyır."""
    periods = schedule_grid.lesson_periods(run.organization)
    labels = dict(schedule.WEEKDAYS)
    cells: dict = {}
    for event in events:
        if event["weekday"] is None:
            continue
        cells.setdefault((event["weekday"], event["pair"]), []).append(event)
    rows = []
    for period in periods:
        row_cells = []
        for weekday in weekdays:
            items = sorted(cells.get((weekday, period["no"]), []), key=lambda e: _WEEK_ORDER.get(e["week_type"], 9))
            row_cells.append({"weekday": weekday, "pair": period["no"], "items": items, "is_empty": not items})
        rows.append({**period, "cells": row_cells})
    return {
        "days": [{"weekday": d, "label": str(labels.get(d, d))} for d in weekdays],
        "rows": rows,
    }


def unplaced(events) -> list:
    return [e for e in events if e["weekday"] is None]


def kpi_tiles(run) -> list:
    kpis = run.kpis or {}
    soft = kpis.get("soft") or {}
    placed, total = kpis.get("placed", 0), kpis.get("events", 0)
    tiles = [
        {
            "label": pgettext(_CTX, "Yerləşdirilib"),
            "value": f"{placed}/{total}",
            "tone": "accent-success" if total and placed == total else "accent-warning",
        },
        {
            "label": pgettext(_CTX, "Sərt pozuntu"),
            "value": kpis.get("hard_total", 0),
            "tone": "accent-success" if not kpis.get("hard_total") else "accent-danger",
            "note": pgettext(_CTX, "toqquşma + qrupda boşluq"),
        },
        {
            "label": pgettext(_CTX, "Müəllim boş cütü"),
            "value": soft.get("teacher_idle_per_week", 0),
            "note": pgettext(_CTX, "həftədə orta (üst/alt)"),
        },
        {
            "label": pgettext(_CTX, "Arzuolunmaz saat"),
            "value": soft.get("discouraged_used", 0),
            "note": pgettext(_CTX, "«dəyişdirilə bilən» xanalar"),
        },
        {
            "label": pgettext(_CTX, "Tək cütlük gün"),
            "value": soft.get("single_pair_days", 0),
            "note": pgettext(_CTX, "qrup bir dərs üçün gəlir"),
        },
    ]
    if soft.get("moved_vs_published"):
        tiles.append({"label": pgettext(_CTX, "Dərc olunmuşdan fərq"), "value": soft.get("moved_vs_published")})
    return tiles


def can_edit(run) -> bool:
    return run.status == RunStatus.DONE


__all__ = [
    "VIEW_GROUP",
    "VIEW_ROOM",
    "VIEW_TEACHER",
    "can_edit",
    "draft_rows",
    "events_of",
    "grid",
    "kpi_tiles",
    "options",
    "select",
    "unplaced",
]
