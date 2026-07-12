"""Tests for the grade-approval chain (U7.2): teacher → chair → dean → official."""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import approval, gradebook, services
from apps.registrar.models import (
    ApprovalStatus,
    Curriculum,
    CurriculumSubject,
    LessonKind,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class _ApprovalBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ap_owner", "ap_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="AP Univ",
                slug="ap-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="ap-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("ap_teacher", "ap_teacher@qku.edu.az", "pw")
            cls.chair = User.objects.create_user("ap_chair", "ap_chair@qku.edu.az", "pw")
            cls.dean = User.objects.create_user("ap_dean", "ap_dean@qku.edu.az", "pw")
            cls.student = User.objects.create_user("ap_student", "ap_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.chair,
                organization=cls.org,
                role=cls.org.roles.get(name="chair_head"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.dean,
                organization=cls.org,
                role=cls.org.roles.get(name="dean"),
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


class ApprovalServiceTest(_ApprovalBase):
    def test_submit_moves_to_submitted_and_locks(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            self.assertEqual(scheme.approval_status, ApprovalStatus.SUBMITTED)
            self.assertEqual(scheme.submitted_by_id, self.teacher.id)
            self.assertTrue(gradebook.journal_is_locked(self.offering))

    def test_submit_locks_mark_editing(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
            written = gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 10}
                ],
                by_user=self.teacher,
            )
            self.assertEqual(written, 0)

    def test_full_chain_publishes(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
            approval.chair_approve(offering=self.offering, by_user=self.chair)
            scheme = approval.dean_approve(offering=self.offering, by_user=self.dean)
            self.assertEqual(scheme.approval_status, ApprovalStatus.APPROVED)
            self.assertEqual(scheme.chair_approved_by_id, self.chair.id)
            self.assertEqual(scheme.dean_approved_by_id, self.dean.id)
            self.assertTrue(scheme.is_published)

    def test_dean_cannot_skip_chair(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
            # Dean approval before chair approval is a no-op (stays SUBMITTED).
            scheme = approval.dean_approve(offering=self.offering, by_user=self.dean)
            self.assertEqual(scheme.approval_status, ApprovalStatus.SUBMITTED)
            self.assertFalse(scheme.is_published)

    def test_return_unlocks_and_records_reason(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
            scheme = approval.return_for_revision(
                offering=self.offering, by_user=self.chair, reason="Seminar balları natamamdır"
            )
            self.assertEqual(scheme.approval_status, ApprovalStatus.RETURNED)
            self.assertEqual(scheme.returned_reason, "Seminar balları natamamdır")
            self.assertFalse(gradebook.journal_is_locked(self.offering))
            # Teacher can re-submit after fixing.
            scheme = approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
            self.assertEqual(scheme.approval_status, ApprovalStatus.SUBMITTED)
            self.assertEqual(scheme.returned_reason, "")

    def test_non_instructor_cannot_submit(self):
        with bypass_rls():
            with self.assertRaises(PermissionDenied):
                approval.submit_for_approval(offering=self.offering, by_user=self.student)

    def test_non_chair_cannot_approve(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
            with self.assertRaises(PermissionDenied):
                approval.chair_approve(offering=self.offering, by_user=self.student)

    def test_teacher_cannot_dean_approve(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
            approval.chair_approve(offering=self.offering, by_user=self.chair)
            with self.assertRaises(PermissionDenied):
                approval.dean_approve(offering=self.offering, by_user=self.teacher)


class ApprovalViewTest(_ApprovalBase):
    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_teacher_submits_via_view(self):
        resp = self._client(self.teacher).post(
            reverse("registrar:journal_detail", args=[self.offering.id]), {"action": "submit_approval"}
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            self.assertEqual(scheme.approval_status, ApprovalStatus.SUBMITTED)

    def test_chair_can_open_submitted_journal(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
        resp = self._client(self.chair).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 200)

    def test_chair_cannot_open_draft_journal(self):
        # Draft journals are not yet visible to reviewers (no leak).
        resp = self._client(self.chair).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 404)

    def test_chair_and_dean_approve_via_view(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
        self._client(self.chair).post(
            reverse("registrar:journal_detail", args=[self.offering.id]), {"action": "chair_approve"}
        )
        self._client(self.dean).post(
            reverse("registrar:journal_detail", args=[self.offering.id]), {"action": "dean_approve"}
        )
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            self.assertEqual(scheme.approval_status, ApprovalStatus.APPROVED)
            self.assertTrue(scheme.is_published)

    def test_student_cannot_chair_approve_via_view(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
        resp = self._client(self.student).post(
            reverse("registrar:journal_detail", args=[self.offering.id]), {"action": "chair_approve"}
        )
        self.assertEqual(resp.status_code, 404)  # not editor, not reviewer
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            self.assertEqual(scheme.approval_status, ApprovalStatus.SUBMITTED)

    def test_approvals_inbox_lists_submitted_for_chair(self):
        with bypass_rls():
            approval.submit_for_approval(offering=self.offering, by_user=self.teacher)
        resp = self._client(self.chair).get(reverse("registrar:approvals_inbox"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CS101")

    def test_approvals_inbox_forbidden_for_teacher(self):
        resp = self._client(self.teacher).get(reverse("registrar:approvals_inbox"))
        self.assertEqual(resp.status_code, 404)
