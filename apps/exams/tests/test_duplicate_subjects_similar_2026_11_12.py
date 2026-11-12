"""Sahib 2026-11-12: 533 Bi ing — «İnformasiya texnologiyaları» + «… (ixtisas üzrə)» eyni qrupda iki jurnal.

Oxşar adlı iki aktiv jurnal bir jurnala enir (qrupun planındakı kart saxlanılır, kartlara toxunulmur, heç bir xana
itmir, paket geri qaytarılır); ikisi də qrupun planındadırsa və ya adlar yalnız rəqəmlə fərqlənirsə toxunulmur.
"""

import datetime
import io

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.registrar import duplicate_subjects_similar_2026_11_12 as similar
from apps.registrar.models import (
    CourseOffering,
    CurriculumSubject,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    Subject,
)
from core.rls import bypass_rls

D1, D2 = datetime.date(2026, 10, 5), datetime.date(2026, 10, 8)
T1 = datetime.time(16, 55)


class SimilarKindTest(SimpleTestCase):
    def test_qualifier_same_typo_and_numbered(self):
        self.assertEqual(
            similar.similar_kind("İnformasiya texnologiyaları", "İnformasiya texnologiyaları (ixtisas üzrə)"),
            "qualifier",
        )
        self.assertEqual(similar.similar_kind("Verilənlər bazası", "Verilenler  bazasi"), "same")
        self.assertEqual(similar.similar_kind("Kompüter şəbəkələri", "Kompüter şəbəkləri"), "typo")
        self.assertEqual(similar.similar_kind("Kompüter qrafikası-1", "Kompüter qrafikası-2"), "")
        self.assertEqual(similar.similar_kind("Xarici dil-1", "Xarici dil-2"), "")
        self.assertEqual(similar.similar_kind("Fizika", "Kimya"), "")


class SimilarJournalsTest(_MidtermSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.offering.subject.name = "İnformasiya texnologiyaları (ixtisas üzrə)"
            self.offering.subject.save(update_fields=["name"])
            self.other = Subject.objects.create(
                organization=self.org, code="QKU-1047", name="İnformasiya texnologiyaları"
            )
            self.source = CourseOffering.objects.create(
                organization=self.org, subject=self.other, group=self.group, period=self.period, instructor=self.teacher
            )
            self.w = Enrollment.objects.create(organization=self.org, student=self.student, offering=self.source)
            self._mark(self._lesson(self.offering, D1), self.enrollment, "present")
            self._mark(self._lesson(self.source, D1), self.w, "present")
            self._mark(self._lesson(self.source, D2), self.w, "absent")

    def _lesson(self, offering, day):
        return Lesson.objects.create(
            organization=self.org, offering=offering, date=day, kind=LessonKind.LECTURE, hours=2, start_time=T1
        )

    def _mark(self, lesson, enrollment, status):
        return LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, status=status)

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
        counts, batch, lines = {}, "", out.getvalue().splitlines()
        for line in lines:
            self.assertRegex(line, r"^twin_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if line.startswith(("twin_merge: similar=", "twin_merge: pair=")):
                continue
            for item in line.split()[1:]:
                key, value = item.split("=")
                batch = value if key == "batch" else batch
                counts[key] = value
        return counts, batch, lines

    def _state(self):
        with bypass_rls():
            self.source.refresh_from_db()
            return (
                self.source.is_active,
                Lesson.objects.filter(offering=self.offering).count(),
                LessonMark.objects.filter(lesson__offering=self.offering).count(),
            )

    def test_dry_run_reports_and_writes_nothing(self):
        counts, _batch, lines = self._call("--only", "similar")
        self.assertEqual(counts["similar_qualifier"], "1")
        self.assertEqual(counts["similar_merge_plan"], "1")
        found = [line for line in lines if line.startswith("twin_merge: similar=")]
        self.assertEqual(len(found), 1)
        self.assertIn(f"source={self.source.pk}", found[0])
        self.assertIn(f"target={self.offering.pk}", found[0])
        self.assertIn("result=merged", found[0])
        self.assertEqual(self._state(), (True, 1, 1))

    def test_apply_merges_into_plan_journal_and_undo_restores(self):
        counts, batch, _lines = self._call("--only", "similar", "--apply")
        self.assertEqual(counts["pairs_merged"], "1")
        self.assertEqual(self._state(), (False, 2, 2))  # D1 eyni dərs, D2 köçdü; W-nin xanaları itmədi
        with bypass_rls():
            self.assertEqual(Subject.objects.filter(pk=self.other.pk, is_archived=False).count(), 1)  # kart qalır
        self._call("--undo", "--batch", batch, "--apply")
        self.assertEqual(self._state(), (True, 1, 1))

    def test_both_in_group_plan_is_left_alone(self):
        with bypass_rls():
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.other, semester_number=1
            )
        counts, _batch, _lines = self._call("--only", "similar", "--apply")
        self.assertEqual(counts["similar_skip_both_in_plan"], "1")
        self.assertNotIn("pairs_merged", counts)
        self.assertEqual(self._state(), (True, 1, 1))

    def test_numbered_parts_are_not_candidates(self):
        with bypass_rls():
            Subject.objects.filter(pk=self.offering.subject_id).update(name="Kompüter qrafikası-1")
            Subject.objects.filter(pk=self.other.pk).update(name="Kompüter qrafikası-2")
        counts, _batch, _lines = self._call("--only", "similar", "--apply")
        self.assertNotIn("similar_qualifier", counts)
        self.assertEqual(self._state(), (True, 1, 1))
