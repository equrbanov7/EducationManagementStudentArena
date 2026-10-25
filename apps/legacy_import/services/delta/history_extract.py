"""MariaDB → TARİXİ semestrlərin (legacy 1–13) boşluq paketi (``legacy_delta_extract --history-semester``).

Niyə ayrıca bölmə (2026-10-25 auditi)
-------------------------------------
Tarixi semestrlərdə 147 435 real xana-gün yeni sistemə gəlməyib — HAMISI tələbənin həmin açılışda
qeydiyyatı (``Enrollment``) olmadığı üçün: cutover-də hesabı açılmayan tələbələr, K9 qrup uyğunsuzluğu,
karantin (qrupu silinmiş) jurnallar, jurnal siyahısında olmayan amma xanası olan tələbələr. Bunların
hamısının ortaq nişanı: ``(uniqid, tələbə)`` cütünün cutover ledger-ində (``journal_enrollment``)
``migrated`` sətri YOXDUR.

Ölçü
----
Tarixi xanalar ~4,9 mln sətirdir; paketə YALNIZ boşluq cütlərinin xanaları düşür (ledger süzgəci —
~0,3 mln sətir, gzip-də bir neçə MB). Süzgəc ledger-i hədəfdən oxuyur (yalnız oxu): əmr bunu Django
bazasından (prod NÜSXƏSİ) qurub buraya ``migrated_pairs`` kimi ötürür — bu modul yalnız SQL-dir.

Bölmə ``bundle["history"]``:

* ``semesters`` — işlənən legacy semestr id-ləri;
* ``journals`` — boşluq cütü olan real (``fake=0``, ``sonra_sil=0``) jurnallar;
* ``points`` — boşluq cütlərinin boş olmayan xanaları (əsas cədvəl + J-V7: kəsimdən əvvəlki arxiv sətri,
  əsas cədvəldə qarşılığı yoxdursa);
* ``lesson_dates`` — yalnız açılışı OLMAYAN (karantin) jurnalların dərs tarixləri;
* ``excuse_windows`` — boşluq tələbələrinin BÜTÜN üzrlü qayıb pəncərələri;
* ``fin_counts`` — boşluq tələbələrinin FİN-lərinin bütün ``students`` cədvəlindəki sayı (dublikat FİN yazılmasın);
* ``lesson_topics`` (yalnız ``topics=True``) — tarixi jurnalların dərs tarixi → sillabus mövzusu / otaq.
"""

from __future__ import annotations

from collections import Counter

from .extract import (
    GROUP_COLUMNS,
    JOURNAL_COLUMNS,
    POINT_COLUMNS,
    STUDENT_COLUMNS,
    DeltaExtractor,
    _ident,
    parse_id_list,
)

#: J-V7 (``rehearsal_journal_points_source.ARCHIVE_CUTOFF``) ilə eyni kəsim — arxivin yalnız bundan əvvəlki sətri.
ARCHIVE_CUTOFF = "2022-03-30"
POINT_CHUNK = 200
_EXAM_MONTHS = ("im", "im2")


def parse_semesters(raw) -> list[int]:
    """``"1-13"`` / ``"2,3,7"`` / ``[1, 2]`` → sıralı unikal siyahı."""

    if isinstance(raw, (list, tuple, set)):
        parts = [str(value) for value in raw]
    else:
        parts = str(raw or "").replace(" ", "").split(",")
    out: set[int] = set()
    for part in parts:
        if not part:
            continue
        if "-" in part:
            low, _sep, high = part.partition("-")
            if not (low.isdigit() and high.isdigit()) or int(low) > int(high):
                raise ValueError(f"legacy_delta_history_semesters_invalid: {part!r}")
            out.update(range(int(low), int(high) + 1))
        elif part.isdigit():
            out.add(int(part))
        else:
            raise ValueError(f"legacy_delta_history_semesters_invalid: {part!r}")
    return sorted(out)


def _real_journal(row) -> bool:
    return not (int(row.get("fake") or 0) == 1 or int(row.get("sonra_sil") or 0) == 1)


