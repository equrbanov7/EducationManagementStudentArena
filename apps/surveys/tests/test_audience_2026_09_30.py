"""Sorğu qurucusu (2026-09-30) — auditoriyanın həlli: ailələr, struktur daraltması, iştirak."""

from __future__ import annotations

from django.test import TestCase

from apps.organizations.models import Membership
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from apps.surveys.services.audience import audience_user_ids, role_families, user_in_audience
from apps.surveys.services.survey_results import participation
from core.rls import bypass_rls

from .builder_world import make_survey, manager
from .factories import build_world, member


def _memberships(org, user):
    return list(
        Membership.objects.filter(organization=org, user=user, is_active=True).select_related("role", "scope_unit")
    )


class AudienceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svaud", students=2)
        org = cls.w["org"]
        with bypass_rls():
            cls.dean = member(org, "svaud_dean", "dean", unit=cls.w["faculty"])
            cls.chair_head = member(org, "svaud_ch", "chair_head", unit=cls.w["chair_b"])
            cls.qc = manager(cls.w)
            program = Program.objects.get(organization=org)
            curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2025)
            cls.program = program
            # Tələbə 0 — G-101 (kafedra A altında, 2-ci kurs); tələbə 1 — qrupsuz.
            StudentAcademicRecord.objects.create(
                organization=org,
                student=cls.w["students"][0],
                program=program,
                curriculum=curriculum,
                group=cls.w["group"],
                admission_year=2025,
            )

    def _in(self, survey, user):
        with bypass_rls():
            return user_in_audience(survey, user, _memberships(self.w["org"], user))

    def test_role_families(self):
        with bypass_rls():
            self.assertEqual(role_families(_memberships(self.w["org"], self.w["students"][0])), {"students"})
            self.assertEqual(role_families(_memberships(self.w["org"], self.w["teacher_a"])), {"teachers"})
            self.assertEqual(role_families(_memberships(self.w["org"], self.dean)), {"staff"})

    def test_plain_audiences(self):
        cases = {
            "students": {self.w["students"][0]: True, self.w["teacher_a"]: False, self.dean: False},
            "teachers": {self.w["students"][0]: False, self.w["teacher_a"]: True, self.dean: False},
            "staff": {self.w["students"][0]: False, self.w["teacher_a"]: False, self.dean: True},
            "everyone": {self.w["students"][0]: True, self.w["teacher_a"]: True, self.dean: True},
        }
        for audience, expected in cases.items():
            survey = make_survey(self.w, audience=audience, publish=False, kinds=())
            for user, result in expected.items():
                with self.subTest(audience=audience, user=user.username):
                    self.assertEqual(self._in(survey, user), result)
            with bypass_rls():
                ids = audience_user_ids(survey)
            self.assertEqual({u.pk for u, r in expected.items() if r} <= ids, True)
            self.assertFalse({u.pk for u, r in expected.items() if not r} & ids)

    def test_unit_narrowing_uses_student_group_and_staff_scope_unit(self):
        survey = make_survey(
            self.w, audience="everyone", publish=False, kinds=(), audience_filter={"units": [str(self.w["chair_a"].pk)]}
        )
        self.assertTrue(self._in(survey, self.w["students"][0]))  # qrupu kafedra A altında
        self.assertFalse(self._in(survey, self.w["students"][1]))  # akademik qeydi yoxdur
        self.assertTrue(self._in(survey, self.w["teacher_a"]))  # üzvlüyü kafedra A
        self.assertFalse(self._in(survey, self.w["teacher_b"]))  # kafedra B
        self.assertFalse(self._in(survey, self.chair_head))  # kafedra B müdiri
        faculty_wide = make_survey(
            self.w, audience="staff", publish=False, kinds=(), audience_filter={"units": [str(self.w["faculty"].pk)]}
        )
        self.assertTrue(self._in(faculty_wide, self.chair_head))  # kafedra B fakültənin alt-ağacıdır
        with bypass_rls():
            self.assertIn(self.chair_head.pk, audience_user_ids(faculty_wide))

    def test_program_and_course_year_are_student_only(self):
        survey = make_survey(
            self.w,
            audience="everyone",
            publish=False,
            kinds=(),
            audience_filter={"programs": [str(self.program.pk)], "course_years": [2]},
        )
        self.assertTrue(self._in(survey, self.w["students"][0]))
        self.assertFalse(self._in(survey, self.w["teacher_a"]))
        other_year = make_survey(
            self.w, audience="students", publish=False, kinds=(), audience_filter={"course_years": [3]}
        )
        self.assertFalse(self._in(other_year, self.w["students"][0]))
        with bypass_rls():
            self.assertEqual(audience_user_ids(survey), {self.w["students"][0].pk})

    def test_deleted_unit_fails_closed(self):
        survey = make_survey(
            self.w,
            audience="students",
            publish=False,
            kinds=(),
            audience_filter={"units": ["00000000-0000-0000-0000-000000000001"]},
        )
        self.assertFalse(self._in(survey, self.w["students"][0]))
        with bypass_rls():
            self.assertEqual(audience_user_ids(survey), set())

    def test_participation_by_faculty_rows(self):
        survey = make_survey(self.w, audience="students", anonymous=False)
        with bypass_rls():
            data = participation(survey)
        self.assertEqual((data["expected"], data["completed"], data["rate"]), (2, 0, 0))
        self.assertEqual([row["label"] for row in data["units"]], ["Fakültə F"])
