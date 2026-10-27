"""RİM 2026-10-27 düzəliş planları — köhnə sistemin paketi (``legacy_delta_extract``) + hədəf baza (prod nüsxəsi).

LOKAL qurulur (``build_twin_repair_plans``), heç nə YAZMIR; nəticə YALNIZ id-lərdir (ad / FİN yoxdur) — şifrələnib
draft release-ə yüklənir, prod-da registrar əmrləri tətbiq edir:

* ``relocate.json`` (``twin-relocate/1``) → ``relocate_twin_enrollment``: tələbənin «ev» jurnalı
  (:mod:`.delta.home_journal` — delta-nın düzəldilmiş qaydası ilə EYNİ) başqa açılışdadırsa, onun W-dəki xanalarından
  ev jurnalının xanası olanlar (eyni tarix + saat) ev açılışının dərsinə; ev jurnalının itmiş «qb»-ləri (köhnə delta
  «yalnız qb» fantom dərsini atmışdı) ``restore``;
* ``merge.json`` (``twin-merge/1``) → ``merge_twin_offerings``: fənn kodu toqquşması (``Catalog.code_collision``) ilə
  yanlış karta düşmüş delta açılışı (W) + eyni qrup/dövrdə düzgün fənnin açılışı (T);
* ``lessonkinds.json`` (``legacy-lesson-kinds/1``) → ``fix_legacy_lesson_kinds``: köçürmənin yaratdığı «seminar»
  dərsləri, xanalarının legacy kodu əksəriyyətlə 2-dir (laboratoriya).
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from django.apps import apps as django_apps
from django.db import models

from .delta.apply import DeltaRun
from .delta.collisions import delta_created_offerings
from .delta.home_journal import build_home_index, cell_counts, journal_is_active, legacy_unit_id, offerings_related
from .delta.journals import JournalSlices, OfferingIndex
from .delta.lessons import CALENDAR, mark_value, winning_cells
from .delta.resolve import lesson_date, subject_key
from .rehearsal_journal_lesson_kinds import LAB, cell_kind

RELOCATE_FORMAT = "twin-relocate/1"
#: «Fantom dərs»: köçürmənin yaratdığı, ən çox bu qədər xanalı dərs (diaqnozun detektoru ilə eyni: 1–3 xana) ...
PHANTOM_MAX = 3
#: ... və ev açılışında eyni slotda ən azı bu qədər xanalı dərs var.
HOME_MIN = 5
#: Əkiz birləşməsində düzgün fənnin açılışı ada görə (legacy adında yazı səhvi ola bilər).
NAME_MATCH_MIN = 0.85
MERGE_FORMAT = "twin-merge/1"
KINDS_FORMAT = "legacy-lesson-kinds/1"


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _hhmm(value) -> str:
    return value.strftime("%H:%M") if value else ""


class PlanBuilder:
    def __init__(self, *, organization, bundle: dict, until: datetime.date):
        self.org = organization
        self.bundle = bundle
        self.until = until
        self.counts: Counter = Counter()
        self.run = DeltaRun(organization=organization, actor=None, bundle=bundle, tag="rim-plan", until=until)
        full = set((bundle.get("snapshot") or {}).get("full_semesters") or [])
        self.journals = [
            row
            for row in bundle["journals"]
            if not row.get("fake") and not row.get("sonra_sil") and (not full or row.get("semestr") in full)
        ]
        self.slices = self._slices()
        uniqids = set(self.slices)
        self.cells = [row for row in winning_cells(bundle["points"]) if row["journal_uniqid"] in uniqids]
        self.homes = build_home_index(self.run, self.slices, cell_counts(self.cells))

    # ── jurnal → açılış (yalnız oxu) ──────────────────────────────────────
    def _slices(self) -> dict:
        run, index, out = self.run, OfferingIndex(self.run), {}
        for journal in self.journals:
            period = run.period_of(journal["semestr"])
            legacy = run.legacy_subjects.get(journal["lesson_id"])
            subject = run.catalog.subject_for(legacy)[0] if legacy and period else None
            if subject is None and legacy and period:
                # Toqquşan kod: delta jurnalı məhz bu (yanlış adlı) karta yazıb — data oradadır (əkiz birləşməsindən əvvəl).
                subject = run.catalog.code_collision(legacy)
            if subject is None:
                self.counts["journal_unmapped"] += 1
                continue
            entry = JournalSlices(journal)
            for group_id in parse_ids(journal["groups_id"]):
                legacy_group = run.legacy_groups.get(group_id)
                unit = run.catalog.group_for(legacy_group)[0] if legacy_group else None
                offering = index.find(subject, period, unit)[0] if unit is not None else None
                if offering is not None and offering.is_active and offering not in entry.offerings:
                    entry.offerings.append(offering)
            if entry.offerings:
                out[journal["uniqid"]] = entry
        self.counts["journals_mapped"] = len(out)
        return out

    def _student(self, legacy_id, entry):
        user_id, _outcome = self.run.students.resolve(legacy_id, create=False)
        if user_id is None:
            return None, None
        offering = entry.pick(
            self.run.students.group_of.get(user_id), self.run.catalog, legacy_unit_id(self.run, legacy_id)
        )
        return user_id, offering

    def _cell_rows(self):
        """``(hesab, açılış, jurnal, tarix, "HH:MM", sətir)`` — təqvim xanaları, tələbəsi və tarixi həll olunanlar."""

        for row in self.cells:
            if row["month_id"] not in CALENDAR:
                continue
            entry = self.slices[row["journal_uniqid"]]
            user_id, offering = self._student(row["student_id"], entry)
            period = self.run.period_of(entry.journal["semestr"])
            day = lesson_date(period, int(row["month_id"]), _int(row["day_number"])) if period else None
            if user_id is None or offering is None or day is None:
                continue
            yield user_id, offering, entry.journal, day, str(row["time"])[:5], row

    # ── relocate ──────────────────────────────────────────────────────────
    def relocate(self) -> dict:
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        LessonMark = django_apps.get_model("registrar", "LessonMark")
        Lesson = django_apps.get_model("registrar", "Lesson")
        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        excused = self.run.excuse_index()
        home_cells: dict = defaultdict(dict)
        for user_id, offering, journal, day, hhmm, row in self._cell_rows():
            key = (user_id, offering.subject_id, offering.period_id)
            home = self.homes.home(key)
            if (
                home is None
                or not journal_is_active(journal)
                or not offerings_related(self.run.catalog, home, offering)
            ):
                continue
            status, _score, _outcome = mark_value(row["point"])
            if status == "absent" and (_int(row.get("excusable")) == 1 or excused(row["student_id"], day)):
                status = "excused"
            if status:
                home_cells[key][(day, hhmm)] = status
        keys = [key for key in self.homes.keys() if self.homes.home(key) is not None]
        students = {key[0] for key in keys}
        periods = {key[2] for key in keys}
        by_key = defaultdict(list)
        for enrollment in Enrollment.objects.filter(
            organization=self.org, student_id__in=students, offering__period_id__in=periods
        ).select_related("offering"):
            by_key[(enrollment.student_id, enrollment.offering.subject_id, enrollment.offering.period_id)].append(
                enrollment
            )
        registry = defaultdict(set)
        for student_id, group_id in Record.objects.filter(
            organization=self.org, student_id__in=students, is_active=True
        ).values_list("student_id", "group_id"):
            registry[student_id].add(group_id)
        lesson_index: dict = {}
        items = []
        for key in sorted(keys, key=lambda value: (value[0], str(value[1]), str(value[2]))):
            home = self.homes.home(key)
            wrong = [
                row
                for row in by_key.get(key, ())
                if row.status == "enrolled" and not offerings_related(self.run.catalog, home, row.offering)
            ]
            if not wrong:
                continue
            home_enrollment = next((row for row in by_key.get(key, ()) if row.offering_id == home.pk), None)
            if home_enrollment is not None and home_enrollment.status != "enrolled":
                self.counts["relocate_home_not_enrolled"] += 1
                continue
            lessons = lesson_index.setdefault(home.pk, self._lessons(Lesson, home))
            taken = set()
            if home_enrollment is not None:
                taken = set(LessonMark.objects.filter(enrollment=home_enrollment).values_list("lesson_id", flat=True))
            for source in wrong:
                if source.offering.group_id in registry[key[0]] and home.group_id not in registry[key[0]]:
                    self.counts["relocate_registry_group_is_source"] += 1
                    continue
                item = self._relocate_item(LessonMark, key, source, home, lessons, home_cells[key], taken)
                if item is not None:
                    items.append(item)
        self.counts["relocate_items"] = len(items)
        self.counts["relocate_students"] = len({item["student"] for item in items})
        self.counts["relocate_source_offerings"] = len({item["source_offering"] for item in items})
        for item in items:
            item.pop("source_offering")
        return {"format": RELOCATE_FORMAT, "items": items}

    @staticmethod
    def _lessons(Lesson, offering) -> dict:
        out: dict = {}
        for pk, day, start, kind, marks in (
            Lesson.objects.filter(offering=offering)
            .annotate(mark_count=models.Count("marks"))
            .values_list("pk", "date", "start_time", "kind", "mark_count")
        ):
            out.setdefault(("slot", day, _hhmm(start)), pk)
            out.setdefault(("kind", day, kind), []).append(pk)
            out[("marks", pk)] = marks
        return out

    def _relocate_item(self, LessonMark, key, source, home, lessons, cells, taken):
        """Bir W qeydiyyatı. YALNIZ «fantom» xana köçür: W-dəki dərsi köçürmənin yaratdığıdır (``created_by`` boş),
        ``PHANTOM_MAX`` xanadan azdır, ev açılışında eyni slotda ``HOME_MIN`` xanalı dərs var və tələbənin həmin slotda
        ev jurnalında xanası var. W-də köçürmənin gətirdiyi BAL xanası böyük dərsdə qalırsa — tələbə W-də həqiqətən
        qiymət alıb, bənd yaradılmır (sayılır); qalan iştirak / «qb» xanaları W-də qalır (qayıb T-yə daşınmır). Müəllimin sonradan yazdığı xanalar W-də qalır (sayılır).
        """

        moves, used, emptied = [], set(taken), Counter()
        marks = list(LessonMark.objects.filter(enrollment=source).select_related("lesson"))
        per_lesson = Counter(
            LessonMark.objects.filter(lesson_id__in={mark.lesson_id for mark in marks}).values_list(
                "lesson_id", flat=True
            )
        )
        local_real = teacher_left = 0
        for mark in marks:
            slot = (mark.lesson.date, _hhmm(mark.lesson.start_time))
            phantom = mark.lesson.created_by_id is None and per_lesson[mark.lesson_id] <= PHANTOM_MAX
            target = lessons.get(("slot",) + slot)
            if target is None and slot in cells:
                same_kind = lessons.get(("kind", mark.lesson.date, mark.lesson.kind)) or []
                target = same_kind[0] if len(same_kind) == 1 else None
            if slot in cells and phantom and target is not None and lessons.get(("marks", target), 0) >= HOME_MIN:
                if target in used:
                    self.counts["relocate_marks_target_taken"] += 1
                    continue
                used.add(target)
                moves.append({"mark": str(mark.pk), "lesson": str(target)})
                emptied[mark.lesson_id] += 1
                continue
            if mark.entered_by_id is not None:
                teacher_left += 1
            elif mark.score is not None and not phantom:
                local_real += 1
        if not moves:
            return None
        if local_real:
            self.counts["relocate_skipped_source_has_real_marks"] += 1
            return None
        restore = []
        for (day, hhmm), status in sorted(cells.items()):
            target = lessons.get(("slot", day, hhmm))
            if status in ("absent", "excused") and day <= self.until and target is not None and target not in used:
                restore.append({"lesson": str(target), "status": status})
                used.add(target)
        self.counts["relocate_moves"] += len(moves)
        self.counts["relocate_restores"] += len(restore)
        self.counts["relocate_source_marks_left"] += len(marks) - len(moves)
        self.counts["relocate_teacher_marks_left"] += teacher_left
        self.counts["relocate_phantom_lessons"] += sum(
            1 for lesson_id, count in emptied.items() if count == per_lesson[lesson_id]
        )
        return {
            "student": key[0],
            "source": str(source.pk),
            "source_offering": str(source.offering_id),
            "target_offering": str(home.pk),
            "moves": moves,
            "restore": restore,
            "drop_source": True,
        }

    # ── merge ─────────────────────────────────────────────────────────────
    def merge(self) -> dict:
        """Toqquşan legacy fənnin hər qrupu: W = (kod kartı, dövr, qrup) delta-nın yaratdığı açılış; T = həmin qrup +
        dövrdə düzgün fənnin açılışı — ``collision_target`` kartı, o tapılmasa ADI legacy adına ən yaxın (≥ 0.85,
        yazı səhvinə dözümlü — «Analtik» / «Analitik») TƏK açılış."""

        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        created = delta_created_offerings(self.org)
        pairs, seen = [], set()
        for journal in self.journals:
            legacy = self.run.legacy_subjects.get(journal["lesson_id"])
            wrong = self.run.catalog.code_collision(legacy) if legacy else None
            period = self.run.period_of(journal["semestr"])
            if wrong is None or period is None:
                continue
            right = self.run.catalog.collision_target(legacy)
            for group_id in parse_ids(journal["groups_id"]):
                legacy_group = self.run.legacy_groups.get(group_id)
                unit = self.run.catalog.group_for(legacy_group)[0] if legacy_group else None
                if unit is None:
                    continue
                source = CourseOffering.objects.filter(
                    organization=self.org, subject=wrong, period=period, group=unit, is_active=True
                ).first()
                if source is None or str(source.pk) not in created:
                    continue
                target = self._merge_target(CourseOffering, legacy, right, source)
                if target is None:
                    self.counts["merge_no_target_offering"] += 1
                    continue
                if (source.pk, target.pk) not in seen:
                    seen.add((source.pk, target.pk))
                    pairs.append({"source": str(source.pk), "target": str(target.pk)})
        self.counts["merge_pairs"] = len(pairs)
        return {"format": MERGE_FORMAT, "pairs": pairs}

    def _merge_target(self, CourseOffering, legacy, right, source):
        siblings = (
            CourseOffering.objects.filter(
                organization=self.org, period_id=source.period_id, group_id=source.group_id, is_active=True
            )
            .exclude(pk=source.pk)
            .select_related("subject")
        )
        if right is not None:
            exact = [row for row in siblings if row.subject_id == right.pk]
            if exact:
                return exact[0]
        wanted = subject_key(legacy.get("name"))
        scored = [
            (SequenceMatcher(None, wanted, subject_key(row.subject.name)).ratio(), row)
            for row in siblings
            if row.subject_id != source.subject_id
        ]
        close = [row for ratio, row in scored if ratio >= NAME_MATCH_MIN]
        return close[0] if len(close) == 1 else None

    # ── lesson kinds ──────────────────────────────────────────────────────
    def lesson_kinds(self) -> dict:
        LessonMark = django_apps.get_model("registrar", "LessonMark")
        legacy_kind: dict = {}
        periods = set()
        for user_id, offering, _journal, day, hhmm, row in self._cell_rows():
            kind = cell_kind(lab=_int(row.get("lab")), sem_muh=_int(row.get("sem_muh")))
            if kind:
                legacy_kind[(user_id, offering.subject_id, day, hhmm)] = kind
                periods.add(offering.period_id)
        votes: dict = defaultdict(Counter)
        rows = LessonMark.objects.filter(
            organization=self.org,
            lesson__kind="seminar",
            lesson__created_by__isnull=True,
            lesson__offering__period_id__in=periods,
        ).values_list(
            "lesson_id", "enrollment__student_id", "lesson__offering__subject_id", "lesson__date", "lesson__start_time"
        )
        for lesson_id, student_id, subject_id, day, start in rows.iterator(chunk_size=5000):
            kind = legacy_kind.get((student_id, subject_id, day, _hhmm(start)))
            if kind:
                votes[lesson_id][kind] += 1
        lessons = sorted(str(lesson_id) for lesson_id, count in votes.items() if count[LAB] * 2 > sum(count.values()))
        self.counts["kinds_lessons"] = len(lessons)
        return {"format": KINDS_FORMAT, "lessons": lessons}


def parse_ids(raw) -> list:
    from .delta.extract import parse_id_list

    return parse_id_list(raw)


__all__ = ["KINDS_FORMAT", "MERGE_FORMAT", "RELOCATE_FORMAT", "PlanBuilder"]
