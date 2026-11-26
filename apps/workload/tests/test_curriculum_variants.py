from django.test import TestCase

from apps.registrar.models import Curriculum, CurriculumSubject
from apps.workload.services.curriculum_import import curriculum_row_suggestions

from .factories import make_org, make_structure


class CurriculumVariantTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("wl-plan-variants")
        cls.stack = make_structure(cls.org)

    def plan_row(self, year, credits, contact, *, version=1, active=True, group=""):
        plan = Curriculum.objects.create(
            organization=self.org,
            program=self.stack["program"],
            admission_year=year,
            version=version,
            is_active=active,
        )
        return CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=plan,
            subject=self.stack["subject"],
            semester_number=1,
            credits=credits,
            lecture_hours=contact[0],
            seminar_hours=contact[1],
            lab_hours=contact[2],
            is_elective=bool(group),
            elective_group=group,
        )

    def suggestions(self, **kwargs):
        return curriculum_row_suggestions(organization=self.org, chair=self.stack["chair"], **kwargs)

    def test_only_identical_effective_credit_and_contact_distribution_merge(self):
        self.plan_row(2026, 0, (30, 15, 0))  # The subject catalogue supplies six credits.
        self.plan_row(2026, 6, (30, 15, 0), version=2)
        self.plan_row(2025, 6, (30, 15, 0))
        self.plan_row(2024, 4, (30, 15, 0))
        self.plan_row(2023, 6, (30, 0, 15))
        self.plan_row(2022, 2, (10, 10, 0), active=False)
        rows = self.suggestions()
        self.assertEqual(
            [
                (r["credits_value"], r["lecture_hours"], r["seminar_hours"], r["lab_hours"], r["admission_years"])
                for r in rows
            ],
            [(6, 30, 15, 0, [2026, 2025]), (4, 30, 15, 0, [2024]), (6, 30, 0, 15, [2023])],
        )
        self.assertTrue(all(r["has_variants"] for r in rows))
        self.assertEqual([r["suggested_total_hours"] for r in rows], [180, 120, 180])
        self.assertEqual(self.suggestions(limit=2), rows[:2])

    def test_identical_cohorts_stay_simple_and_elective_blocks_are_distinct(self):
        self.plan_row(2026, 3, (15, 15, 0), group="A")
        self.plan_row(2025, 3, (15, 15, 0), group="A")
        (simple,) = self.suggestions()
        self.assertFalse(simple["has_variants"])
        self.assertEqual(simple["admission_years"], [2026, 2025])
        self.plan_row(2024, 3, (15, 15, 0), group="B")
        self.plan_row(2023, 3, (15, 15, 0))
        self.assertEqual(
            [(r["is_elective"], r["elective_group"]) for r in self.suggestions()],
            [(True, "A"), (True, "B"), (False, "")],
        )
