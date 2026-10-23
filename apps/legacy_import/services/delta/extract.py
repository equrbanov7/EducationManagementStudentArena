"""MariaDB (köhnə sistem) → delta paketi.

İki sxem oxunur (eyni serverdə, ikisi də YALNIZ OXUNUR):

* ``source`` — yeni snapshot (məs. 2026-10-21 dump-ı);
* ``baseline`` — cutover-in mənbə snapshot-u (2026-08-17). Verilməyibsə «tam semestr»lərdən
  başqa heç nə götürülmür.

Paketə düşən:

* **tam semestrlər** — baseline-da jurnalı OLMAYAN semestrlər (və ya ``full_semesters`` açıq verilib):
  bütün jurnallar, dərs tarixləri, bütün xanalar;
* **köhnə semestrlərin deltası** — baseline-dan sonra YARANAN və ya DƏYİŞƏN xanalar (bal, im, im2 …);
* bunların istinad etdiyi tələbə / işçi / qrup / ixtisas / kafedra / fənn sətirləri + yeni/dəyişənlər;
* tam semestr jurnallarının sillabusları + baseline-dan sonra yaranan/dəyişən sillabuslar.

Şəxsi sütunlardan YALNIZ tutuşdurma üçün lazım olanlar seçilir (ad, ata adı, FİN, doğum tarixi, cins).
Parol, telefon, e-poçt, kart, telegram SEÇİLMİR.
"""

from __future__ import annotations

import datetime
import json

from ..syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS

STUDENT_COLUMNS = (
    "id",
    "first_name",
    "last_name",
    "father_name",
    "fincode",
    "sex",
    "gender",
    "birthday",
    "group_id",
    "speciality_id",
    "entry_year",
    "azadedildi",
    "education_level",
    "education_type",
    "payment_type",
)
STUDENT_DIFF_COLUMNS = ("group_id", "azadedildi", "first_name", "last_name", "father_name", "fincode")
WORKER_COLUMNS = (
    "id",
    "first_name",
    "last_name",
    "father_name",
    "department_id",
    "teacher_type",
    "inzibati",
    "kollec_or_uni",
)
GROUP_COLUMNS = (
    "id",
    "name",
    "speciality_id",
    "department_id",
    "start_year",
    "eyani_qiyabi",
    "bak_or_mag",
    "sector",
    "kollec_or_uni",
)
JOURNAL_COLUMNS = (
    "id",
    "uniqid",
    "lesson_id",
    "teacher_id",
    "groups_id",
    "students_id",
    "semestr",
    "fake",
    "sonra_sil",
    "active",
    "fenn_saati",
    "kredit",
    "sillabus_id",
)
POINT_COLUMNS = (
    "id",
    "journal_uniqid",
    "month_id",
    "day_number",
    "student_id",
    "point",
    "time",
    "excusable",
    "sem_muh",
    "lab",
    "update_counter",
    "updated_at",
)
#: Dəyişiklik müqayisəsi bu sütunlarla aparılır (``updated_at``/``ga`` səs-küydür).
POINT_DIFF_COLUMNS = (
    "journal_uniqid",
    "month_id",
    "day_number",
    "student_id",
    "point",
    "time",
    "excusable",
    "sem_muh",
    "lab",
)
SYLLABUS_COLUMNS = ("id", "uniqid", "lesson_id", "teacher_id", "ders_saati", "language", "active")
WEEK_COLUMNS = ("id", "uniqid", "movzu", "muh_saat", "sem_saat", "praktiki_saat", "lab_saat", "qeyd")


def _ident(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"legacy_delta_identifier_invalid: {name!r}")
    return f"`{name}`"


def _json_value(value):
    if isinstance(value, datetime.timedelta):
        seconds = int(value.total_seconds())
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}" if 0 <= seconds < 86400 else ""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def parse_id_list(raw) -> list[int]:
    """``journals.groups_id`` / ``students_id`` JSON massivi → ``[int]``; pozuqsa boş siyahı."""

    try:
        values = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    out = []
    for value in values:
        text = str(value).strip()
        if text.isdigit():
            out.append(int(text))
    return out


