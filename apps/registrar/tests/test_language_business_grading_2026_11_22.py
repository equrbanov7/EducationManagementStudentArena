"""«Xarici dildə işgüzar kommunikasiya -1/-2/-3» — sərbəst iş 10 + davamiyyət 10 + midterm 10, final 70 (sahib 2026-11-22).

Profil səviyyə fənlərinin alt dəstidir (:mod:`core.language_business_rule`): aktivlik (praktiki məşğələ ortası) yerinə
sərbəst iş sayılır, müəllim Midterm xanasını pəncərəsiz yazır (0–10), imtahan körpüləri səviyyə qaydasından (midterm
10-a miqyaslanır, final 70). RİM açarı söndürüləndə fənn adi səviyyə qaydasına qayıdır; adi fənlər dəyişmir.
"""

import datetime
from decimal import Decimal
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    CourseOffering,
    Enrollment,
    FinalGrade,
    Lesson,
    LessonMark,
    SelfWorkMark,
    SelfWorkTopic,
)
from core import language_business_rule as rule
from core import language_level_rule as levels
from core.rls import bypass_rls, journal_unlock

LEVELS = ("Beginner", "elementary", "pre-intermediate", "intermediate")
OWNER_NAMES = tuple(
    f"Xarici dildə işgüzar və kommunikasiya -{number} ({level})" for number in (1, 2, 3) for level in LEVELS
)
CATALOG_VARIANTS = (
    "Xarici dildə işgüzar və akademik kommunikasiya-1(pre-intermadiate)",
    "Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)",
    "Xarici dildə işgüzar akademik kommunikasiya-2(elementary)",
    "XARİCİ DİLDƏ İŞGÜZAR VƏ KOMMUNİKASİYA – 2 (INTERMEDIATE)",
    "Xarici dilde isguzar ve kommunikasiya 3 (Pre Intermediate)",
    "  Xarici  dildə işgüzar və kommunikasiya-3 ( Beginner )  ",
)
#: Sahib 2026-11-22 (2): prod-da səviyyəsiz cari jurnallar — «…-1» (27), «…-2» (45), «…-3» (1) + boşluq variantları.
NOLEVEL_NAMES = (
    "Xarici dildə işgüzar və akademik kommunikasiya-1",
    "Xarici dildə işgüzar və akademik kommunikasiya-2",
    "Xarici dildə işgüzar və akademik kommunikasiya-3",
    "Xarici dildə işgüzar və akademik kommunikasiya -3",
    "Xarici dildə işgüzar və akademik kommunikasiya - 2",
    "xarici dildə işgüzar və kommunikasiya 1",
)
NEGATIVES = (
    "Xarici dil-1",
    "Xarici dil-1(elementary)",
    "İşgüzar yazışmalar",
    "Azərbaycan dilində işgüzar və akademik kommunikasiya-1",
    "Xarici dildə işgüzar və akademik kommunikasiya",
    "Xarici dildə işgüzar və akademik kommunikasiya-1 (A1)",
    "Xarici dildə işgüzar və kommunikasiya -1 (upper-intermediate)",
    "Xarici dildə işgüzar və kommunikasiya -4 (Beginner)",
    "Xarici dildə işgüzar və kommunikasiya -12 (Beginner)",
    "Azərbaycan dilində işgüzar və akademik kommunikasiya",
    "Proqramlaşdırma",
)
BUSINESS_NAME = "Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)"
NOLEVEL_NAME = "Xarici dildə işgüzar və akademik kommunikasiya -2"
OTHER_LEVEL_NAME = "Xarici dildə kommunikasiya-1(intermediate)"
REGULAR_NAME = "Proqramlaşdırma"


