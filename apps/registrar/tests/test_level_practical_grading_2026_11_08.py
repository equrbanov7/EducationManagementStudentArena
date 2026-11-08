"""Xarici dil səviyyə fənləri: 10 / 10 / 10 / 70 hər səthdə + seminar = «Praktiki məşğələ» (sahib 2026-11-08).

Fənlər: «Xarici dildə işgüzar və (akademik) kommunikasiya -1 (Beginner / elementary / pre-intermediate /
intermediate)» və yazın «-2 …» cütləri. Qayda fənn adındandır (:mod:`core.language_level_rule`) — prod-da məlumat
əməliyyatı yoxdur. Adi fənn 10 / 10 / 30 / 50 və «Seminar» olaraq qalır.
"""

import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    CourseOffering,
    FinalGrade,
    Lesson,
    LessonMark,
)
from core import language_level_rule as levels
from core.rls import bypass_rls

LEVEL_NAMES = (
    "Xarici dildə işgüzar və kommunikasiya -1 (Beginner)",
    "Xarici dildə işgüzar və kommunikasiya -1 (elementary)",
    "Xarici dildə işgüzar və kommunikasiya -1 (pre-intermediate)",
    "Xarici dildə işgüzar və kommunikasiya -1 (intermediate)",
    "Xarici dildə işgüzar və akademik kommunikasiya-1(pre-intermadiate)",
    "Xarici dildə işgüzar akademik kommunikasiya-2(elementary)",
    "Xarici dildə işgüzar və kommunikasiya -2 (Beginner)",
    "Xarici dildə işgüzar və kommunikasiya -2 (Pre-Intermediate)",
    "Xarici dildə işgüzar və kommunikasiya -2 (Intermediate)",
)
LEVEL_NAME = "Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)"
REGULAR_NAME = "Proqramlaşdırma"


class LevelRuleRegistryTests(SimpleTestCase):
    def test_all_owner_variants_match_and_regular_subjects_do_not(self):
        for name in LEVEL_NAMES:
            with self.subTest(name=name):
                self.assertTrue(levels.is_level_name(name))
                self.assertTrue(levels.is_practical_name(name))
        for name in (REGULAR_NAME, "Xarici dildə işgüzar və akademik kommunikasiya-1", "İngilis dili (ixtisas)"):
            with self.subTest(name=name):
                self.assertFalse(levels.is_level_name(name))

    def test_caps_are_10_10_10_and_70(self):
        self.assertEqual(
            (levels.ATTENDANCE_MAX, levels.ACTIVITY_MAX, levels.MIDTERM_MAX, levels.ENTRY_MAX, levels.EXAM_MAX),
            (10, 10, 10, 30, 70),
        )

    def test_registrar_aliases_read_the_same_registry(self):
        from apps.registrar import language_level_grading, language_levels

        self.assertIs(language_levels.LEVEL_RE, levels.LEVEL_RE)
        self.assertEqual(language_levels.level_of("X-2 (Pre Intermediate)"), "pre-intermediate")
        self.assertEqual(
            (language_level_grading.MIDTERM_MAX, language_level_grading.EXAM_MAX, language_level_grading.ENTRY_MAX),
            (10, 70, 30),
        )
        self.assertEqual(language_level_grading.exam_cap(REGULAR_NAME, 50), 50)
        self.assertEqual(language_level_grading.exam_cap(LEVEL_NAME, 50), 70)


class LevelSyllabusFormulaTests(SimpleTestCase):
    def test_level_formula_is_10_10_10_70_with_practical_label(self):
        from apps.syllabus.assessment_formula import LEVEL, activity_kinds_for_syllabus, formula_rows, formula_text

        syllabus = SimpleNamespace(subject_id=1, subject=SimpleNamespace(name=LEVEL_NAME), offering=None)
        kinds = activity_kinds_for_syllabus(syllabus)
        self.assertEqual(kinds, (LEVEL,))
        with translation.override("az"):
            rows = formula_rows(kinds, selfwork=True, split=True)  # RİM açarları səviyyə fənninə aid deyil
            self.assertEqual(
                [(row["key"], row["score"]) for row in rows],
                [("attendance", 10), ("midterm", 10), ("activity", 10), ("final", 70)],
            )
            self.assertIn("Praktiki məşğələ", rows[2]["label"])
            text = formula_text(kinds)
            self.assertIn("= 100", text)
            self.assertIn("30", text)
            self.assertIn("70", text)

    def test_regular_formula_keeps_standard(self):
        from apps.syllabus.assessment_formula import formula_rows

        rows = formula_rows(("seminar",), selfwork=False, split=False)
        self.assertEqual(
            [(row["key"], row["score"]) for row in rows],
            [("attendance", 10), ("midterm", 30), ("activity", 10), ("final", 50)],
        )