class HistoryExtractor:
    """Tarixi boşluq bölməsinin SQL-i (``DeltaExtractor``-ın kursoru və köməkçiləri üzərində)."""

    def __init__(self, extractor: DeltaExtractor, *, semesters, migrated_pairs, migrated_journals):
        self.x = extractor
        self.semesters = sorted({int(value) for value in semesters})
        self.migrated_pairs = migrated_pairs
        self.migrated_journals = migrated_journals
        self.stats: Counter = Counter()

    def journals(self) -> list[dict]:
        x = self.x
        marks = ", ".join(["%s"] * len(self.semesters))
        cols = ", ".join(_ident(column) for column in JOURNAL_COLUMNS)
        return x._rows(f"SELECT {cols} FROM {x.src}.journals WHERE semestr IN ({marks}) ORDER BY id", self.semesters)

    def _gap(self, row) -> bool:
        if not str(row.get("point") or "").strip():
            self.stats["points.blank"] += 1
            return False
        if f"{row['journal_uniqid']}:{row['student_id']}" in self.migrated_pairs:
            self.stats["points.migrated_pair"] += 1
            return False
        return True

    def points(self, uniqids) -> list[dict]:
        """Boşluq cütlərinin xanaları — kiçik dəstələrlə (bir dəstə ~100 min sətir)."""

        x = self.x
        cols = ", ".join(f"p.{_ident(column)}" for column in POINT_COLUMNS)
        archive_cols = ", ".join(f"a.{_ident(column)}" for column in POINT_COLUMNS)
        same_slot = (
            "p.journal_uniqid = a.journal_uniqid AND p.student_id = a.student_id AND p.month_id = a.month_id "
            "AND p.day_number = a.day_number AND (p.time <=> a.time)"
        )
        out: list[dict] = []
        ordered = sorted(uniqids)
        for start in range(0, len(ordered), POINT_CHUNK):
            part = ordered[start : start + POINT_CHUNK]
            marks = ", ".join(["%s"] * len(part))
            for row in x._rows(
                f"SELECT {cols} FROM {x.src}.journals_dates_points p WHERE p.journal_uniqid IN ({marks})", part
            ):
                if self._gap(row):
                    row["delta"] = "history"
                    out.append(row)
            for row in x._rows(
                f"SELECT {archive_cols} FROM {x.src}.journals_dates_points_archive a "
                f"LEFT JOIN {x.src}.journals_dates_points p ON {same_slot} "
                f"WHERE a.journal_uniqid IN ({marks}) AND p.id IS NULL AND a.added_date < %s",
                [*part, ARCHIVE_CUTOFF],
            ):
                if self._gap(row):
                    row["delta"] = "history_archive"
                    self.stats["points.archive"] += 1
                    out.append(row)
        out.sort(key=lambda row: (row["delta"], row["id"]))
        return out

    def lesson_dates(self, journal_ids) -> list[dict]:
        return self.x.lesson_dates(journal_ids) if journal_ids else []

    def excuse_windows(self, student_ids) -> list[dict]:
        ids = sorted(student_ids)
        out: list[dict] = []
        for start in range(0, len(ids), self.x.chunk):
            part = ids[start : start + self.x.chunk]
            marks = ", ".join(["%s"] * len(part))
            out += self.x._rows(
                "SELECT id, student_id, allowed_date_start, allowed_date_end "
                f"FROM {self.x.src}.allowed_qb WHERE student_id IN ({marks}) ORDER BY id",
                part,
            )
        return out

    def fin_counts(self, students) -> dict:
        from ..rehearsal_placement_phase import _legacy_fin

        wanted = {_legacy_fin(row.get("fincode")) for row in students} - {""}
        counts: Counter = Counter()
        for row in self.x._rows(f"SELECT fincode FROM {self.x.src}.students"):
            value = row.get("fincode")
            fin = _legacy_fin(value if isinstance(value, str) else None)
            if fin in wanted:
                counts[fin] += 1
        return dict(sorted(counts.items()))

    def activity(self, student_ids, periods) -> dict:
        """legacy tələbə → onun jurnalda (siyahı və ya xana) olduğu BÜTÜN dövrlərin adları (bütün semestrlər).

        ``repair_enrollments_select`` E2/E3 «hazırda oxuyur» sübutunun girişi — paketin semestr bölgüsündən asılı
        olmasın deyə bütün jurnallardan qurulur.
        """

        x = self.x
        labels = {row["id"]: str(row.get("name") or "") for row in periods}
        wanted = set(student_ids)
        out: dict = {}
        for row in x._rows(f"SELECT uniqid, semestr, students_id FROM {x.src}.journals"):
            label = labels.get(row["semestr"], "")
            for student in parse_id_list(row["students_id"]):
                if student in wanted:
                    out.setdefault(student, set()).add(label)
        ids = sorted(wanted)
        for start in range(0, len(ids), x.chunk):
            part = ids[start : start + x.chunk]
            marks = ", ".join(["%s"] * len(part))
            for row in x._rows(
                f"SELECT DISTINCT p.student_id, j.semestr FROM {x.src}.journals_dates_points p "
                f"JOIN {x.src}.journals j ON j.uniqid = p.journal_uniqid WHERE p.student_id IN ({marks})",
                part,
            ):
                out.setdefault(row["student_id"], set()).add(labels.get(row["semestr"], ""))
        return {str(student): sorted(values - {""}) for student, values in sorted(out.items())}

    def lesson_topics(self, journals) -> list[dict]:
        """Tarixi jurnalların (açılışı olan) dərs tarixi → mövzu/otaq; mövzusu da, otağı da boş sətir düşmür."""

        semestr = {row["uniqid"]: row["semestr"] for row in journals}
        ids = sorted(row["id"] for row in journals if row["uniqid"] in self.migrated_journals)
        out = []
        for row in self.x.lesson_topics(ids):
            has_topic = bool(str(row.get("movzu") or "").strip())
            has_room = str(row.get("room") or "0").strip() not in ("", "0")
            if not (has_topic or has_room):
                self.stats["topics.blank"] += 1
                continue
            row["semestr"] = semestr.get(row["journal_uniqid"])
            out.append(row)
        return out


