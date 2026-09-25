"""Nəticə API-si — əhatə (kafedra müdiri / rektor), k-gizlətmə, tamamlayıcı qayda, şərhlər."""

from __future__ import annotations

from django.test import TestCase

from apps.registrar.models import CourseOffering, Enrollment
from apps.surveys import public
from apps.surveys.forms import validate_answers
from apps.surveys.services.submit import submit_target
from apps.surveys.services.targets import student_targets
from apps.surveys.services.templates import template_questions
from core.rls import bypass_rls

from .factories import build_world, close_journal, member, open_campaign


def _answers(template, section, *, score, overall, text=""):
    questions = template_questions(template, section=section)
    data = {}
    for question in questions:
        if question.kind == "likert5":
            data[f"q_{question.code}"] = str(score)
        elif question.kind == "scale10":
            data[f"q_{question.code}"] = str(overall)
        elif text:
            data[f"q_{question.code}"] = text
    cleaned, errors, _values = validate_answers(questions, data)
    assert not errors, errors
    return cleaned


class ResultsApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        w = cls.w = build_world("svres", students=4)
        with bypass_rls():
            # Fizika müəllimi B-nin ikinci qrupda (1 tələbə) açılışı — tamamlayıcı qayda üçün.
            from apps.organizations.models import OrgUnit
            from core.constants import OrgUnitType

            cls.group2 = OrgUnit.objects.create(
                organization=w["org"], name="G-102", slug="svres-g2", unit_type=OrgUnitType.GROUP, parent=w["chair_b"]
            )
            cls.off_phys2 = CourseOffering.objects.create(
                organization=w["org"],
                subject=w["phys"],
                period=w["period"],
                group=cls.group2,
                instructor=w["teacher_b"],
            )
            cls.lonely = member(w["org"], "svres_lonely", "student")
            Enrollment.objects.create(organization=w["org"], student=cls.lonely, offering=cls.off_phys2)
            # Ümumi bölmə snapshot-u tələbənin akademik qeydindən (qrup) gəlir.
            from apps.registrar.models import Curriculum, Program, StudentAcademicRecord

            program = Program.objects.get(organization=w["org"])
            curriculum = Curriculum.objects.create(organization=w["org"], program=program, admission_year=2025)
            for student, group in [(s, w["group"]) for s in w["students"]] + [(cls.lonely, cls.group2)]:
                StudentAcademicRecord.objects.create(
                    organization=w["org"],
                    student=student,
                    program=program,
                    curriculum=curriculum,
                    group=group,
                    admission_year=2025,
                )
            for offering in (w["off_math"], w["off_phys"], cls.off_phys2):
                close_journal(w["org"], offering)
            cls.campaign = open_campaign(w)
            template = cls.campaign.template
            for index, student in enumerate(w["students"] + [cls.lonely]):
                for target in student_targets(cls.campaign, student):
                    if target.is_general:
                        cleaned = _answers(template, "general", score=4, overall=0, text=f"Kitabxana təklifi {index}")
                    elif target.teacher_id == w["teacher_c"].pk and index >= 2:
                        continue  # müəllim C: yalnız 2 cavab (< k)
                    else:
                        cleaned = _answers(template, "teacher", score=5, overall=8, text=f"Şərh {index}")
                    submit_target(campaign=cls.campaign, student=student, target=target, cleaned_answers=cleaned)
            cls.rector = member(w["org"], "svres_rector", "rector")
            cls.chair_head = member(w["org"], "svres_chair", "chair_head", unit=w["chair_a"])
            cls.qc_staff = member(w["org"], "svres_qc", "quality_control_staff")
            cls.dean = member(w["org"], "svres_dean", "dean", unit=w["faculty"])

    def _scope(self, user):
        with bypass_rls():
            return public.results_scope(user, self.w["org"])

    def _table(self, user, **filters):
        with bypass_rls():
            return public.teacher_table(self.w["org"], self._scope(user), public.ResultFilters(**filters))

    def test_rector_and_quality_staff_see_whole_organization(self):
        for user in (self.rector, self.qc_staff):
            rows = {row["teacher_id"]: row for row in self._table(user)["rows"]}
            self.assertEqual(
                set(rows), {self.w["teacher_a"].pk, self.w["teacher_b"].pk, self.w["teacher_c"].pk}, user.username
            )

    def test_chair_head_sees_only_own_kafedra(self):
        rows = {row["teacher_id"] for row in self._table(self.chair_head)["rows"]}
        self.assertEqual(rows, {self.w["teacher_a"].pk, self.w["teacher_c"].pk})
        with bypass_rls():
            detail = public.teacher_detail(self.w["org"], self._scope(self.chair_head), self.w["teacher_b"].pk)
        self.assertFalse(detail["found"])

    def test_dean_without_grant_has_no_access(self):
        self.assertFalse(self._scope(self.dean).has_structure_access)
        self.assertEqual(self._table(self.dean)["rows"], [])

    def test_small_groups_are_suppressed(self):
        rows = {row["teacher_id"]: row for row in self._table(self.rector)["rows"]}
        c_row = rows[self.w["teacher_c"].pk]
        self.assertEqual(c_row["n"], 2)
        self.assertTrue(c_row["suppressed"])
        self.assertIsNone(c_row["avg_overall"])
        a_row = rows[self.w["teacher_a"].pk]
        self.assertFalse(a_row["suppressed"])
        self.assertEqual(a_row["avg_overall"], 8.0)
        self.assertEqual(a_row["likert_index"], 5.0)
        self.assertEqual(a_row["recommend_top2"], 1.0)

    def test_complement_rule_hides_narrowed_slice_that_would_expose_the_rest(self):
        # B: 4 cavab G-101-də + 1 cavab G-102-də. G-101 filtri n=4 ≥ k, amma 5−4=1 < k.
        rows = {row["teacher_id"]: row for row in self._table(self.rector, group_id=self.w["group"].pk)["rows"]}
        self.assertEqual(rows[self.w["teacher_b"].pk]["n"], 4)
        self.assertTrue(rows[self.w["teacher_b"].pk]["suppressed"])
        with bypass_rls():
            detail = public.teacher_detail(self.w["org"], self._scope(self.rector), self.w["teacher_b"].pk)
        per_group = {row["group_name"]: row for row in detail["offerings"]}
        self.assertTrue(per_group["G-101"]["suppressed"])  # 5 − 4 = 1 < k
        self.assertTrue(per_group["G-102"]["suppressed"])  # 1 < k
        self.assertFalse(detail["suppressed"])  # müəllimin ümumi nəticəsi (5) görünür

    def test_teacher_detail_comments_only_above_threshold_and_without_identifiers(self):
        with bypass_rls():
            detail_a = public.teacher_detail(self.w["org"], self._scope(self.rector), self.w["teacher_a"].pk)
            detail_c = public.teacher_detail(self.w["org"], self._scope(self.rector), self.w["teacher_c"].pk)
        self.assertEqual(len(detail_a["comments"]), 8)  # 4 tələbə × (strengths + improve)
        self.assertEqual(set(detail_a["comments"][0]), {"question_code", "text"})
        self.assertEqual(detail_c["comments"], [])
        self.assertEqual(detail_a["distributions"]["overall"], {8: 4})

    def test_summary_participation_and_questions(self):
        with bypass_rls():
            data = public.summary(self.w["org"], self._scope(self.rector), public.ResultFilters())
        # Gözlənilən: riyaziyyat 4×(A,C) + fizika 4×B + fizika-2 1×B = 13; qəbz: 4 + 2 + 4 + 1 = 11.
        self.assertEqual(data["participation"]["expected"], 13)
        self.assertEqual(data["participation"]["receipts"], 11)
        self.assertEqual(data["participation"]["general_receipts"], 5)
        self.assertEqual(data["n"], 11)
        codes = {row["code"] for row in data["questions"]}
        self.assertIn("clarity", codes)
        self.assertIn("overall", codes)

    def test_general_suggestions_are_searchable_and_scoped(self):
        with bypass_rls():
            org_wide = public.general_suggestions(self.w["org"], self._scope(self.rector), query="kitabxana")
            chair = public.general_suggestions(self.w["org"], self._scope(self.chair_head))
        self.assertFalse(org_wide["suppressed"])
        self.assertTrue(all("Kitabxana" in item["text"] for item in org_wide["items"]))
        self.assertEqual(len(org_wide["items"]), 5)
        # Kafedra A: yalnız G-101 (A altında) tələbələrinin ümumi cavabları — 4 ≥ k.
        self.assertEqual(chair["n"], 4)

    def test_distribution_trend_options_and_search(self):
        scope = self._scope(self.rector)
        with bypass_rls():
            dist = public.distribution(self.w["org"], scope, "clarity")
            trend = public.trend(self.w["org"], scope, teacher_id=self.w["teacher_a"].pk)
            options = public.filter_options(self.w["org"], scope)
            found = public.search_teachers(self.w["org"], scope, self.w["teacher_a"].username[:6])
            campaigns = public.campaigns_for(self.w["org"])
        self.assertEqual(dist["buckets"][4], {"score": 5, "count": 11})
        self.assertEqual(len(trend), 1)
        self.assertEqual(trend[0]["n"], 4)
        self.assertEqual({row["label"] for row in options["groups"]}, {"G-101", "G-102"})
        self.assertIn(self.w["teacher_a"].pk, {row["id"] for row in found})
        self.assertEqual(campaigns[0]["responses"], 11)
        self.assertEqual(campaigns[0]["receipts"], 11)
