"""Characterization tests for the registrar curriculum models (U1)."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Organization
from apps.registrar.models import Curriculum, CurriculumSubject, DegreeLevel, Program, Subject
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class RegistrarModelTest(TestCase):
    """The curriculum layer models, constraints and the plan-grouping query."""

    def setUp(self):
        self.owner = User.objects.create_user("reg_owner", "reg_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="Reg Univ",
                slug="reg-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )

    def _make_plan(self):
        with bypass_rls():
            program = Program.objects.create(
                organization=self.org, code="CS", name="Kompüter elmləri", degree_level=DegreeLevel.BACHELOR
            )
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
            math = Subject.objects.create(organization=self.org, code="MATH101", name="Riyaziyyat", ects=6)
            prog = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma", ects=6)
            el_a = Subject.objects.create(organization=self.org, code="EL-A", name="Seçmə A", ects=4)
            el_b = Subject.objects.create(organization=self.org, code="EL-B", name="Seçmə B", ects=4)
            # Semester 1: two mandatory + a 2-subject elective block (choose 1).
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=curriculum, subject=math, semester_number=1
            )
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=curriculum, subject=prog, semester_number=1
            )
            CurriculumSubject.objects.create(
                organization=self.org,
                curriculum=curriculum,
                subject=el_a,
                semester_number=1,
                is_elective=True,
                elective_group="SB1",
                required_choices=1,
            )
            CurriculumSubject.objects.create(
                organization=self.org,
                curriculum=curriculum,
                subject=el_b,
                semester_number=1,
                is_elective=True,
                elective_group="SB1",
                required_choices=1,
            )
        return curriculum

    def test_plan_separates_mandatory_and_elective_blocks(self):
        curriculum = self._make_plan()
        with bypass_rls():
            rows = list(CurriculumSubject.objects.filter(curriculum=curriculum, semester_number=1))
            mandatory = [r for r in rows if not r.is_elective]
            electives = [r for r in rows if r.is_elective]
            self.assertEqual(len(mandatory), 2)
            self.assertEqual(len(electives), 2)
            # All electives here belong to one block "SB1" that requires 1 choice.
            self.assertEqual({r.elective_group for r in electives}, {"SB1"})
            self.assertEqual({r.required_choices for r in electives}, {1})

    def test_subject_code_unique_per_org(self):
        self._make_plan()
        with bypass_rls(), self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subject.objects.create(organization=self.org, code="CS101", name="Dublikat", ects=6)

    def test_curriculum_unique_per_program_year(self):
        curriculum = self._make_plan()
        with bypass_rls(), self.assertRaises(IntegrityError):
            with transaction.atomic():
                Curriculum.objects.create(organization=self.org, program=curriculum.program, admission_year=2024)

    def test_str_representations(self):
        curriculum = self._make_plan()
        with bypass_rls():
            program = curriculum.program
            # `__str__` = `display_label`: rəsmi kod yoxdursa yalnız ad; daxili
            # `code` ("CS") heç bir halda görünmür.
            self.assertEqual(str(program), "Kompüter elmləri")
            self.assertNotIn("CS", str(program))
            row = CurriculumSubject.objects.filter(curriculum=curriculum, is_elective=True).first()
            self.assertIn("seçmə", str(row))
