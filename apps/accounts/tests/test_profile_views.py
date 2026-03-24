"""
Tests for profile and dashboard views.
"""

from decimal import Decimal
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
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

    def test_profile_edit_section(self):
        """Test that edit-profile section renders form with save button."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=edit-profile")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yadda Saxla")

    def test_profile_change_password_section_renders(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=change-password")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Şifrəni dəyiş")
        self.assertContains(response, 'name="old_password"', html=False)
        self.assertContains(response, 'name="new_password1"', html=False)
        self.assertContains(response, 'name="new_password2"', html=False)

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
        self.assertNotContains(response, reverse("accounts:student_organization_request"))

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
        self.assertContains(response, "Təşkilat daxili rol (səviyyəli rol)")
        self.assertContains(response, "Profil rolları (multi-role / checkbox)")

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
        self.assertContains(response, "Pending Assignment Visible")
        self.assertContains(response, "Recently Graded Hidden Assignment")
        self.assertContains(response, "Async Written Exam")
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
        )

        self._login_user()
        response = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(response.status_code, 200)

        items = response.context["evaluated_review_items"]
        assignment_item = next(item for item in items if item["type"] == "assignment")
        project_item = next(item for item in items if item["type"] == "project")
        lab_item = next(item for item in items if item["type"] == "lab")

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
