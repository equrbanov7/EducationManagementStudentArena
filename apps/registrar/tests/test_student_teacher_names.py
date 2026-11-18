"""MR-000490: tələbə kabinetində bölünmüş jurnalın seminar müəllimi də görünür (yalnız tələbəni əhatə edən pay)."""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, transcript
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, LessonKind, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class StudentTeacherNamesTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user("stn_owner", "stn_owner@qku.edu.az", "pw")
        self.lecturer = User.objects.create_user("stn_lec", "l@qku.edu.az", "pw", first_name="Fatma", last_name="Ə")
        self.seminarist = User.objects.create_user("stn_sem", "s@qku.edu.az", "pw", first_name="Aytac", last_name="İ")
        self.other = User.objects.create_user("stn_oth", "o@qku.edu.az", "pw", first_name="Nigar", last_name="X")
        self.student = User.objects.create_user("stn_st1", "st1@qku.edu.az", "pw")
        self.student2 = User.objects.create_user("stn_st2", "st2@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="STN",
                slug="stn",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            for user, role in (
                (self.lecturer, "teacher"),
                (self.seminarist, "teacher"),
                (self.other, "teacher"),
                (self.student, "student"),
                (self.student2, "student"),
            ):
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )
            group = OrgUnit.objects.create(organization=self.org, name="G", slug="stn-g", unit_type=OrgUnitType.GROUP)
            period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            subject = Subject.objects.create(organization=self.org, code="BS", name="Biostatistika", ects=5)
            self.offering = CourseOffering.objects.create(
                organization=self.org,
                subject=subject,
                period=period,
                group=group,
                instructor=self.lecturer,
                lesson_hours=45,
            )
            self.enr = Enrollment.objects.create(organization=self.org, student=self.student, offering=self.offering)
            self.enr2 = Enrollment.objects.create(organization=self.org, student=self.student2, offering=self.offering)
            day = datetime.date(2026, 9, 20)
            gradebook.create_lesson(allow_past=True, offering=self.offering, date=day, kind=LessonKind.LECTURE)
            gradebook.create_lesson(allow_past=True, offering=self.offering, date=day, kind=LessonKind.SEMINAR)

    def _teacher(self, student):
        data = transcript.build_student_overall_record(student=student, organization=self.org)
        return [row["teacher_name"] for sem in data["semesters"] for row in sem["rows"]][0]

    def test_owner_only_shows_plain_name(self):
        self.assertEqual(self._teacher(self.student), "Fatma Ə")

    def test_seminar_share_shows_both_teachers(self):
        JournalShare.objects.create(
            organization=self.org, offering=self.offering, teacher=self.seminarist, kinds=["seminar"]
        )
        name = self._teacher(self.student)
        self.assertIn("Fatma Ə (", name)
        self.assertIn("Aytac İ (", name)
        self.assertTrue(name.startswith("Fatma Ə"))

    def test_partial_share_only_for_covered_student(self):
        share = JournalShare.objects.create(
            organization=self.org, offering=self.offering, teacher=self.other, kinds=["seminar"]
        )
        share.enrollments.add(self.enr2)
        self.assertEqual(self._teacher(self.student), "Fatma Ə")
        self.assertIn("Nigar X", self._teacher(self.student2))

    def test_inactive_share_ignored(self):
        JournalShare.objects.create(
            organization=self.org, offering=self.offering, teacher=self.seminarist, kinds=["seminar"], is_active=False
        )
        self.assertEqual(self._teacher(self.student), "Fatma Ə")
