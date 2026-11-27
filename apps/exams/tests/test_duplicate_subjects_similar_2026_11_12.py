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
    def test_qualifier_same_and_lookalikes(self):
        self.assertEqual(
            similar.similar_kind("İnformasiya texnologiyaları", "İnformasiya texnologiyaları (ixtisas üzrə)"),
            "qualifier",
        )
        self.assertEqual(similar.similar_kind("Verilənlər bazası", "Verilenler  bazasi"), "same")
        self.assertEqual(similar.similar_kind("Kompüter şəbəkələri", "Kompüter şəbəkləri"), "")
        self.assertEqual(similar.similar_kind("Kompüter qrafikası-1", "Kompüter qrafikası-2"), "")
        self.assertEqual(similar.similar_kind("Xarici dil-1", "Xarici dil-2"), "")
        self.assertEqual(similar.similar_kind("Fizika", "Kimya"), "")
        # prod dry-run 2026-11-12: iki hərf fərqi, amma FƏRQLİ fənlər
        self.assertEqual(
            similar.similar_kind("Kəmiyyət əsaslı tədqiqat metodları", "Keyfiyyət əsaslı tədqiqat metodları"), ""
        )

    def test_genitive_inflection_2026_11_27(self):
        self.assertEqual(
            similar.similar_kind("Verilənlər bazası sistemləri", "Verilənlərin bazası sistemləri"), "inflection"
        )
        self.assertEqual(similar.similar_kind("Kompüterlər şəbəkəsi", "Kompüterlərin şəbəkəsi"), "inflection")
        # hərf səhvi, rəqəm, fərqli söz sayı — oxşar deyil
        self.assertEqual(similar.similar_kind("Verilənlər bazası sistemləri", "Verilənlər bazası sitemləri"), "")
        self.assertEqual(similar.similar_kind("Verilənlər bazası", "Verilənlərin bazası sistemləri"), "")
        self.assertEqual(similar.similar_kind("Dil-1", "Dil-1in"), "")


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

    def test_student_pairs_report_reads_only_2026_11_27(self):
        with bypass_rls():
            Subject.objects.filter(pk=self.offering.subject_id).update(name="Verilənlər bazası sistemləri")
            Subject.objects.filter(pk=self.other.pk).update(name="Verilənlərin bazası sistemləri")
            before = self._state()
        counts, _batch, lines = self._call("--only", "student_pairs")
        self.assertEqual(counts["student_pairs_inflection"], "1")
        self.assertEqual(counts["student_pairs_students"], "1")
        self.assertTrue(any("kind=inflection" in line and "students=1" in line for line in lines))
        self.assertEqual(self._state(), before)
        from django.core.management import CommandError

        with self.assertRaisesMessage(CommandError, "duplicate_subjects_apply_needs_explicit_step"):
            self._call("--only", "student_pairs", "--apply")

    def test_student_merge_subgroup_journal_into_parent_and_undo_2026_11_27(self):
        from apps.organizations.models import OrgUnit

        with bypass_rls():
            Subject.objects.filter(pk=self.offering.subject_id).update(name="Verilənlər bazası sistemləri")
            Subject.objects.filter(pk=self.other.pk).update(name="Fizika")  # aynı qrupun cütü namizəd olmasın
            third = Subject.objects.create(organization=self.org, code="QKU-267", name="Verilənlərin bazası sistemləri")
            sub = OrgUnit.objects.create(
                organization=self.org,
                name="Alt-1",
                slug="alt-1-x",
                unit_type=self.group.unit_type,
                parent=self.group.parent,
            )
            sub_off = CourseOffering.objects.create(
                organization=self.org, subject=third, group=sub, period=self.period, instructor=self.teacher
            )
            row = Enrollment.objects.create(organization=self.org, student=self.student, offering=sub_off)
            self._mark(self._lesson(sub_off, D2), row, "absent")
            # Ana jurnalda alt qrupdan başqa tələbə də var (234 K az = K-1 + K-2).
            from django.contrib.auth import get_user_model

            from apps.organizations.models import Membership

            mate = get_user_model().objects.create_user("sim_mate", "sim_mate@x.test", "pw")
            Membership.objects.create(
                organization=self.org, user=mate, role=self.org.roles.get(name="student"), is_active=True
            )
            Enrollment.objects.create(organization=self.org, student=mate, offering=self.offering)

        def state():
            with bypass_rls():
                sub_off.refresh_from_db()
                return sub_off.is_active, LessonMark.objects.filter(lesson__offering=self.offering).count()

        counts, _batch, lines = self._call("--only", "student_merge")
        self.assertEqual(counts["student_pairs_mergeable"], "1")
        self.assertTrue(any(f"target={self.offering.pk}" in line and "result=merged" in line for line in lines), lines)
        self.assertEqual(state(), (True, 1))  # dry-run
        counts, batch, _lines = self._call("--only", "student_merge", "--apply")
        self.assertEqual(counts["pairs_merged"], "1")
        self.assertEqual(state(), (False, 2))  # D2 qayıbı ana jurnala keçdi, alt qrup jurnalı passiv
        self._call("--undo", "--batch", batch, "--apply")
        self.assertEqual(state(), (True, 1))

    def test_student_merge_skips_when_teachers_differ(self):
        with bypass_rls():
            Subject.objects.filter(pk=self.offering.subject_id).update(name="Verilənlər bazası sistemləri")
            Subject.objects.filter(pk=self.other.pk).update(name="Verilənlərin bazası sistemləri")
            CourseOffering.objects.filter(pk=self.source.pk).update(instructor=self.owner)
        counts, _batch, _lines = self._call("--only", "student_merge", "--apply")
        self.assertEqual(counts["student_pairs_manual"], "1")
        self.assertNotIn("pairs_merged", counts)
        self.assertEqual(self._state(), (True, 1, 1))

    def test_numbered_parts_are_not_candidates(self):
        with bypass_rls():
            Subject.objects.filter(pk=self.offering.subject_id).update(name="Kompüter qrafikası-1")
            Subject.objects.filter(pk=self.other.pk).update(name="Kompüter qrafikası-2")
        counts, _batch, _lines = self._call("--only", "similar", "--apply")
        self.assertNotIn("similar_qualifier", counts)
        self.assertEqual(self._state(), (True, 1, 1))
