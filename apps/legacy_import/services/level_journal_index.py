"""Köhnə sistemin cari semestr jurnalları → yeni sistemin açılış/qeydiyyatları (YALNIZ OXU) — plan qurucularının ortaq
indeksi (sahib 2026-10-27: İngilis dili səviyyə jurnalları, «sonra kafedra-kafedra davam et»).

Mənbə: ``legacy_delta_extract`` paketi (jurnallar, xanalar, ``journals_dates_rooms`` sətirləri ``lesson_topics``-də,
``journals_dates_added_by_teacher`` sətirləri ``lesson_dates``-də) + hədəf baza (prod nüsxəsi). Hər aktiv jurnal üçün:
müəllim (``_Teachers`` — ``legacy_journal_teachers_extract`` ilə eyni həll), fənn (``Catalog.subject_for``), siyahı
(``students_id`` + xanası olanlar), siyahının cari dövrdəki EYNİ fənn üzrə ``enrolled`` qeydiyyatları (``hits``:
açılış → qeydiyyatlar), tarixli dərs sətirləri (tarix + saat → növ) və tələbə üzrə xana sayı.

İşlədənlər: :mod:`.journal_share_plan` (``journal-shares/1``), :mod:`.level_merge_plan` (``level-merge/1``),
:mod:`.chair_journal_health`. Heç nə yazmır; ad/FİN saxlamır (yalnız id-lər).
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from .delta.apply import DeltaRun
from .delta.extract import parse_id_list
from .delta.journal_teachers import _Teachers
from .delta.resolve import lesson_date

#: ``journals_dates_rooms.sem_muh`` / ``journals_dates_added_by_teacher.sem_muh`` → dərs növü.
ROOM_KIND = {1: "lecture", 0: "seminar", 3: "seminar", 2: "lab"}


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _hhmm(value) -> str:
    return str(value or "")[:5]


def parse_time(text: str):
    try:
        return datetime.time.fromisoformat(text)
    except ValueError:
        return None


def journal_is_current(row: dict, semesters) -> bool:
    """Plan üçün sayılan jurnal: tam semestrdə, aktiv, «fake» / «sonra sil» deyil."""
    return (
        _int(row.get("semestr")) in semesters
        and _int(row.get("fake")) != 1
        and _int(row.get("sonra_sil")) != 1
        and _int(row.get("active")) == 1
    )


@dataclass
class LegacyJournal:
    legacy_id: int
    uniqid: str
    subject_id: object = None
    subject_name: str = ""
    teacher_id: int | None = None
    #: ``[(legacy tələbə id, istifadəçi id | None)]`` — siyahı + xanası olanlar (sıra saxlanılır).
    students: list = field(default_factory=list)
    #: açılış id → həmin açılışdakı siyahı tələbələrinin ``enrolled`` qeydiyyat id-ləri.
    hits: dict = field(default_factory=dict)
    #: ``(tarix, "HH:MM")`` → növ (``journals_dates_rooms``) və ya ``None`` (yalnız ay cədvəlində).
    slots: dict = field(default_factory=dict)
    #: ay cədvəlinin növləri — tarixli sətir yoxdursa son ehtiyat.
    month_kinds: set = field(default_factory=set)
    #: legacy tələbə id → xana sayı.
    points: Counter = field(default_factory=Counter)

    @property
    def resolved(self) -> bool:
        return self.subject_id is not None and self.teacher_id is not None


class LegacyIndex:
    """Bir dəfəlik oxu: köhnə jurnallar + cari dövrün qeydiyyatları, açılışları, dərs növləri."""

    def __init__(self, *, organization, bundle: dict, period, journals=None, enrollments=None):
        self.organization = organization
        self.period = period
        self.counts: Counter = Counter()
        self._load_enrollments(enrollments)
        if journals is not None:  # testlər / əvvəlcədən qurulmuş giriş
            self.journals = list(journals)
            self._attach_hits()
            return
        self.run = DeltaRun(organization=organization, actor=None, bundle=bundle, tag="share-plan", until=None)
        semesters = {_int(value) for value in (bundle.get("snapshot") or {}).get("full_semesters") or []} or {14}
        rows = [row for row in bundle["journals"] if journal_is_current(row, semesters)]
        self.journals = self._resolve(bundle, rows)
        self._attach_hits()

    # ── yeni sistem ──────────────────────────────────────────────────────
    def _load_enrollments(self, enrollments) -> None:
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        rows = enrollments
        if rows is None:
            rows = list(
                Enrollment.objects.filter(
                    organization=self.organization, offering__period=self.period, status="enrolled"
                ).values("id", "student_id", "offering_id", "offering__subject_id", "offering__subject__name")
            )
        self.enrolled = {row["id"]: row for row in rows}
        self.by_student_subject = defaultdict(list)
        for row in rows:
            self.by_student_subject[(row["student_id"], row["offering__subject_id"])].append(row)
        self.offerings = {
            row["id"]: row
            for row in CourseOffering.objects.filter(organization=self.organization, period=self.period).values(
                "id", "instructor_id", "subject_id", "subject__name", "group_id", "is_active"
            )
        }

    def lesson_kinds(self) -> dict:
        """``(açılış, tarix, başlanğıc)`` → növ (yalnız lazım olanda oxunur)."""
        Lesson = django_apps.get_model("registrar", "Lesson")
        return {
            (offering_id, day, start): kind
            for offering_id, day, start, kind in Lesson.objects.filter(
                organization=self.organization, offering__period=self.period
            ).values_list("offering_id", "date", "start_time", "kind")
        }

    # ── köhnə sistem ─────────────────────────────────────────────────────
    def _resolve(self, bundle: dict, rows: list) -> list:
        run = self.run
        teachers = _Teachers(self.organization, run.catalog, {row["id"]: row for row in bundle["workers"]})
        subjects = {row["id"]: row for row in bundle["subjects"]}
        points = defaultdict(Counter)
        for row in bundle["points"]:
            points[row["journal_uniqid"]][row["student_id"]] += 1
        rooms = defaultdict(list)
        for row in bundle.get("lesson_topics") or []:
            rooms[row["journal_uniqid"]].append(row)
        added = defaultdict(list)
        for row in bundle.get("lesson_dates") or []:
            added[row["journal_id"]].append(row)
        out = []
        for row in rows:
            self.counts["journals"] += 1
            entry = LegacyJournal(legacy_id=_int(row["id"]), uniqid=str(row["uniqid"] or ""))
            legacy_subject = subjects.get(row["lesson_id"])
            subject = run.catalog.subject_for(legacy_subject)[0] if legacy_subject else None
            if subject is None:
                self.counts["subject_unresolved"] += 1
            else:
                entry.subject_id, entry.subject_name = subject.pk, subject.name
            entry.teacher_id = teachers.resolve(row["teacher_id"])[0]
            if entry.teacher_id is None:
                self.counts["teacher_unresolved"] += 1
            entry.points = points.get(entry.uniqid, Counter())
            roster = list(dict.fromkeys(parse_id_list(row["students_id"]) + sorted(entry.points)))
            for legacy_id in roster:
                user_id = run.students.resolve(legacy_id, create=False)[0]
                if user_id is None:
                    self.counts["student_unresolved"] += 1
                entry.students.append((legacy_id, user_id))
            self._slots(entry, run.period_of(row["semestr"]), rooms.get(entry.uniqid, ()), added.get(row["id"], ()))
            out.append(entry)
        return out

    @staticmethod
    def _slots(entry, legacy_period, rooms, added) -> None:
        for row in added:
            kind = ROOM_KIND.get(_int(row.get("sem_muh")))
            if kind:
                entry.month_kinds.add(kind)
        if legacy_period is None:
            return
        for row in rooms:
            day = lesson_date(legacy_period, _int(row["month"]), _int(row["day"]))
            if day:
                entry.slots[(day, _hhmm(row.get("times")))] = ROOM_KIND.get(_int(row.get("sem_muh")))
        for row in added:
            day = lesson_date(legacy_period, _int(row["month"]), _int(row["day"]))
            if day and (day, _hhmm(row.get("time"))) not in entry.slots:
                entry.slots[(day, _hhmm(row.get("time")))] = None

    def _attach_hits(self) -> None:
        for entry in self.journals:
            hits = defaultdict(set)
            if entry.subject_id is not None:
                for _legacy_id, user_id in entry.students:
                    for row in self.by_student_subject.get((user_id, entry.subject_id), ()):
                        hits[row["offering_id"]].add(row["id"])
            entry.hits = dict(hits)
            if entry.resolved:
                self.counts["journal_with_hits" if hits else "journal_no_hits"] += 1

    # ── köməkçilər ───────────────────────────────────────────────────────
    def resolved_journals(self) -> list:
        return [entry for entry in self.journals if entry.resolved]

    def covered_enrollments(self) -> set:
        """Hər hansı köhnə jurnalın siyahısına düşən qeydiyyatlar."""
        return {pk for entry in self.journals for ids in entry.hits.values() for pk in ids}

    def journals_by_enrollment(self) -> dict:
        """qeydiyyat → onu siyahısında saxlayan (həll olunmuş) jurnallar."""
        out = defaultdict(list)
        for entry in self.resolved_journals():
            for ids in entry.hits.values():
                for pk in ids:
                    out[pk].append(entry)
        return out


__all__ = ["LegacyIndex", "LegacyJournal", "ROOM_KIND", "journal_is_current", "parse_time"]
