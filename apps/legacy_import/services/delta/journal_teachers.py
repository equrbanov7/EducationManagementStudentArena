"""Köhnə sistemin cari semestr jurnalları → «kim hansı növü keçir» sübut faylı (sahib 2026-10-25, vakant saatlar).

Niyə ayrıca fayl (delta paketi deyil)
-------------------------------------
``legacy_delta_apply`` cari semestrin jurnallarını yeni sistemə açılış + dərs kimi köçürüb, amma dərsin MÜƏLLİMİ
(``Lesson.instructor``) boş qalıb və bir açılışa bir neçə köhnə jurnal (mühazirə bir müəllimdə, seminar
digərində) düşəndə hamısı açılışın sahibinə «yazılır». Köhnə sistemdə isə hər jurnal öz müəllimini və keçdiyi
NÖVLƏRİ (``journals.sem_muh``: 1 — mühazirə, 0/3 — seminar, 2 — laboratoriya) açıq saxlayır. Bu modul həmin
məlumatı yeni sistemin AÇARLARINA (fənn UUID-i, qrup UUID-ləri, istifadəçi id-si) çevirir — faylda AD / FİN YOXDUR.

Həll (yazmır, hesab YARATMIR):

* fənn — ``Catalog.subject_for`` (ledger → ``QKU-<id>`` kodu → tək ad);
* qrup — ``Catalog.group_for``; alt qrupdursa ana qrup da əlavə olunur (yük sətri ana qrupdadır);
* müəllim — ledger (``worker``) → kafedra dərs yükü faylının ad tutuşdurması (``chair_teacher_resolver``,
  ``apply=False`` — tapılmasa hesab yaradılmır, ``teacher_id = null`` + status).

Saxta / «sonra sil» jurnallar atılır; aktiv olmayan və dərs tarixi olmayanlar faylda qalır (bayraqla) —
qərarı :mod:`apps.workload.services.vacant_fill` verir.
"""

from __future__ import annotations

import json
import os
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from .extract import _ident, parse_id_list
from .people import worker_display
from .resolve import Catalog, ledger_map

FORMAT = "legacy-journal-teachers/1"
KIND_CODES = {"1": "lecture", "0": "seminar", "3": "seminar", "2": "lab"}


def _rows(cursor, sql: str, params=()) -> list[dict]:
    cursor.execute(sql, params)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _by_ids(cursor, src: str, table: str, columns: str, ids) -> dict:
    ids = sorted({int(value) for value in ids if value})
    out: dict = {}
    for start in range(0, len(ids), 2000):
        part = ids[start : start + 2000]
        marks = ", ".join(["%s"] * len(part))
        for row in _rows(cursor, f"SELECT {columns} FROM {src}.{_ident(table)} WHERE id IN ({marks})", part):
            out[int(row["id"])] = row
    return out


def current_semester(cursor, source: str) -> dict:
    rows = _rows(
        cursor, f"SELECT id, name FROM {_ident(source)}.semestr_jurnal WHERE is_current = '1' ORDER BY id DESC"
    )
    return rows[0] if rows else {}


def _kinds(raw) -> list[str]:
    try:
        values = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return (
        sorted({KIND_CODES[str(value)] for value in values if str(value) in KIND_CODES})
        if isinstance(values, list)
        else []
    )


class _Teachers:
    def __init__(self, organization, catalog, workers: dict):
        self.organization = organization
        self.catalog = catalog
        self.workers = workers
        self.ledger = ledger_map(organization, "worker", workers)
        self.users = django_apps.get_model("auth", "User").objects
        self._resolvers: dict = {}
        self._cache: dict = {}

    def resolve(self, legacy_id) -> tuple:
        if legacy_id not in self._cache:
            self._cache[legacy_id] = self._resolve(legacy_id)
        return self._cache[legacy_id]

    def _resolve(self, legacy_id) -> tuple:
        from apps.accounts.public import legacy_accounts

        target = self.ledger.get(str(legacy_id))
        if target and self.users.filter(pk=int(target)).exists():
            return int(target), "ledger"
        row = self.workers.get(int(legacy_id))
        display = worker_display(row) if row else ""
        if not display:
            return None, "source_missing"
        chair = self.catalog.unit_for_department(row.get("department_id"))
        key = getattr(chair, "pk", None)
        if key not in self._resolvers:
            self._resolvers[key] = legacy_accounts.chair_teacher_resolver(
                self.organization, chair, actor_user=None, apply=False
            )
        resolved, _created = legacy_accounts.teacher_resolution_statuses()
        result = self._resolvers[key].resolve(display)
        if result.status in resolved and result.user is not None and result.user.pk:
            return result.user.pk, f"matched_{result.status}"
        return None, f"unresolved_{result.status}"


