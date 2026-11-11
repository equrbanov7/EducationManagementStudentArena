"""Dublikat fənlər — kataloq addımı «yalnız cari və gələcək» + imtahan qaydası (sahib 2026-11-11).

* «Köhnə illərin jurnalını ciddiyə alma, boşver — əsas indi və bundan sonra olandır.» — keçmiş dövrdə iki kartın datalı
  jurnalı (prod: «2022/2023 Payız · 232 M rus») kataloq birləşməsini bloklamır, köhnə jurnallar yerində qalır;
* cari dövrün iki jurnalı əvvəlki kimi jurnal birləşməsindən keçir (heç bir xana itmir);
* «Hansı fənnə bağlı imtahan verilibsə o formada saxla» — cari imtahan bir kartdadırsa o kart saxlanılır, imtahanın
  jurnal bağı yenilənir və nəticə jurnala düşür; paket geri qaytarılır.
"""

import datetime
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.exams.models import Exam
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar import duplicate_subjects_2026_11_11 as duplicates
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonKind, LessonMark, Subject
from core.constants import OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
D1 = datetime.date(2026, 10, 5)
T1 = datetime.time(10, 10)
LINE_RE = r"^twin_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$"


class CurrentOnlyCatalogueTest(_MidtermSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.typo = Subject.objects.create(organization=self.org, code="QKU-77", name="Proqramlasdirma")
            self.source = CourseOffering.objects.create(
                organization=self.org, subject=self.typo, group=self.group, period=self.period, instructor=self.teacher
            )
            self.w1 = Enrollment.objects.create(organization=self.org, student=self.student, offering=self.source)
            lesson = Lesson.objects.create(
                organization=self.org, offering=self.source, date=D1, kind=LessonKind.LECTURE, hours=2, start_time=T1
            )
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=self.w1, status="absent")
            # «2022/2023 Payız · JBG1: hər iki fənn üzrə açılış var» — iki datalı köhnə jurnal.
            self.past = AcademicPeriod.objects.create(
                organization=self.org,
                name="2022/2023 Payız",
                period_type=self.period.period_type,
                academic_year="2022/2023",
                start_date=datetime.date(2022, 9, 1),
                end_date=datetime.date(2023, 1, 31),
            )
            self.past_typo = CourseOffering.objects.create(
                organization=self.org, subject=self.typo, group=self.group, period=self.past
            )
            self.past_keeper = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, group=self.group, period=self.past
            )
            for offering in (self.past_typo, self.past_keeper):
                Enrollment.objects.create(organization=self.org, student=self.student, offering=offering)
        self.plan = {
            "format": duplicates.FORMAT,
            "auto_catalogue": False,
            "groups": [
                {
                    "name": "typo",
                    "keeper": str(self.subject.pk),
                    "sources": [str(self.typo.pk)],
                    "reviewed": True,
                    "pairs": [{"source": str(self.source.pk), "target": str(self.offering.pk)}],
                }
            ],
            "doubles": [],
        }
        patch = mock.patch.object(duplicates, "PLAN", self.plan)
        patch.start()
        self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "merge_duplicate_subjects_20261111",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts, batch = {}, ""
        self.lines = out.getvalue().splitlines()
        for line in self.lines:
            self.assertRegex(line, LINE_RE)
            if line.startswith(("twin_merge: pair=", "twin_merge: group=", "twin_merge: catalogue_exam=")):
                continue
            for item in line.split()[1:]:
                key, value = item.split("=")
                if key == "batch":
                    batch = value
                else:
                    counts[key] = value
        return counts, batch

    def _detail(self):
        return next(line for line in self.lines if line.startswith("twin_merge: group=typo detail=1"))

    def _subject_of(self, offering):
        with bypass_rls():
            return CourseOffering.objects.get(pk=offering.pk).subject_id

    def _no_journal_conflict(self):
        """Mənbə kartın cari jurnalı başqa qrupdadır — cari toqquşma yoxdur (imtahan qaydası testləri)."""
        with bypass_rls():
            other = OrgUnit.objects.create(
                organization=self.org, name="JBG2", slug="jb-g2", unit_type=OrgUnitType.GROUP
            )
            CourseOffering.objects.filter(pk=self.source.pk).delete()
            self.source = CourseOffering.objects.create(
                organization=self.org, subject=self.typo, group=other, period=self.period, instructor=self.teacher
            )
        self.plan["groups"][0]["pairs"] = []

    def _midterm_on(self, subject):
        exam, options = self._exam()
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(subject=subject)
            exam.refresh_from_db()
            exam.allowed_units.add(self.group)
        return exam, options

    # (b) keçmiş toqquşma bloklamır; cari toqquşma jurnal birləşməsindən keçir, xana itmir
    def test_past_conflict_no_longer_blocks_and_current_journals_merge_without_losing_marks(self):
        with bypass_rls():
            marks_before = LessonMark.objects.count()
        counts, _ = self._call("--only", "journals", "--apply")
        self.assertEqual(counts["pairs_merged"], "1")
        counts, _ = self._call("--only", "catalogue")
        self.assertEqual(counts["catalogue_blocked_offering"], "1")  # köhnə rejim: keçmiş toqquşma bloklayır
        counts, _ = self._call("--only", "catalogue", "--current-only", "--apply")
        self.assertEqual(counts["catalogue_groups_merged"], "1")
        self.assertIn("twin_merge: group=typo catalogue=merged archived=1", self.lines)
        detail = self._detail()
        self.assertIn("keeper=cs101 keeper_name=proqramlasdirma source=qku-77", detail)
        self.assertIn("keeper_rule=plan", detail)
        self.assertIn("offerings_left_past=1", detail)
        with bypass_rls():
            self.assertTrue(Subject.objects.get(pk=self.typo.pk).is_archived)
            self.assertGreaterEqual(LessonMark.objects.count(), marks_before)
            moved = LessonMark.objects.filter(lesson__offering=self.offering, enrollment__student=self.student)
            self.assertEqual(list(moved.values_list("status", flat=True)), ["absent"])
        self.assertEqual(self._subject_of(self.past_typo), self.typo.pk)  # köhnə jurnal yerində
        self.assertEqual(self._subject_of(self.past_keeper), self.subject.pk)
        self.assertEqual(self._subject_of(self.source), self.typo.pk)  # birləşdirilmiş passiv jurnal tarixçədə (K4)

    def test_current_conflict_without_journal_merge_still_blocks(self):
        counts, _ = self._call("--only", "catalogue", "--current-only", "--apply")
        self.assertEqual(counts["catalogue_blocked_offering"], "1")
        self.assertIn("twin_merge: group=typo catalogue=blocked reason=offering", self.lines)
        with bypass_rls():
            self.assertFalse(Subject.objects.get(pk=self.typo.pk).is_archived)

    # (c) imtahan qaydası + nəticə jurnala + (d) paketin geri qaytarılması
    def test_exam_on_one_card_makes_it_the_keeper_relinks_and_undo_restores(self):
        self._no_journal_conflict()
        exam, options = self._midterm_on(self.typo)
        self._finish(exam, options, correct=2)
        counts, batch = self._call("--only", "catalogue", "--current-only", "--apply")
        self.assertEqual(counts["catalogue_keeper_switched_by_exam"], "1")
        self.assertIn("keeper=qku-77", self._detail())
        self.assertIn("keeper_rule=exam exams_kept=1 exams_source=0", self._detail())
        self.assertEqual(counts["catalogue_exams_resynced"], "1")
        with bypass_rls():
            self.assertTrue(Subject.objects.get(pk=self.subject.pk).is_archived)
            self.assertFalse(Subject.objects.get(pk=self.typo.pk).is_archived)
            exam.refresh_from_db()
            self.assertEqual(exam.subject_id, self.typo.pk)
            self.assertIn(self.offering.pk, set(exam.journal_offerings.values_list("pk", flat=True)))
        self.assertEqual(self._subject_of(self.offering), self.typo.pk)
        self.assertEqual(self._subject_of(self.past_keeper), self.subject.pk)  # köhnə jurnal arxiv kartda
        row = self._score_row()
        self.assertIsNotNone(row)  # nəticə jurnala düşdü (66.7% × 30)
        self.assertEqual(int(row.score), 20)

        self._call("--undo", "--batch", batch, "--apply")
        with bypass_rls():
            self.assertFalse(Subject.objects.get(pk=self.subject.pk).is_archived)
            exam.refresh_from_db()
            self.assertEqual(exam.subject_id, self.typo.pk)
        self.assertEqual(self._subject_of(self.offering), self.subject.pk)

    def test_exam_card_whose_journal_was_already_merged_is_skipped(self):
        """Jurnal addımı imtahan kartının cari jurnalını planın kartına birləşdiribsə (K4) imtahan kartı saxlanıla
        bilmir; planın kartı imtahanın fənnini dəyişərdi — qrup ATLANIR, imtahan öz fənnində qalır."""
        exam, _options = self._midterm_on(self.typo)
        self._call("--only", "journals", "--apply")
        counts, _ = self._call("--only", "catalogue", "--current-only", "--apply")
        self.assertNotIn("catalogue_groups_merged", counts)
        self.assertEqual(counts["catalogue_skipped_exam_journal_merged"], "1")
        self.assertIn("twin_merge: group=typo catalogue=skipped reason=exam_journal_merged", self.lines)
        self.assertIn("keeper=qku-77", self._detail())
        with bypass_rls():
            self.assertEqual(Exam.objects.get(pk=exam.pk).subject_id, self.typo.pk)
            self.assertFalse(Subject.objects.get(pk=self.typo.pk).is_archived)
            self.assertFalse(Subject.objects.get(pk=self.subject.pk).is_archived)

    def test_exams_on_both_cards_are_skipped(self):
        self._no_journal_conflict()
        on_keeper, _ = self._midterm_on(self.subject)
        on_source, _ = self._midterm_on(self.typo)
        counts, _ = self._call("--only", "catalogue", "--current-only", "--apply")
        self.assertNotIn("catalogue_groups_merged", counts)
        self.assertEqual(counts["catalogue_skipped_exams_on_both_cards"], "1")
        self.assertIn("twin_merge: group=typo catalogue=skipped reason=exams_on_both_cards", self.lines)
        self.assertIn("keeper_rule=exams_both exams_kept=1 exams_source=1", self._detail())
        with bypass_rls():
            self.assertEqual(Exam.objects.get(pk=on_keeper.pk).subject_id, self.subject.pk)
            self.assertEqual(Exam.objects.get(pk=on_source.pk).subject_id, self.typo.pk)
            self.assertFalse(Subject.objects.get(pk=self.typo.pk).is_archived)
            self.assertEqual(self._subject_of(self.source), self.typo.pk)

    def test_guard_report_still_counts(self):
        counts, _ = self._call("--only", "report")
        for key in ("guard_twin_card_pairs", "guard_same_subject_pairs", "guard_same_name_card_groups"):
            self.assertIn(key, counts)
        self.assertEqual(counts["guard_twin_card_pairs"], "1")  # tələbədə cari dövrdə iki kart