@override_settings(UNIVERSITY_MODE=True)
class LevelSurfacesTests(TestCase):
    setUpTestData = classmethod(fixtures.ExamScoreEntrySectionTest.setUpTestData.__func__)
    _client = fixtures.ExamScoreEntrySectionTest._client

    def prepare(self, name=LEVEL_NAME):
        with bypass_rls():
            self.subject.name = name
            self.subject.save(update_fields=["name"])
            # Köhnə 50 saxlanılır — hər oxu normallaşdırmalıdır; Midterm komponentinin xam tavanı da 30 qalır.
            AssessmentScheme.objects.update_or_create(
                organization=self.org, offering=self.offering, defaults={"entry_score_max": 50}
            )
            self.period.academic_year = "2026/2027"
            self.period.start_date = "2026-09-01"
            self.period.end_date = "2099-01-31"
            self.period.save()
            component = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
            )
            ComponentScore.objects.create(
                organization=self.org, component=component, enrollment=self.enrollment, score=8
            )
            for index in range(2):
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=self.offering,
                    date=datetime.date(2026, 9, 1) + datetime.timedelta(days=index),
                    kind="seminar",
                    hours=2,
                )
                LessonMark.objects.create(
                    organization=self.org, lesson=lesson, enrollment=self.enrollment, status="present", score=8
                )
            FinalGrade.objects.update_or_create(
                organization=self.org, enrollment=self.enrollment, defaults={"exam_score": Decimal(45)}
            )

    def get(self, user, url):
        with translation.override("az"):
            response = self._client(user).get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def journal_url(self, tab=""):
        url = reverse("registrar:journal_detail", args=[self.offering.pk])
        return f"{url}?jt={tab}" if tab else url

    def test_level_offering_is_practical_without_flag_or_chair(self):
        from apps.registrar import practical_label, practical_toggle

        self.prepare()
        offering = CourseOffering.objects.select_related("subject").get(pk=self.offering.pk)
        self.assertFalse(offering.seminar_is_practical)
        with translation.override("az"):
            self.assertTrue(practical_label.offering_is_practical(offering))
            self.assertEqual(dict(practical_label.kind_choices(offering))["seminar"], "Praktiki məşğələ")
            lesson = Lesson.objects.filter(offering_id=offering.pk).first()
            with self.assertNumQueries(1):  # açılış keşdə deyil — bir sorğu, sonra memo
                self.assertEqual(lesson.get_kind_display(), "Praktiki məşğələ")
                self.assertEqual(lesson.get_kind_display(), "Praktiki məşğələ")
        self.assertIsNone(practical_toggle.context(self.center, offering))

    def test_regular_offering_keeps_seminar_label(self):
        from apps.registrar import practical_label

        self.prepare(REGULAR_NAME)
        offering = CourseOffering.objects.select_related("subject").get(pk=self.offering.pk)
        with translation.override("az"):
            self.assertFalse(practical_label.offering_is_practical(offering))
            lesson = Lesson.objects.filter(offering_id=offering.pk).first()
            self.assertEqual(lesson.get_kind_display(), "Seminar")

    def test_teacher_journal_tabs_show_level_caps_and_practical(self):
        self.prepare()
        grid = self.get(self.teacher, self.journal_url())
        self.assertIn('<option value="seminar">Praktiki məşğələ</option>', grid)
        final = self.get(self.teacher, self.journal_url("yekun"))
        self.assertIn('MIDTERM<div class="jd2-th-sub">/10</div>', final)
        self.assertIn("İMTAHANA QƏDƏR BAL<div>/30</div>", final)
        self.assertIn("Praktiki məşğələ ballarının ədədi ortası", final)
        interim = self.get(self.teacher, self.journal_url("kollokvium"))
        self.assertIn('<span class="jd2-th-sub">/10</span>', interim)

    def test_regular_teacher_journal_keeps_30_and_seminar(self):
        self.prepare(REGULAR_NAME)
        final = self.get(self.teacher, self.journal_url("yekun"))
        self.assertIn('MIDTERM<div class="jd2-th-sub">/30</div>', final)
        self.assertIn("İMTAHANA QƏDƏR BAL<div>/50</div>", final)
        self.assertNotIn("Praktiki məşğələ", final)

    def test_student_results_dashboard_and_subjects_use_level_rule(self):
        self.prepare()
        profile = reverse("accounts:profile")
        results = self.get(self.student, profile + "?section=my-results&results_type=academic")
        self.assertIn('<span class="ems-breakdown__max">/70</span>', results)
        self.assertNotIn('<span class="ems-breakdown__max">/50</span>', results)
        self.assertIn('<span class="ems-breakdown__max">/10</span>', results)  # Midterm /10
        dashboard = self.get(self.student, profile + "?section=dashboard")
        self.assertIn("Midterm — aralıq imtahan (0–10 bal)", dashboard)
        self.assertNotIn("(0–30 bal)", dashboard)
        subjects = self.get(self.student, profile + "?section=my-subjects")
        self.assertIn("Xarici dil səviyyə fənləri", subjects)
        self.assertIn("Aktivlik (praktiki məşğələ)", subjects)
        journal = self.get(self.student, profile + f"?section=my-journal&subject={self.enrollment.pk}")
        self.assertIn("Praktiki məşğələ", journal)

    def test_regular_student_results_keep_50(self):
        self.prepare(REGULAR_NAME)
        profile = reverse("accounts:profile")
        results = self.get(self.student, profile + "?section=my-results&results_type=academic")
        self.assertIn('<span class="ems-breakdown__max">/50</span>', results)
        self.assertNotIn('<span class="ems-breakdown__max">/70</span>', results)
        dashboard = self.get(self.student, profile + "?section=dashboard")
        self.assertIn("(0–30 bal)", dashboard)
        subjects = self.get(self.student, profile + "?section=my-subjects")
        self.assertNotIn("Xarici dil səviyyə fənləri", subjects)

    def test_exam_result_summary_carries_level_exam_max(self):
        from apps.registrar.public import exam_result_summary

        for name, cap in ((LEVEL_NAME, 70), (REGULAR_NAME, 50)):
            with self.subTest(name=name), bypass_rls():
                self.prepare(name)
                summary = exam_result_summary(student=self.student, subject_id=self.subject.pk, organization=self.org)
                self.assertTrue(summary["linked"])
                self.assertEqual(summary["exam_score_max"], cap)
                AssessmentComponent.objects.filter(offering=self.offering).delete()
                Lesson.objects.filter(offering=self.offering).delete()

    def test_syllabus_kinds_for_level_offering(self):
        from apps.syllabus.assessment_formula import LEVEL, activity_kinds_for_offering

        self.prepare()
        offering = CourseOffering.objects.select_related("subject").get(pk=self.offering.pk)
        self.assertEqual(activity_kinds_for_offering(offering), (LEVEL,))


class DashboardNoticeTests(SimpleTestCase):
    def test_mixed_subjects_append_level_caps(self):
        from apps.accounts.views.profile._sections.dashboard_student import _interim_notice

        spec = SimpleNamespace(is_midterm=True, description="Midterm — aralıq imtahan (0–30 bal)")
        with translation.override("az"):
            mixed = _interim_notice(spec, [{"subject_name": LEVEL_NAME}, {"subject_name": REGULAR_NAME}])
            self.assertTrue(mixed.startswith(spec.description))
            self.assertIn("0–10", mixed)
            self.assertIn("0–70", mixed)
            self.assertEqual(_interim_notice(spec, [{"subject_name": REGULAR_NAME}]), spec.description)