def ledger_sets(organization) -> tuple[set, set]:
    """Hədəfin (prod NÜSXƏSİ, yalnız oxu) cutover ledger-i: ``migrated`` cütlər + açılışı köçmüş jurnallar."""

    from .resolve import ledger_map

    pairs = set(ledger_map(organization, "journal_enrollment"))
    journals = {str(key).partition(":")[0] for key in ledger_map(organization, "course_offering")}
    return pairs, journals


def build_history_bundle(
    extractor: DeltaExtractor,
    *,
    snapshot: dict,
    semesters,
    migrated_pairs,
    migrated_journals,
    gaps: bool = True,
    topics: bool = False,
) -> dict:
    """Tam paket (delta ``SECTIONS`` + ``history``); delta bölmələri yalnız istinad üçün doldurulur.

    ``gaps`` → ``history`` fazasının bölmələri, ``topics`` → ``history_topics``-in. Yaddaş üçün ikisi ayrı
    paketlərdə, boşluqlar isə semestr dəstələri ilə qurula bilər — hesab qərarının «fəaliyyət» sübutu
    (``activity``) BÜTÜN jurnallardan hesablanır, ona görə bölgüdən asılı deyil.
    """

    x = extractor
    h = HistoryExtractor(x, semesters=semesters, migrated_pairs=migrated_pairs, migrated_journals=migrated_journals)
    all_journals = h.journals()
    real = [row for row in all_journals if _real_journal(row)]
    h.stats["journals.fake_or_deleted_later"] = len(all_journals) - len(real)
    points = h.points({row["uniqid"] for row in real if row["uniqid"]}) if gaps else []
    gap_journals = {row["journal_uniqid"] for row in points}
    journals = [row for row in real if row["uniqid"] in gap_journals]
    student_ids = {row["student_id"] for row in points}
    quarantined = {row["id"] for row in journals if row["uniqid"] not in migrated_journals}
    students = x._by_ids("students", STUDENT_COLUMNS, student_ids)
    for row in students:
        row["is_new"] = False
    group_ids = {row["group_id"] for row in students}
    subject_ids = set()
    for row in journals:
        group_ids.update(parse_id_list(row["groups_id"]))
        subject_ids.add(row["lesson_id"])
    groups = x._by_ids("groups", GROUP_COLUMNS, group_ids)
    for row in groups:
        row["is_new"] = False
    speciality_ids = {row["speciality_id"] for row in groups} | {row["speciality_id"] for row in students}
    specialities = x._by_ids("speciality", ("id", "department_id", "name", "speciality_code"), speciality_ids)
    subjects = x._by_ids("lessons", ("id", "name", "lesson_code", "department_id", "type"), subject_ids)
    department_ids = (
        {row["department_id"] for row in specialities}
        | {row["department_id"] for row in groups}
        | {row["department_id"] for row in subjects}
    )
    departments = x._by_ids("departments", ("id", "name", "department_id", "kollec_or_uni"), department_ids)
    periods = x._rows(f"SELECT id, name, type, is_current FROM {x.src}.semestr_jurnal ORDER BY id")
    history = {
        "semesters": h.semesters,
        "journals": journals,
        "points": points,
        "lesson_dates": h.lesson_dates(quarantined),
        "excuse_windows": h.excuse_windows(student_ids) if student_ids else [],
        "fin_counts": h.fin_counts(students),
        "activity": h.activity(student_ids, periods) if student_ids else {},
        "lesson_topics": h.lesson_topics(real) if topics else [],
    }
    h.stats["points.exam"] = sum(1 for row in points if row["month_id"] in _EXAM_MONTHS)
    h.stats["pairs"] = len({(row["journal_uniqid"], row["student_id"]) for row in points})
    h.stats["journals.quarantined"] = len(quarantined)
    history["stats"] = dict(sorted(h.stats.items()))
    return {
        "snapshot": {**snapshot, "full_semesters": [], "history_semesters": h.semesters},
        "periods": periods,
        "departments": departments,
        "specialities": specialities,
        "groups": groups,
        "subjects": subjects,
        "workers": [],
        "students": students,
        "journals": [],
        "lesson_dates": [],
        "points": [],
        "excuse_windows": [],
        "syllabi": [],
        "lesson_topics": [],
        "history": history,
    }


__all__ = ["ARCHIVE_CUTOFF", "HistoryExtractor", "build_history_bundle", "ledger_sets", "parse_semesters"]
