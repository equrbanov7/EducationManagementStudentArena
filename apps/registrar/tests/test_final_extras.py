"""Tests for bonus/penalty + final comment (U15)."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook, services
from apps.registrar.models import Curriculum, CurriculumSubject, LessonKind, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class FinalExtrasTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("fx_owner", "fx_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="FX Univ",
                slug="fx-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="fx-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma", ects=6)
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("fx_teacher", "fx_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("fx_student", "fx_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=cls.record, period=cls.period, semester_number=1)
            cls.offering = cls.student.enrollments.get().offering
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            cls.enrollment = cls.offering.enrollments.get()
            # Entry 40 = 4 seminar dərsi × 10 bal (per-mark tavan 10-dur).
            for day in range(1, 5):
                lesson = gradebook.create_lesson(
                    allow_past=True, offering=cls.offering, date=datetime.date(2024, 10, day), kind=LessonKind.SEMINAR
                )
                gradebook.save_marks(
                    enforce_day=False,
                    offering=cls.offering,
                    entries=[
                        {"lesson_id": lesson.id, "enrollment_id": cls.enrollment.id, "status": "present", "score": 10}
                    ],
                    by_user=cls.teacher,
                )
            finals.set_exam_score(enrollment=cls.enrollment, score=45, by_user=cls.teacher)  # total 85

    def test_bonus_raises_total_and_letter(self):
        with bypass_rls():
            finals.set_final_extras(enrollment=self.enrollment, bonus="8", by_user=self.teacher)
            result = finals.compute_final_result(enrollment=self.enrollment)
        self.assertEqual(result["total"], Decimal("93"))  # 85 + 8
        self.assertEqual(result["letter"], "A")
        self.assertTrue(result["passed"])

    def test_total_clamped_at_100(self):
        with bypass_rls():
            finals.set_final_extras(enrollment=self.enrollment, bonus="20", by_user=self.teacher)
            # Beşinci seminar → entry 50 (per-mark tavan 10 olduğundan əlavə dərs).
            extra = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=datetime.date(2024, 10, 5), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {
                        "lesson_id": extra.id,
                        "enrollment_id": self.enrollment.id,
                        "status": "present",
                        "score": 10,
                    }
                ],
                by_user=self.teacher,
            )
            result = finals.compute_final_result(enrollment=self.enrollment)
        self.assertEqual(result["total"], Decimal("100"))  # 50 + 45 + 20 → clamp

    def test_penalty_lowers_total_and_bonus_is_clamped(self):
        with bypass_rls():
            finals.set_final_extras(enrollment=self.enrollment, bonus="-50", by_user=self.teacher)  # → -20
            result = finals.compute_final_result(enrollment=self.enrollment)
        self.assertEqual(result["bonus"], Decimal("-20"))
        self.assertEqual(result["total"], Decimal("65"))  # 85 - 20

    def test_comment_saved_and_exposed(self):
        with bypass_rls():
            finals.set_final_extras(enrollment=self.enrollment, comment="Əla fəallıq!", by_user=self.teacher)
            result = finals.compute_final_result(enrollment=self.enrollment)
        self.assertEqual(result["comment"], "Əla fəallıq!")

    def test_locked_journal_blocks_extras(self):
        with bypass_rls():
            finals.publish_offering(offering=self.offering, by_user=self.teacher)
            outcome = finals.set_final_extras(enrollment=self.enrollment, bonus="5", by_user=self.teacher)
            result = finals.compute_final_result(enrollment=self.enrollment)
        self.assertIsNone(outcome)
        self.assertEqual(result["bonus"], Decimal("0"))

    def test_bonus_change_is_audited(self):
        from apps.audit.models import AuditLog

        with bypass_rls():
            finals.set_final_extras(enrollment=self.enrollment, bonus="3", by_user=self.teacher)
            log = (
                AuditLog.objects.filter(resource_type="registrar.grade.final", resource_id=str(self.offering.pk))
                .order_by("-created_at")
                .first()
            )
        self.assertEqual(log.changes[0]["item"], "Bonus/cərimə")
        self.assertEqual(log.changes[0]["new"], "3")

    def test_view_saves_bonus_and_comment(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                "action": "save_finals",
                f"exam__{self.enrollment.id}": "45",
                f"bonus__{self.enrollment.id}": "4",
                f"fcomment__{self.enrollment.id}": "Yaxşı irəliləyiş",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            result = finals.compute_final_result(enrollment=self.enrollment)
        self.assertEqual(result["bonus"], Decimal("4"))
        self.assertEqual(result["comment"], "Yaxşı irəliləyiş")