def extract(cursor, *, source: str, semester: int, organization) -> dict:
    """MariaDB (yalnız oxu) + hədəf baza (yalnız oxu) → sübut faylının məzmunu (adsız)."""
    src = _ident(source)
    journals = _rows(
        cursor,
        f"SELECT id, lesson_id, teacher_id, groups_id, sem_muh, active, fake, sonra_sil FROM {src}.journals "
        "WHERE semestr = %s ORDER BY id",
        (semester,),
    )
    dates = Counter()
    ids = [row["id"] for row in journals]
    for start in range(0, len(ids), 2000):
        part = ids[start : start + 2000]
        marks = ", ".join(["%s"] * len(part))
        for row in _rows(
            cursor,
            f"SELECT journal_id, COUNT(*) AS n FROM {src}.journals_dates_added_by_teacher "
            f"WHERE journal_id IN ({marks}) GROUP BY journal_id",
            part,
        ):
            dates[int(row["journal_id"])] = int(row["n"])
    group_ids = {gid for row in journals for gid in parse_id_list(row["groups_id"])}
    subjects = _by_ids(cursor, src, "lessons", "id, name", {row["lesson_id"] for row in journals})
    groups = _by_ids(cursor, src, "groups", "id, name", group_ids)
    workers = _by_ids(
        cursor,
        src,
        "workers",
        "id, first_name, last_name, father_name, department_id",
        {r["teacher_id"] for r in journals},
    )
    catalog = Catalog(organization)
    teachers = _Teachers(organization, catalog, workers)
    stats: Counter = Counter()
    out = []
    for row in journals:
        stats["journals"] += 1
        if int(row["fake"] or 0) or int(row["sonra_sil"] or 0):
            stats["skipped_fake"] += 1
            continue
        legacy_subject = subjects.get(int(row["lesson_id"] or 0))
        subject, how = catalog.subject_for(legacy_subject) if legacy_subject else (None, "source_missing")
        stats[f"subject_{how}"] += 1
        units = []
        for gid in parse_id_list(row["groups_id"]):
            legacy_group = groups.get(gid)
            unit, ghow = catalog.group_for(legacy_group) if legacy_group else (None, "source_missing")
            stats[f"group_{ghow}"] += 1
            if unit is not None:
                units.append(unit)
                parent = catalog.units.get(unit.parent_id)
                if parent is not None and parent.unit_type == "group":
                    units.append(parent)
        if subject is None or not units:
            stats["skipped_unresolved"] += 1
            continue
        teacher_id, status = teachers.resolve(row["teacher_id"])
        stats[f"teacher_{status.split('_')[0]}"] += 1
        out.append(
            {
                "legacy_id": int(row["id"]),
                "subject_id": str(subject.pk),
                "group_ids": sorted({str(unit.pk) for unit in units}),
                "teacher_id": teacher_id,
                "teacher_status": status,
                "kinds": _kinds(row["sem_muh"]),
                "dates": dates.get(int(row["id"]), 0),
                "active": bool(int(row["active"] or 0)),
            }
        )
    stats["written"] = len(out)
    return {
        "format": FORMAT,
        "source_schema": source,
        "semester": semester,
        "extracted_at": timezone.now().isoformat(),
        "journals": out,
        "stats": dict(stats),
    }


def write(path: str, data: dict) -> None:
    target = os.path.expanduser(path)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, sort_keys=True)


__all__ = ["FORMAT", "KIND_CODES", "current_semester", "extract", "write"]