class BusinessNameRuleTests(SimpleTestCase):
    def test_all_twelve_owner_names_and_catalog_variants_match(self):
        self.assertEqual(len(OWNER_NAMES), 12)
        for name in (*OWNER_NAMES, *CATALOG_VARIANTS):
            with self.subTest(name=name):
                self.assertTrue(rule.is_business_name(name))
                self.assertTrue(levels.is_level_name(name))  # profil səviyyə fənlərinin alt dəstidir

    def test_nolevel_names_match_grading_but_not_cohort_grouping(self):
        from apps.registrar import language_level_grading, language_levels

        for name in NOLEVEL_NAMES:
            with self.subTest(name=name):
                self.assertTrue(rule.is_business_name(name))
                self.assertTrue(rule.is_nolevel_business_name(name))
                self.assertTrue(rule.graded_level_name(name))
                self.assertTrue(language_level_grading.is_graded_name(name))
                self.assertTrue(levels.is_practical_name(name))  # «Praktiki məşğələ» etiketi
                # Kohort / səviyyə qrupu məntiqi dəyişmir.
                self.assertEqual(levels.level_of(name), "")
                self.assertFalse(levels.is_level_name(name))
                self.assertFalse(language_levels.is_level_subject(name))
                self.assertFalse(language_level_grading.is_level_name(name))
        with override_settings(ACADEMIC_LANGUAGE_BUSINESS_PROFILE=False):
            self.assertFalse(rule.graded_level_name(NOLEVEL_NAME))
            self.assertTrue(rule.graded_level_name(BUSINESS_NAME))  # səviyyəli ad səviyyə qaydasında qalır

    def test_negatives(self):
        for name in NEGATIVES:
            with self.subTest(name=name):
                self.assertFalse(rule.is_business_name(name))
                if not levels.is_level_name(name):
                    self.assertFalse(rule.graded_level_name(name))
        self.assertFalse(rule.is_business_name(OTHER_LEVEL_NAME))
        self.assertTrue(levels.is_level_name(OTHER_LEVEL_NAME))

    def test_caps_total_100(self):
        self.assertEqual(
            (rule.SELFWORK_MAX, rule.ATTENDANCE_MAX, rule.MIDTERM_MAX, rule.ENTRY_MAX, rule.EXAM_MAX),
            (10, 10, 10, 30, 70),
        )
        self.assertEqual(rule.ENTRY_MAX + rule.EXAM_MAX, 100)
        self.assertEqual((rule.MIDTERM_MAX, rule.EXAM_MAX), (levels.MIDTERM_MAX, levels.EXAM_MAX))

    def test_runtime_switch(self):
        from core import runtime_settings

        self.assertIn(rule.SETTING_KEY, runtime_settings.SPECS)
        self.assertEqual(runtime_settings.SPECS[rule.SETTING_KEY].group, "academic")
        self.assertTrue(rule.applies_to_name(BUSINESS_NAME))
        with override_settings(ACADEMIC_LANGUAGE_BUSINESS_PROFILE=False):
            self.assertFalse(rule.applies_to_name(BUSINESS_NAME))
            self.assertTrue(rule.is_business_name(BUSINESS_NAME))


