"""``legacy_delta_extract --official-entry`` — ``official_entry`` fazasının paketi (SYS-1, YALNIZ OXUYUR).

Rəsmi vərəqdə jurnal id-si və semestr YOXDUR — yalnız qrup id-si (``<table data-id>``), fənn adı, müəllim adı,
seçilmiş dərs saatı və tələbə sətirləri var. Vərəq cədvəli köhnə jurnal AİLƏSİNƏ (``parent_id`` ilə bölünmüş
mühazirə + seminar jurnalları bir ailədir) belə bağlanır:

1. namizədlər — fənni (``lessons.name``, qatlanmış) eyni olan, saxta / «sonra sil» olmayan jurnal ailələri:
   əvvəl qrupu ``groups_id``-də olanlar; belə ailə yoxdursa (qrup sonradan dəyişib / birləşmiş qrup — ~70 %
   uyğunsuzluğun səbəbi) vərəqdəki tələbələrdən ən azı birini ``students_id``-də saxlayanlar;
2. ən yaxşı ailə — açar ``(imtahan uyğunluğu, qrup uyğunluğu, müəllim uyğunluğu, saat uyğunluğu, export-dan əvvəl
   yaradılıb, ortaq tələbə sayı)``: vərəqdəki ``İmtahan`` / ``T.imtahan`` ailənin ``im`` / ``im2`` xanası ilə neçə
   tələbədə üst-üstə düşür (payız vərəqi yaz jurnalı açıldıqdan SONRA çap olunanda eyni adlı yaz fənni ilə
   qarışmasın deyə); «əvvəl yaradılıb» sərt süzgəc DEYİL, açarın bir hissəsidir — ``added_date`` köhnə sistemdə
   jurnal yenidən qurulanda yenilənib (qrupu uyğun ~6 800 cədvəl yalnız buna görə düşürdü); bərabərlikdə ən son semestr;
3. açarı EYNİ, semestri fərqli ikinci ailə qalırsa — cədvəl «ambiqü» sayılır;
4. sonra HƏR TƏLƏBƏ SƏTRİ ayrıca öz ailəsinə bağlanır (:meth:`JournalIndex.choose_row`) — fənni təkrar keçən
   tələbənin vərəqi köhnə cəhdə yox, həmin kursa düşsün; cədvəlin ailəsi yalnız bərabərlik kəsicisidir.

Hər ``(ailə, tələbə)`` üçün ƏN SON export-un sətri saxlanılır — Yekun dolu sətir varsa onların ən sonu.
Paketə yalnız ``--official-entry`` semestrlərinə düşən ailələr yazılır; tutuşdurma isə BÜTÜN semestrlərlə
aparılır (6-cı semestrin vərəqi səhvən 7-yə yazılmasın).

Paketdə tələbə adı YOXDUR — yalnız legacy tələbə id-si, jurnal uniqid-ləri və rəqəmlər.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .extract import DeltaExtractor, parse_id_list
from .official_entry_sheets import number, parse_export
from .resolve import person_key, subject_key

PHASE = "official_entry"
#: ``bundle.SECTIONS`` — bu paketdə boş qalanlar.
_EMPTY_SECTIONS = (
    "departments",
    "specialities",
    "groups",
    "subjects",
    "workers",
    "students",
    "journals",
    "lesson_dates",
    "points",
    "excuse_windows",
    "syllabi",
    "lesson_topics",
)
_EXPORT_FETCH = 200


def _flag(value) -> bool:
    return str(value or "0").strip() not in ("", "0")


class JournalIndex:
    """Bütün köhnə jurnallar: ``(qrup, fənn açarı)`` → ailələr; ailənin ``im``/``im2`` xanaları, müəllimi."""

    def __init__(self, journals, lessons, workers, finals):
        self.family_of: dict[int, int] = {}
        self.members: dict[int, list[dict]] = defaultdict(list)
        self.by_group_subject: dict[tuple, set[int]] = defaultdict(set)
        self.by_subject: dict[str, set[int]] = defaultdict(set)
        self.students: dict[int, set[int]] = defaultdict(set)
        names = {row["id"]: subject_key(row.get("name")) for row in lessons}
        people = {
            row["id"]: person_key(" ".join(str(row.get(k) or "") for k in ("first_name", "last_name", "father_name")))
            for row in workers
        }
        for row in journals:
            if _flag(row.get("fake")) or _flag(row.get("sonra_sil")):
                continue
            root = int(row.get("parent_id") or 0) or int(row["id"])
            self.family_of[int(row["id"])] = root
            self.members[root].append(row)
            subject = names.get(row["lesson_id"], "")
            self.by_subject[subject].add(root)
            self.students[root].update(parse_id_list(row.get("students_id")))
            for group_id in parse_id_list(row.get("groups_id")):
                self.by_group_subject[(group_id, subject)].add(root)
        self.teachers = {root: {people.get(r["teacher_id"], "") for r in rows} for root, rows in self.members.items()}
        self.hours = {root: {int(r.get("fenn_saati") or 0) for r in rows} for root, rows in self.members.items()}
        self.started = {root: min(str(r.get("added_date") or "") for r in rows) for root, rows in self.members.items()}
        self.semester = {root: max(int(r.get("semestr") or 0) for r in rows) for root, rows in self.members.items()}
        self.finals: dict[tuple, set] = defaultdict(set)
        uniqid_root = {r["uniqid"]: root for root, rows in self.members.items() for r in rows}
        for row in finals:
            root = uniqid_root.get(row["journal_uniqid"])
            value = number(str(row["point"] or ""))
            if root is not None and value is not None:
                self.finals[(root, int(row["student_id"]))].add(_point(value))

    def uniqids(self, root: int) -> list[str]:
        return sorted(r["uniqid"] for r in self.members[root])

    def choose(self, table, exported: str) -> tuple[int | None, str]:
        """Cədvəlin ailəsi və nəticə tokeni (``matched`` / ``matched_by_students`` / ``no_candidate`` / ``ambiguous``)."""

        subject = subject_key(table.subject)
        grouped = self.by_group_subject.get((table.group_id, subject), set())
        sheet_students = {row.student_id for row in table.rows}
        roots = grouped or {root for root in self.by_subject.get(subject, ()) if sheet_students & self.students[root]}
        if not roots:
            return None, "no_candidate"
        teacher = person_key(table.teacher)
        keys = {}
        for root in roots:
            exams = 0
            for row in table.rows:
                stored = self.finals.get((root, row.student_id), set())
                if any(value is not None and _point(value) in stored for value in (row.exam, row.resit)):
                    exams += 1
            keys[root] = (
                exams,
                int(root in grouped),
                int(bool(teacher) and teacher in self.teachers[root]),
                int(table.hours in self.hours[root]),
                int(bool(self.started[root]) and self.started[root][:10] <= exported[:10]),
                len(sheet_students & self.students[root]),
            )
        ranked = sorted(roots, key=lambda root: (keys[root], self.semester[root], root), reverse=True)
        best = ranked[0]
        if any(keys[r] == keys[best] and self.semester[r] != self.semester[best] for r in ranked[1:]):
            return None, "ambiguous"
        return best, "matched" if grouped else "matched_by_students"

    def choose_row(self, table, row, table_root, exported: str) -> tuple[int | None, str]:
        """Bir TƏLƏBƏ sətrinin ailəsi — tələbənin ÖZ jurnalı (``students_id``) arasından.

        Cədvəl səviyyəli seçim qrupa görədir; fənni TƏKRAR keçən tələbədə qrupun köhnə jurnalı yeni kursun vərəqini
        özünə çəkirdi (2025/26 «39+26=65» vərəqi 2022/23 «31+4=35» yazılışına). Açar: ``(bu sətrin imtahanı ailənin
        im/im2-si ilə üst-üstə düşür, export-dan əvvəl başlayıb, semestr, cədvəlin ailəsidir)`` — imtahan uyğunluğu
        köhnə semestrin sonradan çap olunan vərəqini, «ən son başlamış kurs» isə imtahandan əvvəlki vərəqi düz yerə
        aparır. Tələbə heç bir ailənin siyahısında deyilsə cədvəlin ailəsi qalır.
        """

        roots = [r for r in self.by_subject.get(subject_key(table.subject), ()) if row.student_id in self.students[r]]
        if not roots:
            return (table_root, "row.table_family") if table_root is not None else (None, "row.no_family")
        stored = self.finals

        def key(root):
            exam = int(
                any(
                    v is not None and _point(v) in stored.get((root, row.student_id), ()) for v in (row.exam, row.resit)
                )
            )
            started = int(bool(self.started[root]) and self.started[root][:10] <= exported[:10])
            return (exam, started, self.semester[root], int(root == table_root))

        ranked = sorted(roots, key=lambda root: (key(root), root), reverse=True)
        best = ranked[0]
        if len(ranked) > 1 and key(ranked[1]) == key(best):
            return None, "row.ambiguous"
        return best, "row.own_family" if best == table_root else "row.moved_family"


def _point(value) -> str:
    """Vərəq rəqəmini xana mətni ilə müqayisə formasına salır (``17`` ↔ ``"17"``, ``27.0`` ↔ ``"27"``)."""

    return format(value.normalize(), "f")


def collect_rows(cursor, source: str, index: JournalIndex, semesters, stats: Counter) -> list[dict]:
    """Bütün export-ları axınla oxu → ``(ailə, tələbə)`` başına seçilmiş sətir."""

    import pymysql.cursors

    best: dict[tuple, tuple] = {}
    # ~1.4 GB HTML — server tərəfli (axın) kursor; eyni bağlantı = eyni ardıcıl snapshot.
    stream = cursor.connection.cursor(pymysql.cursors.SSCursor)
    stream.execute(f"SELECT id, export_time, data FROM {source}.balvereqi_logs ORDER BY id")
    while True:
        batch = stream.fetchmany(_EXPORT_FETCH)
        if not batch:
            break
        for export_id, exported, data in batch:
            exported = str(exported)
            for table in parse_export(data):
                stats["tables"] += 1
                table_root, outcome = index.choose(table, exported)
                stats[f"tables.{outcome}"] += 1
                for row in table.rows:
                    root, row_outcome = index.choose_row(table, row, table_root, exported)
                    stats[row_outcome] += 1
                    if root is None or index.semester[root] not in semesters:
                        continue
                    rank = (row.total is not None, exported, int(export_id))
                    current = best.get((root, row.student_id))
                    if current is None or rank > current[0]:
                        best[(root, row.student_id)] = (rank, export_id, exported, row)
    stream.close()
    out = []
    for (root, student_id), (_rank, export_id, exported, row) in sorted(best.items()):
        out.append(
            {
                "family": root,
                "journals": index.uniqids(root),
                "semestr": index.semester[root],
                "student_id": student_id,
                "export_id": int(export_id),
                "export_time": exported,
                "entry": _text(row.entry),
                "exam": _text(row.exam),
                "total": _text(row.total),
                "resit": _text(row.resit),
                "concession": row.concession,
                "attendance_fail": row.attendance_fail,
            }
        )
    stats["rows"] = len(out)
    stats["rows.with_total"] = sum(1 for row in out if row["total"] is not None)
    return out


def _text(value):
    return None if value is None else format(value.normalize(), "f")


def build_official_entry_bundle(extractor: DeltaExtractor, *, snapshot: dict, semesters) -> dict:
    x = extractor
    semesters = {int(value) for value in semesters}
    journals = x._rows(
        "SELECT id, uniqid, parent_id, lesson_id, teacher_id, groups_id, students_id, semestr, added_date, fake, "
        "sonra_sil, "
        f"fenn_saati FROM {x.src}.journals ORDER BY id"
    )
    lessons = x._by_ids("lessons", ("id", "name"), {row["lesson_id"] for row in journals})
    workers = x._by_ids(
        "workers", ("id", "first_name", "last_name", "father_name"), {r["teacher_id"] for r in journals}
    )
    finals = x._rows(
        "SELECT journal_uniqid, student_id, point FROM "
        f"{x.src}.journals_dates_points WHERE month_id IN ('im', 'im2')"
    )
    index = JournalIndex(journals, lessons, workers, finals)
    stats: Counter = Counter()
    rows = collect_rows(x.cur, x.src, index, semesters, stats)
    by_semester = Counter(row["semestr"] for row in rows)
    periods = x._rows(f"SELECT id, name, type, is_current FROM {x.src}.semestr_jurnal ORDER BY id")
    info = {
        "semesters": sorted(semesters),
        **dict(sorted(stats.items())),
        **{f"rows.semester_{k}": v for k, v in sorted(by_semester.items())},
    }
    return {
        "snapshot": {**snapshot, "full_semesters": [], "phases": [PHASE], "official_entry": info},
        **{name: [] for name in _EMPTY_SECTIONS},
        "periods": periods,
        "official_entries": rows,
    }


__all__ = ["PHASE", "JournalIndex", "build_official_entry_bundle", "collect_rows"]
