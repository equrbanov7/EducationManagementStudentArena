"""
Tests for profile and dashboard views.
"""

from decimal import Decimal
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.accounts.models import ProfileRole
from apps.notifications.models import (
    InAppNotification,
    MembershipRequestRoleType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.notifications.services import create_notification
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "teacher",
        ProfileRole.STUDENT: "student",
        ProfileRole.MEMBER: "member",
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


def _ensure_default_blog_categories():
    """Sqlite sürətli dövrə (--no-migrations) üçün blog seed kateqoriyalarını təmin et.

    CI migrasiyaları işlədir və 0002_seed_default_categories bunları onsuz da
    yaradır — orada get_or_create no-op olur. Yerli --no-migrations rejimində
    isə bu testlərin arxalandığı "Technology"/"Programming" ağacı yaranır.
    """
    from apps.blog.models import Category

    technology, _ = Category.objects.get_or_create(
        slug="technology",
        defaults={"name": "Technology", "sort_order": 10, "show_in_navbar": True, "is_default": True},
    )
    Category.objects.get_or_create(
        slug="programming",
        defaults={"name": "Programming", "parent": technology, "sort_order": 10, "is_default": True},
    )
    return technology


class ProfileViewTest(TestCase):
    """Tests for the profile view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def _delete_account(self, user, *, password="testpass123"):
        self.client.force_login(user)
        return self.client.post(
            reverse("accounts:delete_account"),
            {"password": password},
            follow=True,
        )

    def test_profile_requires_login(self):
        """Test that profile page requires authentication."""
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_page_loads(self):
        """Test that profile page loads for authenticated user."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil")

    def test_profile_avatar_redirects_unauthenticated_to_login(self):
        response = self.client.get(reverse("accounts:profile_avatar", kwargs={"user_id": self.user.id}))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:profile_avatar', kwargs={'user_id': self.user.id})}",
            fetch_redirect_response=False,
        )

    def test_profile_creates_userprofile(self):
        """Test that profile view creates UserProfile if missing."""
        from apps.accounts.models import UserProfile

        # Delete any auto-created profile
        UserProfile.objects.filter(user=self.user).delete()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_profile_has_stats(self):
        """Test that profile page includes stats context."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertIn("assigned_exams_count", response.context)
        self.assertIn("assigned_courses_count", response.context)
        self.assertIn("assigned_tasks_count", response.context)
        self.assertIn("is_teacher", response.context)
        self.assertIn("is_admin", response.context)

    def test_statistics_sidebar_link_forces_navigation(self):
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-section="statistics"', html=False)
        self.assertContains(response, 'data-force-navigation="true"', html=False)

    def test_statistics_section_places_ai_panel_above_filters_and_uses_bootstrap_select(self):
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(reverse("accounts:profile") + "?section=statistics")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="statsAiSummaryCard"', html=False)
        self.assertContains(response, 'id="statsFilterForm"', html=False)
        self.assertContains(response, "data-bootstrap-select", html=False)

        content = response.content.decode("utf-8")
        self.assertLess(content.index('id="statsAiSummaryCard"'), content.index('id="statsFilterForm"'))

    def test_statistics_section_uses_auto_submit_and_hides_reset_without_filters(self):
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(reverse("accounts:profile") + "?section=statistics")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-stats-auto-submit="true"', html=False)
        self.assertNotContains(response, 'id="statsFilterReset"', html=False)

    def test_superadmin_statistics_shows_org_select_and_reset_when_filter_active(self):
        superuser = User.objects.create_superuser(
            username="stats_superadmin",
            email="stats_superadmin@example.com",
            password="adminpass123",
        )
        organization = Organization.objects.create(
            name="Statistics Filter Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=superuser,
            status="active",
            is_active=True,
        )

        self.client.force_login(superuser)
        response = self.client.get(
            reverse("accounts:profile") + f"?section=statistics&stat_organization={organization.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="stat_organization"', html=False)
        self.assertContains(response, "data-bootstrap-select", html=False)
        self.assertContains(response, 'id="statsFilterReset"', html=False)

    def test_superadmin_statistics_org_table_uses_pagination(self):
        superuser = User.objects.create_superuser(
            username="stats_pagination_superadmin",
            email="stats_pagination_superadmin@example.com",
            password="adminpass123",
        )

        for index in range(9):
            Organization.objects.create(
                name=f"Statistics Org {index}",
                org_type=OrganizationType.UNIVERSITY,
                owner=superuser,
                status="active",
                is_active=True,
            )

        self.client.force_login(superuser)
        response = self.client.get(reverse("accounts:profile") + "?section=statistics")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="statsOrgTable"', html=False)
        self.assertContains(response, "stats_org_page=2")

    def test_student_statistics_filters_are_scoped_to_current_student(self):
        from apps.courses.models import Course, CourseMembership
        from apps.exams.models import StudentGroup

        owner = User.objects.create_user("stats_scope_owner", "stats_scope_owner@example.com", "pass123")
        organization = Organization.objects.create(
            name="Student Statistics Scope Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        teacher = User.objects.create_user("stats_scope_teacher", "stats_scope_teacher@example.com", "pass123")
        student = User.objects.create_user("stats_scope_student", "stats_scope_student@example.com", "pass123")
        other_student = User.objects.create_user(
            "stats_scope_other_student",
            "stats_scope_other_student@example.com",
            "pass123",
        )
        _assign_user_to_org(teacher, organization, ProfileRole.TEACHER)
        _assign_user_to_org(student, organization, ProfileRole.STUDENT)
        _assign_user_to_org(other_student, organization, ProfileRole.STUDENT)

        own_course = Course.objects.create(
            owner=teacher,
            organization=organization,
            title="Own Course",
            description="",
            status="published",
        )
        other_course = Course.objects.create(
            owner=teacher,
            organization=organization,
            title="Other Course",
            description="",
            status="published",
        )
        CourseMembership.objects.create(course=own_course, user=student, role="student")
        CourseMembership.objects.create(course=other_course, user=other_student, role="student")

        own_group = StudentGroup.objects.create(teacher=teacher, organization=organization, name="Own Group")
        own_group.students.add(student)
        other_group = StudentGroup.objects.create(teacher=teacher, organization=organization, name="Other Group")
        other_group.students.add(other_student)

        _login_with_org(self.client, student, organization)
        response = self.client.get(
            reverse("accounts:profile")
            + f"?section=statistics&stat_course={other_course.id}&stat_group={other_group.id}&stat_organization={organization.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.context["statistics_courses"]], [own_course.id])
        self.assertEqual([row["id"] for row in response.context["statistics_groups"]], [own_group.id])
        self.assertIsNone(response.context["statistics_filters"]["course"])
        self.assertIsNone(response.context["statistics_filters"]["group"])
        self.assertIsNone(response.context["statistics_filters"]["organization"])
        self.assertNotContains(response, "Other Course")
        self.assertNotContains(response, "Other Group")

    def test_student_statistics_do_not_include_org_live_exam_aggregates(self):
        from apps.courses.models import Course
        from apps.exams.models import Exam
        from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession

        owner = User.objects.create_user("stats_live_owner", "stats_live_owner@example.com", "pass123")
        organization = Organization.objects.create(
            name="Student Live Statistics Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        teacher = User.objects.create_user("stats_live_teacher", "stats_live_teacher@example.com", "pass123")
        student = User.objects.create_user("stats_live_student", "stats_live_student@example.com", "pass123")
        _assign_user_to_org(teacher, organization, ProfileRole.TEACHER)
        _assign_user_to_org(student, organization, ProfileRole.STUDENT)

        course = Course.objects.create(
            owner=teacher,
            organization=organization,
            title="Live Course",
            description="",
            status="published",
        )
        exam = Exam.objects.create(
            author=teacher,
            organization=organization,
            course=course,
            title="Live Exam",
            exam_type="test",
            is_active=True,
        )
        session = LiveSession.objects.create(exam=exam, host_user=teacher, state=LiveSession.STATE_FINISHED)
        player = LivePlayer.objects.create(session=session, nickname="Anonymous", client_id="anon-client")
        LiveAnswer.objects.create(session=session, player=player, question_id=1, is_correct=True)

        _login_with_org(self.client, student, organization)
        response = self.client.get(reverse("accounts:profile") + "?section=statistics")

        self.assertEqual(response.status_code, 200)
        summary = response.context["statistics_data"]["summary"]
        self.assertEqual(summary["live_total"], 0)
        self.assertEqual(summary["live_correct"], 0)
        self.assertEqual(summary["live_accuracy"], 0)
        self.assertNotContains(response, "live_total_answers", html=False)

    def test_profile_edit_section(self):
        """Test that edit-profile section renders form with save button."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=edit-profile")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yadda Saxla")

    def test_profile_info_places_delete_account_in_action_area(self):
        self.client.login(username="testuser", password="testpass123")
        self.client.cookies["django_language"] = "en"

        response = self.client.get(
            reverse("accounts:profile") + "?section=profile-info",
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete Account")
        self.assertContains(response, 'data-bs-target="#deleteAccountConfirmModal"', html=False)
        self.assertNotContains(response, 'data-section="delete-account"', html=False)

    def test_delete_account_section_falls_back_to_profile_info(self):
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(reverse("accounts:profile") + "?section=delete-account")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_section"], "profile-info")

    def test_delete_account_succeeds_for_active_teacher_student_and_member_roles(self):
        owner = User.objects.create_user(
            username="delete_roles_owner",
            email="delete_roles_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Delete Roles Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )

        scenarios = [
            ("teacher", ProfileRole.TEACHER, "teacher"),
            ("student", ProfileRole.STUDENT, "student"),
            ("member", ProfileRole.MEMBER, "member"),
        ]

        for label, profile_role, membership_role_name in scenarios:
            with self.subTest(role=label):
                user = User.objects.create_user(
                    username=f"delete_{label}_user",
                    email=f"delete_{label}_user@example.com",
                    password="testpass123",
                )
                _assign_user_to_org(user, organization, profile_role, membership_role_name=membership_role_name)

                response = self._delete_account(user)

                self.assertRedirects(response, reverse("accounts:login"))
                user.refresh_from_db()
                user.profile.refresh_from_db()
                self.assertFalse(user.is_active)
                self.assertTrue(user.profile.is_deleted)

    def test_delete_account_cancels_pending_join_requests(self):
        requester = User.objects.create_user(
            username="delete_pending_request",
            email="delete_pending_request@example.com",
            password="testpass123",
        )
        owner = User.objects.create_user(
            username="delete_pending_request_owner",
            email="delete_pending_request_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Delete Pending Request Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        requester.profile.role = ProfileRole.TEACHER
        requester.profile.organization = None
        requester.profile.organization_type = OrganizationType.INDIVIDUAL
        requester.profile.requested_organization = organization
        requester.profile.requested_organization_name = organization.name
        requester.profile.requested_organization_message = "Join request"
        requester.profile.save(
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
        pending_request = StudentOrganizationRequest.objects.create(
            user=requester,
            organization=organization,
            role_type=MembershipRequestRoleType.TEACHER,
            status=StudentOrganizationRequestStatus.PENDING,
            message="Join request",
        )

        response = self._delete_account(requester)

        self.assertRedirects(response, reverse("accounts:login"))
        requester.refresh_from_db()
        requester.profile.refresh_from_db()
        pending_request.refresh_from_db()
        self.assertFalse(requester.is_active)
        self.assertTrue(requester.profile.is_deleted)
        self.assertIsNone(requester.profile.requested_organization)
        self.assertEqual(pending_request.status, StudentOrganizationRequestStatus.CANCELLED)

    def test_delete_account_succeeds_for_user_with_pending_invite(self):
        invited_user = User.objects.create_user(
            username="delete_pending_invite",
            email="delete_pending_invite@example.com",
            password="testpass123",
        )
        owner = User.objects.create_user(
            username="delete_pending_invite_owner",
            email="delete_pending_invite_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Delete Pending Invite Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        invited_user.profile.role = ProfileRole.STUDENT
        invited_user.profile.organization = None
        invited_user.profile.organization_type = OrganizationType.INDIVIDUAL
        invited_user.profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])
        pending_invite = Membership.objects.create(
            user=invited_user,
            organization=organization,
            role=organization.roles.get(name="student"),
            assigned_by=owner,
            is_primary=False,
            is_active=False,
            title="__student_pending_invite__",
        )

        response = self._delete_account(invited_user)

        self.assertRedirects(response, reverse("accounts:login"))
        invited_user.refresh_from_db()
        invited_user.profile.refresh_from_db()
        pending_invite.refresh_from_db()
        self.assertFalse(invited_user.is_active)
        self.assertTrue(invited_user.profile.is_deleted)
        self.assertFalse(pending_invite.is_active)

    def test_delete_account_succeeds_for_pending_and_suspended_org_owners(self):
        for status in ("pending", "suspended"):
            with self.subTest(status=status):
                owner = User.objects.create_user(
                    username=f"delete_{status}_owner",
                    email=f"delete_{status}_owner@example.com",
                    password="testpass123",
                )
                owner.profile.role = ProfileRole.ORG_ADMIN
                owner.profile.organization_type = OrganizationType.UNIVERSITY
                owner.profile.save(update_fields=["role", "organization_type", "updated_at"])
                Organization.objects.create(
                    name=f"Delete {status.title()} Owner Org",
                    org_type=OrganizationType.UNIVERSITY,
                    owner=owner,
                    status=status,
                    is_active=True,
                )

                response = self._delete_account(owner)

                self.assertRedirects(response, reverse("accounts:login"))
                owner.refresh_from_db()
                owner.profile.refresh_from_db()
                self.assertFalse(owner.is_active)
                self.assertTrue(owner.profile.is_deleted)

    def test_delete_account_blocks_last_active_org_owner(self):
        owner = User.objects.create_user(
            username="delete_active_owner",
            email="delete_active_owner@example.com",
            password="testpass123",
        )
        owner.profile.role = ProfileRole.ORG_ADMIN
        owner.profile.organization_type = OrganizationType.UNIVERSITY
        owner.profile.save(update_fields=["role", "organization_type", "updated_at"])
        Organization.objects.create(
            name="Delete Active Owner Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )

        response = self._delete_account(owner)

        self.assertRedirects(response, reverse("accounts:profile") + "?section=profile-info")
        owner.refresh_from_db()
        owner.profile.refresh_from_db()
        self.assertTrue(owner.is_active)
        self.assertFalse(owner.profile.is_deleted)

    def test_edit_profile_organization_type_uses_translated_bootstrap_select(self):
        self.client.login(username="testuser", password="testpass123")
        self.client.cookies["django_language"] = "en"

        response = self.client.get(
            reverse("accounts:profile") + "?section=edit-profile",
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="form-select" id="organization_type"', html=False)
        self.assertContains(response, 'disabled aria-disabled="true"', html=False)
        self.assertContains(response, "Organization Type")
        self.assertContains(response, "University")
        self.assertNotContains(response, "org_type_university")

    def test_edit_profile_organization_type_links_to_join_flow_for_teacher_without_org(self):
        teacher_user = User.objects.create_user(
            username="teacher_edit_profile",
            email="teacher_edit_profile@example.com",
            password="testpass123",
        )
        teacher_profile = teacher_user.profile
        teacher_profile.organization = None
        teacher_profile.organization_type = OrganizationType.INDIVIDUAL
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        self.client.force_login(teacher_user)
        response = self.client.get(reverse("accounts:profile") + "?section=edit-profile")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "?section=student-organization-request")

    def test_profile_change_password_section_renders(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=change-password")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Şifrəni dəyiş")
        self.assertContains(response, 'name="old_password"', html=False)
        self.assertContains(response, 'name="new_password1"', html=False)
        self.assertContains(response, 'name="new_password2"', html=False)

    def test_profile_language_switcher_keeps_current_section_query(self):
        self.client.login(username="testuser", password="testpass123")
        url = reverse("accounts:profile") + "?section=notifications&notif_filter=unread"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'name="next" value="/accounts/profile/?section=notifications&amp;notif_filter=unread"',
            html=False,
        )

    def test_profile_language_switcher_inline_script_uses_csp_nonce(self):
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<script nonce="', html=False)
        self.assertContains(response, "document.currentScript", html=False)

    def test_profile_organization_access_rows_exclude_pending_owned_orgs(self):
        active_org = Organization.objects.create(
            name="Visible Active Org",
            slug="visible-active-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        Organization.objects.create(
            name="Hidden Pending Org",
            slug="hidden-pending-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="pending",
            is_active=True,
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        access_rows = response.context["organization_access_rows"]
        self.assertEqual([row["organization"].id for row in access_rows], [active_org.id])

    def test_pending_org_owner_profile_creates_pending_approval_notification(self):
        self.user.profile.role = ProfileRole.ORG_OWNER
        self.user.profile.save(update_fields=["role", "updated_at"])
        pending_org = Organization.objects.create(
            name="Profile Pending Org",
            slug="profile-pending-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="pending",
            is_active=True,
        )
        self.user.profile.organization = pending_org
        self.user.profile.requested_organization = pending_org
        self.user.profile.save(update_fields=["organization", "requested_organization", "updated_at"])

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.user,
                metadata__event="organization_pending_approval",
                metadata__organization_id=str(pending_org.id),
            ).exists()
        )

    def test_approved_org_owner_profile_restores_management_ui_without_existing_membership(self):
        self.user.profile.role = ProfileRole.ORG_OWNER
        self.user.profile.save(update_fields=["role", "updated_at"])
        approved_org = Organization.objects.create(
            name="Profile Approved Org",
            slug="profile-approved-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
            status="active",
            is_active=True,
        )
        self.user.profile.organization = approved_org
        self.user.profile.requested_organization = approved_org
        self.user.profile.save(update_fields=["organization", "requested_organization", "updated_at"])

        self.client.login(username="testuser", password="testpass123")
        session = self.client.session
        session.pop("active_organization", None)
        session.save()

        response = self.client.get(reverse("accounts:profile") + "?section=posts")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "?section=student-organization-management")
        self.assertContains(response, "?section=role-assignment")
        self.assertEqual(self.client.session.get("active_organization"), approved_org.slug)

    def test_join_organization_sidebar_and_section_are_translated_in_english(self):
        profile = self.user.profile
        profile.role = ProfileRole.TEACHER
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])
        self.client.login(username="testuser", password="testpass123")
        self.client.cookies["django_language"] = "en"
        response = self.client.get(
            reverse("accounts:profile") + "?section=student-organization-request",
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Join organization")
        self.assertContains(response, "Search current organizations, choose one")

    def test_staff_management_sidebar_and_section_are_translated_in_english(self):
        owner = User.objects.create_user(
            username="staff_org_owner",
            email="staff_org_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Staff Translation Org",
            slug="staff-translation-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.MEMBER, membership_role_name="dean")

        _login_with_org(self.client, self.user, organization)
        self.client.cookies["django_language"] = "en"
        response = self.client.get(
            reverse("accounts:profile") + "?section=student-organization-management",
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Management")
        self.assertContains(response, "Organization students")
        self.assertContains(response, "Student requests")

    def test_profile_notification_modal_keeps_real_newlines_and_internal_link_query(self):
        self.client.login(username="testuser", password="testpass123")
        create_notification(
            recipient=self.user,
            title="Permission reminder",
            message="Line 1\nLine 2",
            link=reverse("accounts:profile") + "?section=permission-editor&role=7",
        )

        response = self.client.get(reverse("accounts:profile") + "?section=notifications")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-notif-link="/accounts/profile/?section=permission-editor&amp;role=7"',
            html=False,
        )
        self.assertNotContains(response, "\\u000A", html=False)
        self.assertNotContains(response, "\\u003F", html=False)

    def test_profile_notifications_search_filters_results(self):
        self.client.login(username="testuser", password="testpass123")
        create_notification(recipient=self.user, title="Budget update", message="Quarterly report")
        create_notification(recipient=self.user, title="Exam reminder", message="Starts tomorrow")

        response = self.client.get(reverse("accounts:profile") + "?section=notifications&notif_search=budget")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Budget update")
        self.assertNotContains(response, "Exam reminder")
        self.assertEqual(response.context["in_app_notifications_page"].paginator.count, 1)
        self.assertEqual(
            response.context["notif_pagination_query"],
            "section=notifications&notif_filter=all&notif_search=budget",
        )

    def test_profile_notifications_pagination_uses_requested_page(self):
        self.client.login(username="testuser", password="testpass123")
        for index in range(11):
            create_notification(recipient=self.user, title=f"Notification {index}")

        response = self.client.get(reverse("accounts:profile") + "?section=notifications&notif_page=2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["in_app_notifications_page"].number, 2)

    def test_profile_change_password_updates_password_and_keeps_session(self):
        self.client.login(username="testuser", password="testpass123")

        response = self.client.post(
            reverse("accounts:profile") + "?section=change-password",
            data={
                "profile_form": "change-password",
                "section": "change-password",
                "old_password": "testpass123",
                "new_password1": "UpdatedStrongPass123!",
                "new_password2": "UpdatedStrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile") + "?section=change-password")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("UpdatedStrongPass123!"))

        follow_up = self.client.get(reverse("accounts:profile"))
        self.assertEqual(follow_up.status_code, 200)

    def test_profile_edit_section_prefills_existing_values(self):
        from apps.accounts.models import UserProfile
        from apps.courses.models import Course

        self.user.first_name = "Elvin"
        self.user.last_name = "Qurbanov"
        self.user.email = "elvin@example.com"
        self.user.save(update_fields=["first_name", "last_name", "email"])

        profile = UserProfile.objects.get(user=self.user)
        profile.phone = "+994501112233"
        profile.location = "Baku"
        profile.student_university_name = "ADA University"
        profile.student_school_identifier = "AZ-123"
        profile.bio = "Bio test text"
        profile.save(
            update_fields=[
                "phone",
                "location",
                "student_university_name",
                "student_school_identifier",
                "bio",
                "updated_at",
            ]
        )
        org = Organization.objects.create(
            name="Profile Edit Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        profile.organization = org
        profile.organization_type = org.org_type
        profile.save(update_fields=["organization", "organization_type", "updated_at"])
        Course.objects.create(owner=self.user, title="Owned Course", status="published", organization=org)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=edit-profile")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Elvin"')
        self.assertContains(response, 'value="Qurbanov"')
        self.assertContains(response, 'value="elvin@example.com"')
        self.assertContains(response, 'value="+994501112233"')
        self.assertContains(response, 'value="Baku"')
        self.assertContains(response, 'value="ADA University"')
        self.assertContains(response, 'value="AZ-123"')
        self.assertContains(response, "Bio test text")

    def test_non_profile_post_does_not_overwrite_profile_fields(self):
        from apps.accounts.models import UserProfile

        self.user.first_name = "Elvin"
        self.user.last_name = "Qurbanov"
        self.user.email = "elvin@example.com"
        self.user.save(update_fields=["first_name", "last_name", "email"])

        profile = UserProfile.objects.get(user=self.user)
        profile.phone = "+994501112233"
        profile.location = "Baku"
        profile.student_university_name = "ADA University"
        profile.student_school_identifier = "AZ-123"
        profile.bio = "Bio test text"
        profile.save(
            update_fields=[
                "phone",
                "location",
                "student_university_name",
                "student_school_identifier",
                "bio",
                "updated_at",
            ]
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            reverse("accounts:profile") + "?section=posts",
            data={"title": "Post title", "content": "Post content"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile") + "?section=posts")

        self.user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(self.user.first_name, "Elvin")
        self.assertEqual(self.user.last_name, "Qurbanov")
        self.assertEqual(self.user.email, "elvin@example.com")
        self.assertEqual(profile.phone, "+994501112233")
        self.assertEqual(profile.location, "Baku")
        self.assertEqual(profile.student_university_name, "ADA University")
        self.assertEqual(profile.student_school_identifier, "AZ-123")
        self.assertEqual(profile.bio, "Bio test text")

    def test_edit_profile_ignores_privilege_fields_from_post(self):
        from apps.accounts.models import ProfileRole, UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.role = ProfileRole.MEMBER
        profile.save(update_fields=["role", "updated_at"])

        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            reverse("accounts:profile") + "?section=edit-profile",
            data={
                "profile_form": "edit-profile",
                "first_name": "Safe",
                "last_name": "User",
                "email": "safe_user@example.com",
                "role": ProfileRole.ORG_ADMIN,
                "is_superuser": "1",
                "is_staff": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

        self.user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(self.user.first_name, "Safe")
        self.assertEqual(self.user.last_name, "User")
        self.assertEqual(self.user.email, "safe_user@example.com")
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_staff)
        self.assertEqual(profile.role, ProfileRole.MEMBER)

    def test_edit_profile_does_not_change_organization_type_from_post(self):
        from apps.accounts.models import UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.save(update_fields=["organization_type", "updated_at"])

        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            reverse("accounts:profile") + "?section=edit-profile",
            data={
                "profile_form": "edit-profile",
                "first_name": "Elvin",
                "last_name": "Qurbanov",
                "email": "elvin@example.com",
                "organization_type": OrganizationType.UNIVERSITY,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

        profile.refresh_from_db()
        self.assertEqual(profile.organization_type, OrganizationType.INDIVIDUAL)

    def test_superuser_is_teacher_and_admin(self):
        """Test that superusers always pass role checks."""
        superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        self.assertTrue(superuser.is_teacher_or_above)
        self.assertTrue(superuser.is_admin_level)

    def test_profile_my_exams_context_for_teacher(self):
        """Test that teacher profile includes my_exams context."""
        from apps.accounts.models import UserProfile
        from apps.exams.models import Exam

        UserProfile.objects.get(user=self.user)
        organization = Organization.objects.create(
            name="Teacher Profile Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)

        exam = Exam.objects.create(author=self.user, title="Profile Exam", is_active=True)

        _login_with_org(self.client, self.user, organization)

        profile_url = reverse("accounts:profile") + "?section=my-exams"
        response = self.client.get(profile_url)
        self.assertIn("my_exams_count", response.context)
        self.assertIn("my_created_courses_count", response.context)
        self.assertContains(response, f'{reverse("exams:teacher_exam_detail", args=[exam.slug])}?from_section=my-exams')
        expected_return_to = quote(response.wsgi_request.get_full_path(), safe="/")
        self.assertContains(response, f"return_to={expected_return_to}")

    def test_profile_my_exams_filters_practical_separately_from_written(self):
        from apps.exams.models import Exam

        organization = Organization.objects.create(
            name="Teacher Practical Filter Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)

        written_exam = Exam.objects.create(
            author=self.user,
            title="Profile Written Filter Exam",
            exam_type="written",
            is_active=True,
        )
        coding_exam = Exam.objects.create(
            author=self.user,
            title="Profile Practical Filter Exam",
            exam_type="coding",
            is_active=True,
        )

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile") + "?section=my-exams&exam_type=coding")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["my_exams_filter_type"], "coding")
        self.assertContains(response, 'value="coding" selected', html=False)
        self.assertContains(response, coding_exam.title)
        self.assertNotContains(response, written_exam.title)

    def test_publish_notification_section_renders_search_and_scrollable_targets(self):
        from apps.exams.models import StudentGroup

        organization = Organization.objects.create(
            name="Notification Search Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)
        StudentGroup.objects.create(
            teacher=self.user,
            organization=organization,
            name="Alpha Search Group",
        )

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile") + "?section=publish-notification")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="pnTargetSearch"', html=False)
        self.assertContains(response, 'class="pn-target-scroll"', html=False)
        self.assertContains(response, "Alpha Search Group")

    def test_publish_notification_post_sends_group_notification_and_redirects_back(self):
        from apps.exams.models import StudentGroup
        from apps.notifications.models import InAppNotification

        organization = Organization.objects.create(
            name="Notification Delivery Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="notif_student",
            email="notif_student@example.com",
            password="testpass123",
        )
        _assign_user_to_org(student, organization, ProfileRole.STUDENT)

        group = StudentGroup.objects.create(
            teacher=self.user,
            organization=organization,
            name="Broadcast Group",
        )
        group.students.add(student)

        _login_with_org(self.client, self.user, organization)
        response = self.client.post(
            reverse("accounts:profile") + "?section=publish-notification",
            data={
                "profile_form": "publish-notification",
                "section": "publish-notification",
                "notif_title": "Group update",
                "notif_message": "Important schedule change",
                "notif_targets": [f"group_{group.pk}"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile") + "?section=publish-notification")

        notifications = InAppNotification.objects.filter(recipient=student)
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.first().title, "Group update")

    def test_publish_notification_org_targets_are_unique_per_organization(self):
        organization = Organization.objects.create(
            name="Notification Unique Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)
        Membership.objects.create(
            user=self.user,
            organization=organization,
            role=organization.roles.get(name="rector"),
            is_primary=False,
            is_active=True,
        )

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile") + "?section=publish-notification")

        self.assertEqual(response.status_code, 200)
        targets = response.context["publish_notification_targets"]
        org_targets = [target for target in targets if target["value"] == f"org_{organization.pk}"]
        self.assertEqual(len(org_targets), 1)
        self.assertEqual(
            [target["label"] for target in org_targets],
            ["Təşkilat: Notification Unique Org (bütün üzvlər)"],
        )

    def test_superadmin_publish_notification_can_target_organization_uuid(self):
        from apps.notifications.models import InAppNotification

        superadmin = User.objects.create_superuser(
            username="notif_superadmin",
            email="notif_superadmin@example.com",
            password="adminpass123",
        )
        organization_owner = User.objects.create_user(
            username="notif_org_owner",
            email="notif_org_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Notification UUID Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=organization_owner,
            status="active",
            is_active=True,
        )
        recipient = User.objects.create_user(
            username="notif_org_member",
            email="notif_org_member@example.com",
            password="testpass123",
        )
        _assign_user_to_org(recipient, organization, ProfileRole.STUDENT)

        self.client.force_login(superadmin)
        response = self.client.post(
            reverse("accounts:profile") + "?section=publish-notification",
            data={
                "profile_form": "publish-notification",
                "section": "publish-notification",
                "notif_title": "Org update",
                "notif_message": "Organization-wide announcement",
                "notif_targets": [f"org_{organization.pk}"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile") + "?section=publish-notification")

        notifications = InAppNotification.objects.filter(recipient=recipient)
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.first().title, "Org update")

    def test_profile_role_field(self):
        """Test that profile has role field with default member role."""
        from apps.accounts.models import ProfileRole, UserProfile

        self.client.login(username="testuser", password="testpass123")
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.role, ProfileRole.MEMBER)
        self.assertEqual(profile.role_level, 20)

    def test_profile_role_level_check(self):
        """Test that active-organization membership is used for role level checks."""
        organization = Organization.objects.create(
            name="Role Level Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)
        self.user.set_active_organization_context(organization)
        self.assertTrue(self.user.is_teacher_or_above)

    def test_student_profile_hides_teacher_and_admin_navigation(self):
        owner = User.objects.create_user(
            username="student_nav_owner",
            email="student_nav_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Student Navigation Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.STUDENT)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("accounts:role_assignment"))
        self.assertNotContains(response, reverse("accounts:permission_editor"))
        self.assertNotContains(response, reverse("exams:teacher_group_list"))
        self.assertNotContains(response, reverse("accounts:pending_review"))

    def test_student_profile_shows_posts_and_results_navigation(self):
        owner = User.objects.create_user(
            username="student_results_owner",
            email="student_results_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Student Results Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.STUDENT)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("create_post"))
        self.assertContains(response, reverse("accounts:my_results"))
        self.assertContains(response, reverse("accounts:pending_answers"))
        self.assertContains(response, reverse("accounts:student_organization_request"))
        self.assertContains(response, reverse("accounts:profile") + "?section=notifications")

    def test_student_with_pending_join_request_can_open_profile_without_active_org(self):
        owner = User.objects.create_user(
            username="student_pending_owner",
            email="student_pending_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Student Pending Request Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        profile = self.user.profile
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.role = ProfileRole.STUDENT
        profile.requested_organization = organization
        profile.requested_organization_name = organization.name
        profile.requested_organization_message = "Qoşulmaq istəyirəm"
        profile.student_university_name = organization.name
        profile.save(
            update_fields=[
                "organization",
                "organization_type",
                "role",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "student_university_name",
                "updated_at",
            ]
        )
        StudentOrganizationRequest.objects.create(
            user=self.user,
            organization=organization,
            status=StudentOrganizationRequestStatus.PENDING,
            message="Qoşulmaq istəyirəm",
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təşkilat təsdiqi gözlənilir")
        self.assertContains(response, organization.name)

    def test_profile_uses_effective_role_label_without_active_org_context(self):
        profile = self.user.profile
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.role = ProfileRole.STUDENT
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(response.context["primary_user_role_label"], "Tələbə")
        self.assertEqual(response.context["user_roles"][0]["name"], ProfileRole.STUDENT)
        self.assertContains(response, "Tələbə")
        self.assertIn('href="/accounts/profile/"', content)
        self.assertIn("blog-header__nav-link--active", content)
        self.assertIn("blog-header__nav-link--logout", content)
        self.assertNotContains(response, ">İstifadəçi<", html=False)

    def test_profile_info_shows_student_group_membership_readonly(self):
        from apps.accounts.models import ProfileRole
        from apps.exams.models import StudentGroup
        from apps.organizations.models import Membership, Organization, Role
        from core.constants import OrganizationType, RoleScopeType

        owner = User.objects.create_user(
            username="group_owner",
            email="group_owner@example.com",
            password="testpass123",
        )
        teacher = User.objects.create_user(
            username="group_teacher",
            email="group_teacher@example.com",
            password="testpass123",
        )

        organization = Organization.objects.create(
            name="Group Test University",
            slug="group-test-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            is_active=True,
            status="active",
        )
        teacher_role, _ = Role.objects.get_or_create(
            organization=organization,
            name="teacher",
            defaults={
                "display_name": "Müəllim",
                "level": 60,
                "scope_type": RoleScopeType.ORGANIZATION,
                "is_system": True,
                "is_active": True,
            },
        )
        student_role, _ = Role.objects.get_or_create(
            organization=organization,
            name="student",
            defaults={
                "display_name": "Tələbə",
                "level": 10,
                "scope_type": RoleScopeType.ORGANIZATION,
                "is_system": True,
                "is_active": True,
            },
        )

        teacher_profile = teacher.profile
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.organization = organization
        teacher_profile.organization_type = OrganizationType.UNIVERSITY
        teacher_profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])

        student_profile = self.user.profile
        student_profile.role = ProfileRole.STUDENT
        student_profile.organization = organization
        student_profile.organization_type = OrganizationType.UNIVERSITY
        student_profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])

        Membership.objects.create(
            user=teacher,
            organization=organization,
            role=teacher_role,
            is_primary=True,
            is_active=True,
        )
        Membership.objects.create(
            user=self.user,
            organization=organization,
            role=student_role,
            is_primary=True,
            is_active=True,
        )

        student_group = StudentGroup.objects.create(
            teacher=teacher,
            organization=organization,
            name="Qrup 101",
        )
        student_group.students.add(self.user)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=profile-info")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Qrup üzvlüyü")
        self.assertContains(response, "Qrup 101")
        self.assertContains(response, "Group Test University")

    def test_profile_info_handles_many_student_groups_without_breaking(self):
        from apps.accounts.models import ProfileRole
        from apps.exams.models import StudentGroup
        from apps.organizations.models import Membership, Organization, Role
        from core.constants import OrganizationType, RoleScopeType

        owner = User.objects.create_user(
            username="group_owner_many",
            email="group_owner_many@example.com",
            password="testpass123",
        )
        teacher = User.objects.create_user(
            username="group_teacher_many",
            email="group_teacher_many@example.com",
            password="testpass123",
        )

        organization = Organization.objects.create(
            name="Many Group University",
            slug="many-group-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            is_active=True,
            status="active",
        )
        teacher_role, _ = Role.objects.get_or_create(
            organization=organization,
            name="teacher",
            defaults={
                "display_name": "Müəllim",
                "level": 60,
                "scope_type": RoleScopeType.ORGANIZATION,
                "is_system": True,
                "is_active": True,
            },
        )
        student_role, _ = Role.objects.get_or_create(
            organization=organization,
            name="student",
            defaults={
                "display_name": "Tələbə",
                "level": 10,
                "scope_type": RoleScopeType.ORGANIZATION,
                "is_system": True,
                "is_active": True,
            },
        )

        teacher_profile = teacher.profile
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.organization = organization
        teacher_profile.organization_type = OrganizationType.UNIVERSITY
        teacher_profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])

        student_profile = self.user.profile
        student_profile.role = ProfileRole.STUDENT
        student_profile.organization = organization
        student_profile.organization_type = OrganizationType.UNIVERSITY
        student_profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])

        Membership.objects.create(
            user=teacher,
            organization=organization,
            role=teacher_role,
            is_primary=True,
            is_active=True,
        )
        Membership.objects.create(
            user=self.user,
            organization=organization,
            role=student_role,
            is_primary=True,
            is_active=True,
        )

        for idx in range(55):
            group = StudentGroup.objects.create(
                teacher=teacher,
                organization=organization,
                name=f"Qrup-{idx:02d}",
            )
            group.students.add(self.user)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=profile-info")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "55 qrup")
        self.assertContains(response, "+5 əlavə qrup var")

    def test_profile_info_restores_group_membership_from_profile_org_when_session_org_is_missing(self):
        from apps.exams.models import StudentGroup

        owner = User.objects.create_user(
            username="group_owner_restore",
            email="group_owner_restore@example.com",
            password="testpass123",
        )
        teacher = User.objects.create_user(
            username="group_teacher_restore",
            email="group_teacher_restore@example.com",
            password="testpass123",
        )

        primary_org = Organization.objects.create(
            name="Restore Group University",
            slug="restore-group-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            is_active=True,
            status="active",
        )

        _assign_user_to_org(teacher, primary_org, ProfileRole.TEACHER)
        _assign_user_to_org(self.user, primary_org, ProfileRole.STUDENT)

        student_group = StudentGroup.objects.create(
            teacher=teacher,
            organization=primary_org,
            name="Qrup Restore 101",
        )
        student_group.students.add(self.user)

        self.client.login(username="testuser", password="testpass123")
        session = self.client.session
        session.pop("active_organization", None)
        session.save()

        response = self.client.get(reverse("accounts:profile") + "?section=profile-info")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Qrup Restore 101")
        self.assertContains(response, "Restore Group University")
        self.assertEqual(self.client.session.get("active_organization"), primary_org.slug)

    def test_profile_avatar_update_form_updates_avatar_and_navbar(self):
        tiny_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00"
            b"\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        avatar_file = SimpleUploadedFile("avatar.png", tiny_png, content_type="image/png")

        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "profile_form": "update-avatar",
                "section": "profile-info",
                "avatar": avatar_file,
            },
        )

        self.assertRedirects(response, reverse("accounts:profile") + "?section=profile-info")
        self.user.refresh_from_db()
        self.assertTrue(self.user.profile.avatar.name.startswith("avatars/"))

        avatar_response = self.client.get(reverse("accounts:profile_avatar", kwargs={"user_id": self.user.id}))
        self.assertEqual(avatar_response.status_code, 200)
        self.assertEqual(avatar_response["Content-Type"], "image/png")

        versioned_avatar_response = self.client.get(
            reverse("accounts:profile_avatar", kwargs={"user_id": self.user.id}),
            {"v": "1710000000"},
        )
        self.assertEqual(versioned_avatar_response.status_code, 200)
        self.assertEqual(versioned_avatar_response["Content-Type"], "image/png")

        profile_response = self.client.get(reverse("accounts:profile") + "?section=profile-info")
        self.assertEqual(profile_response.status_code, 200)
        self.assertContains(profile_response, "blog-header__user-avatar-image")

    def test_profile_avatar_rejects_invalid_version_parameter(self):
        tiny_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00"
            b"\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        self.user.profile.avatar = SimpleUploadedFile("avatar.png", tiny_png, content_type="image/png")
        self.user.profile.save(update_fields=["avatar", "updated_at"])
        self.client.login(username="testuser", password="testpass123")

        avatar_url = reverse("accounts:profile_avatar", kwargs={"user_id": self.user.id})

        for payload in (
            "1773691661' AND '1'='1' --",
            "1773691663-2",
            "'(",
            '"',
            ";",
            "()",
            "ZAP%n%s%n%s",
            "ZAP%x%x%x%x",
        ):
            with self.subTest(payload=payload):
                response = self.client.get(avatar_url, {"v": payload})
                self.assertEqual(response.status_code, 400)

    def test_student_profile_keeps_single_assigned_courses_sidebar_entry(self):
        owner = User.objects.create_user(
            username="student_sidebar_owner",
            email="student_sidebar_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Student Sidebar Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.STUDENT)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:assigned_courses"))
        self.assertNotContains(response, reverse("accounts:profile") + "?section=courses")

    def test_teacher_profile_shows_teacher_navigation_only(self):
        owner = User.objects.create_user(
            username="teacher_nav_owner",
            email="teacher_nav_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Teacher Navigation Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("exams:teacher_group_list"))
        self.assertContains(response, reverse("accounts:pending_review"))
        self.assertNotContains(response, reverse("accounts:superadmin_organizations"))
        self.assertNotContains(response, reverse("accounts:student_organization_management"))
        self.assertContains(response, reverse("accounts:student_organization_request"))
        self.assertContains(response, reverse("accounts:student_leave_organization"))

    def test_profile_restores_org_context_for_teacher_course_modal(self):
        personal_org = Organization.objects.create(
            name="Teacher Personal Workspace",
            org_type=OrganizationType.INDIVIDUAL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        Membership.objects.update_or_create(
            user=self.user,
            organization=personal_org,
            defaults={
                "role": personal_org.roles.get(name="member"),
                "is_primary": True,
                "is_active": True,
            },
        )

        school_owner = User.objects.create_user(
            username="teacher_school_owner",
            email="teacher_school_owner@example.com",
            password="testpass123",
        )
        school_org = Organization.objects.create(
            name="Teacher Course Org",
            org_type=OrganizationType.SCHOOL,
            owner=school_owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, school_org, ProfileRole.TEACHER)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=my-courses")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get("active_organization"), school_org.slug)

        modal_response = self.client.get(
            reverse("courses:create_course") + "?modal=1",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(modal_response.status_code, 200)
        self.assertContains(modal_response, 'id="createCourseModalForm"', html=False)

    def test_teacher_without_org_sees_join_request_navigation(self):
        teacher_user = User.objects.create_user(
            username="teacher_join_nav",
            email="teacher_join_nav@example.com",
            password="testpass123",
        )
        teacher_profile = teacher_user.profile
        teacher_profile.organization = None
        teacher_profile.organization_type = OrganizationType.INDIVIDUAL
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.requested_organization = None
        teacher_profile.requested_organization_name = ""
        teacher_profile.requested_organization_message = ""
        teacher_profile.save(
            update_fields=[
                "organization",
                "organization_type",
                "role",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "updated_at",
            ]
        )

        self.client.force_login(teacher_user)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{reverse('accounts:profile')}?section=student-organization-request")
        self.assertContains(response, "Təşkilata qoşul")

    def test_join_request_navigation_stays_under_general_sidebar_group(self):
        owner = User.objects.create_user(
            username="general_nav_owner",
            email="general_nav_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="General Navigation Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        notifications_link = content.index(f'{reverse("accounts:profile")}?section=notifications')
        join_link = content.index("?section=student-organization-request")
        posts_link = content.index(f'{reverse("accounts:profile")}?section=posts')
        self.assertLess(notifications_link, join_link)
        self.assertLess(join_link, posts_link)

    def test_profile_info_shows_pending_organization_invites_for_student_without_selected_org(self):
        owner = User.objects.create_user(
            username="invite_owner",
            email="invite_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Invite Ready Org",
            slug="invite-ready-org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )

        profile = self.user.profile
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.role = ProfileRole.STUDENT
        profile.requested_organization = None
        profile.requested_organization_name = ""
        profile.requested_organization_message = ""
        profile.save(
            update_fields=[
                "organization",
                "organization_type",
                "role",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "updated_at",
            ]
        )

        Membership.objects.create(
            user=self.user,
            organization=organization,
            role=organization.roles.get(name="student"),
            assigned_by=owner,
            is_primary=False,
            is_active=False,
            title="__student_pending_invite__",
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=profile-info")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təşkilat dəvətləri")
        self.assertContains(response, "Invite Ready Org")
        self.assertContains(response, "Qəbul et")
        self.assertContains(response, reverse("accounts:student_org_invitation_action"))
        self.assertContains(response, "?section=student-organization-request")

    def test_student_without_selected_org_can_accept_invite_from_profile_info(self):
        owner = User.objects.create_user(
            username="accept_owner",
            email="accept_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Accepted From Profile Org",
            slug="accepted-from-profile-org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )

        profile = self.user.profile
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.role = ProfileRole.STUDENT
        profile.requested_organization = None
        profile.requested_organization_name = ""
        profile.requested_organization_message = ""
        profile.save(
            update_fields=[
                "organization",
                "organization_type",
                "role",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "updated_at",
            ]
        )

        invite_membership = Membership.objects.create(
            user=self.user,
            organization=organization,
            role=organization.roles.get(name="student"),
            assigned_by=owner,
            is_primary=False,
            is_active=False,
            title="__student_pending_invite__",
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            reverse("accounts:student_org_invitation_action"),
            {
                "invite_id": str(invite_membership.id),
                "action": "accept",
                "next": reverse("accounts:profile") + "?section=profile-info",
            },
        )

        self.assertRedirects(response, reverse("accounts:profile") + "?section=profile-info")

        profile.refresh_from_db()
        invite_membership.refresh_from_db()
        self.assertEqual(profile.organization, organization)
        self.assertEqual(profile.role, ProfileRole.STUDENT)
        self.assertEqual(profile.requested_organization, organization)
        self.assertTrue(invite_membership.is_active)
        self.assertEqual(invite_membership.title, "")

    def test_member_profile_shows_group_navigation(self):
        owner = User.objects.create_user(
            username="member_nav_owner",
            email="member_nav_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Member Navigation Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.MEMBER)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("exams:teacher_group_list"))
        self.assertNotContains(response, reverse("accounts:pending_review"))
        self.assertContains(response, reverse("accounts:student_organization_request"))
        self.assertContains(response, reverse("accounts:student_leave_organization"))

    def test_groups_section_supports_search_detail_and_student_pagination(self):
        from apps.exams.models import StudentGroup

        organization = Organization.objects.create(
            name="Groups Detail Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)

        alpha_group = StudentGroup.objects.create(
            teacher=self.user,
            organization=organization,
            name="Alpha Detail Group",
        )
        StudentGroup.objects.create(
            teacher=self.user,
            organization=organization,
            name="Beta Hidden Group",
        )
        for idx in range(15):
            student = User.objects.create_user(
                username=f"group_student_{idx:02d}",
                email=f"group_student_{idx:02d}@example.com",
                password="testpass123",
            )
            _assign_user_to_org(student, organization, ProfileRole.STUDENT)
            alpha_group.students.add(student)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "groups",
                "group_q": "Alpha",
                "group": str(alpha_group.id),
                "students_page": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["teacher_groups_filtered_count"], 1)
        self.assertEqual(response.context["selected_teacher_group"], alpha_group)
        self.assertEqual(response.context["selected_group_students_count"], 15)
        self.assertEqual(response.context["selected_group_students_page"].number, 2)
        self.assertEqual([group.name for group in response.context["teacher_groups"]], ["Alpha Detail Group"])
        self.assertContains(response, "Qrup detalları")
        self.assertContains(response, "Alpha Detail Group")
        self.assertContains(response, "group_student_12")

    def test_org_admin_profile_shows_groups_and_management_navigation(self):
        organization = Organization.objects.create(
            name="Org Admin Navigation Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.ORG_ADMIN)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{reverse('accounts:profile')}?section=role-assignment")
        self.assertContains(response, reverse("accounts:student_organization_management"))
        self.assertContains(response, reverse("accounts:permission_editor"))
        self.assertNotContains(response, reverse("accounts:pending_review"))
        self.assertContains(response, reverse("exams:teacher_group_list"))
        # Management-section CONTENT is delivered lazily by the AJAX section
        # loader (the base profile page only renders the active section plus
        # empty placeholders), so assert the navigation entries here and verify
        # the level-role / multi-role content via the actual section endpoints.
        self.assertContains(response, f"{reverse('accounts:profile')}?section=manage-roles")

        role_assignment_response = self.client.get(reverse("accounts:profile") + "?section=role-assignment")
        self.assertEqual(role_assignment_response.status_code, 200)
        self.assertContains(role_assignment_response, "Təşkilat daxili rol (səviyyəli rol)")

        manage_roles_response = self.client.get(reverse("accounts:profile") + "?section=manage-roles")
        self.assertEqual(manage_roles_response.status_code, 200)
        self.assertContains(manage_roles_response, "Profil rolları (multi-role / checkbox)")

    def test_org_admin_profile_staff_management_marks_all_invite_forms_for_frontend(self):
        organization = Organization.objects.create(
            name="Org Admin Invite Binding Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.ORG_ADMIN)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile") + "?section=student-organization-management")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertRegex(
            content,
            r'<form[^>]*data-unassigned-form[^>]*>[\s\S]*?id="selectAllUnassignedStudents"',
        )
        self.assertRegex(
            content,
            r'<form[^>]*data-unassigned-form[^>]*>[\s\S]*?id="selectAllUnassignedTeachers"',
        )
        self.assertRegex(
            content,
            r'<form[^>]*data-unassigned-form[^>]*>[\s\S]*?id="selectAllUnassignedStaff"',
        )

    def test_manage_roles_table_shows_username(self):
        superuser = User.objects.create_superuser(
            username="profile_superadmin",
            email="profile_superadmin@example.com",
            password="adminpass123",
        )
        organization = Organization.objects.create(
            name="Manage Roles Table Org",
            org_type=OrganizationType.SCHOOL,
            owner=superuser,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.MEMBER)
        _login_with_org(self.client, superuser, organization)
        response = self.client.get(reverse("accounts:manage_roles"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"@{self.user.username}")

    def test_superadmin_profile_shows_user_management_as_inline_section(self):
        superuser = User.objects.create_superuser(
            username="inline_superadmin",
            email="inline_superadmin@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'{reverse("accounts:profile")}?section=superadmin-users')
        self.assertContains(response, 'data-section="superadmin-users"', html=False)
        self.assertContains(response, 'data-profile-section-panel="superadmin-users"', html=False)

    def test_superadmin_profile_shows_ai_settings_as_inline_section(self):
        superuser = User.objects.create_superuser(
            username="ai_inline_superadmin",
            email="ai_inline_superadmin@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'{reverse("accounts:profile")}?section=superadmin-ai')
        self.assertContains(response, 'data-section="superadmin-ai"', html=False)
        self.assertContains(response, 'data-profile-section-panel="superadmin-ai"', html=False)

    def test_superadmin_profile_shows_org_features_as_inline_section(self):
        superuser = User.objects.create_superuser(
            username="feature_inline_superadmin",
            email="feature_inline_superadmin@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'{reverse("accounts:profile")}?section=superadmin-org-features')
        self.assertContains(response, 'data-section="superadmin-org-features"', html=False)
        self.assertContains(response, 'data-profile-section-panel="superadmin-org-features"', html=False)

    def test_superadmin_ai_settings_section_renders_inside_profile(self):
        superuser = User.objects.create_superuser(
            username="ai_section_superadmin",
            email="ai_section_superadmin@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse("accounts:profile") + "?section=superadmin-ai")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_section"], "superadmin-ai")
        self.assertContains(response, 'data-profile-section-panel="superadmin-ai"', html=False)
        self.assertContains(
            response,
            f'name="next" value="{reverse("accounts:profile")}?section=superadmin-ai"',
            html=False,
        )

    def test_superadmin_org_features_section_renders_inside_profile(self):
        superuser = User.objects.create_superuser(
            username="feature_section_superadmin",
            email="feature_section_superadmin@example.com",
            password="adminpass123",
        )
        org_owner = User.objects.create_user(
            username="feature_section_owner",
            email="feature_section_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Feature Section Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=org_owner,
            status="active",
            is_active=True,
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse("accounts:profile") + "?section=superadmin-org-features")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_section"], "superadmin-org-features")
        self.assertContains(response, 'data-profile-section-panel="superadmin-org-features"', html=False)
        self.assertContains(response, organization.name)
        self.assertContains(response, "Yazılı imtahan")
        self.assertContains(response, "Sərbəst iş")
        self.assertContains(response, "Kurs işi")
        self.assertContains(response, "Lab işi")
        self.assertContains(
            response,
            f'name="next" value="{reverse("accounts:profile")}?section=superadmin-org-features"',
            html=False,
        )

    def test_superadmin_ai_settings_post_respects_next_redirect(self):
        superuser = User.objects.create_superuser(
            username="ai_post_superadmin",
            email="ai_post_superadmin@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        response = self.client.post(
            reverse("accounts:superadmin_ai_settings"),
            {
                "action": "save",
                "enabled": "on",
                "rate_limit": "120/1h",
                "summary_model": "gemini-2.5-flash",
                "grading_model": "gemini-2.5-flash-lite",
                "monthly_budget": "8.50",
                "next": f'{reverse("accounts:profile")}?section=superadmin-ai',
            },
            follow=False,
        )

        self.assertRedirects(
            response,
            reverse("accounts:profile") + "?section=superadmin-ai",
            fetch_redirect_response=False,
        )

    def test_superadmin_user_management_filters_blocked_users_by_role_and_group(self):
        superuser = User.objects.create_superuser(
            username="filter_superadmin",
            email="filter_superadmin@example.com",
            password="adminpass123",
        )
        organization = Organization.objects.create(
            name="Superadmin Filter Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=superuser,
            status="active",
            is_active=True,
        )

        blocked_user = User.objects.create_user(
            username="blocked_student",
            email="blocked_student@example.com",
            password="testpass123",
        )
        _assign_user_to_org(blocked_user, organization, ProfileRole.STUDENT)
        blocked_user.profile.student_group_number = "CS-204"
        blocked_user.profile.save(update_fields=["student_group_number", "updated_at"])
        blocked_user.is_active = False
        blocked_user.save(update_fields=["is_active"])

        active_user = User.objects.create_user(
            username="active_student",
            email="active_student@example.com",
            password="testpass123",
        )
        _assign_user_to_org(active_user, organization, ProfileRole.STUDENT)
        active_user.profile.student_group_number = "BIO-101"
        active_user.profile.save(update_fields=["student_group_number", "updated_at"])

        self.client.force_login(superuser)
        response = self.client.get(
            reverse("accounts:profile")
            + "?section=superadmin-users&user_status=blocked&user_role=student&user_group=CS-204"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "blocked_student")
        self.assertNotContains(response, "active_student")
        self.assertContains(response, "Bloklanıb")

    def test_superadmin_can_block_user_from_management(self):
        superuser = User.objects.create_superuser(
            username="block_superadmin",
            email="block_superadmin@example.com",
            password="adminpass123",
        )
        target_user = User.objects.create_user(
            username="block_target",
            email="block_target@example.com",
            password="testpass123",
        )

        self.client.force_login(superuser)
        response = self.client.post(
            reverse("accounts:superadmin_user_management"),
            {
                "action": "block",
                "user_id": target_user.pk,
                "next": reverse("accounts:profile") + "?section=superadmin-users&user_status=blocked",
            },
        )

        self.assertRedirects(response, reverse("accounts:profile") + "?section=superadmin-users&user_status=blocked")
        target_user.refresh_from_db()
        self.assertFalse(target_user.is_active)

    def test_superadmin_can_soft_delete_user_from_management(self):
        superuser = User.objects.create_superuser(
            username="delete_superadmin",
            email="delete_superadmin@example.com",
            password="adminpass123",
        )
        target_user = User.objects.create_user(
            username="delete_target",
            email="delete_target@example.com",
            password="testpass123",
        )

        self.client.force_login(superuser)
        response = self.client.post(
            reverse("accounts:superadmin_user_management"),
            {
                "action": "soft_delete",
                "user_id": target_user.pk,
                "next": reverse("accounts:profile") + "?section=superadmin-users&user_status=deleted",
            },
        )

        self.assertRedirects(response, reverse("accounts:profile") + "?section=superadmin-users&user_status=deleted")
        target_user.refresh_from_db()
        target_user.profile.refresh_from_db()
        self.assertFalse(target_user.is_active)
        self.assertTrue(target_user.profile.is_deleted)

    def test_superadmin_can_hard_delete_soft_deleted_pending_org_owner(self):
        superuser = User.objects.create_superuser(
            username="hard_delete_superadmin",
            email="hard_delete_superadmin@example.com",
            password="adminpass123",
        )
        target_user = User.objects.create_user(
            username="pending_owner_target",
            email="pending_owner_target@example.com",
            password="testpass123",
        )
        pending_org = Organization.objects.create(
            name="Pending Owner Org",
            org_type=OrganizationType.SCHOOL,
            owner=target_user,
            status="pending",
            is_active=True,
            organization_identifier="SCH-900",
            license_identifier="LIC-900",
        )

        self.client.force_login(superuser)

        soft_delete_response = self.client.post(
            reverse("accounts:superadmin_user_management"),
            {
                "action": "soft_delete",
                "user_id": target_user.pk,
                "next": reverse("accounts:profile") + "?section=superadmin-users&user_status=deleted",
            },
        )

        self.assertRedirects(
            soft_delete_response,
            reverse("accounts:profile") + "?section=superadmin-users&user_status=deleted",
        )

        hard_delete_response = self.client.post(
            reverse("accounts:superadmin_user_management"),
            {
                "action": "hard_delete",
                "user_id": target_user.pk,
                "next": reverse("accounts:profile") + "?section=superadmin-users&user_status=deleted",
            },
        )

        self.assertRedirects(
            hard_delete_response,
            reverse("accounts:profile") + "?section=superadmin-users&user_status=deleted",
        )
        self.assertFalse(User.objects.filter(pk=target_user.pk).exists())
        self.assertFalse(Organization.objects.filter(pk=pending_org.pk).exists())

    def test_manage_roles_shows_primary_role_summary_for_multi_role_user(self):
        from apps.accounts.models import ProfileRole
        from apps.organizations.models import Membership

        superuser = User.objects.create_superuser(
            username="profile_superadmin_primary",
            email="profile_superadmin_primary@example.com",
            password="adminpass123",
        )
        organization = Organization.objects.create(
            name="Manage Roles Primary Org",
            org_type=OrganizationType.SCHOOL,
            owner=superuser,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)
        Membership.objects.update_or_create(
            user=self.user,
            organization=organization,
            role=organization.roles.get(name="member"),
            defaults={
                "is_primary": False,
                "is_active": True,
            },
        )

        _login_with_org(self.client, superuser, organization)
        response = self.client.get(reverse("accounts:manage_roles"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primary:")
        self.assertContains(response, "Müəllim (60)")

    def test_org_owner_with_teacher_secondary_role_sees_teacher_navigation(self):
        organization = Organization.objects.create(
            name="Owner Teacher Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.TEACHER)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:pending_review"))

    def test_org_owner_can_assign_secondary_role_to_self_via_manage_roles(self):
        organization = Organization.objects.create(
            name="Owner Self Manage Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
            status="active",
            is_active=True,
        )
        profile = self.user.profile
        profile.organization = organization
        profile.organization_type = organization.org_type
        profile.role = ProfileRole.ORG_OWNER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        Membership.objects.update_or_create(
            user=self.user,
            organization=organization,
            role=organization.roles.get(name="rector"),
            defaults={
                "is_primary": True,
                "is_active": True,
            },
        )

        _login_with_org(self.client, self.user, organization)
        response = self.client.post(
            reverse("accounts:manage_roles"),
            data={
                "user_id": self.user.id,
                "action": "assign",
                "role_names": [ProfileRole.TEACHER],
                "next": reverse("accounts:manage_roles"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:manage_roles"))

        self.user.refresh_from_db()
        self.user.set_active_organization_context(organization)
        self.assertTrue(self.user.has_role(ProfileRole.ORG_OWNER))
        self.assertTrue(self.user.has_role(ProfileRole.TEACHER))
        self.assertTrue(
            Membership.objects.filter(
                user=self.user,
                organization=organization,
                role__name="teacher",
                is_active=True,
            ).exists()
        )

    def test_profile_page_does_not_backfill_teacher_membership_from_legacy_profile_role(self):
        organization = Organization.objects.create(
            name="Legacy Teacher Owner Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
            status="active",
            is_active=True,
        )
        profile = self.user.profile
        profile.organization = organization
        profile.organization_type = organization.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        Membership.objects.update_or_create(
            user=self.user,
            organization=organization,
            role=organization.roles.get(name="rector"),
            defaults={
                "is_primary": True,
                "is_active": True,
            },
        )

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("accounts:pending_review"))
        self.assertTrue(
            Membership.objects.filter(
                user=self.user,
                organization=organization,
                role__name="rector",
                is_active=True,
            ).exists()
        )
        self.assertFalse(
            Membership.objects.filter(
                user=self.user,
                organization=organization,
                role__name="teacher",
                is_active=True,
            ).exists()
        )

    def test_superadmin_profile_lists_owned_and_member_organizations(self):
        superuser = User.objects.create_superuser(
            username="profile_superadmin_orgs",
            email="profile_superadmin_orgs@example.com",
            password="adminpass123",
        )
        owned_org = Organization.objects.create(
            name="Superadmin Owned Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=superuser,
            status="active",
            is_active=True,
        )
        member_owner = User.objects.create_user(
            username="member_org_owner",
            email="member_org_owner@example.com",
            password="testpass123",
        )
        member_org = Organization.objects.create(
            name="Superadmin Member Org",
            org_type=OrganizationType.SCHOOL,
            owner=member_owner,
            status="active",
            is_active=True,
        )
        Membership.objects.update_or_create(
            user=superuser,
            organization=member_org,
            role=member_org.roles.get(name="teacher"),
            defaults={
                "is_primary": True,
                "is_active": True,
            },
        )

        _login_with_org(self.client, superuser, member_org)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təşkilat girişləri")
        self.assertContains(response, owned_org.name)
        self.assertContains(response, member_org.name)
        self.assertContains(response, reverse("organizations:dashboard", kwargs={"slug": member_org.slug}))
        self.assertContains(response, reverse("organizations:switch", kwargs={"slug": owned_org.slug}))

    def test_superadmin_profile_renders_superadmin_control_inside_profile_without_active_org(self):
        superuser = User.objects.create_superuser(
            username="profile_superadmin_org_management",
            email="profile_superadmin_org_management@example.com",
            password="adminpass123",
        )
        owner_pending = User.objects.create_user(
            username="pending_org_owner",
            email="pending_org_owner@example.com",
            password="testpass123",
        )
        owner_active = User.objects.create_user(
            username="active_org_owner",
            email="active_org_owner@example.com",
            password="testpass123",
        )
        pending_org = Organization.objects.create(
            name="Pending Profile Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner_pending,
            status="pending",
            is_active=True,
        )
        active_org = Organization.objects.create(
            name="Active Profile Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner_active,
            status="active",
            is_active=True,
        )

        self.client.force_login(superuser)
        response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "superadmin-organizations",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "?section=superadmin-organizations")
        self.assertContains(response, pending_org.name)
        self.assertContains(response, active_org.name)
        self.assertContains(response, reverse("accounts:superadmin_organizations"))
        self.assertContains(
            response,
            'name="next" value="/accounts/profile/?section=superadmin-organizations"',
            html=False,
        )

    def test_superadmin_profile_staff_management_defaults_to_organizations_without_active_org(self):
        superuser = User.objects.create_superuser(
            username="profile_superadmin_staff_management",
            email="profile_superadmin_staff_management@example.com",
            password="adminpass123",
        )
        owner_pending = User.objects.create_user(
            username="staff_pending_org_owner",
            email="staff_pending_org_owner@example.com",
            password="testpass123",
        )
        owner_active = User.objects.create_user(
            username="staff_active_org_owner",
            email="staff_active_org_owner@example.com",
            password="testpass123",
        )
        pending_org = Organization.objects.create(
            name="Staff Pending Profile Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner_pending,
            status="pending",
            is_active=True,
        )
        active_org = Organization.objects.create(
            name="Staff Active Profile Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner_active,
            status="active",
            is_active=True,
        )

        self.client.force_login(superuser)
        response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "student-organization-management",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pending_org.name)
        self.assertContains(response, active_org.name)
        self.assertEqual(response.context["student_org_management_section"]["active_management_view"], "organizations")
        self.assertEqual(response.context["student_org_management_section"]["organization_records"].paginator.count, 2)

    def test_superadmin_staff_management_page_lists_organizations_without_active_org(self):
        superuser = User.objects.create_superuser(
            username="standalone_superadmin_staff_management",
            email="standalone_superadmin_staff_management@example.com",
            password="adminpass123",
        )
        owner_pending = User.objects.create_user(
            username="standalone_pending_org_owner",
            email="standalone_pending_org_owner@example.com",
            password="testpass123",
        )
        owner_active = User.objects.create_user(
            username="standalone_active_org_owner",
            email="standalone_active_org_owner@example.com",
            password="testpass123",
        )
        pending_org = Organization.objects.create(
            name="Standalone Pending Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner_pending,
            status="pending",
            is_active=True,
        )
        active_org = Organization.objects.create(
            name="Standalone Active Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner_active,
            status="active",
            is_active=True,
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse("accounts:student_organization_management"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pending_org.name)
        self.assertContains(response, active_org.name)
        self.assertEqual(response.context["active_management_view"], "organizations")
        self.assertEqual(response.context["organization_records"].paginator.count, 2)

    def test_superadmin_profile_renders_category_management_section(self):
        _ensure_default_blog_categories()
        superuser = User.objects.create_superuser(
            username="profile_superadmin_category",
            email="profile_superadmin_category@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse("accounts:profile") + "?section=category-management")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "?section=create-category")
        self.assertContains(response, "?section=category-management")
        self.assertContains(response, _("Create category"))
        self.assertContains(response, _("Categories"))
        self.assertContains(response, "Technology")
        self.assertContains(response, "js-category-management-search-form")
        self.assertContains(response, "data-category-subcategory-toggle")
        self.assertContains(response, "data-category-delete-trigger")
        self.assertContains(response, "js-category-management-toast-container")
        self.assertContains(response, 'id="categoryEditModal"', html=False)
        self.assertContains(response, 'id="categoryDeleteModal"', html=False)

    def test_superadmin_category_management_link_is_positioned_with_education_items(self):
        superuser = User.objects.create_superuser(
            username="profile_superadmin_category_sidebar",
            email="profile_superadmin_category_sidebar@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        create_post_index = content.index("?section=create-post")
        create_category_index = content.index("?section=create-category")
        manage_categories_index = content.index("?section=category-management")
        my_exams_index = content.index("?section=my-exams")

        self.assertLess(create_post_index, create_category_index)
        self.assertLess(create_category_index, manage_categories_index)
        self.assertLess(manage_categories_index, my_exams_index)

    def test_profile_create_post_section_renders_inline_form(self):
        superuser = User.objects.create_superuser(
            username="profile_inline_create_post",
            email="profile_inline_create_post@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)

        response = self.client.get(reverse("accounts:profile") + "?section=create-post")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-profile-section-panel="create-post"', html=False)
        self.assertContains(response, 'id="createForm"', html=False)
        self.assertContains(response, 'id="createTitle"', html=False)
        self.assertNotContains(response, "Create post action")

    def test_regular_user_cannot_access_category_management_section_or_create_categories(self):
        from apps.blog.models import Category

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "?section=create-category")
        self.assertNotContains(response, "?section=category-management")

        post_response = self.client.post(
            reverse("accounts:profile") + "?section=create-category",
            data={
                "profile_form": "category-create",
                "section": "create-category",
                "name_az": "Test Kateqoriya",
                "name_en": "Test Category",
                "name_ru": "Тестовая категория",
                "name_tr": "Test Kategori",
            },
        )

        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(post_response.url, reverse("accounts:profile") + "?section=profile-info")
        self.assertFalse(Category.objects.filter(name_en="Test Category").exists())

    def test_superadmin_can_create_root_category_and_subcategory_from_profile(self):
        from apps.blog.models import Category

        superuser = User.objects.create_superuser(
            username="profile_superadmin_create_category",
            email="profile_superadmin_create_category@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        create_url = reverse("accounts:profile") + "?section=create-category"

        root_response = self.client.post(
            create_url,
            data={
                "profile_form": "category-create",
                "section": "create-category",
                "name_az": "Robototexnika",
                "name_en": "Robotics",
                "name_ru": "Робототехника",
                "name_tr": "Robotik",
                "sort_order": 25,
            },
        )

        self.assertEqual(root_response.status_code, 302)
        self.assertEqual(root_response.url, create_url)

        root_category = Category.objects.get(name_en="Robotics")
        self.assertIsNone(root_category.parent_id)

        sub_response = self.client.post(
            create_url,
            data={
                "profile_form": "category-create",
                "section": "create-category",
                "parent": root_category.id,
                "name_az": "Sensor sistemləri",
                "name_en": "Sensor Systems",
                "name_ru": "Сенсорные системы",
                "name_tr": "Sensör Sistemleri",
            },
        )

        self.assertEqual(sub_response.status_code, 302)
        self.assertEqual(sub_response.url, create_url)

        subcategory = Category.objects.get(name_en="Sensor Systems")
        self.assertEqual(subcategory.parent, root_category)

    def test_superadmin_can_edit_category_from_profile(self):
        from apps.blog.models import Category

        superuser = User.objects.create_superuser(
            username="profile_superadmin_edit_category",
            email="profile_superadmin_edit_category@example.com",
            password="adminpass123",
        )
        category = Category.objects.create(
            name_az="Köhnə ad",
            name_en="Old Name",
            name_ru="Старое имя",
            name_tr="Eski ad",
        )

        self.client.force_login(superuser)
        response = self.client.post(
            reverse("accounts:profile") + "?section=category-management",
            data={
                "profile_form": "category-management-save",
                "section": "category-management",
                "category_id": category.id,
                "name_az": "Yeni ad",
                "name_en": "New Name",
                "name_ru": "Новое имя",
                "name_tr": "Yeni isim",
                "sort_order": 3,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile") + "?section=category-management")

        category.refresh_from_db()
        self.assertEqual(category.name_en, "New Name")
        self.assertEqual(category.name_az, "Yeni ad")
        self.assertEqual(category.sort_order, 3)

    def test_superadmin_profile_category_management_blocks_duplicate_names(self):
        _ensure_default_blog_categories()
        superuser = User.objects.create_superuser(
            username="profile_superadmin_duplicate_category",
            email="profile_superadmin_duplicate_category@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        response = self.client.post(
            reverse("accounts:profile") + "?section=create-category",
            data={
                "profile_form": "category-create",
                "section": "create-category",
                "name_az": "Texnologiya",
                "name_en": "Technology",
                "name_ru": "Технологии",
                "name_tr": "Teknoloji",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "başqa kateqoriya artıq mövcuddur")
        self.assertEqual(response.context["active_section"], "create-category")

    def test_superadmin_profile_category_management_search_filters_tree(self):
        _ensure_default_blog_categories()
        superuser = User.objects.create_superuser(
            username="profile_superadmin_category_search",
            email="profile_superadmin_category_search@example.com",
            password="adminpass123",
        )

        self.client.force_login(superuser)
        response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "category-management",
                "category_search": "Programming",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Technology")
        self.assertContains(response, "Programming")
        self.assertNotContains(response, "Web Development")

    def test_superadmin_profile_category_management_paginates_roots(self):
        from apps.blog.models import Category

        superuser = User.objects.create_superuser(
            username="profile_superadmin_category_pagination",
            email="profile_superadmin_category_pagination@example.com",
            password="adminpass123",
        )

        for index in range(7):
            Category.objects.create(
                name_az=f"Arxiv Kateqoriya {index}",
                name_en=f"Archive Category {index}",
                name_ru=f"Архивная категория {index}",
                name_tr=f"Arsiv Kategori {index}",
                sort_order=1000 + index,
            )

        self.client.force_login(superuser)
        response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "category-management",
                "category_page": 999,
            },
        )

        self.assertEqual(response.status_code, 200)
        page = response.context["category_management_page"]
        self.assertEqual(page.number, page.paginator.num_pages)
        self.assertTrue(page.object_list)
        self.assertTrue(all(item.name_en.startswith("Archive Category") for item in page.object_list))
        self.assertEqual(page.object_list[-1].name_en, "Archive Category 6")

    def test_superadmin_profile_category_delete_is_blocked_when_posts_exist(self):
        from apps.blog.models import Category, Post

        superuser = User.objects.create_superuser(
            username="profile_superadmin_delete_category",
            email="profile_superadmin_delete_category@example.com",
            password="adminpass123",
        )
        author = User.objects.create_user(
            username="category_delete_author_profile",
            email="category_delete_author_profile@example.com",
            password="authorpass123",
        )
        category = Category.objects.create(
            name_az="Silinməyən kateqoriya",
            name_en="Undeletable Category",
            name_ru="Неудаляемая категория",
            name_tr="Silinemez kategori",
        )
        Post.objects.create(
            author=author,
            category=category,
            title="Protected category post",
            content="Protected category content",
        )

        self.client.force_login(superuser)
        response = self.client.post(
            reverse("accounts:profile") + "?section=category-management",
            data={
                "profile_form": "category-management-delete",
                "section": "category-management",
                "category_id": category.id,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bu kateqoriyanı silmək olmur")
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())

    def test_manage_roles_assigns_multiple_roles_and_keeps_highest_as_primary(self):
        from apps.accounts.models import ProfileRole
        from apps.organizations.models import Membership

        superuser = User.objects.create_superuser(
            username="superadmin_manage_roles",
            email="superadmin_manage_roles@example.com",
            password="adminpass123",
        )
        organization = Organization.objects.create(
            name="Manage Roles Assign Org",
            org_type=OrganizationType.SCHOOL,
            owner=superuser,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.MEMBER)

        _login_with_org(self.client, superuser, organization)

        response = self.client.post(
            reverse("accounts:manage_roles"),
            data={
                "user_id": self.user.id,
                "action": "assign",
                "role_names": [ProfileRole.TEACHER, ProfileRole.ORG_ADMIN],
                "next": reverse("accounts:manage_roles"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:manage_roles"))

        self.user.refresh_from_db()
        self.user.set_active_organization_context(organization)
        self.assertEqual(self.user.profile.role, ProfileRole.ORG_ADMIN)
        self.assertTrue(self.user.has_role(ProfileRole.ORG_ADMIN))
        self.assertTrue(self.user.has_role(ProfileRole.TEACHER))
        self.assertFalse(self.user.groups.filter(name__in=[ProfileRole.TEACHER, ProfileRole.ORG_ADMIN]).exists())
        self.assertTrue(
            Membership.objects.filter(
                user=self.user,
                organization=organization,
                role__name="teacher",
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            Membership.objects.filter(
                user=self.user,
                organization=organization,
                role__level__gte=80,
                is_active=True,
            ).exists()
        )

    def test_manage_roles_respects_next_redirect_url(self):
        from apps.accounts.models import ProfileRole

        superuser = User.objects.create_superuser(
            username="superadmin_manage_roles_next",
            email="superadmin_manage_roles_next@example.com",
            password="adminpass123",
        )
        organization = Organization.objects.create(
            name="Manage Roles Redirect Org",
            org_type=OrganizationType.SCHOOL,
            owner=superuser,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.MEMBER)

        _login_with_org(self.client, superuser, organization)

        next_url = reverse("accounts:profile") + "?section=manage-roles"
        response = self.client.post(
            reverse("accounts:manage_roles"),
            data={
                "user_id": self.user.id,
                "action": "assign",
                "role_names": [ProfileRole.TEACHER],
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

    def test_global_teacher_group_does_not_grant_teacher_navigation_in_active_org(self):
        from django.contrib.auth.models import Group

        teacher_group, _ = Group.objects.get_or_create(name=ProfileRole.TEACHER)
        self.user.groups.add(teacher_group)

        organization = Organization.objects.create(
            name="Group Leakage Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, organization, ProfileRole.MEMBER)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("accounts:pending_review"))

    def test_assigned_tasks_section_lists_exam_assignment_lab_and_project(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment
        from apps.courses.models import Course, CourseMembership
        from apps.exams.models import Exam
        from apps.labs.models import Lab
        from apps.projects.models import Project

        teacher = User.objects.create_user(
            username="tasks_teacher",
            email="tasks_teacher@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Assigned Tasks Org",
            org_type=OrganizationType.SCHOOL,
            owner=teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(teacher, organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.user, organization, ProfileRole.STUDENT)

        course = Course.objects.create(
            owner=teacher,
            title="Task Course",
            status="published",
        )
        CourseMembership.objects.create(
            course=course,
            user=self.user,
            role="student",
            group_name="850",
        )

        assignment = Assignment.objects.create(
            course=course,
            title="Task Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        assignment.assigned_students.add(self.user)

        unassigned_assignment = Assignment.objects.create(
            course=course,
            title="Unassigned Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        unassigned_assignment.assigned_students.add(teacher)

        lab = Lab.objects.create(
            course=course,
            title="Task Lab",
            start_datetime=timezone.now() - timedelta(hours=2),
            end_datetime=timezone.now() + timedelta(days=1),
            status="published",
            created_by=teacher,
        )
        lab.allowed_students.add(self.user)

        project = Project.objects.create(
            course=course,
            title="Task Project",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=3),
            status="active",
        )
        project.assigned_students.add(self.user)

        exam = Exam.objects.create(
            author=teacher,
            title="Task Exam",
            exam_type="test",
            is_active=True,
            is_public=False,
        )
        exam.allowed_users.add(self.user)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(reverse("accounts:profile") + "?section=assigned-exams")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təyin olunmuş tapşırıqlar")
        self.assertContains(response, assignment.title)
        self.assertContains(response, lab.title)
        self.assertContains(response, project.title)
        self.assertContains(response, exam.title)
        self.assertNotContains(response, unassigned_assignment.title)
        self.assertNotContains(response, "assigned_type=courses")

        self.assertEqual(response.context["assigned_tasks_count"], 4)
        self.assertEqual(response.context["assigned_task_counts"]["exams"], 1)
        self.assertEqual(response.context["assigned_task_counts"]["courses"], 1)
        self.assertEqual(response.context["assigned_task_counts"]["assignments"], 1)
        self.assertEqual(response.context["assigned_task_counts"]["labs"], 1)
        self.assertEqual(response.context["assigned_task_counts"]["independent"], 1)

        exam_item = next(item for item in response.context["assigned_task_items"] if item["category"] == "exams")
        assignment_item = next(
            item for item in response.context["assigned_task_items"] if item["category"] == "assignments"
        )
        self.assertFalse(any(item["category"] == "courses" for item in response.context["assigned_task_items"]))
        lab_item = next(item for item in response.context["assigned_task_items"] if item["category"] == "labs")
        project_item = next(
            item for item in response.context["assigned_task_items"] if item["category"] == "independent"
        )

        self.assertIn("from_section=assigned-exams", assignment_item["detail_url"])
        self.assertIn("assigned_type=all", assignment_item["detail_url"])
        self.assertIn("from_section=assigned-exams", lab_item["detail_url"])
        self.assertIn("assigned_type=all", lab_item["detail_url"])
        self.assertIn("from_section=assigned-exams", project_item["detail_url"])
        self.assertIn("assigned_type=all", project_item["detail_url"])
        self.assertIn(reverse("exams:start_exam", kwargs={"slug": exam.slug}), exam_item["detail_url"])
        self.assertIn("from_section=assigned-exams", exam_item["detail_url"])
        self.assertIn("assigned_type=all", exam_item["detail_url"])

    def test_assigned_tasks_search_filters_items(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment
        from apps.courses.models import Course, CourseMembership

        teacher = User.objects.create_user(
            username="tasks_search_teacher",
            email="tasks_search_teacher@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Assigned Tasks Search Org",
            org_type=OrganizationType.SCHOOL,
            owner=teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(teacher, organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.user, organization, ProfileRole.STUDENT)

        course = Course.objects.create(owner=teacher, title="Search Course", status="published")
        CourseMembership.objects.create(course=course, user=self.user, role="student")

        keep_item = Assignment.objects.create(
            course=course,
            title="Python Search Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=1),
            status="published",
        )
        keep_item.assigned_students.add(self.user)

        hidden_item = Assignment.objects.create(
            course=course,
            title="Java Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=1),
            status="published",
        )
        hidden_item.assigned_students.add(self.user)

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(
            reverse("accounts:profile"),
            {"section": "assigned-exams", "assigned_search": "python"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["assigned_tasks_search_query"], "python")
        self.assertContains(response, keep_item.title)
        self.assertNotContains(response, hidden_item.title)

    def test_assigned_courses_search_filters_items(self):
        from apps.courses.models import Course, CourseMembership

        teacher = User.objects.create_user(
            username="assigned_courses_search_teacher",
            email="assigned_courses_search_teacher@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="Assigned Courses Search Org",
            org_type=OrganizationType.SCHOOL,
            owner=teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(teacher, organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.user, organization, ProfileRole.STUDENT)

        keep_course = Course.objects.create(owner=teacher, title="Python Fundamentals", status="published")
        hidden_course = Course.objects.create(owner=teacher, title="Rust Advanced", status="published")
        CourseMembership.objects.create(course=keep_course, user=self.user, role="student")
        CourseMembership.objects.create(course=hidden_course, user=self.user, role="student")

        _login_with_org(self.client, self.user, organization)
        response = self.client.get(
            reverse("accounts:profile"),
            {"section": "assigned-courses", "assigned_course_search": "python"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["assigned_courses_search_query"], "python")
        self.assertEqual(len(response.context["assigned_courses"]), 1)
        self.assertEqual(response.context["assigned_courses"][0].id, keep_course.id)

    def test_superadmin_pending_post_approvals_filters_by_organization_and_personal_scope(self):
        from apps.blog.models import Post

        superadmin = User.objects.create_superuser(
            username="pending_posts_superadmin",
            email="pending_posts_superadmin@example.com",
            password="testpass123",
        )

        owner_a = User.objects.create_user("pending_posts_owner_a", "owner_a@example.com", "testpass123")
        owner_b = User.objects.create_user("pending_posts_owner_b", "owner_b@example.com", "testpass123")

        org_a = Organization.objects.create(
            name="Pending Posts Org A",
            slug="pending-posts-org-a",
            org_type=OrganizationType.SCHOOL,
            owner=owner_a,
            status="active",
            is_active=True,
        )
        org_b = Organization.objects.create(
            name="Pending Posts Org B",
            slug="pending-posts-org-b",
            org_type=OrganizationType.SCHOOL,
            owner=owner_b,
            status="active",
            is_active=True,
        )

        org_a_student = User.objects.create_user("pending_posts_student_a", "student_a@example.com", "testpass123")
        org_b_student = User.objects.create_user("pending_posts_student_b", "student_b@example.com", "testpass123")
        personal_author = User.objects.create_user(
            "pending_posts_personal_author",
            "personal_author@example.com",
            "testpass123",
        )

        _assign_user_to_org(org_a_student, org_a, ProfileRole.STUDENT)
        _assign_user_to_org(org_b_student, org_b, ProfileRole.STUDENT)

        personal_profile = personal_author.profile
        personal_profile.role = ProfileRole.TEACHER
        personal_profile.organization = None
        personal_profile.organization_type = OrganizationType.INDIVIDUAL
        personal_profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])

        Post.objects.create(
            author=org_a_student,
            title="Org A Pending Post",
            content="Org A content",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )
        Post.objects.create(
            author=org_b_student,
            title="Org B Pending Post",
            content="Org B content",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )
        Post.objects.create(
            author=personal_author,
            title="Personal Pending Post",
            content="Personal content",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self.client.force_login(superadmin)
        org_response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "pending-post-approvals",
                "approval_organization": str(org_a.id),
                "approval_status": "pending",
            },
        )

        self.assertEqual(org_response.status_code, 200)
        org_titles = [item["post"].title for item in org_response.context["pending_post_approval_items"]]
        self.assertEqual(org_titles, ["Org A Pending Post"])
        self.assertEqual(org_response.context["pending_post_approval_filter_organization"], str(org_a.id))

        available_org_ids = {
            str(item["id"]) for item in org_response.context["pending_post_approval_available_organizations"]
        }
        self.assertIn(str(org_a.id), available_org_ids)
        self.assertIn("__personal__", available_org_ids)

        personal_response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "pending-post-approvals",
                "approval_organization": "__personal__",
                "approval_status": "pending",
            },
        )

        self.assertEqual(personal_response.status_code, 200)
        personal_titles = [item["post"].title for item in personal_response.context["pending_post_approval_items"]]
        self.assertEqual(personal_titles, ["Personal Pending Post"])

    def test_superadmin_pending_post_approvals_paginate_filtered_results(self):
        from apps.blog.models import Post

        superadmin = User.objects.create_superuser(
            username="pending_posts_pagination_superadmin",
            email="pending_posts_pagination_superadmin@example.com",
            password="testpass123",
        )
        owner = User.objects.create_user("pending_posts_page_owner", "page_owner@example.com", "testpass123")
        organization = Organization.objects.create(
            name="Pending Posts Pagination Org",
            slug="pending-posts-pagination-org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )

        for index in range(11):
            student = User.objects.create_user(
                username=f"pending_page_student_{index}",
                email=f"pending_page_student_{index}@example.com",
                password="testpass123",
            )
            _assign_user_to_org(student, organization, ProfileRole.STUDENT)
            Post.objects.create(
                author=student,
                title=f"Paginated Pending {index}",
                content="Pagination content",
                requires_approval=True,
                approval_status=Post.ApprovalStatus.PENDING,
                is_published=False,
            )

        self.client.force_login(superadmin)
        response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "pending-post-approvals",
                "approval_organization": str(organization.id),
                "approval_page": 2,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_post_approval_page_obj"].number, 2)
        self.assertEqual(len(response.context["pending_post_approval_items"]), 1)
        page_titles = [item["post"].title for item in response.context["pending_post_approval_items"]]
        self.assertEqual(page_titles, ["Paginated Pending 0"])
        self.assertIn(
            f"approval_organization={organization.id}",
            response.context["pending_post_approval_pagination_query"],
        )

    def test_superadmin_pending_post_approvals_default_to_all_posts_and_show_org_filter(self):
        from apps.blog.models import Post

        scope_marker = "ScopeMarkerPendingPostsAll"
        superadmin = User.objects.create_superuser(
            username="pending_posts_all_superadmin",
            email="pending_posts_all_superadmin@example.com",
            password="testpass123",
        )
        owner = User.objects.create_user("pending_posts_all_owner", "owner_all@example.com", "testpass123")
        teacher = User.objects.create_user("pending_posts_all_teacher", "teacher_all@example.com", "testpass123")
        personal_author = User.objects.create_user(
            "pending_posts_all_personal",
            "personal_all@example.com",
            "testpass123",
        )

        organization = Organization.objects.create(
            name="Pending Posts All Org",
            slug="pending-posts-all-org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(teacher, organization, ProfileRole.TEACHER)

        personal_profile = personal_author.profile
        personal_profile.role = ProfileRole.TEACHER
        personal_profile.organization = None
        personal_profile.organization_type = OrganizationType.INDIVIDUAL
        personal_profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])

        Post.objects.create(
            author=teacher,
            title=f"{scope_marker} Published Org Teacher Post",
            content="Published org post",
            requires_approval=False,
            approval_status=Post.ApprovalStatus.APPROVED,
            is_published=True,
        )
        Post.objects.create(
            author=personal_author,
            title=f"{scope_marker} Personal Hidden Post",
            content="Personal hidden post",
            requires_approval=False,
            approval_status=Post.ApprovalStatus.APPROVED,
            is_published=False,
        )

        _login_with_org(self.client, superadmin, organization)
        response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "pending-post-approvals",
                "approval_search": scope_marker,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_post_approval_filter_status"], "all")
        self.assertEqual(response.context["pending_post_approval_total_count"], 2)
        titles = [item["post"].title for item in response.context["pending_post_approval_items"]]
        self.assertEqual(
            titles,
            [
                f"{scope_marker} Personal Hidden Post",
                f"{scope_marker} Published Org Teacher Post",
            ],
        )
        available_org_ids = {
            str(item["id"]) for item in response.context["pending_post_approval_available_organizations"]
        }
        self.assertIn(str(organization.id), available_org_ids)
        self.assertIn("__personal__", available_org_ids)

    def test_org_admin_pending_post_approvals_are_scoped_to_active_organization_posts(self):
        from apps.blog.models import Post

        scope_marker = "ScopeMarkerOrgScopedPosts"
        org_admin = User.objects.create_user(
            username="pending_posts_org_admin",
            email="pending_posts_org_admin@example.com",
            password="testpass123",
        )
        owner_a = User.objects.create_user("pending_posts_owner_one", "owner_one@example.com", "testpass123")
        owner_b = User.objects.create_user("pending_posts_owner_two", "owner_two@example.com", "testpass123")
        teacher_a = User.objects.create_user("pending_posts_teacher_one", "teacher_one@example.com", "testpass123")
        teacher_b = User.objects.create_user("pending_posts_teacher_two", "teacher_two@example.com", "testpass123")

        org_a = Organization.objects.create(
            name="Pending Posts Admin Org A",
            slug="pending-posts-admin-org-a",
            org_type=OrganizationType.SCHOOL,
            owner=owner_a,
            status="active",
            is_active=True,
        )
        org_b = Organization.objects.create(
            name="Pending Posts Admin Org B",
            slug="pending-posts-admin-org-b",
            org_type=OrganizationType.SCHOOL,
            owner=owner_b,
            status="active",
            is_active=True,
        )

        _assign_user_to_org(org_admin, org_a, ProfileRole.ORG_ADMIN, membership_role_name="director")
        _assign_user_to_org(teacher_a, org_a, ProfileRole.TEACHER)
        _assign_user_to_org(teacher_b, org_b, ProfileRole.TEACHER)

        Post.objects.create(
            author=teacher_a,
            title=f"{scope_marker} Org A Visible Post",
            content="Org A content",
            requires_approval=False,
            approval_status=Post.ApprovalStatus.APPROVED,
            is_published=True,
        )
        Post.objects.create(
            author=teacher_b,
            title=f"{scope_marker} Org B Hidden Post",
            content="Org B content",
            requires_approval=False,
            approval_status=Post.ApprovalStatus.APPROVED,
            is_published=True,
        )

        _login_with_org(self.client, org_admin, org_a)
        response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "pending-post-approvals",
                "approval_search": scope_marker,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_post_approval_filter_status"], "all")
        self.assertEqual(response.context["pending_post_approval_total_count"], 1)
        titles = [item["post"].title for item in response.context["pending_post_approval_items"]]
        self.assertEqual(titles, [f"{scope_marker} Org A Visible Post"])


class AssignedItemsViewTest(TestCase):
    """Tests for assigned exams and courses views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            name="Assigned Items Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, self.organization, ProfileRole.STUDENT)

    def _login_user(self, user=None):
        _login_with_org(self.client, user or self.user, self.organization)

    def test_assigned_exams_requires_login(self):
        """Test that assigned exams page requires authentication."""
        response = self.client.get(reverse("accounts:assigned_exams"))
        self.assertEqual(response.status_code, 302)

    def test_assigned_exams_loads(self):
        """Test that assigned exams page loads."""
        self._login_user()
        response = self.client.get(reverse("accounts:assigned_exams"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təyin olunmuş imtahanlarım")

    def test_assigned_courses_requires_login(self):
        """Test that assigned courses page requires authentication."""
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 302)

    def test_assigned_courses_loads(self):
        """Test that assigned courses page loads."""
        self._login_user()
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təyin olunmuş kurslarım")

    def test_assigned_courses_with_items_uses_course_dashboard_link(self):
        from apps.courses.models import Course, CourseMembership

        teacher = User.objects.create_user(
            username="course_teacher",
            email="course_teacher@example.com",
            password="testpass123",
        )
        _assign_user_to_org(teacher, self.organization, ProfileRole.TEACHER)
        course = Course.objects.create(
            owner=teacher,
            title="Assigned Course",
            status="published",
        )
        CourseMembership.objects.create(course=course, user=self.user, role="student")

        self._login_user()
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned Course")
        self.assertContains(response, reverse("courses:course_dashboard", args=[course.id]))

    def test_assigned_courses_empty_state_message(self):
        self._login_user()
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No courses assigned yet.")

    def test_assigned_exams_shows_only_assigned_and_links_to_start(self):
        from apps.courses.models import Course, CourseMembership
        from apps.exams.models import Exam

        teacher = User.objects.create_user(
            username="exam_teacher",
            email="exam_teacher@example.com",
            password="testpass123",
        )
        _assign_user_to_org(teacher, self.organization, ProfileRole.TEACHER)
        course = Course.objects.create(
            owner=teacher,
            title="Assigned Exam Course",
            status="published",
        )
        CourseMembership.objects.create(course=course, user=self.user, role="student")

        direct_exam = Exam.objects.create(
            author=teacher,
            title="Directly Assigned Exam",
            is_active=True,
            is_public=False,
        )
        direct_exam.allowed_users.add(self.user)

        course_exam = Exam.objects.create(
            author=teacher,
            title="Course Assigned Exam",
            is_active=True,
            is_public=False,
            course=course,
        )

        code_exam = Exam.objects.create(
            author=teacher,
            title="Code Assigned Exam",
            is_active=True,
            is_public=False,
            access_code="123456",
        )
        code_exam.allowed_users.add(self.user)

        assigned_public_exam = Exam.objects.create(
            author=teacher,
            title="Assigned Public Exam",
            is_active=True,
            is_public=True,
        )
        assigned_public_exam.allowed_users.add(self.user)

        public_exam = Exam.objects.create(
            author=teacher,
            title="Public Unassigned Exam",
            is_active=True,
            is_public=True,
        )

        self._login_user()
        response = self.client.get(reverse("accounts:assigned_exams"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, direct_exam.title)
        self.assertContains(response, course_exam.title)
        self.assertContains(response, code_exam.title)
        self.assertNotContains(response, assigned_public_exam.title)
        self.assertNotContains(response, public_exam.title)
        self.assertContains(response, reverse("exams:start_exam", args=[direct_exam.slug]))
        self.assertContains(response, reverse("exams:start_exam", args=[course_exam.slug]))
        self.assertContains(response, reverse("exams:exam_code_check"))
        self.assertContains(response, f'data-exam-slug="{code_exam.slug}"')

    def test_assigned_exams_restore_profile_org_context_when_session_org_is_missing(self):
        from apps.exams.models import Exam, ExamQuestion, StudentGroup

        teacher = User.objects.create_user(
            username="assigned_group_teacher",
            email="assigned_group_teacher@example.com",
            password="testpass123",
        )

        _assign_user_to_org(teacher, self.organization, ProfileRole.TEACHER)

        group = StudentGroup.objects.create(
            teacher=teacher,
            organization=self.organization,
            name="Assigned Route Group",
        )
        group.students.add(self.user)

        exam = Exam.objects.create(
            author=teacher,
            title="Assigned Group Route Exam",
            is_active=True,
            is_public=False,
        )
        exam.allowed_groups.add(group)
        ExamQuestion.objects.create(
            exam=exam,
            text="Assigned route question",
            order=1,
            points=1,
        )

        self._login_user()
        session = self.client.session
        session.pop("active_organization", None)
        session.save()

        response = self.client.get(reverse("accounts:assigned_exams"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, exam.title)
        self.assertEqual(self.client.session.get("active_organization"), self.organization.slug)


class MyResultsViewTest(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from apps.exams.models import Exam, ExamAttempt
        from apps.labs.models import Lab, LabAssignment, LabSubmission
        from apps.projects.models import Project, ProjectSubmission

        self.client = Client()
        self.teacher = User.objects.create_user(
            username="results_teacher",
            email="results_teacher@example.com",
            password="testpass123",
        )
        self.student = User.objects.create_user(
            username="results_student",
            email="results_student@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            name="My Results Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

        self.course = Course.objects.create(owner=self.teacher, title="Result Course", status="published")

        self.exam = Exam.objects.create(
            author=self.teacher,
            title="Unified Exam",
            is_active=True,
            is_public=True,
        )
        self.exam_attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
        )

        self.assignment = Assignment.objects.create(
            course=self.course,
            title="Unified Assignment",
            start_date=timezone.now(),
            status="published",
        )
        self.assignment_submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Assignment answer",
            status="graded",
            feedback="Assignment feedback",
            grade=91,
        )

        self.lab = Lab.objects.create(
            course=self.course,
            title="Unified Lab",
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(days=2),
            status="published",
            created_by=self.teacher,
        )
        self.lab_assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)
        self.lab_submission = LabSubmission.objects.create(
            assignment=self.lab_assignment,
            submission_text="Lab answer",
            status="submitted",
        )

        self.project = Project.objects.create(
            course=self.course,
            title="Unified Project",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=3),
            status="active",
        )
        self.project_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Project answer",
            status="pending",
        )

    def _login_student(self):
        _login_with_org(self.client, self.student, self.organization)

    def test_my_results_requires_login(self):
        response = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(response.status_code, 302)

    def test_my_results_unified_list_contains_all_submission_types(self):
        self._login_student()
        response = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unified Exam")
        self.assertContains(response, "Unified Assignment")
        self.assertContains(response, "Unified Lab")
        self.assertContains(response, "Unified Project")
        self.assertContains(response, "View answer/details")

    def test_my_results_filter_labs_only(self):
        self._login_student()
        response = self.client.get(reverse("accounts:my_results") + "?type=labs")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unified Lab")
        self.assertNotContains(response, "Unified Assignment")

    def test_profile_my_results_search_filters_section_items(self):
        self._login_student()
        response = self.client.get(
            reverse("accounts:profile"),
            {"section": "my-results", "results_search": "Unified Lab"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["my_results_search_query"], "Unified Lab")
        self.assertEqual(len(response.context["my_result_items"].object_list), 1)
        self.assertEqual(response.context["my_result_items"].object_list[0]["title"], "Unified Lab")
        self.assertContains(response, 'class="results-section-search-form js-profile-debounce-search"')

    def test_profile_my_results_pagination_uses_partial_and_preserves_search(self):
        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission

        for index in range(7):
            assignment = Assignment.objects.create(
                course=self.course,
                title=f"Bulk Result Assignment {index}",
                start_date=timezone.now(),
                status="published",
            )
            Submission.objects.create(
                assignment=assignment,
                user=self.student,
                content=f"Bulk answer {index}",
                status="submitted",
            )

        self._login_student()
        response = self.client.get(
            reverse("accounts:profile"),
            {
                "section": "my-results",
                "results_type": "courses",
                "results_search": "Bulk Result",
            },
        )

        self.assertEqual(response.status_code, 200)
        page_obj = response.context["my_results_page_obj"]
        self.assertEqual(page_obj.paginator.per_page, 6)
        self.assertTrue(page_obj.has_next())
        self.assertIn("section=my-results", response.context["my_results_pagination_query"])
        self.assertIn("results_type=courses", response.context["my_results_pagination_query"])
        self.assertIn("results_search=Bulk+Result", response.context["my_results_pagination_query"])
        self.assertContains(response, "results_page=2")

    def test_my_result_detail_for_assignment_submission(self):
        self._login_student()
        response = self.client.get(
            reverse(
                "accounts:my_result_detail",
                kwargs={"item_type": "courses", "item_id": self.assignment_submission.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unified Assignment")
        self.assertContains(response, "Assignment feedback")
        self.assertContains(response, reverse("accounts:profile") + "?section=my-results")
        self.assertContains(response, "results_type=all")

    def test_my_result_detail_for_lab_submission_shows_question_answers(self):
        from apps.labs.models import LabAnswer, LabBlock, LabQuestion

        block = LabBlock.objects.create(lab=self.lab, title="Core block", order=1)
        question_one = LabQuestion.objects.create(
            block=block,
            question_number=1,
            question_text="Explain the JavaScript loop flow.",
        )
        question_two = LabQuestion.objects.create(
            block=block,
            question_number=2,
            question_text="Upload your notes.",
        )

        self.lab_submission.submission_text = ""
        self.lab_submission.save(update_fields=["submission_text"])

        LabAnswer.objects.create(
            lab=self.lab,
            question=question_one,
            student=self.student,
            attempt_number=self.lab_submission.attempt_number,
            answer="The loop repeats until the condition becomes false.",
            is_draft=False,
            score=47,
        )
        LabAnswer.objects.create(
            lab=self.lab,
            question=question_two,
            student=self.student,
            attempt_number=self.lab_submission.attempt_number,
            answer_file=SimpleUploadedFile("lab-proof.txt", b"proof"),
            is_draft=False,
        )

        self._login_student()
        response = self.client.get(
            reverse(
                "accounts:my_result_detail",
                kwargs={"item_type": "labs", "item_id": self.lab_submission.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explain the JavaScript loop flow.")
        self.assertContains(response, "The loop repeats until the condition becomes false.")
        self.assertContains(response, "lab-proof")
        self.assertContains(response, 'data-answer-toggle="')
        self.assertNotContains(response, "No text answer")

    def test_my_result_detail_preserves_profile_results_filter_in_back_link(self):
        self._login_student()
        response = self.client.get(
            reverse(
                "accounts:my_result_detail",
                kwargs={"item_type": "courses", "item_id": self.assignment_submission.id},
            )
            + "?results_type=courses"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:profile") + "?section=my-results")
        self.assertContains(response, "results_type=courses")

    def test_my_results_hides_recently_graded_submission_until_window_closes(self):
        from datetime import timedelta

        from django.utils import timezone

        self.assignment_submission.graded_at = timezone.now()
        self.assignment_submission.save(update_fields=["graded_at"])

        self._login_student()
        response = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Unified Assignment")

        self.assignment_submission.graded_at = timezone.now() - timedelta(minutes=6)
        self.assignment_submission.save(update_fields=["graded_at"])
        response_after_window = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(response_after_window.status_code, 200)
        self.assertContains(response_after_window, "Unified Assignment")

    def test_my_result_detail_redirects_when_review_window_is_open(self):
        from django.utils import timezone

        self.assignment_submission.graded_at = timezone.now()
        self.assignment_submission.save(update_fields=["graded_at"])

        self._login_student()
        response = self.client.get(
            reverse(
                "accounts:my_result_detail",
                kwargs={"item_type": "courses", "item_id": self.assignment_submission.id},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("section=my-results", response.url)


class PendingAnswersViewTest(TestCase):
    """Tests for student pending answers section and standalone view."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from apps.exams.models import Exam, ExamAttempt
        from apps.projects.models import Project, ProjectSubmission

        self.client = Client()
        self.teacher = User.objects.create_user(
            username="pending_answers_teacher",
            email="pending_answers_teacher@example.com",
            password="testpass123",
        )
        self.student = User.objects.create_user(
            username="pending_answers_student",
            email="pending_answers_student@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            name="Pending Answers Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

        self.course = Course.objects.create(owner=self.teacher, title="Pending Answers Course", status="published")

        self.pending_assignment = Assignment.objects.create(
            course=self.course,
            title="Pending Assignment Visible",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=1),
            status="published",
        )
        Submission.objects.create(
            assignment=self.pending_assignment,
            user=self.student,
            content="Pending assignment answer",
            status="submitted",
        )

        self.recently_graded_assignment = Assignment.objects.create(
            course=self.course,
            title="Recently Graded Hidden Assignment",
            start_date=timezone.now() - timedelta(days=2),
            due_date=timezone.now() + timedelta(days=1),
            status="published",
        )
        self.recent_submission = Submission.objects.create(
            assignment=self.recently_graded_assignment,
            user=self.student,
            content="Recent graded assignment",
            status="graded",
            grade=90,
            graded_at=timezone.now(),
        )

        old_assignment = Assignment.objects.create(
            course=self.course,
            title="Old Finalized Assignment",
            start_date=timezone.now() - timedelta(days=4),
            due_date=timezone.now() - timedelta(days=2),
            status="published",
        )
        Submission.objects.create(
            assignment=old_assignment,
            user=self.student,
            content="Old graded assignment",
            status="graded",
            grade=88,
            graded_at=timezone.now() - timedelta(minutes=6),
        )

        self.written_exam = Exam.objects.create(
            author=self.teacher,
            title="Async Written Exam",
            exam_type="written",
            is_active=True,
        )
        ExamAttempt.objects.create(
            user=self.student,
            exam=self.written_exam,
            status="submitted",
            checked_by_teacher=False,
        )

        self.practical_exam = Exam.objects.create(
            author=self.teacher,
            title="Async Practical Exam",
            exam_type="coding",
            is_active=True,
        )
        ExamAttempt.objects.create(
            user=self.student,
            exam=self.practical_exam,
            status="submitted",
            checked_by_teacher=False,
        )

        self.project = Project.objects.create(
            course=self.course,
            title="Pending Project Work",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=2),
            status="active",
        )
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Pending project answer",
            status="pending",
        )

    def _login_student(self):
        _login_with_org(self.client, self.student, self.organization)

    def test_pending_answers_requires_login(self):
        response = self.client.get(reverse("accounts:pending_answers"))
        self.assertEqual(response.status_code, 302)

    def test_pending_answers_lists_only_pending_or_window_items(self):
        self._login_student()
        response = self.client.get(reverse("accounts:pending_answers"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gözləmədə olan cavablar")
        self.assertContains(response, "Profilə qayıt")
        self.assertContains(response, "data-bootstrap-select", html=False)
        self.assertContains(response, "Tapşırıq, imtahan və kurs üzrə axtar")
        self.assertNotContains(response, "Pending cavablar")
        self.assertNotContains(response, "Profile geri dön")
        self.assertContains(response, "Pending Assignment Visible")
        self.assertContains(response, "Recently Graded Hidden Assignment")
        self.assertContains(response, "Async Written Exam")
        self.assertContains(response, "Async Practical Exam")
        self.assertContains(response, "Pending Project Work")
        self.assertNotContains(response, "Old Finalized Assignment")

        items = response.context["pending_answer_items"]
        recent_item = next(item for item in items if item["title"] == "Recently Graded Hidden Assignment")
        self.assertGreater(recent_item["review_window_seconds_left"], 0)
        self.assertIn("section=pending-answers", recent_item["detail_url"])

    def test_pending_answers_search_filters_results(self):
        self._login_student()
        response = self.client.get(reverse("accounts:pending_answers") + "?pending_search=Async")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Async Written Exam")
        self.assertNotContains(response, "Pending Assignment Visible")

    def test_pending_answers_filters_practical_separately_from_written(self):
        self._login_student()
        response = self.client.get(reverse("accounts:pending_answers") + "?pending_type=practical_exams")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_answers_active_filter"], "practical_exams")
        self.assertContains(response, 'value="practical_exams" selected', html=False)
        self.assertContains(response, "Async Practical Exam")
        self.assertNotContains(response, "Async Written Exam")


class StudentDashboardAssignmentVisibilityTest(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment
        from apps.courses.models import Course, CourseMembership

        self.client = Client()
        self.teacher = User.objects.create_user(
            username="dashboard_teacher",
            email="dashboard_teacher@example.com",
            password="testpass123",
        )
        self.student = User.objects.create_user(
            username="dashboard_student",
            email="dashboard_student@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            name="Student Dashboard Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

        self.course = Course.objects.create(owner=self.teacher, title="Dashboard Course", status="published")
        CourseMembership.objects.create(course=self.course, user=self.student, role="student")

        self.visible_assignment = Assignment.objects.create(
            course=self.course,
            title="Visible Dashboard Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        self.visible_assignment.assigned_students.add(self.student)

        self.hidden_assignment = Assignment.objects.create(
            course=self.course,
            title="Hidden Dashboard Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )

    def test_student_dashboard_only_lists_assignments_assigned_to_student(self):
        _login_with_org(self.client, self.student, self.organization)
        response = self.client.get(reverse("accounts:student_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Dashboard Assignment")
        self.assertNotContains(response, "Hidden Dashboard Assignment")


class GradingQueueViewTest(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        self.client = Client()
        self.teacher = User.objects.create_user(
            username="grading_queue_teacher",
            email="grading_queue_teacher@example.com",
            password="testpass123",
        )
        self.student = User.objects.create_user(
            username="grading_queue_student",
            email="grading_queue_student@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            name="Grading Queue Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

        self.course = Course.objects.create(owner=self.teacher, title="Grading Queue Course", status="published")
        self.assignment = Assignment.objects.create(
            course=self.course,
            title="Queue Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
            max_score=75,
        )
        self.submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Queue answer body",
            status="submitted",
            files=[{"name": "queue-answer.pdf", "path": "assignments/submissions/queue-answer.pdf"}],
        )

    def test_grading_queue_renders_assignment_review_actions_and_stats(self):
        _login_with_org(self.client, self.teacher, self.organization)
        response = self.client.get(reverse("accounts:grading_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Queue Assignment")
        self.assertContains(response, "Queue answer body")
        self.assertContains(response, reverse("assignments:grade_submission", kwargs={"pk": self.submission.id}))
        self.assertContains(response, "/ 75")
        self.assertContains(response, "/media/assignments/submissions/queue-answer.pdf")
        # Student identity must be hidden during grading phase.
        self.assertContains(response, "Anonim tələbə")
        self.assertNotContains(response, "grading_queue_student")


class PendingReviewViewTest(TestCase):
    """Tests for pending review view (teacher-only)."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.org = Organization.objects.create(
            name="Pending Review Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, self.org, ProfileRole.MEMBER)

    def _set_user_role(self, user, role):
        _assign_user_to_org(user, self.org, role)

    def _login_user(self, user=None):
        _login_with_org(self.client, user or self.user, self.org)

    def test_pending_review_requires_login(self):
        """Test that pending review requires authentication."""
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 302)

    def test_pending_review_redirects_non_teacher(self):
        """Test that non-teacher users are redirected."""
        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 302)  # Redirect for non-teacher

    def test_pending_review_loads_for_teacher(self):
        self._set_user_role(self.user, ProfileRole.TEACHER)
        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("review_items", response.context)

    def test_pending_review_uses_submitted_dates_and_oldest_sort_order(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.exams.models import Exam, ExamAttempt

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_sort_student",
            email="pending_sort_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)

        older_exam = Exam.objects.create(
            author=self.user, title="Older Pending Exam", exam_type="written", is_active=True
        )
        newer_exam = Exam.objects.create(
            author=self.user, title="Newer Pending Exam", exam_type="written", is_active=True
        )

        now = timezone.now()
        older_attempt = ExamAttempt.objects.create(
            user=student,
            exam=older_exam,
            status="submitted",
            checked_by_teacher=False,
        )
        older_attempt.started_at = now - timedelta(hours=5)
        older_attempt.finished_at = now - timedelta(hours=4)
        older_attempt.save(update_fields=["started_at", "finished_at"])

        newer_attempt = ExamAttempt.objects.create(
            user=student,
            exam=newer_exam,
            status="submitted",
            checked_by_teacher=False,
        )
        newer_attempt.started_at = now - timedelta(hours=2)
        newer_attempt.finished_at = now - timedelta(hours=1)
        newer_attempt.save(update_fields=["started_at", "finished_at"])

        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"), {"submitted_order": "oldest"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Göndərilib:")
        self.assertContains(response, "data-bootstrap-select", html=False)

        exam_items = [
            item
            for item in response.context["review_items"]
            if item["type"] == "exam" and item["title"] in {"Older Pending Exam", "Newer Pending Exam"}
        ]
        self.assertEqual([item["title"] for item in exam_items], ["Older Pending Exam", "Newer Pending Exam"])
        self.assertEqual(exam_items[0]["submitted_at"], older_attempt.finished_at)
        self.assertEqual(exam_items[1]["submitted_at"], newer_attempt.finished_at)

    def test_pending_review_only_includes_teacher_owned_exam_attempts(self):
        from apps.exams.models import Exam, ExamAttempt

        other_teacher = User.objects.create_user(
            username="other_teacher",
            email="other_teacher@example.com",
            password="testpass123",
        )
        student = User.objects.create_user(
            username="pending_student",
            email="pending_student@example.com",
            password="testpass123",
        )

        self._set_user_role(self.user, ProfileRole.TEACHER)
        self._set_user_role(other_teacher, ProfileRole.TEACHER)
        self._set_user_role(student, ProfileRole.STUDENT)

        teacher_exam = Exam.objects.create(
            author=self.user,
            title="Teacher Pending Exam",
            exam_type="written",
            is_active=True,
        )
        other_exam = Exam.objects.create(
            author=other_teacher,
            title="Other Pending Exam",
            exam_type="written",
            is_active=True,
        )

        ExamAttempt.objects.create(
            user=student,
            exam=teacher_exam,
            status="submitted",
            checked_by_teacher=False,
        )
        ExamAttempt.objects.create(
            user=student,
            exam=other_exam,
            status="submitted",
            checked_by_teacher=False,
        )

        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Teacher Pending Exam")
        self.assertNotContains(response, "Other Pending Exam")

    def test_pending_review_exam_item_shows_exam_creator_name(self):
        from apps.exams.models import Exam, ExamAttempt

        self._set_user_role(self.user, ProfileRole.TEACHER)
        self.user.first_name = "Teacher"
        self.user.last_name = "Owner"
        self.user.save(update_fields=["first_name", "last_name"])

        student = User.objects.create_user(
            username="pending_creator_student",
            email="pending_creator_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        exam = Exam.objects.create(
            author=self.user,
            title="Creator Name Pending Exam",
            exam_type="written",
            is_active=True,
        )
        ExamAttempt.objects.create(user=student, exam=exam, status="submitted", checked_by_teacher=False)

        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))

        self.assertEqual(response.status_code, 200)
        exam_item = next(item for item in response.context["review_items"] if item["title"] == exam.title)
        self.assertEqual(exam_item["creator_display"], "Teacher Owner")
        self.assertContains(response, "Müəllim: Teacher Owner")

    def test_pending_review_coding_exam_item_uses_practical_type_label(self):
        from apps.exams.models import Exam, ExamAttempt

        self._set_user_role(self.user, ProfileRole.TEACHER)
        student = User.objects.create_user(
            username="pending_coding_student",
            email="pending_coding_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        exam = Exam.objects.create(
            author=self.user,
            title="Pending Practical Exam",
            exam_type="coding",
            is_active=True,
        )
        ExamAttempt.objects.create(user=student, exam=exam, status="submitted", checked_by_teacher=False)

        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))

        self.assertEqual(response.status_code, 200)
        exam_item = next(item for item in response.context["review_items"] if item["title"] == exam.title)
        self.assertEqual(exam_item["type_label"], "Praktiki imtahan")
        self.assertContains(response, "Praktiki imtahan")

    def test_pending_review_coding_exam_shows_recheck_during_review_window(self):
        from django.utils import timezone

        from apps.exams.models import Exam, ExamAttempt

        self._set_user_role(self.user, ProfileRole.TEACHER)
        student = User.objects.create_user(
            username="pending_coding_recheck_student",
            email="pending_coding_recheck_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        exam = Exam.objects.create(
            author=self.user,
            title="Recent Practical Review Exam",
            exam_type="coding",
            is_active=True,
        )
        ExamAttempt.objects.create(
            user=student,
            exam=exam,
            status="submitted",
            checked_by_teacher=True,
            teacher_score=80,
            teacher_checked_at=timezone.now(),
        )

        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))

        self.assertEqual(response.status_code, 200)
        exam_item = next(item for item in response.context["review_items"] if item["title"] == exam.title)
        self.assertTrue(exam_item["is_recheck"])
        self.assertEqual(exam_item["action_label"], "Yenidən yoxla")
        self.assertEqual(exam_item["countdown_mode"], "recheck")
        self.assertGreater(exam_item["review_window_seconds_left"], 0)
        self.assertContains(response, "Yenidən yoxla")

    def test_coding_exam_moves_to_review_results_after_review_window(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.exams.models import Exam, ExamAttempt

        self._set_user_role(self.user, ProfileRole.TEACHER)
        student = User.objects.create_user(
            username="old_coding_review_student",
            email="old_coding_review_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        exam = Exam.objects.create(
            author=self.user,
            title="Finalized Practical Review Exam",
            exam_type="coding",
            is_active=True,
        )
        ExamAttempt.objects.create(
            user=student,
            exam=exam,
            status="submitted",
            checked_by_teacher=True,
            teacher_score=88,
            teacher_checked_at=timezone.now() - timedelta(minutes=6),
        )

        self._login_user()
        pending_response = self.client.get(reverse("accounts:pending_review"))
        results_response = self.client.get(reverse("accounts:review_results"))

        self.assertEqual(pending_response.status_code, 200)
        self.assertEqual(results_response.status_code, 200)
        self.assertNotContains(pending_response, "Finalized Practical Review Exam")
        self.assertContains(results_response, "Finalized Practical Review Exam")

    def test_profile_pending_review_section_renders_pr_page_pagination_links(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.exams.models import Exam, ExamAttempt

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_pagination_student",
            email="pending_pagination_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)

        base_time = timezone.now() - timedelta(hours=3)
        for index in range(16):
            exam = Exam.objects.create(
                author=self.user,
                title=f"Paginated Pending Exam {index}",
                exam_type="written",
                is_active=True,
            )
            attempt = ExamAttempt.objects.create(
                user=student,
                exam=exam,
                status="submitted",
                checked_by_teacher=False,
            )
            attempt.started_at = base_time + timedelta(minutes=index)
            attempt.finished_at = attempt.started_at + timedelta(minutes=20)
            attempt.save(update_fields=["started_at", "finished_at"])

        self._login_user()
        response = self.client.get(reverse("accounts:profile"), {"section": "pending-review"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pr_page=2")
        self.assertEqual(response.context["pending_review_page_obj"].number, 1)

        second_page_response = self.client.get(
            reverse("accounts:profile"),
            {"section": "pending-review", "pr_page": 2},
        )

        self.assertEqual(second_page_response.status_code, 200)
        self.assertEqual(second_page_response.context["pending_review_page_obj"].number, 2)
        self.assertContains(second_page_response, "Paginated Pending Exam 15")

    def test_pending_review_reveals_written_exam_student_when_org_override_enabled(self):
        from apps.exams.models import Exam, ExamAttempt

        self.org.set_written_exam_identity_reveal_enabled(True)
        self.org.save(update_fields=["settings", "updated_at"])
        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_visible_exam_student",
            email="pending_visible_exam_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        exam = Exam.objects.create(
            author=self.user,
            title="Visible Pending Exam",
            exam_type="written",
            is_active=True,
        )
        ExamAttempt.objects.create(
            user=student,
            exam=exam,
            status="submitted",
        )

        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))

        self.assertEqual(response.status_code, 200)
        exam_item = next(item for item in response.context["review_items"] if item["title"] == "Visible Pending Exam")
        self.assertEqual(exam_item["student_display"], student.username)
        self.assertTrue(exam_item["can_view_student_identity"])
        self.assertContains(response, student.username)
        self.assertNotContains(response, "Anonim tələbə")

    def test_pending_review_reveals_assignment_student_when_org_override_enabled(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        self.org.set_assignment_identity_reveal_enabled(True)
        self.org.save(update_fields=["settings", "updated_at"])
        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_visible_assignment_student",
            email="pending_visible_assignment_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        course = Course.objects.create(owner=self.user, title="Visible Pending Assignment Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Visible Pending Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Pending assignment answer",
            status="submitted",
        )

        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))

        self.assertEqual(response.status_code, 200)
        assignment_item = next(
            item for item in response.context["review_items"] if item["title"] == "Visible Pending Assignment"
        )
        self.assertEqual(assignment_item["student_display"], student.username)
        self.assertTrue(assignment_item["can_view_student_identity"])
        self.assertContains(response, student.username)

    def test_pending_review_detail_reveals_assignment_student_when_org_override_enabled(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        self.org.set_assignment_identity_reveal_enabled(True)
        self.org.save(update_fields=["settings", "updated_at"])
        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_detail_visible_assignment_student",
            email="pending_detail_visible_assignment_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        course = Course.objects.create(owner=self.user, title="Visible Pending Detail Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Visible Pending Detail Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Pending detail answer",
            status="submitted",
        )

        self._login_user()
        response = self.client.get(
            reverse(
                "accounts:pending_review_detail",
                kwargs={"item_type": "assignment", "item_id": submission.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, student.username)
        self.assertFalse(response.context["is_identity_hidden"])

    def test_pending_review_assignment_points_to_pending_detail_with_type_label(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_assignment_student",
            email="pending_assignment_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        course = Course.objects.create(owner=self.user, title="Pending Detail Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Pending Detail Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Pending detail answer",
            status="submitted",
        )

        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 200)
        items = response.context["review_items"]
        assignment_item = next(item for item in items if item["type"] == "assignment")
        self.assertEqual(assignment_item["type_label"], "Sərbəst iş")
        self.assertEqual(assignment_item["student_display"], "Anonim tələbə")
        self.assertIn(
            reverse(
                "accounts:pending_review_detail",
                kwargs={"item_type": "assignment", "item_id": submission.id},
            ),
            assignment_item["action_url"],
        )
        self.assertContains(response, "Anonim tələbə")
        self.assertNotContains(response, student.username)

    def test_pending_review_reveals_assignment_student_after_pregrade_window_closes(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="revealed_pending_assignment_student",
            email="revealed_pending_assignment_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        course = Course.objects.create(owner=self.user, title="Revealed Pending Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Revealed Pending Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Older pending answer",
            status="submitted",
        )
        # Simulate a submission that was submitted more than 5 minutes ago.
        submission.submitted_at = timezone.now() - timedelta(minutes=6)
        submission.save(update_fields=["submitted_at"])

        self._login_user()
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 200)

        items = response.context["review_items"]
        assignment_item = next(item for item in items if item["title"] == "Revealed Pending Assignment")
        # Pending (submitted) submissions must ALWAYS remain anonymous —
        # the student identity is only revealed after grading AND the re-check window closes.
        self.assertEqual(assignment_item["student_display"], "Anonim tələbə")
        self.assertEqual(assignment_item["action_label"], "Yoxla")
        self.assertContains(response, "Anonim tələbə")
        self.assertNotContains(response, student.username)

    def test_pending_review_detail_allows_edit_within_window_and_locks_after(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_lock_student",
            email="pending_lock_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        course = Course.objects.create(owner=self.user, title="Pending Lock Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Pending Lock Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Answer to lock test",
            status="submitted",
        )

        self._login_user()
        detail_url = reverse(
            "accounts:pending_review_detail",
            kwargs={"item_type": "assignment", "item_id": submission.id},
        )

        save_response = self.client.post(
            detail_url,
            {"score": "87.5", "feedback": "Initial review feedback"},
        )
        self.assertEqual(save_response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "graded")
        self.assertEqual(float(submission.grade), 87.5)
        self.assertEqual(submission.feedback, "Initial review feedback")
        self.assertIsNotNone(submission.graded_at)

        pending_response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(pending_response.status_code, 200)
        self.assertContains(pending_response, "Pending Lock Assignment")
        self.assertContains(pending_response, "Yenidən yoxla")
        pending_items = pending_response.context["review_items"]
        lock_item = next(item for item in pending_items if item["title"] == "Pending Lock Assignment")
        self.assertGreater(lock_item["review_window_seconds_left"], 0)

        submission.graded_at = timezone.now() - timedelta(minutes=6)
        submission.save(update_fields=["graded_at"])

        locked_response = self.client.post(
            detail_url,
            {"score": "95", "feedback": "Should not be saved"},
        )
        self.assertEqual(locked_response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(float(submission.grade), 87.5)
        self.assertEqual(submission.feedback, "Initial review feedback")

        pending_after_window = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(pending_after_window.status_code, 200)
        self.assertNotContains(pending_after_window, "Pending Lock Assignment")

    def test_pending_review_detail_preserves_saved_assignment_score_in_ui_and_shows_confirm_modal(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_assignment_grade_student",
            email="pending_assignment_grade_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        course = Course.objects.create(owner=self.user, title="Pending Score Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Pending Score Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Saved score answer",
            status="graded",
            grade="30.00",
            feedback="Saved score feedback",
            graded_at=timezone.now(),
        )

        self._login_user()
        response = self.client.get(
            reverse(
                "accounts:pending_review_detail",
                kwargs={"item_type": "assignment", "item_id": submission.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_score"')
        self.assertContains(response, 'value="30"')
        self.assertContains(response, 'step="1"')
        self.assertContains(response, "courseActionConfirmModal")

    def test_pending_review_detail_deduplicates_assignment_attachments(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_attachment_student",
            email="pending_attachment_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        course = Course.objects.create(owner=self.user, title="Attachment Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Attachment Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Attachment answer",
            status="submitted",
            files=[{"name": "VBS.docx", "path": "assignments/submissions/vbs.docx"}],
        )

        self._login_user()
        response = self.client.get(
            reverse(
                "accounts:pending_review_detail",
                kwargs={"item_type": "assignment", "item_id": submission.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["attachments"]), 1)
        self.assertEqual(response.context["attachments"][0]["name"], "VBS.docx")
        self.assertEqual(response.content.decode("utf-8").count("VBS.docx"), 1)

    def test_pending_review_lab_detail_preserves_manual_total_without_checkbox(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.courses.models import Course, CourseMembership
        from apps.labs.models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="pending_lab_student",
            email="pending_lab_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        course = Course.objects.create(owner=self.user, title="Pending Lab Course", status="published")
        CourseMembership.objects.create(course=course, user=student, role="student")
        lab = Lab.objects.create(
            course=course,
            title="Pending Review Lab",
            description="Pending review manual total",
            start_datetime=timezone.now() - timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=2),
            max_score=100,
            max_attempts=2,
            status="published",
            created_by=self.user,
        )
        assignment = LabAssignment.objects.create(lab=lab, student=student)
        submission = LabSubmission.objects.create(
            assignment=assignment,
            status="graded",
            score="95.00",
            feedback="Manual total should persist",
            graded_at=timezone.now(),
            attempt_number=1,
        )
        block = LabBlock.objects.create(lab=lab, title="Manual Block", order=1)
        question = LabQuestion.objects.create(
            block=block,
            question_text="Explain the pending review solution",
            question_number=1,
            points=100,
        )
        answer = LabAnswer.objects.create(
            lab=lab,
            question=question,
            student=student,
            submission=submission,
            attempt_number=1,
            answer="Pending review lab answer",
            is_draft=False,
        )

        self._login_user()
        detail_url = reverse(
            "accounts:pending_review_detail",
            kwargs={"item_type": "lab", "item_id": submission.id},
        )

        initial_response = self.client.get(detail_url)
        self.assertEqual(initial_response.status_code, 200)
        self.assertContains(initial_response, 'value="95"')
        self.assertContains(initial_response, 'step="1"')
        self.assertContains(initial_response, "courseActionConfirmModal")
        self.assertNotContains(initial_response, "Yekun balı əl ilə dəyiş")
        self.assertNotContains(initial_response, "useManualTotal")

        save_response = self.client.post(
            detail_url,
            {
                "score": "95.00",
                "feedback": "Updated manual total review",
                f"answer_score_{answer.id}": "",
            },
        )
        self.assertEqual(save_response.status_code, 302)
        submission.refresh_from_db()
        answer.refresh_from_db()
        self.assertEqual(submission.score, Decimal("95.00"))
        self.assertEqual(submission.feedback, "Updated manual total review")
        self.assertIsNone(answer.score)

        submission.submitted_at = timezone.now() - timedelta(minutes=10)
        submission.graded_at = timezone.now() - timedelta(minutes=6)
        submission.save(update_fields=["submitted_at", "graded_at"])

        locked_response = self.client.get(detail_url)
        self.assertEqual(locked_response.status_code, 200)
        self.assertContains(locked_response, student.username)
        self.assertContains(locked_response, 'value="95"')
        self.assertContains(locked_response, "Yoxlama bağlanıb.")


class ReviewResultsViewTest(TestCase):
    """Tests for evaluated review results view (teacher-only)."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="review_user",
            email="review_user@example.com",
            password="testpass123",
        )
        self.org = Organization.objects.create(
            name="Review Results Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.user, self.org, ProfileRole.MEMBER)

    def _set_user_role(self, user, role):
        _assign_user_to_org(user, self.org, role)

    def _login_user(self, user=None):
        _login_with_org(self.client, user or self.user, self.org)

    def test_review_results_requires_login(self):
        response = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(response.status_code, 302)

    def test_review_results_redirects_non_teacher(self):
        self._login_user()
        response = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(response.status_code, 302)

    def test_review_results_loads_for_teacher(self):
        self._set_user_role(self.user, ProfileRole.TEACHER)
        self._login_user()
        response = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("evaluated_review_items", response.context)

    def test_review_results_formats_exam_score_with_percent_badge_and_sorts_by_submission_date(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.exams.models import Exam, ExamAttempt

        self._set_user_role(self.user, ProfileRole.TEACHER)
        self.user.first_name = "Review"
        self.user.last_name = "Teacher"
        self.user.save(update_fields=["first_name", "last_name"])

        student = User.objects.create_user(
            username="review_sort_student",
            email="review_sort_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)

        older_exam = Exam.objects.create(
            author=self.user, title="Older Reviewed Exam", exam_type="test", is_active=True
        )
        newer_exam = Exam.objects.create(
            author=self.user, title="Newer Reviewed Exam", exam_type="test", is_active=True
        )

        now = timezone.now()
        older_attempt = ExamAttempt.objects.create(
            user=student,
            exam=older_exam,
            status="submitted",
            correct_count=22,
            wrong_count=3,
        )
        older_attempt.started_at = now - timedelta(hours=6)
        older_attempt.finished_at = now - timedelta(hours=5)
        older_attempt.save(update_fields=["started_at", "finished_at"])

        newer_attempt = ExamAttempt.objects.create(
            user=student,
            exam=newer_exam,
            status="submitted",
            teacher_score=91,
        )
        newer_attempt.started_at = now - timedelta(hours=2)
        newer_attempt.finished_at = now - timedelta(hours=1)
        newer_attempt.save(update_fields=["started_at", "finished_at"])

        self._login_user()
        response = self.client.get(reverse("accounts:review_results"), {"evaluated_submitted_order": "oldest"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-bootstrap-select", html=False)
        # Müəllim balı olan attempt-də faiz badge-i göstərilmir.
        self.assertNotContains(response, "91%", html=False)

        exam_items = [
            item
            for item in response.context["evaluated_review_items"]
            if item["type"] == "exam" and item["title"] in {"Older Reviewed Exam", "Newer Reviewed Exam"}
        ]
        self.assertEqual([item["title"] for item in exam_items], ["Older Reviewed Exam", "Newer Reviewed Exam"])
        # Nəticə sütununda əsas dəyər BAL-dır (bal / maks); faiz ayrıca badge-dədir.
        self.assertEqual(exam_items[0]["score_display"], "22 / 25")
        self.assertEqual(exam_items[0]["score_percent_display"], "88%")
        self.assertEqual(exam_items[1]["score_display"], "91")
        self.assertEqual(exam_items[1]["score_percent_display"], "")
        self.assertEqual(exam_items[0]["evaluator_display"], "Review Teacher")
        self.assertContains(response, "Review Teacher")
        self.assertEqual(exam_items[0]["submitted_at"], older_attempt.finished_at)
        self.assertEqual(exam_items[1]["submitted_at"], newer_attempt.finished_at)

    def test_review_results_exam_action_url_points_to_attempt_detail(self):
        from apps.exams.models import Exam, ExamAttempt

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="review_result_student",
            email="review_result_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)
        exam = Exam.objects.create(
            author=self.user,
            title="Direct Detail Test",
            exam_type="test",
            is_active=True,
        )
        attempt = ExamAttempt.objects.create(
            user=student,
            exam=exam,
            status="submitted",
        )

        self._login_user()
        response = self.client.get(reverse("accounts:review_results"))

        self.assertEqual(response.status_code, 200)
        items = response.context["evaluated_review_items"]
        exam_item = next(item for item in items if item["type"] == "exam" and item["title"] == exam.title)
        expected_path = reverse(
            "exams:teacher_view_attempt",
            kwargs={"slug": exam.slug, "attempt_id": attempt.id},
        )
        self.assertIn(expected_path, exam_item["action_url"])
        self.assertNotIn("/results/", exam_item["action_url"])

    def test_review_results_non_exam_action_urls_point_to_review_detail_page(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from apps.labs.models import Lab, LabAssignment, LabSubmission
        from apps.projects.models import Project, ProjectSubmission

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="review_result_student_2",
            email="review_result_student_2@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)

        course = Course.objects.create(owner=self.user, title="Review Result Course", status="published")

        assignment = Assignment.objects.create(
            course=course,
            title="Reviewed Assignment",
            start_date=timezone.now() - timedelta(days=1),
            status="published",
        )
        assignment_submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Assignment reviewed answer",
            status="graded",
            grade=88,
            graded_by=self.user,
        )

        project = Project.objects.create(
            course=course,
            title="Reviewed Project",
            start_date=timezone.now() - timedelta(days=2),
            deadline=timezone.now() + timedelta(days=2),
            status="active",
        )
        project_submission = ProjectSubmission.objects.create(
            project=project,
            student=student,
            content="Project reviewed answer",
            status="graded",
            grade=91,
            graded_by=self.user,
        )

        lab = Lab.objects.create(
            course=course,
            title="Reviewed Lab",
            start_datetime=timezone.now() - timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=1),
            status="published",
            created_by=self.user,
        )
        lab_assignment = LabAssignment.objects.create(lab=lab, student=student)
        lab_submission = LabSubmission.objects.create(
            assignment=lab_assignment,
            submission_text="Lab reviewed answer",
            status="graded",
            score=77,
            graded_by=self.user,
        )

        self._login_user()
        response = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(response.status_code, 200)

        items = response.context["evaluated_review_items"]
        assignment_item = next(item for item in items if item["type"] == "assignment")
        project_item = next(item for item in items if item["type"] == "project")
        lab_item = next(item for item in items if item["type"] == "lab")

        self.assertEqual(assignment_item["evaluator_display"], self.user.username)
        self.assertEqual(project_item["evaluator_display"], self.user.username)
        self.assertEqual(lab_item["evaluator_display"], self.user.username)
        self.assertIn(
            reverse(
                "accounts:review_result_detail",
                kwargs={"item_type": "assignment", "item_id": assignment_submission.id},
            ),
            assignment_item["action_url"],
        )
        self.assertIn(
            reverse(
                "accounts:review_result_detail",
                kwargs={"item_type": "project", "item_id": project_submission.id},
            ),
            project_item["action_url"],
        )
        self.assertIn(
            reverse(
                "accounts:review_result_detail",
                kwargs={"item_type": "lab", "item_id": lab_submission.id},
            ),
            lab_item["action_url"],
        )

    def test_review_result_detail_assignment_loads_for_teacher(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        self._set_user_role(self.user, ProfileRole.TEACHER)

        student = User.objects.create_user(
            username="review_detail_student",
            email="review_detail_student@example.com",
            password="testpass123",
        )
        self._set_user_role(student, ProfileRole.STUDENT)

        course = Course.objects.create(owner=self.user, title="Detail Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Detail Assignment",
            start_date=timezone.now() - timedelta(days=1),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Detail content",
            status="graded",
            grade=100,
        )

        self._login_user()
        response = self.client.get(
            reverse(
                "accounts:review_result_detail",
                kwargs={"item_type": "assignment", "item_id": submission.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Assignment")