class DeltaExtractor:
    """Bir MariaDB bağlantısı üzərində (``cursor``) paket bölmələrini yığır."""

    def __init__(self, cursor, *, source: str, baseline: str = "", full_semesters=(), chunk: int = 5000):
        self.cur = cursor
        self.src = _ident(source)
        self.base = _ident(baseline) if baseline else ""
        self.full_semesters = sorted({int(value) for value in full_semesters})
        self.chunk = chunk
        self.stats: dict = {}

    # ── köməkçilər ────────────────────────────────────────────────────────
    def _rows(self, sql: str, params=()) -> list[dict]:
        self.cur.execute(sql, params)
        names = [column[0] for column in self.cur.description]
        return [{name: _json_value(value) for name, value in zip(names, row)} for row in self.cur.fetchall()]

    def _by_ids(self, table: str, columns, ids) -> list[dict]:
        ids = sorted({int(value) for value in ids if value})
        cols = ", ".join(_ident(column) for column in columns)
        out: list[dict] = []
        for start in range(0, len(ids), self.chunk):
            part = ids[start : start + self.chunk]
            marks = ", ".join(["%s"] * len(part))
            out += self._rows(f"SELECT {cols} FROM {self.src}.{_ident(table)} WHERE id IN ({marks}) ORDER BY id", part)
        return out

    def _new_or_changed(self, table: str, columns) -> tuple[set, set]:
        """Baseline-a görə YENİ və DƏYİŞƏN id-lər (baseline yoxdursa boş)."""

        if not self.base:
            return set(), set()
        table_sql = _ident(table)
        new = {
            row["id"]
            for row in self._rows(
                f"SELECT n.id FROM {self.src}.{table_sql} n LEFT JOIN {self.base}.{table_sql} o ON o.id = n.id "
                "WHERE o.id IS NULL"
            )
        }
        same = " AND ".join(f"n.{_ident(column)} <=> o.{_ident(column)}" for column in columns)
        changed = {
            row["id"]
            for row in self._rows(
                f"SELECT n.id FROM {self.src}.{table_sql} n JOIN {self.base}.{table_sql} o ON o.id = n.id "
                f"WHERE NOT ({same})"
            )
        }
        return new, changed

    # ── bölmələr ──────────────────────────────────────────────────────────
    def resolve_full_semesters(self) -> list[int]:
        if self.full_semesters or not self.base:
            return self.full_semesters
        rows = self._rows(
            f"SELECT DISTINCT n.semestr FROM {self.src}.journals n LEFT JOIN {self.base}.journals o ON o.id = n.id "
            "WHERE o.id IS NULL ORDER BY n.semestr"
        )
        self.full_semesters = [int(row["semestr"]) for row in rows]
        return self.full_semesters

    def journals(self) -> list[dict]:
        if not self.full_semesters:
            return []
        marks = ", ".join(["%s"] * len(self.full_semesters))
        cols = ", ".join(_ident(column) for column in JOURNAL_COLUMNS)
        return self._rows(
            f"SELECT {cols} FROM {self.src}.journals WHERE semestr IN ({marks}) ORDER BY id", self.full_semesters
        )

    def lesson_dates(self, journal_ids) -> list[dict]:
        ids = sorted(journal_ids)
        out: list[dict] = []
        for start in range(0, len(ids), self.chunk):
            part = ids[start : start + self.chunk]
            marks = ", ".join(["%s"] * len(part))
            out += self._rows(
                "SELECT id, journal_id, month, day, time, sem_muh "
                f"FROM {self.src}.journals_dates_added_by_teacher WHERE journal_id IN ({marks}) ORDER BY id",
                part,
            )
        return out

    def points(self, full_uniqids) -> list[dict]:
        cols = ", ".join(f"p.{_ident(column)}" for column in POINT_COLUMNS)
        out: list[dict] = []
        uniqids = sorted(full_uniqids)
        for start in range(0, len(uniqids), self.chunk):
            part = uniqids[start : start + self.chunk]
            marks = ", ".join(["%s"] * len(part))
            for row in self._rows(
                f"SELECT {cols} FROM {self.src}.journals_dates_points p WHERE p.journal_uniqid IN ({marks})", part
            ):
                row["delta"] = "full"
                out.append(row)
        if self.base:
            seen = set(full_uniqids)
            same = " AND ".join(f"p.{_ident(column)} <=> o.{_ident(column)}" for column in POINT_DIFF_COLUMNS)
            for row in self._rows(
                f"SELECT {cols}, (o.id IS NULL) AS is_new FROM {self.src}.journals_dates_points p "
                f"LEFT JOIN {self.base}.journals_dates_points o ON o.id = p.id "
                f"WHERE o.id IS NULL OR NOT ({same})"
            ):
                if row["journal_uniqid"] in seen:
                    continue
                row["delta"] = "new" if row.pop("is_new") else "changed"
                out.append(row)
        out.sort(key=lambda row: row["id"])
        return out

    def excuse_windows(self, student_ids, since: str) -> list[dict]:
        rows = self._rows(
            "SELECT id, student_id, allowed_date_start, allowed_date_end "
            f"FROM {self.src}.allowed_qb WHERE allowed_date_end >= %s ORDER BY id",
            [since],
        )
        wanted = set(student_ids)
        return [row for row in rows if row["student_id"] in wanted]

    def students(self, referenced) -> list[dict]:
        new, changed = self._new_or_changed("students", STUDENT_DIFF_COLUMNS)
        rows = self._by_ids("students", STUDENT_COLUMNS, set(referenced) | new | changed)
        baseline = {}
        if self.base and changed:
            cols = ", ".join(_ident(column) for column in ("id", *STUDENT_DIFF_COLUMNS))
            ids = sorted(changed)
            marks = ", ".join(["%s"] * len(ids))
            baseline = {
                row["id"]: row
                for row in self._rows(f"SELECT {cols} FROM {self.base}.students WHERE id IN ({marks})", ids)
            }
        for row in rows:
            row["is_new"] = row["id"] in new
            if row["id"] in baseline:
                row["baseline"] = {key: value for key, value in baseline[row["id"]].items() if key != "id"}
        return rows

    def syllabi(self, referenced_ids) -> list[dict]:
        new, changed = self._new_or_changed("sillabus", SYLLABUS_COLUMNS[1:])
        headers = self._by_ids("sillabus", SYLLABUS_COLUMNS, set(referenced_ids) | new | changed)
        uniqids = sorted({row["uniqid"] for row in headers if row["uniqid"]})
        week: dict = {}
        sections: dict = {}
        for start in range(0, len(uniqids), self.chunk):
            part = uniqids[start : start + self.chunk]
            marks = ", ".join(["%s"] * len(part))
            cols = ", ".join(_ident(column) for column in WEEK_COLUMNS)
            for row in self._rows(
                f"SELECT {cols} FROM {self.src}.sillabus_sem_muh WHERE uniqid IN ({marks}) ORDER BY id", part
            ):
                week.setdefault(row["uniqid"], []).append(row)
            for table in SYLLABUS_SECTION_CONTRACTS:
                for row in self._rows(
                    f"SELECT id, uniqid, name FROM {self.src}.{_ident(table)} WHERE uniqid IN ({marks}) ORDER BY id",
                    part,
                ):
                    sections.setdefault(row["uniqid"], {}).setdefault(table, []).append([row["id"], row["name"]])
        for row in headers:
            row["is_new"] = row["id"] in new
            row["is_changed"] = row["id"] in changed
            row["week"] = week.get(row["uniqid"], [])
            row["sections"] = sections.get(row["uniqid"], {})
        return headers