@override_settings(UNIVERSITY_MODE=True)
class BusinessProfileTests(TestCase):
    setUpTestData = classmethod(fixtures.ExamScoreEntrySectionTest.setUpTestData.__func__)
    _client = fixtures.ExamScoreEntrySectionTest._client

    def prepare(self, name=BUSINESS_NAME, *, selfwork_points=6, midterm=8, practical=9):
        """2026/2027 dövrü, Midterm 8, iki praktiki məşğələ balı 9, sərbəst iş 6, final 45."""
        with bypass_rls():
            self.subject.name = name
            self.subject.save(update_fields=["name"])
            AssessmentScheme.objects.update_or_create(
                organization=self.org, offering=self.offering, defaults={"entry_score_max": 50}
            )
            self.period.academic_year = "2026/2027"
            self.period.start_date = "2026-09-01"
            self.period.end_date = "2099-01-31"
            self.period.save()
            self.midterm = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
            )
            if midterm is not None:
                ComponentScore.objects.create(
                    organization=self.org, component=self.midterm, enrollment=self.enrollment, score=midterm
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
                    organization=self.org, lesson=lesson, enrollment=self.enrollment, status="present", score=practical
                )
            AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Sərbəst iş", kind="self_work", max_score=10
            )
            topic = SelfWorkTopic.objects.create(
                organization=self.org, offering=self.offering, title="Esse", max_points=10, slot_index=1
            )
            if selfwork_points:
                SelfWorkMark.objects.create(
                    organization=self.org,
                    topic=topic,
                    enrollment=self.enrollment,
                    done=True,
                    points=Decimal(selfwork_points),
                )
            FinalGrade.objects.update_or_create(
                organization=self.org, enrollment=self.enrollment, defaults={"exam_score": Decimal(45)}
            )

    def offering_fresh(self):
        return CourseOffering.objects.select_related("subject", "period", "organization").get(pk=self.offering.pk)

    def enrollment_fresh(self):
        return Enrollment.objects.select_related("offering__subject", "offering__period").get(pk=self.enrollment.pk)

    def parts(self):
        from apps.registrar import gradebook_components

        return gradebook_components.entry_parts_for(self.enrollment_fresh(), 50)

    # ── Komponentlər / hesab ────────────────────────────────────────────────
    def test_business_practical_plus_selfwork_capped_at_10(self):
        from apps.registrar import language_business_grading

        self.prepare()  # praktiki ortası 9 + sərbəst iş 6 = 15 → 10
        with bypass_rls():
            self.assertTrue(language_business_grading.is_business(self.offering_fresh()))
            parts = self.parts()
        self.assertTrue(parts.practical_selfwork)
        self.assertEqual(parts.activity, Decimal(10))
        self.assertEqual(parts.activity_parts, (Decimal(9), Decimal(6)))
        self.assertEqual(parts.selfwork, 0)
        self.assertFalse(parts.selfwork_active)  # ayrıca sütun yoxdur — bir «Praktiki / sərbəst iş» sütunu
        self.assertEqual(parts.midterm, Decimal(8))
        self.assertEqual(parts.midterm_max, Decimal(10))
        self.assertEqual(parts.total, parts.attendance + Decimal(18))

    def test_business_practical_average_counts_like_seminar(self):
        self.prepare(selfwork_points=0, practical=7)
        with bypass_rls():
            parts = self.parts()
        self.assertEqual(parts.activity, Decimal(7))
        self.assertEqual(parts.activity_parts, (Decimal(7), Decimal(0)))
        self.assertEqual(parts.total, parts.attendance + Decimal(15))

    def test_business_practical_and_selfwork_add_below_cap(self):
        self.prepare(selfwork_points=4, practical=3)
        with bypass_rls():
            parts = self.parts()
        self.assertEqual(parts.activity, Decimal(7))

    def test_nolevel_offering_gets_full_profile(self):
        from apps.registrar import (
            exam_score_assessment,
            interim_components,
            language_business_grading,
            language_level_grading,
            student_display_policy,
        )

        self.prepare(NOLEVEL_NAME, midterm=None)
        with bypass_rls():
            offering = self.offering_fresh()
            self.assertTrue(language_level_grading.is_level(offering))
            self.assertTrue(language_business_grading.is_business(offering))
            self.assertEqual(exam_score_assessment.cap_for(offering, exam_score_assessment.FINAL), 70)
            self.assertEqual(exam_score_assessment.cap_for(offering, exam_score_assessment.MIDTERM), 10)
            self.assertEqual(student_display_policy.entry_cap(offering, None), 30)
            grid = interim_components.get_kollokvium_grid(offering)
            self.assertTrue(grid["teacher_write"])
            self.assertEqual(grid["components"][0].max_score, 10)
            parts = self.parts()
        self.assertEqual(parts.activity, Decimal(10))
        self.assertEqual(parts.midterm_max, Decimal(10))
        self.post_midterm(9)
        self.assertEqual(self.cell(), Decimal(9))
        self.post_midterm(11)
        self.assertEqual(self.cell(), Decimal(9))

    @override_settings(ACADEMIC_LANGUAGE_BUSINESS_PROFILE=False)
    def test_nolevel_switch_off_is_university_standard(self):
        from apps.registrar import exam_score_assessment, language_level_grading

        self.prepare(NOLEVEL_NAME)
        with bypass_rls():
            offering = self.offering_fresh()
            self.assertFalse(language_level_grading.is_level(offering))
            self.assertEqual(exam_score_assessment.cap_for(offering, exam_score_assessment.FINAL), 50)
            parts = self.parts()
        self.assertEqual(parts.midterm_max, Decimal(30))

    def test_business_final_result_totals_100_with_exam_70(self):
        from apps.registrar import exam_score_assessment, finals, gradebook

        self.prepare(selfwork_points=10, midterm=10)
        with bypass_rls():
            FinalGrade.objects.filter(enrollment=self.enrollment).update(exam_score=Decimal(70))
            offering = self.offering_fresh()
            self.assertEqual(exam_score_assessment.cap_for(offering, exam_score_assessment.FINAL), 70)
            self.assertEqual(exam_score_assessment.cap_for(offering, exam_score_assessment.MIDTERM), 10)
            self.assertEqual(finals.exam_score_max(gradebook.ensure_assessment_scheme(offering=offering)), 70)
            result = finals.compute_final_result(enrollment=self.enrollment_fresh(), organization=self.org)
        self.assertEqual(result["entry_score"], Decimal(30))
        self.assertEqual(result["total"], Decimal(100))

    def test_batch_path_matches_single_row_path(self):
        from apps.registrar import finals_batch, gradebook

        for name, selfwork, practical in ((BUSINESS_NAME, 6, 9), (NOLEVEL_NAME, 2, 5)):
            with self.subTest(name=name):
                with bypass_rls():
                    SelfWorkMark.objects.filter(enrollment=self.enrollment).delete()
                    SelfWorkTopic.objects.filter(offering=self.offering).delete()
                    ComponentScore.objects.filter(enrollment=self.enrollment).delete()
                    AssessmentComponent.objects.filter(offering=self.offering).delete()
                    LessonMark.objects.filter(enrollment=self.enrollment).delete()
                    Lesson.objects.filter(offering=self.offering).delete()
                self.prepare(name, selfwork_points=selfwork, practical=practical)
                with bypass_rls():
                    single = gradebook.entry_score_for(self.enrollment_fresh(), 50)
                    enrollment = self.enrollment_fresh()
                    batch = finals_batch.build([enrollment], with_finals=True)
                    batched = gradebook.entry_score_for(enrollment, 50, **batch.entry_kwargs(enrollment))
                self.assertEqual(single, batched)

    @override_settings(ACADEMIC_LANGUAGE_BUSINESS_PROFILE=False)
    def test_switch_off_returns_to_level_rule(self):
        self.prepare()
        with bypass_rls():
            parts = self.parts()
        self.assertEqual(parts.activity, Decimal(9))  # praktiki məşğələ ortası
        self.assertFalse(parts.practical_selfwork)
        self.assertEqual(parts.selfwork, 0)
        self.assertFalse(parts.selfwork_active)

    def test_other_level_subject_keeps_practical_activity(self):
        self.prepare(OTHER_LEVEL_NAME)
        with bypass_rls():
            parts = self.parts()
        self.assertEqual(parts.activity, Decimal(9))
        self.assertFalse(parts.selfwork_active)
        self.assertEqual(parts.midterm_max, Decimal(10))

    def test_regular_offering_unchanged(self):
        from apps.registrar import exam_score_assessment, language_business_grading

        self.prepare(REGULAR_NAME)
        with bypass_rls():
            offering = self.offering_fresh()
            self.assertFalse(language_business_grading.is_business(offering))
            parts = self.parts()
            self.assertEqual(exam_score_assessment.cap_for(offering, exam_score_assessment.FINAL), 50)
        self.assertEqual(parts.midterm_max, Decimal(30))
        self.assertFalse(parts.selfwork_active)  # sərbəst iş RİM-də söndürülü (defolt)
        self.assertFalse(parts.practical_selfwork)
        self.assertEqual(parts.activity, Decimal(9))

    def test_selfwork_active_only_for_business(self):
        from core import academic_rules

        self.prepare()
        with bypass_rls():
            self.assertFalse(academic_rules.selfwork_enabled())
            self.assertTrue(academic_rules.selfwork_active_for_offering(self.offering_fresh()))
            self.subject.name = REGULAR_NAME
            self.subject.save(update_fields=["name"])
            self.assertFalse(academic_rules.selfwork_active_for_offering(self.offering_fresh()))

    # ── Midterm xanası (müəllim) ────────────────────────────────────────────
    def save_url(self):
        return reverse("registrar:journal_kollokvium_save", args=[self.offering.pk])

    def post_midterm(self, value):
        key = f"kscore__{self.midterm.pk}__{self.enrollment.pk}"
        return self._client(self.teacher).post(self.save_url(), {key: str(value)})

    def cell(self):
        with bypass_rls():
            row = ComponentScore.objects.filter(component=self.midterm, enrollment=self.enrollment).first()
        return None if row is None else row.score

    def test_teacher_writes_midterm_without_window_0_to_10(self):
        from apps.registrar import interim_components

        self.prepare(midterm=None)
        with bypass_rls():
            grid = interim_components.get_kollokvium_grid(self.offering_fresh())
        self.assertTrue(grid["teacher_write"])
        self.assertTrue(grid["any_writable"])
        self.assertFalse(grid["any_open"])
        self.assertTrue(grid["rows"][0]["cells"][0]["editable"])
        self.assertEqual(grid["components"][0].max_score, 10)
        self.post_midterm(7)
        self.assertEqual(self.cell(), Decimal(7))
        self.post_midterm(11)  # tavandan böyük — rədd, əvvəlki bal qalır
        self.assertEqual(self.cell(), Decimal(7))
        self.post_midterm(0)
        self.assertEqual(self.cell(), Decimal(0))

    def test_teacher_cell_locks_after_edit_window(self):
        from apps.registrar import interim_components

        self.prepare(midterm=None)
        self.post_midterm(6)
        self.assertEqual(self.cell(), Decimal(6))
        with bypass_rls(), journal_unlock():
            ComponentScore.objects.filter(component=self.midterm).update(
                created_at=timezone.now() - datetime.timedelta(days=2)
            )
        self.post_midterm(9)
        self.assertEqual(self.cell(), Decimal(6))
        with bypass_rls():
            grid = interim_components.get_kollokvium_grid(self.offering_fresh())
        self.assertFalse(grid["rows"][0]["cells"][0]["editable"])

    def test_regular_offering_midterm_needs_window(self):
        from apps.registrar import interim_components

        self.prepare(REGULAR_NAME, midterm=None)
        with bypass_rls():
            grid = interim_components.get_kollokvium_grid(self.offering_fresh())
        self.assertFalse(grid["teacher_write"])
        self.assertFalse(grid["any_writable"])
        self.post_midterm(7)
        self.assertIsNone(self.cell())

    def test_midterm_transfer_lands_on_10_scale(self):
        from apps.registrar import midterm_bridge

        self.prepare(midterm=None)
        with bypass_rls():
            status, cell = midterm_bridge.record_midterm_result(
                student=self.student,
                subject_id=self.subject.pk,
                organization=self.org,
                score_percent=Decimal("84"),
                attempt_id=2211,
                notify=False,
                by_user=self.center,
            )
        self.assertEqual(status, midterm_bridge.WRITTEN)
        self.assertEqual(cell.component_id, self.midterm.pk)
        self.assertEqual(cell.score, Decimal(8))  # 84 % × 10 = 8,4 → 8 (yarım-yuxarı)

    # ── Səthlər ─────────────────────────────────────────────────────────────
    def get(self, user, url):
        with translation.override("az"):
            response = self._client(user).get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def journal_url(self, tab=""):
        url = reverse("registrar:journal_detail", args=[self.offering.pk])
        return f"{url}?jt={tab}" if tab else url

    def test_teacher_journal_tabs(self):
        self.prepare()
        final = self.get(self.teacher, self.journal_url("yekun"))
        self.assertIn('MIDTERM<div class="jd2-th-sub">/10</div>', final)
        self.assertIn("İMTAHANA QƏDƏR BAL<div>/30</div>", final)
        self.assertIn('class="jd2-fb-semhead">Praktiki / sərbəst iş', final)
        self.assertNotIn("SƏRBƏST İŞ", final)
        self.assertIn("Giriş balı = davamiyyət + Midterm + praktiki / sərbəst iş", final)
        interim = self.get(self.teacher, self.journal_url("kollokvium"))
        self.assertIn("data-jd-teacher-midterm", interim)
        self.assertIn('name="kscore__', interim)
        selfwork = self.get(self.teacher, self.journal_url("serbest"))
        self.assertIn('id="jd-panel-serbest"', selfwork)

    def test_regular_teacher_journal_unchanged(self):
        self.prepare(REGULAR_NAME)
        final = self.get(self.teacher, self.journal_url("yekun"))
        self.assertIn('MIDTERM<div class="jd2-th-sub">/30</div>', final)
        self.assertNotIn("SƏRBƏST İŞ", final)
        interim = self.get(self.teacher, self.journal_url("kollokvium"))
        self.assertNotIn("data-jd-teacher-midterm", interim)

    def test_student_subjects_show_business_weights(self):
        self.prepare()
        subjects = self.get(self.student, reverse("accounts:profile") + "?section=my-subjects")
        self.assertIn("data-business-weights", subjects)
        self.assertIn("Xarici dildə işgüzar kommunikasiya", subjects)
        self.assertIn("Praktiki / sərbəst iş", subjects)
        self.assertNotIn("Aktivlik (praktiki məşğələ)", subjects)

    # ── Audit əmri ──────────────────────────────────────────────────────────
    def test_audit_command_counts_only(self):
        self.prepare()
        out = StringIO()
        call_command("audit_language_business_grading_20261122", org=self.org.slug, stdout=out)
        lines = out.getvalue().strip().splitlines()
        self.assertTrue(all(line.startswith("language_business: ") for line in lines))
        text = out.getvalue()
        self.assertIn("applied=1", text)
        self.assertIn("components_max_above_ten=1", text)  # xam tavan 30 qalıb (yenidən miqyaslanmır)
        self.assertIn("seminar_scores=2", text)
        self.assertIn("marks=1", text)
        self.assertIn("nolevel_applied=0", text)
        self.assertNotIn(self.student.username, text)
        with bypass_rls():
            self.assertEqual(ComponentScore.objects.get(component=self.midterm).score, Decimal(8))

    def test_audit_command_refuses_apply_and_unknown_org(self):
        with self.assertRaisesMessage(CommandError, "read_only_command_no_apply"):
            call_command("audit_language_business_grading_20261122", org=self.org.slug, apply=True, stdout=StringIO())
        with self.assertRaisesMessage(CommandError, "organization_not_found"):
            call_command("audit_language_business_grading_20261122", org="yoxdur", stdout=StringIO())


class AuditFailureCodeTests(SimpleTestCase):
    def test_failure_code_is_sanitized(self):
        from apps.registrar.management.commands import audit_language_business_grading_20261122 as command

        self.assertEqual(command.failure_code(KeyError("x")), "language_business_audit_failed_keyerror")
