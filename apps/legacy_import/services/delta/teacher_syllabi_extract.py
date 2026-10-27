"""``legacy_delta_extract --teacher-syllabi`` — ``syllabi_backfill`` fazasının paketi (sahib 2026-10-27, YALNIZ OXUYUR).

Paketə düşən (Django bazasına toxunulmur):

* cari semestrin (``semestr_jurnal.is_current`` və ya ``--full-semester``) saxta / «sonra sil» olmayan jurnalları —
  yalnız başlıq (tələbə / qrup siyahısı BOŞALDILIR, xana / dərs tarixi YOXDUR);
* həmin jurnallardakı hər (müəllim, fənn) cütü üçün müəllimin BÜTÜN köhnə sillabusları (eyni fənn və ya kataloqdakı
  eyni adlı dublikat fənn) + jurnalların öz ``sillabus_id``-si — həftəlik mövzu və peyk bölmələri ilə;
* bunların müəllim / fənn / kafedra sətirləri.

``snapshot.phases = ["syllabi_backfill"]`` və ``snapshot.teacher_syllabi`` — paket adi delta fazaları ilə işlədilə
bilməz (``syllabi_backfill.check_phases``).
"""

from __future__ import annotations

from .extract import WORKER_COLUMNS, DeltaExtractor
from .resolve import subject_key
from .syllabi_backfill import PHASE, journal_pairs

#: ``bundle.SECTIONS`` + əmrin çap etdiyi bölmələr — bu paketdə boş qalanlar.
_EMPTY_SECTIONS = (
    "specialities",
    "groups",
    "students",
    "expelled_students",
    "lesson_dates",
    "points",
    "excuse_windows",
    "lesson_topics",
)


def build_teacher_syllabi_bundle(extractor: DeltaExtractor, *, snapshot: dict, semester: int) -> dict:
    x = extractor
    x.full_semesters = [int(semester)]
    journals = []
    for row in x.journals():
        row["students_id"], row["groups_id"] = "[]", "[]"
        journals.append(row)
    pairs = journal_pairs(journals)
    journals = [row for rows in pairs.values() for row in rows]
    teacher_ids = {teacher_id for teacher_id, _lesson_id in pairs}
    candidates = []
    ids = sorted(teacher_ids)
    for start in range(0, len(ids), x.chunk):
        part = ids[start : start + x.chunk]
        marks = ", ".join(["%s"] * len(part))
        candidates += x._rows(
            f"SELECT id, lesson_id, teacher_id FROM {x.src}.sillabus WHERE teacher_id IN ({marks}) ORDER BY id", part
        )
    lesson_ids = {lesson_id for _teacher_id, lesson_id in pairs} | {row["lesson_id"] for row in candidates}
    lessons = {
        row["id"]: row
        for row in x._by_ids("lessons", ("id", "name", "lesson_code", "department_id", "type"), lesson_ids)
    }

    def key(lesson_id):
        row = lessons.get(lesson_id)
        return subject_key(row.get("name")) if row else f"#{lesson_id}"

    wanted_pairs = {(teacher_id, key(lesson_id)) for teacher_id, lesson_id in pairs}
    syllabus_ids = {row["id"] for row in candidates if (row["teacher_id"], key(row["lesson_id"])) in wanted_pairs}
    syllabus_ids |= {row["sillabus_id"] for row in journals if row.get("sillabus_id")}
    syllabi = x.syllabi(syllabus_ids)
    used_lessons = {lesson_id for _teacher_id, lesson_id in pairs} | {row["lesson_id"] for row in syllabi}
    subjects = [lessons[lesson_id] for lesson_id in sorted(used_lessons) if lesson_id in lessons]
    workers = x._by_ids("workers", WORKER_COLUMNS, teacher_ids)
    department_ids = {row["department_id"] for row in workers} | {row["department_id"] for row in subjects}
    departments = x._by_ids("departments", ("id", "name", "department_id", "kollec_or_uni"), department_ids)
    periods = x._rows(f"SELECT id, name, type, is_current FROM {x.src}.semestr_jurnal ORDER BY id")
    stats = {
        "semester": int(semester),
        "journals": len(journals),
        "pairs": len(pairs),
        "teachers": len(teacher_ids),
        "syllabi": len(syllabi),
    }
    return {
        "snapshot": {**snapshot, "full_semesters": [], "phases": [PHASE], "teacher_syllabi": stats},
        **{name: [] for name in _EMPTY_SECTIONS},
        "periods": periods,
        "departments": departments,
        "subjects": subjects,
        "workers": workers,
        "journals": journals,
        "syllabi": syllabi,
    }


__all__ = ["build_teacher_syllabi_bundle"]
