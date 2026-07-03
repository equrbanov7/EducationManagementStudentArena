from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.assignments.models import Assignment
from apps.notifications.models import (
    InAppNotification,
    MembershipRequestRoleType,
    NotificationType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.notifications.services import notify_org_admins_of_new_request
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "teacher",
        ProfileRole.STUDENT: "student",
        ProfileRole.MEMBER: "member",
        ProfileRole.ORG_ADMIN: "org_admin",
    }.get(profile_role, "member")

    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )


def _login_with_org(client, user, organization):
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()


class NotificationEventFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="notif_owner",
            email="notif_owner@example.com",
            password="StrongPass123!",
        )
        self.teacher = User.objects.create_user(
            username="notif_teacher",
            email="notif_teacher@example.com",
            password="StrongPass123!",
        )
        self.student = User.objects.create_user(
            username="notif_student",
            email="notif_student@example.com",
            password="StrongPass123!",
        )
        self.superadmin = User.objects.create_superuser(
            username="notif_superadmin",
            email="notif_superadmin@example.com",
            password="StrongPass123!",
        )
        self.organization = Organization.objects.create(
            name="Notification Events Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

    def test_profile_notifications_show_pending_teacher_request(self):
        applicant = User.objects.create_user(
            username="pending_teacher",
            email="pending_teacher@example.com",
            password="StrongPass123!",
        )
        applicant.profile.role = ProfileRole.TEACHER
        applicant.profile.organization = None
        applicant.profile.organization_type = OrganizationType.INDIVIDUAL
        applicant.profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])

        StudentOrganizationRequest.objects.create(
            user=applicant,
            organization=self.organization,
            role_type=MembershipRequestRoleType.TEACHER,
            message="Müəllim kimi qoşulmaq istəyirəm.",
            status=StudentOrganizationRequestStatus.PENDING,
        )

        self.client.force_login(applicant)
        response = self.client.get(reverse("accounts:profile") + "?section=notifications")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertContains(response, "müəllim kimi müraciətiniz")
        self.assertEqual(response.context["notifications_unread_count"], 1)

    def test_student_join_request_notifies_org_admins(self):
        applicant = User.objects.create_user(
            username="join_request_student",
            email="join_request_student@example.com",
            password="StrongPass123!",
        )
        applicant.profile.role = ProfileRole.STUDENT
        applicant.profile.organization = None
        applicant.profile.organization_type = OrganizationType.INDIVIDUAL
        applicant.profile.requested_organization = None
        applicant.profile.requested_organization_name = ""
        applicant.profile.requested_organization_message = ""
        applicant.profile.save(
            update_fields=[
                "role",
                "organization",
                "organization_type",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "updated_at",
            ]
        )

        self.client.force_login(applicant)
        response = self.client.post(
            reverse("accounts:student_organization_request"),
            {
                "action": "submit_request",
                "organization_id": str(self.organization.id),
                "request_message": "Təşkilata qoşulmaq istəyirəm.",
                "next": reverse("accounts:profile") + "?section=student-organization-request",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.owner,
                notification_type=NotificationType.APPROVAL,
                title__icontains="Yeni tələbə müraciəti",
            ).exists()
        )

    def test_teacher_request_notification_includes_rich_details_and_superadmin_link(self):
        applicant = User.objects.create_user(
            username="teacher_candidate",
            email="teacher_candidate@example.com",
            password="StrongPass123!",
            first_name="Nigar",
            last_name="Məmmədova",
        )
        applicant.profile.role = ProfileRole.TEACHER
        applicant.profile.organization = None
        applicant.profile.organization_type = OrganizationType.INDIVIDUAL
        applicant.profile.department = "Kompüter elmləri kafedrası"
        applicant.profile.save(update_fields=["role", "organization", "organization_type", "department", "updated_at"])

        request_obj = StudentOrganizationRequest.objects.create(
            user=applicant,
            organization=self.organization,
            role_type=MembershipRequestRoleType.TEACHER,
            message="Riyaziyyat və proqramlaşdırma fənlərini tədris edirəm.",
            status=StudentOrganizationRequestStatus.PENDING,
        )

        notify_org_admins_of_new_request(request_obj=request_obj)

        owner_notification = InAppNotification.objects.get(
            recipient=self.owner,
            notification_type=NotificationType.APPROVAL,
            title__icontains="Yeni müəllim müraciəti",
        )
        self.assertIn("Ad soyad: Nigar Məmmədova", owner_notification.message)
        self.assertIn("Username: @teacher_candidate", owner_notification.message)
        self.assertIn("Kafedra / Departament: Kompüter elmləri kafedrası", owner_notification.message)
        self.assertIn(
            "Müraciət mesajı: Riyaziyyat və proqramlaşdırma fənlərini tədris edirəm.", owner_notification.message
        )
        self.assertIn("/organizations/switch/", owner_notification.link)
        link_query = parse_qs(urlparse(owner_notification.link).query)
        next_url = link_query["next"][0]
        self.assertIn("management_view=teachers", next_url)
        self.assertIn("teacher_tab=requests", next_url)
        self.assertEqual(owner_notification.metadata["link_label"], "Müraciəti aç və cavablandır")

        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.superadmin,
                notification_type=NotificationType.APPROVAL,
                title__icontains="Yeni müəllim müraciəti",
            ).exists()
        )

    def test_assignment_submission_signal_uses_tenant_scope_for_transaction_pooling(self):
        from apps.assignments.models import Submission
        from apps.courses.models import Course
        from apps.notifications.signals import _notify_assignment_submission_events

        course = Course.objects.create(
            owner=self.teacher,
            title="Signal Scoped Course",
            status="published",
            organization=self.organization,
        )
        assignment = Assignment.objects.create(
            course=course,
            title="Signal Scoped Assignment",
            created_by=self.teacher,
            start_date=timezone.now(),
        )
        submission = Submission(assignment=assignment, user=self.student, status="submitted")
        entered = {"atomic": 0}

        @contextmanager
        def recording_atomic():
            entered["atomic"] += 1
            yield

        with (
            patch("apps.notifications.signals.rls_worker_atomic", recording_atomic),
            patch("apps.notifications.signals.set_rls_tenant") as set_rls_tenant,
            patch("apps.notifications.signals.notify_teacher_about_submission") as notify_teacher,
        ):
            _notify_assignment_submission_events(Submission, submission, created=True)

        self.assertEqual(entered["atomic"], 1)
        set_rls_tenant.assert_called_once_with(self.organization.id)
        notify_teacher.assert_called_once_with(task=assignment, student=self.student, task_kind="assignment")

    def test_assignment_create_submit_and_grade_flow_creates_notifications(self):
        from apps.courses.models import Course

        course = Course.objects.create(
            owner=self.teacher,
            title="Notification Algorithms",
            status="published",
            organization=self.organization,
        )

        _login_with_org(self.client, self.teacher, self.organization)
        start_at = timezone.now() - timezone.timedelta(hours=1)
        end_at = timezone.now() + timezone.timedelta(days=3)
        create_response = self.client.post(
            reverse("assignments:create_assignment", args=[course.id]),
            {
                "title": "Binary Search Homework",
                "description": "Solve the tasks",
                "start_date": start_at.strftime("%Y-%m-%dT%H:%M"),
                "deadline": end_at.strftime("%Y-%m-%dT%H:%M"),
                "status": "active",
                "students[]": [str(self.student.id)],
            },
        )
        self.assertEqual(create_response.status_code, 200)

        assignment = Assignment.objects.get(title="Binary Search Homework")
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.student,
                notification_type=NotificationType.ASSIGNMENT,
                title__icontains="Yeni sərbəst iş təyin olundu",
            ).exists()
        )

        _login_with_org(self.client, self.student, self.organization)
        submit_response = self.client.post(
            reverse("assignments:submit_assignment", args=[assignment.id]),
            {"content": "Hazır cavab"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(submit_response.status_code, 200)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.teacher,
                notification_type=NotificationType.ASSIGNMENT,
                title__icontains="Yeni sərbəst iş cavabı",
            ).exists()
        )

        submission = assignment.submissions.get(user=self.student)
        _login_with_org(self.client, self.teacher, self.organization)
        grade_response = self.client.post(
            reverse("assignments:grade_submission", args=[submission.id]),
            {"grade": "91", "feedback": "Yaxşı iş"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(grade_response.status_code, 200)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.student,
                notification_type=NotificationType.GRADE,
                title__icontains="Sərbəst iş nəticəniz hazırdır",
            ).exists()
        )

    def test_course_member_add_notifies_student(self):
        from apps.courses.models import Course

        course = Course.objects.create(
            owner=self.teacher,
            title="Discrete Mathematics",
            status="published",
            organization=self.organization,
        )

        _login_with_org(self.client, self.teacher, self.organization)
        response = self.client.post(
            reverse("courses:add_member", args=[course.id]),
            {
                "user_ids": [str(self.student.id)],
                "group_name": "A1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.student,
                notification_type=NotificationType.COURSE,
                title__icontains="Yeni kurs təyin olundu",
                message__icontains="A1",
            ).exists()
        )

    def test_group_create_notifies_added_student(self):
        _login_with_org(self.client, self.teacher, self.organization)
        response = self.client.post(
            reverse("exams:teacher_create_group"),
            {
                "name": "Qrup 501",
                "students": [str(self.student.id)],
                "primary_teacher": str(self.teacher.id),
                "assigned_teachers": [str(self.teacher.id)],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.student,
                notification_type=NotificationType.COURSE,
                title__icontains="Qrupa əlavə olundunuz",
            ).exists()
        )
