"""«Bir fənn = bir kart» — «Yük bölgüsü» kartları (sahib 2026-11-09).

Sahib: «Xətti cəbr və riyazi analiz 4 ayrı kartdır … eyni fənn, eyni kredit, eyni semestr — bir yük olsun, qruplar
içində bölünsün». Sətirlər (rəsmi Excel sətri, ``TeachingTaskRow``) və saatlar DƏYİŞMİR — kart DƏRC QATIDIR: eyni
tapşırıq + fənn + mövsüm/semestr + kredit sətirləri bir ailədir (:func:`family_key`), səhifələmə ailə üzrədir.

Kartın məzmunu:

* **mühazirə axınları** — aparıcı sətir + ``patok_lead`` ilə ona bağlı tərəfdaşlar (:mod:`.patok`); bağsız tərəfdaş
  «aparıcı seçilməyib» xəbərdarlığı ilə ayrıca; mühazirə saatı axın başına BİR dəfə (sahibin qaydası);
* **seminar / laboratoriya xətləri** — qrup başına: tək qruplu sətir → qrupun özü; çox qruplu sətirdə bölgünün
  struktur qrup bağı (``TeacherAssignment.group``) və ya qeyd parse-i qrupu verir, qeydsiz bölgü «bütün qruplar
  birlikdə» xəttidir (seminar patoku — ``subgroup_count ≤ 1``); jurnalın alt bölmələri (Lab-1/Lab-2, 234 K1/K2)
  registrar fasadından gəlir;
* **digər fəaliyyətlər** (məsləhət, imtahan …) — sətir üzrə köhnə zolaq;
* ``rows`` — sətirlərin tam payload-u (redaktə / silmə / köhnə bölgü modalı).

Sorğu sayı sətir sayından asılı DEYİL: açarlar üçün yüngül ``values`` sorğusu, seçilmiş ailələrin sətirləri bir
sorğu (+ prefetch), balans bir GROUP BY, alt bölmələr toplu.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from types import SimpleNamespace

from ..constants import Activity, RowKind
from .offering_rules import per_group_hours
from .offering_shares import _assignment_group
from .patok import is_partner, partner_lectures
from .queries import _ACTIVITY_LABELS, MAX_PAGE_LIMIT, _label, _serialize, base_rows_queryset, task_rows

TEACHING = (str(Activity.LECTURE), str(Activity.SEMINAR), str(Activity.LAB))
_TOTAL = {"seminar": "seminar_total", "lab": "lab_total"}
_CREDIT_RE = re.compile(r"\d+")


def _credit_key(row) -> int:
    value = int(getattr(row, "credits_value", 0) or 0)
    if value:
        return value
    found = _CREDIT_RE.search(str(getattr(row, "credits", "") or ""))
    return int(found.group()) if found else 0


def family_key(row) -> tuple:
    """Ailə açarı: tapşırıq + sətir növü + fənn + mövsüm/semestr + kredit; intensiv sətir həmişə ayrıca."""
    if row.row_kind == RowKind.INTENSIVE:
        return ("intensive", str(row.pk))
    subject = str(row.subject_id) if row.subject_id else (getattr(row, "subject_text", "") or "").strip().casefold()
    return (str(row.task_id), row.row_kind, subject, row.season, str(row.period_id or ""), _credit_key(row))


def cards_page(
    task,
    *,
    season: str = "",
    search: str = "",
    teacher: str = "",
    status: str = "",
    activity: str = "",
    offset: int = 0,
    limit: int = 0,
    focus_row=None,
) -> dict:
    """Süzgəcə uyğun sətirlərin AİLƏ üzrə ``offset`` / ``limit`` dilimi — ``rows_page`` ilə eyni müqavilə + ``cards``."""
    queryset = task_rows(task, season=season, search=search, teacher=teacher, status=status, activity=activity)
    light = queryset.values(
        "pk", "task_id", "row_kind", "subject_id", "subject_text", "season", "period_id", "credits_value", "credits"
    )
    families: OrderedDict = OrderedDict()
    for item in light:
        families.setdefault(family_key(SimpleNamespace(**item)), []).append(item["pk"])
    keys = list(families)
    total = len(keys)
    offset = max(int(offset or 0), 0)
    limit = min(max(int(limit or 0), 0), MAX_PAGE_LIMIT)
    if focus_row and limit and offset == 0:
        position = next((i for i, key in enumerate(keys) if focus_row in families[key]), None)
        if position is not None:
            limit = min(max(limit, position + 1), MAX_PAGE_LIMIT)
    chosen = keys[offset : offset + limit] if limit else []
    pks = [pk for key in chosen for pk in families[key]]
    rows = list(base_rows_queryset(task).filter(pk__in=pks)) if pks else []
    payloads, rows, balance = _serialize(task, rows)
    by_pk = {row.pk: row for row in rows}
    payload_by_pk = {payload["id"]: payload for payload in payloads}
    cards = []
    if rows:
        patok = partner_lectures(rows)
        sections = _sections(task, rows, payload_by_pk)
        for key in chosen:
            family_rows = [by_pk[pk] for pk in families[key] if pk in by_pk]
            if family_rows:
                cards.append(_card(family_rows, payload_by_pk, balance, patok, sections))
    next_offset = offset + len(chosen)
    return {
        "cards": cards,
        "rows": payloads,
        "total": total,
        "next_offset": next_offset,
        "has_more": next_offset < total,
    }


# ── kart ────────────────────────────────────────────────────────────────────


def _sections(task, rows, payload_by_pk) -> dict:
    """``{(fənn, dövr, qrup): {"lab": [...], "seminar": [...]}}`` — jurnalın alt bölmələri (registrar fasadı)."""
    from apps.registrar.public import offering_section_choices

    keys = set()
    for row in rows:
        if not (row.subject_id and row.period_id) or row.row_kind != RowKind.TEACHING:
            continue
        for group in payload_by_pk[str(row.pk)]["groups"]:
            keys.add((row.subject_id, row.period_id, _uuid(group["id"])))
    if not keys:
        return {}
    found = offering_section_choices(organization=task.organization, keys=keys)
    return {(str(k[0]), str(k[1]), str(k[2])): v for k, v in found.items()}


def _uuid(value):
    from core.http_ids import parse_uuid

    return parse_uuid(value)


def _entry(payload_assignment) -> dict:
    keys = ("id", "teacher_id", "teacher_name", "hours", "is_vacant", "is_hourly_paid", "groups_note", "sub_number")
    return {key: payload_assignment.get(key) for key in keys}


def _card(rows, payload_by_pk, balance, patok, sections) -> dict:
    first = rows[0]
    first_payload = payload_by_pk[str(first.pk)]
    groups, seen = [], set()
    for row in rows:
        for group in payload_by_pk[str(row.pk)]["groups"]:
            if group["id"] not in seen:
                seen.add(group["id"])
                groups.append({**group, "row_id": str(row.pk)})
    specialties = []
    for row in rows:
        name = payload_by_pk[str(row.pk)]["specialty"]
        if name and name not in specialties:
            specialties.append(name)
    credits = next((payload_by_pk[str(row.pk)]["credits"] for row in rows if payload_by_pk[str(row.pk)]["credits"]), "")
    warnings: list = []
    lecture = _lecture(rows, payload_by_pk, balance, patok, warnings)
    seminar = _kind_lines(rows, "seminar", payload_by_pk, balance, sections)
    lab = _kind_lines(rows, "lab", payload_by_pk, balance, sections)
    return {
        "key": "|".join(str(part) for part in family_key(first)),
        "id": str(first.pk),
        "row_ids": [str(row.pk) for row in rows],
        "subject": first_payload["subject"],
        "subject_id": first_payload["subject_id"],
        "row_kind": first.row_kind,
        "season": first.season,
        "season_label": first_payload["season_label"],
        "period_label": first_payload["period_label"],
        "credits": credits,
        "specialties": specialties,
        "groups": groups,
        "total_hours": sum(int(row.total_hours or 0) for row in rows),
        "student_count": sum(int(row.student_count or 0) for row in rows),
        "is_amend_target": any(payload_by_pk[str(row.pk)]["is_amend_target"] for row in rows),
        "teaching_complete": all(payload_by_pk[str(row.pk)]["teaching_complete"] for row in rows),
        "intensive": first_payload["intensive"] if len(rows) == 1 else None,
        "lecture": lecture,
        "seminar": seminar,
        "lab": lab,
        "other": _other(rows, payload_by_pk, balance),
        "warnings": warnings,
        "rows": [payload_by_pk[str(row.pk)] for row in rows],
    }


def _lecture(rows, payload_by_pk, balance, patok, warnings) -> dict:
    """Axınlar: aparıcı sətir + ona bağlı tərəfdaşlar; bağsız tərəfdaş ayrıca (xəbərdarlıqla)."""
    streams: dict = OrderedDict()
    pks = {row.pk for row in rows}
    for row in rows:
        if is_partner(row) or (int(row.lecture_plan or 0) <= 0 and int(row.lecture_total or 0) <= 0):
            continue
        streams[row.pk] = _stream(row, payload_by_pk, balance)
    orphans = []
    for row in rows:
        if not is_partner(row):
            continue
        info = patok.get(row.pk) or {}
        lead_pk = _uuid(info.get("lead_id")) if info.get("lead_id") else None
        if lead_pk in streams and lead_pk in pks:
            streams[lead_pk]["row_ids"].append(str(row.pk))
            streams[lead_pk]["groups"] += payload_by_pk[str(row.pk)]["groups"]
            streams[lead_pk]["linked"] = streams[lead_pk]["linked"] and bool(info.get("linked"))
            continue
        orphan = _stream(row, payload_by_pk, balance)
        orphan.update(
            {
                "hours": int(row.lecture_plan or 0),
                "orphan": True,
                "warning": "foreign_lead" if lead_pk else "no_lead",
                "lead_teacher_name": info.get("teacher_name") or "",
            }
        )
        orphans.append(orphan)
    if orphans:
        warnings.append("patok_unlinked")
    items = list(streams.values()) + orphans
    plan = max((int(row.lecture_plan or 0) for row in rows), default=0)
    without = [
        group
        for row in rows
        if int(row.lecture_plan or 0) <= 0 and int(row.lecture_total or 0) <= 0
        for group in payload_by_pk[str(row.pk)]["groups"]
    ]
    return {
        "plan": plan,
        "streams": items,
        "load_hours": sum(item["hours"] for item in items if not item.get("orphan")),
        "without_groups": without,
    }


def _stream(lead, payload_by_pk, balance) -> dict:
    payload = payload_by_pk[str(lead.pk)]
    info = (balance.get(str(lead.pk)) or {}).get("activities", {}).get("lecture") or {}
    entries = [_entry(a) for a in payload["assignments"] if a["activity"] == "lecture"]
    union = max(int(lead.union_count or 1), 1)
    return {
        "lead_row_id": str(lead.pk),
        "row_ids": [str(lead.pk)],
        "groups": list(payload["groups"]),
        "plan": int(lead.lecture_plan or 0),
        "hours": int(lead.lecture_total or 0),
        "union_count": union,
        "assigned": int(info.get("assigned", 0)),
        "remaining": int(info.get("remaining", 0)),
        "is_complete": bool(info.get("is_complete", not info)),
        "entries": entries,
        "linked": True,
        "orphan": False,
        "warning": "",
    }


def _kind_lines(rows, kind, payload_by_pk, balance, sections) -> dict:
    """Seminar / laboratoriya: qrup başına xətt (``row_id`` + ``group_id``), çox qruplu sətirdə ortaq xətt."""
    lines: list = []
    label = _label(_ACTIVITY_LABELS, kind)
    plan = 0
    row_totals: dict = {}  # sətir cəmi BİR dəfə (çox qruplu sətrin xətləri eyni cəmi daşıyır)
    for row in rows:
        payload = payload_by_pk[str(row.pk)]
        total = int(getattr(row, _TOTAL[kind], 0) or 0)
        per_group = per_group_hours(row)[kind]
        info = (balance.get(str(row.pk)) or {}).get("activities", {}).get(kind) or {}
        assignments = [a for a in row.assignments.all() if a.activity == kind]
        if total <= 0 and not assignments and per_group <= 0:
            continue
        plan = max(plan, per_group)
        row_totals[row.pk] = total
        groups = payload["groups"]
        entries_by_id = {a["id"]: _entry(a) for a in payload["assignments"] if a["activity"] == kind}
        base = {
            "row_id": str(row.pk),
            "plan": per_group,
            "total": total,
            "assigned": int(info.get("assigned", 0)),
            "remaining": int(info.get("remaining", 0)),
            "is_complete": bool(info.get("is_complete", total <= 0)),
            "joint_elsewhere": total <= 0 and per_group > 0 and not assignments,
        }
        if len(groups) <= 1:
            group = groups[0] if groups else None
            lines.append(
                {
                    **base,
                    "group_id": group["id"] if group else "",
                    "label": group["name"] if group else payload["groups_text"] or "—",
                    "joint": False,
                    "entries": [entries_by_id[str(a.pk)] for a in assignments if str(a.pk) in entries_by_id],
                    "sections": _section_options(sections, row, group, kind),
                }
            )
            continue
        row_groups = list(row.groups.all())
        per_group_entries: dict = {group["id"]: [] for group in groups}
        shared, unclear = [], []
        for assignment in assignments:
            entry = entries_by_id.get(str(assignment.pk))
            if entry is None:
                continue
            matched = [g for g in row_groups if _assignment_group(assignment, row, g) is True]
            verdicts = {_assignment_group(assignment, row, g) for g in row_groups}
            if verdicts == {None}:
                unclear.append(entry)
            elif len(matched) == len(row_groups):
                shared.append(entry)
            elif len(matched) == 1:
                bucket = per_group_entries.get(_alias_id(matched[0], groups))
                (bucket if bucket is not None else shared).append(entry)
            else:
                shared.append({**entry, "partial": True})
        joint = int(row.subgroup_count or 1) <= 1
        if joint:
            lines.append(
                {
                    **base,
                    "group_id": "",
                    "label": " · ".join(g["name"] for g in groups),
                    "joint": True,
                    "entries": shared + unclear + [e for items in per_group_entries.values() for e in items],
                    "sections": [],
                }
            )
            continue
        for group in groups:
            lines.append(
                {
                    **base,
                    "group_id": group["id"],
                    "label": group["name"],
                    "joint": False,
                    "entries": per_group_entries[group["id"]],
                    "sections": _section_options(sections, row, group, kind),
                }
            )
        if shared or unclear:
            lines.append(
                {
                    **base,
                    "group_id": "",
                    "label": " · ".join(g["name"] for g in groups),
                    "joint": False,
                    "shared": True,
                    "entries": shared + [{**e, "unclear": True} for e in unclear],
                    "sections": [],
                }
            )
    return {
        "label": str(label),
        "plan": plan,
        "lines": lines,
        "total": sum(row_totals.values()),
    }


def _alias_id(group, payload_groups) -> str:
    """Fiziki qrup → payload-dakı (alias tətbiq olunmuş) id; tapılmasa fiziki id."""
    ids = {g["id"] for g in payload_groups}
    pk = str(group.pk)
    return pk if pk in ids else next(iter(ids), pk)


def _section_options(sections, row, group, kind) -> list:
    if group is None or not (row.subject_id and row.period_id):
        return []
    found = sections.get((str(row.subject_id), str(row.period_id), group["id"])) or {}
    return list(found.get(kind) or [])


def _other(rows, payload_by_pk, balance) -> list:
    items = []
    for row in rows:
        payload = payload_by_pk[str(row.pk)]
        activities = (balance.get(str(row.pk)) or {}).get("activities", {})
        for key, info in activities.items():
            if key in TEACHING:
                continue
            items.append(
                {
                    "row_id": str(row.pk),
                    "activity": key,
                    "label": str(_label(_ACTIVITY_LABELS, key)),
                    **{k: info[k] for k in ("total", "assigned", "remaining", "is_complete")},
                    "entries": [_entry(a) for a in payload["assignments"] if a["activity"] == key],
                }
            )
    return items


__all__ = ["cards_page", "family_key"]
