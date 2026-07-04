"""Service-layer tests for the U2 enrollment flow (mandatory + group elective)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    Enrollment,
    EnrollmentKind,
    GroupElectiveChoice,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class EnrollmentFlowTest(TestCase):
    """The specialty → mandatory auto-enroll + group-level elective flow."""

    def setUp(self):
        self.owner = User.objects.create_user("svc_owner", "svc_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="Svc Univ",
                slug="svc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.specialty = OrgUnit.objects.create(
                organization=self.org, name="CS ixtisas", slug="cs-ixtisas", unit_type=OrgUnitType.SPECIALTY
            )
            self.group = OrgUnit.objects.create(
                organization=self.org,
                name="KE-101",
                slug="ke-101",
                unit_type=OrgUnitType.GROUP,
                parent=self.specialty,
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.program = Program.objects.create(organization=self.org, code="CS", name="Kompüter elmləri")
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.math = Subject.objects.create(organization=self.org, code="MATH101", name="Riyaziyyat")
            self.prog = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            self.el_a = Subject.objects.create(organization=self.org, code="EL-A", name="Seçmə A")
            self.el_b = Subject.objects.create(organization=self.org, code="EL-B", name="Seçmə B")
            # Semester 1 plan: 2 mandatory + a 2-option elective block "SB1".
            for subj in (self.math, self.prog):
                CurriculumSubject.objects.create(
                    organization=self.org, curriculum=self.curriculum, subject=subj, semester_number=1
                )
            for subj in (self.el_a, self.el_b):
                CurriculumSubject.objects.create(
                    organization=self.org,
                    curriculum=self.curriculum,
                    subject=subj,
                    semester_number=1,
                    is_elective=True,
                    elective_group="SB1",
                    required_choices=1,
                )
            # Three students in the same group with academic records.
            self.students = []
            for i in range(3):
                u = User.objects.create_user(f"svc_student{i}", f"svc_student{i}@qku.edu.az", "pw")
                rec = StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=u,
                    program=self.program,
                    curriculum=self.curriculum,
                    group=self.group,
                    admission_year=2024,
                )
                self.students.append(rec)

    def test_enroll_mandatory_subjects(self):
        with bypass_rls():
            created = services.enroll_mandatory_subjects(record=self.students[0], period=self.period, semester_number=1)
            self.assertEqual(created, 2)  # MATH101 + CS101
            enrolled_codes = set(
                Enrollment.objects.filter(student=self.students[0].student).values_list(
                    "offering__subject__code", flat=True
                )
            )
            self.assertEqual(enrolled_codes, {"MATH101", "CS101"})
            # Re-running is idempotent.
            self.assertEqual(
                services.enroll_mandatory_subjects(record=self.students[0], period=self.period, semester_number=1),
                0,
            )

    def test_group_elective_choice_enrolls_every_member(self):
        with bypass_rls():
            choice, enrolled = services.choose_group_elective(
                organization=self.org,
                group=self.group,
                curriculum=self.curriculum,
                period=self.period,
                elective_group="SB1",
                subject=self.el_a,
                decided_by=self.owner,
            )
            self.assertEqual(choice.chosen_subject_id, self.el_a.id)
            self.assertEqual(enrolled, 3, "one group decision must enroll all 3 group members")
            # Every student is enrolled in EL-A as an elective.
            for rec in self.students:
                e = Enrollment.objects.get(student=rec.student, offering__subject=self.el_a)
                self.assertEqual(e.kind, EnrollmentKind.ELECTIVE)

    def test_late_joiner_inherits_group_choice_on_rerun(self):
        with bypass_rls():
            services.choose_group_elective(
                organization=self.org,
                group=self.group,
                curriculum=self.curriculum,
                period=self.period,
                elective_group="SB1",
                subject=self.el_a,
                decided_by=self.owner,
            )
            # A new student joins the group after the decision.
            late = User.objects.create_user("svc_late", "svc_late@qku.edu.az", "pw")
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=late,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2024,
            )
            # Re-applying the same choice enrolls only the new member.
            _, enrolled = services.choose_group_elective(
                organization=self.org,
                group=self.group,
                curriculum=self.curriculum,
                period=self.period,
                elective_group="SB1",
                subject=self.el_a,
                decided_by=self.owner,
            )
            self.assertEqual(enrolled, 1)
            self.assertTrue(Enrollment.objects.filter(student=late, offering__subject=self.el_a).exists())
            # Still exactly one choice row for the block.
            self.assertEqual(
                GroupElectiveChoice.objects.filter(group=self.group, period=self.period, elective_group="SB1").count(),
                1,
            )

    def test_semester_plan_shape(self):
        with bypass_rls():
            services.enroll_mandatory_subjects(record=self.students[0], period=self.period, semester_number=1)
            services.choose_group_elective(
                organization=self.org,
                group=self.group,
                curriculum=self.curriculum,
                period=self.period,
                elective_group="SB1",
                subject=self.el_b,
                decided_by=self.owner,
            )
            plan = services.get_student_semester_plan(record=self.students[0], period=self.period, semester_number=1)
            # 2 mandatory + 1 elective = 3 enrollments.
            self.assertEqual(len(plan["enrollments"]), 3)
            # One elective block "SB1" with 2 options.
            self.assertIn("SB1", plan["elective_blocks"])
            self.assertEqual(len(plan["elective_blocks"]["SB1"]["options"]), 2)
            # The group decided EL-B for SB1.
            self.assertEqual(plan["group_decisions"]["SB1"].code, "EL-B")
