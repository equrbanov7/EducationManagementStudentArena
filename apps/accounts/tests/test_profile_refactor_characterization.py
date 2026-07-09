"""
Characterization tests for the ``profile.py`` refactor (P0.1).

These tests pin down the CURRENT behavior of ``user_profile`` and the other
profile views *before* the file is split into a package. They are intentionally
behavior-only: they do not assert anything new, they only lock the existing
contract so the refactor cannot silently drop a context key, change a redirect,
or alter a form-handling branch.

If any of these tests fail after the refactor, the refactor changed behavior
and must be corrected.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole, UserProfile
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


# The complete set of context keys that user_profile ALWAYS exposes,
# regardless of role or active section. Captured from the pre-refactor
# implementation via AST analysis of the literal `context = {...}` dict and
# the unconditional `context.update({...})` calls.
#
# Note: section-internal keys (e.g. `permission_categories`,
# `actor_permissions`, `can_assign_roles`) are intentionally NOT here — those
# live inside `permission_editor_section` / `role_assignment_section` dicts and
# only when the corresponding section is active. The refactored orchestrator
# must still produce every key below for every authenticated user.
EXPECTED_PROFILE_CONTEXT_KEYS = {
    "active_main_nav",
    "active_section",
    "active_section_title",
    "all_modules",
    "allowed_sections",
    "assignable_roles",
    "assigned_courses",
    "assigned_courses_count",
    "assigned_courses_search_query",
    "assigned_exams_count",
    "assigned_task_counts",
    "assigned_task_items",
    "assigned_tasks_active_filter",
    "assigned_tasks_count",
    "assigned_tasks_search_query",
    "can_approve_posts",
    "can_manage_blog",
    "can_manage_org",
    "can_multi_assign_group_teachers",
    "can_review_submissions",
    "can_view_blog",
    "can_view_owned_learning",
    "can_view_student_assignments",
    "category_management_create_form",
    "category_management_create_parent_options",
    "category_management_create_selected_parent_id",
    "category_management_edit_form",
    "category_management_edit_item",
    "category_management_edit_parent_options",
    "category_management_edit_selected_parent_id",
    "category_management_filtered_count",
    "category_management_page",
    "category_management_page_param",
    "category_management_pagination_query",
    "category_management_search_query",
    "category_management_total_count",
    "courses_count",
    "direct_profile_section",
    "direct_profile_section_template",
    "evaluated_review_available_groups",
    "evaluated_review_count",
    "evaluated_review_filter_group",
    "evaluated_review_filter_type",
    "evaluated_review_items",
    "evaluated_review_page_obj",
    "evaluated_review_pagination_query",
    "evaluated_review_search_query",
    "evaluated_review_submitted_order",
    "evaluated_review_total_count",
    "filter_status",
    "filter_type",
    "group_form",
    "group_students_pagination_query",
    "group_students_search_query",
    "groups_section_return_url",
    "in_app_notifications_page",
    "in_app_unread_count",
    "is_admin",
    "is_superadmin",
    "is_teacher",
    "manage_roles_section",
    "my_courses",
    "my_created_courses",
    "my_created_courses_count",
    "my_exams",
    "my_exams_count",
    "my_exams_filter_type",
    "my_exams_search_query",
    "my_result_counts",
    "my_result_items",
    "my_results_active_filter",
    "my_results_count",
    "my_results_page_obj",
    "my_results_page_param",
    "my_results_pagination_query",
    "my_results_search_query",
    "notif_filter",
    "notif_pagination_query",
    "notif_search_query",
    "notifications_unread_count",
    "organization_access_rows",
    "organizations",
    "pagination_query",
    "password_change_form",
    "pending_answer_counts",
    "pending_answer_items",
    "pending_answers_active_filter",
    "pending_answers_count",
    "pending_answers_search_query",
    "pending_appeals_count",
    "pending_post_approval_available_groups",
    "pending_post_approval_available_organizations",
    "pending_post_approval_count",
    "pending_post_approval_filter_group",
    "pending_post_approval_filter_organization",
    "pending_post_approval_filter_status",
    "pending_post_approval_items",
    "pending_post_approval_page_obj",
    "pending_post_approval_pagination_query",
    "pending_post_approval_search_query",
    "pending_post_approval_total_count",
    "pending_review_available_groups",
    "pending_review_count",
    "pending_review_filter_group",
    "pending_review_filter_status",
    "pending_review_filter_type",
    "pending_review_items",
    "pending_review_page_obj",
    "pending_review_pagination_query",
    "pending_review_search_query",
    "pending_review_submitted_order",
    "pending_review_total_count",
    "pending_student_invites",
    "pending_student_join_message",
    "pending_student_join_org_name",
    "pending_student_join_requests",
    "permission_editor_section",
    "post_category_root_options",
    "post_category_subcategory_options",
    "post_category_tree",
    "post_creation_requires_approval",
    "post_next_url",
    "posting_blocked",
    "posting_blocked_reason",
    "posts_count",
    "primary_user_role_label",
    "profile",
    "profile_base_url",
    "profiles",
    "publish_notification_targets",
    "review_items",
    "role_assignment_section",
    "role_capabilities",
    "roles",
    "search_query",
    "selected_group_students_count",
    "selected_group_students_filtered_count",
    "selected_group_students_page",
    "selected_role",
    "selected_teacher_group",
    "shortcut_sections",
    "statistics_course_page",
    "statistics_course_page_param",
    "statistics_course_pagination_query",
    "statistics_course_rows",
    "statistics_courses",
    "statistics_data",
    "statistics_filters",
    "statistics_group_page",
    "statistics_group_page_param",
    "statistics_group_pagination_query",
    "statistics_group_rows",
    "statistics_groups",
    "statistics_has_active_filters",
    "statistics_org_page",
    "statistics_org_page_param",
    "statistics_org_pagination_query",
    "statistics_org_rows",
    "statistics_organizations",
    "statistics_reset_url",
    "statistics_teacher_course_page",
    "statistics_teacher_course_page_param",
    "statistics_teacher_course_pagination_query",
    "statistics_teacher_course_rows",
    "statistics_teacher_page",
    "statistics_teacher_page_param",
    "statistics_teacher_pagination_query",
    "statistics_teacher_rows",
    "student_can_leave_org",
    "student_member_groups",
    "student_member_groups_count",
    "student_member_groups_more_count",
    "student_org_management_section",
    "student_org_request_section",
    "superadmin_ai_settings_section",
    "superadmin_org_features_section",
    "superadmin_organizations_section",
    "superadmin_pending_org_count",
    "superadmin_users_section",
    "teacher_groups",
    "teacher_groups_count",
    "teacher_groups_filtered_count",
    "teacher_groups_page",
    "teacher_groups_pagination_query",
    "teacher_groups_payload",
    "teacher_groups_search_query",
    "total_count",
    "user_posts",
    "user_roles",
}


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


class ProfileContextContractTest(TestCase):
    """Lock the full context-key contract of user_profile across roles."""

    def setUp(self):
        self.client = Client()
        self.plain_user = User.objects.create_user(
            username="plainuser", email="plain@example.com", password="pw12345678"
        )

    def _assert_full_context(self, response):
        self.assertEqual(response.status_code, 200)
        present = set(response.context.keys())
        missing = EXPECTED_PROFILE_CONTEXT_KEYS - present
        self.assertEqual(
            missing,
            set(),
            f"user_profile context is missing keys after refactor: {sorted(missing)}",
        )

    def test_plain_user_profile_context_complete(self):
        self.client.force_login(self.plain_user)
        response = self.client.get(reverse("accounts:profile"))
        self._assert_full_context(response)

    def test_superadmin_profile_context_complete(self):
        admin = User.objects.create_superuser(username="superadmin", email="sa@example.com", password="pw12345678")
        self.client.force_login(admin)
        response = self.client.get(reverse("accounts:profile"))
        self._assert_full_context(response)

    def test_teacher_profile_context_complete(self):
        org_owner = User.objects.create_user(
            username="charteacherowner", email="towner@example.com", password="pw12345678"
        )
        org = Organization.objects.create(
            name="Char Test Org",
            slug="char-test-org",
            org_type=OrganizationType.SCHOOL,
            owner=org_owner,
            status="active",
            is_active=True,
        )
        teacher = User.objects.create_user(username="charteacher", email="t@example.com", password="pw12345678")
        _assign_user_to_org(teacher, org, ProfileRole.TEACHER)
        _login_with_org(self.client, teacher, org)
        response = self.client.get(reverse("accounts:profile"))
        self._assert_full_context(response)

    def test_student_profile_context_complete(self):
        org_owner = User.objects.create_user(
            username="charstudentowner", email="sowner@example.com", password="pw12345678"
        )
        org = Organization.objects.create(
            name="Char Student Org",
            slug="char-student-org",
            org_type=OrganizationType.SCHOOL,
            owner=org_owner,
            status="active",
            is_active=True,
        )
        student = User.objects.create_user(username="charstudent", email="s@example.com", password="pw12345678")
        _assign_user_to_org(student, org, ProfileRole.STUDENT)
        _login_with_org(self.client, student, org)
        response = self.client.get(reverse("accounts:profile"))
        self._assert_full_context(response)

    def test_each_allowed_section_renders_200(self):
        """Every section the user is allowed to see must still render 200."""
        admin = User.objects.create_superuser(username="sectionadmin", email="sec@example.com", password="pw12345678")
        self.client.force_login(admin)
        base = self.client.get(reverse("accounts:profile"))
        allowed = base.context["allowed_sections"]
        for section in sorted(allowed):
            with self.subTest(section=section):
                resp = self.client.get(reverse("accounts:profile"), {"section": section})
                self.assertEqual(resp.status_code, 200, f"section '{section}' did not render 200")


class ProfileSectionResolutionTest(TestCase):
    """Pin the active-section resolution rules."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="sectionuser", email="su@example.com", password="pw12345678")
        self.client.force_login(self.user)

    def test_unknown_section_falls_back_to_profile_info(self):
        resp = self.client.get(reverse("accounts:profile"), {"section": "does-not-exist"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["active_section"], "profile-info")

    def test_delete_account_section_falls_back_to_profile_info(self):
        resp = self.client.get(reverse("accounts:profile"), {"section": "delete-account"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["active_section"], "profile-info")

    def test_default_section_is_profile_info(self):
        resp = self.client.get(reverse("accounts:profile"))
        self.assertEqual(resp.context["active_section"], "profile-info")


class ProfilePostHandlingTest(TestCase):
    """Pin the POST-form branches of user_profile."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="postuser",
            email="post@example.com",
            password="pw12345678",
            first_name="Old",
            last_name="Name",
        )
        self.client.force_login(self.user)

    def test_edit_profile_updates_user_and_profile_fields(self):
        resp = self.client.post(
            reverse("accounts:profile"),
            {
                "profile_form": "edit-profile",
                "first_name": "New",
                "last_name": "Person",
                "email": "newperson@example.com",
                "phone": "555000",
                "bio": "hello bio",
                "location": "Baku",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "New")
        self.assertEqual(self.user.last_name, "Person")
        self.assertEqual(self.user.email, "newperson@example.com")
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.phone, "555000")
        self.assertEqual(profile.bio, "hello bio")
        self.assertEqual(profile.location, "Baku")

    def test_edit_profile_rejects_missing_required_fields(self):
        """
        Missing first/last/email must redirect back to the edit-profile section
        without modifying the user.

        (profile.py lines 507/511 previously used a buggy
        `redirect("accounts:profile" + "?section=...")` that raised
        NoReverseMatch; fixed to use `reverse()` properly.)
        """
        resp = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "edit-profile", "first_name": "", "last_name": "", "email": ""},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("section=edit-profile", resp.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Old")

    def test_edit_profile_rejects_duplicate_email(self):
        """A duplicate email must redirect back to edit-profile without saving."""
        User.objects.create_user(username="other", email="taken@example.com", password="pw12345678")
        resp = self.client.post(
            reverse("accounts:profile"),
            {
                "profile_form": "edit-profile",
                "first_name": "New",
                "last_name": "Person",
                "email": "taken@example.com",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("section=edit-profile", resp.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "post@example.com")

    def test_change_password_success_redirects_to_change_password_section(self):
        resp = self.client.post(
            reverse("accounts:profile"),
            {
                "profile_form": "change-password",
                "old_password": "pw12345678",
                "new_password1": "BrandNewPw99",
                "new_password2": "BrandNewPw99",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("section=change-password", resp.url)

    def test_change_password_invalid_keeps_change_password_section(self):
        resp = self.client.post(
            reverse("accounts:profile"),
            {
                "profile_form": "change-password",
                "old_password": "wrongpassword",
                "new_password1": "BrandNewPw99",
                "new_password2": "BrandNewPw99",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["active_section"], "change-password")

    def test_unknown_profile_form_redirects_to_safe_section(self):
        resp = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "totally-unknown-form"},
        )
        self.assertEqual(resp.status_code, 302)

    def test_non_profile_post_does_not_overwrite_profile_fields(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.bio = "keep me"
        profile.save(update_fields=["bio"])
        self.client.post(reverse("accounts:profile"), {"profile_form": "totally-unknown-form"})
        profile.refresh_from_db()
        self.assertEqual(profile.bio, "keep me")


class ProfileAvatarViewTest(TestCase):
    """Pin profile_avatar behavior."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="avataruser", email="av@example.com", password="pw12345678")

    def test_avatar_requires_login(self):
        resp = self.client.get(reverse("accounts:profile_avatar", kwargs={"user_id": self.user.id}))
        self.assertEqual(resp.status_code, 302)

    def test_avatar_404_when_no_avatar(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("accounts:profile_avatar", kwargs={"user_id": self.user.id}))
        self.assertEqual(resp.status_code, 404)

    def test_avatar_invalid_version_param_returns_400(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse("accounts:profile_avatar", kwargs={"user_id": self.user.id}),
            {"v": "not-a-number!!"},
        )
        self.assertEqual(resp.status_code, 400)


class PublicProfileViewTest(TestCase):
    """Pin public_user_profile behavior."""

    def setUp(self):
        self.client = Client()
        self.author = User.objects.create_user(username="publicauthor", email="pa@example.com", password="pw12345678")

    def test_public_profile_renders_for_anonymous(self):
        resp = self.client.get(reverse("accounts:public_profile", kwargs={"username": "publicauthor"}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["profile_user"], self.author)

    def test_public_profile_self_redirects_to_private_profile(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("accounts:public_profile", kwargs={"username": "publicauthor"}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))

    def test_public_profile_unknown_user_404(self):
        resp = self.client.get(reverse("accounts:public_profile", kwargs={"username": "nobody-here"}))
        self.assertEqual(resp.status_code, 404)

    def test_public_profile_invalid_page_param_returns_400(self):
        resp = self.client.get(
            reverse("accounts:public_profile", kwargs={"username": "publicauthor"}),
            {"page": "abc"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_public_profile_context_keys_present(self):
        resp = self.client.get(reverse("accounts:public_profile", kwargs={"username": "publicauthor"}))
        expected = {
            "profile_user",
            "profile",
            "display_name",
            "search_query",
            "selected_category",
            "extra_query",
            "category_items",
            "published_posts_count",
            "category_count",
            "profile_bio",
            "profile_location",
            "posts",
        }
        self.assertTrue(expected.issubset(set(resp.context.keys())))