def build_bundle(extractor: DeltaExtractor, *, snapshot: dict, since: str) -> dict:
    """Bütün bölmələri bir paketdə yığ (saf orkestrasiya — SQL ``DeltaExtractor``-dadır)."""

    x = extractor
    full = x.resolve_full_semesters()
    journals = x.journals()
    full_uniqids = {row["uniqid"] for row in journals if row["uniqid"]}
    lesson_dates = x.lesson_dates({row["id"] for row in journals})
    points = x.points(full_uniqids)
    student_ids = {row["student_id"] for row in points}
    group_ids, teacher_ids, subject_ids, syllabus_ids = set(), set(), set(), set()
    for row in journals:
        student_ids.update(parse_id_list(row["students_id"]))
        group_ids.update(parse_id_list(row["groups_id"]))
        teacher_ids.add(row["teacher_id"])
        subject_ids.add(row["lesson_id"])
        if row["sillabus_id"]:
            syllabus_ids.add(row["sillabus_id"])
    students = x.students(student_ids)
    syllabi = x.syllabi(syllabus_ids)
    for row in students:
        group_ids.add(row["group_id"])
        if row.get("baseline"):
            group_ids.add(row["baseline"].get("group_id"))
    for row in syllabi:
        teacher_ids.add(row["teacher_id"])
        subject_ids.add(row["lesson_id"])
    new_workers, _changed = x._new_or_changed("workers", ("first_name", "last_name", "father_name"))
    new_groups, _changed = x._new_or_changed("groups", ("name",))
    workers = x._by_ids("workers", WORKER_COLUMNS, teacher_ids | new_workers)
    groups = x._by_ids("groups", GROUP_COLUMNS, group_ids | new_groups)
    for row in groups:
        row["is_new"] = row["id"] in new_groups
    speciality_ids = {row["speciality_id"] for row in groups} | {row["speciality_id"] for row in students}
    specialities = x._by_ids("speciality", ("id", "department_id", "name", "speciality_code"), speciality_ids)
    department_ids = (
        {row["department_id"] for row in specialities}
        | {row["department_id"] for row in workers}
        | {row["department_id"] for row in groups}
    )
    subjects = x._by_ids("lessons", ("id", "name", "lesson_code", "department_id", "type"), subject_ids)
    department_ids |= {row["department_id"] for row in subjects}
    departments = x._by_ids("departments", ("id", "name", "department_id", "kollec_or_uni"), department_ids)
    periods = x._rows(f"SELECT id, name, type, is_current FROM {x.src}.semestr_jurnal ORDER BY id")
    return {
        "snapshot": {**snapshot, "full_semesters": full, "since": since},
        "periods": periods,
        "departments": departments,
        "specialities": specialities,
        "groups": groups,
        "subjects": subjects,
        "workers": workers,
        "students": students,
        "journals": journals,
        "lesson_dates": lesson_dates,
        "points": points,
        "excuse_windows": x.excuse_windows({row["id"] for row in students}, since),
        "syllabi": syllabi,
    }


__all__ = ["DeltaExtractor", "build_bundle", "parse_id_list"]
