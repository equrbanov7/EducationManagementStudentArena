"""
Integration tests for auth + tenant-scoped role/permission flows.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.organizations.models import Country, Institution, Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


class SignupAndLoginFlowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse("accounts:register")
        self.login_url = reverse("accounts:login")
        self.az = Country.objects.get(code="AZ")

    def _institution(self, org_type):
        institution = Institution.objects.filter(country=self.az, institution_type=org_type, is_active=True).first()
        self.assertIsNotNone(institution, f"Missing seeded institution for {org_type}")
        return institution

    def _register_payload(self, **overrides):
        payload = {
            "username": "newuser",
            "email": "newuser@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
            "country": "AZ",
            "organization_type": OrganizationType.INDIVIDUAL,
            "institution": "",
            "institution_not_listed_name": "",
            "organization_identifier": "",
            "organization_license_identifier": "",
            "initial_role": ProfileRole.MEMBER,
        }
        payload.update(overrides)
        return payload

    def test_signup_user_can_login_immediately_with_username_or_email(self):
        response = self.client.post(self.register_url, self._register_payload())
        self.assertRedirects(response, self.login_url)

        user = User.objects.get(username="newuser")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("StrongPass123!"))

        # Username login
        self.assertTrue(self.client.login(username="newuser", password="StrongPass123!"))
        self.client.logout()

        # Email login (custom backend)
        self.assertTrue(self.client.login(username="newuser@example.com", password="StrongPass123!"))

        profile = user.profile
        self.assertEqual(profile.role, ProfileRole.MEMBER)
        self.assertIsNone(profile.organization)
        self.assertEqual(profile.organization_type, OrganizationType.INDIVIDUAL)
        self.assertFalse(Membership.objects.filter(user=user, is_primary=True).exists())

    def test_signup_form_does_not_offer_student_role(self):
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'value="student"')

    def test_school_signup_creates_tenant_and_membership(self):
        school = self._institution(OrganizationType.SCHOOL)
        response = self.client.post(
            self.register_url,
            self._register_payload(
                username="schooladmin",
                email="schooladmin@example.com",
                organization_type=OrganizationType.SCHOOL,
                institution=str(school.id),
                organization_identifier="",  # should fallback to institution.code
                initial_role=ProfileRole.ORG_ADMIN,
            ),
        )
        self.assertRedirects(response, self.login_url)

        user = User.objects.get(username="schooladmin")
        profile = user.profile
        organization = profile.organization
        self.assertIsNotNone(organization)
        self.assertEqual(organization.org_type, OrganizationType.SCHOOL)
        self.assertEqual(organization.name, school.name)
        self.assertEqual(organization.organization_identifier, school.code)
        self.assertEqual(profile.organization_type, OrganizationType.SCHOOL)
        self.assertEqual(profile.country, "Azerbaijan")
        self.assertEqual(profile.role, ProfileRole.ORG_ADMIN)
        self.assertTrue(Membership.objects.filter(user=user, organization=organization, is_primary=True).exists())

    def test_not_listed_institution_is_saved_for_course_center(self):
        response = self.client.post(
            self.register_url,
            self._register_payload(
                username="centeradmin",
                email="centeradmin@example.com",
                organization_type=OrganizationType.COURSE_CENTER,
                institution="",
                institution_not_listed_name="My New Center",
                organization_identifier="",
                organization_license_identifier="TAX-991",
                initial_role=ProfileRole.ORG_ADMIN,
            ),
        )
        self.assertRedirects(response, self.login_url)
        profile = User.objects.get(username="centeradmin").profile
        self.assertIsNotNone(profile.organization)
        self.assertEqual(profile.organization.name, "My New Center")
        self.assertEqual(profile.organization.license_identifier, "TAX-991")

    def test_student_role_rejected_at_signup(self):
        response = self.client.post(
            self.register_url,
            self._register_payload(
                initial_role=ProfileRole.STUDENT,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_school_signup_rejects_university_institution(self):
        university = self._institution(OrganizationType.UNIVERSITY)
        response = self.client.post(
            self.register_url,
            self._register_payload(
                organization_type=OrganizationType.SCHOOL,
                institution=str(university.id),
                initial_role=ProfileRole.ORG_ADMIN,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")

    def test_school_signup_requires_identifier_when_institution_has_no_code(self):
        school = Institution.objects.create(
            country=self.az,
            institution_type=OrganizationType.SCHOOL,
            name="School No Code",
            code="",
            is_active=True,
        )
        response = self.client.post(
            self.register_url,
            self._register_payload(
                organization_type=OrganizationType.SCHOOL,
                institution=str(school.id),
                organization_identifier="",
                initial_role=ProfileRole.ORG_ADMIN,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "School/University üçün rəsmi identifikator")


class ProfileAndSuspensionFlowTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_student_references_editable_from_profile(self):
        user = User.objects.create_user(
            username="studentprofile",
            email="studentprofile@example.com",
            password="StrongPass123!",
            first_name="Stu",
            last_name="Dent",
        )
        org = Organization.objects.create(
            name="Student Org",
            org_type=OrganizationType.INDIVIDUAL,
            owner=user,
            status="active",
            is_active=True,
        )
        profile = user.profile
        profile.organization = org
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.role = ProfileRole.STUDENT
        profile.save()

        self.client.login(username="studentprofile", password="StrongPass123!")
        response = self.client.post(
            reverse("accounts:profile") + "?section=edit-profile",
            {
                "first_name": "Stu",
                "last_name": "Dent",
                "email": "studentprofile@example.com",
                "phone": "",
                "location": "",
                "bio": "",
                "student_university_name": "ADA University",
                "student_school_identifier": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil uğurla yeniləndi")

        profile.refresh_from_db()
        self.assertEqual(profile.student_university_name, "ADA University")

    def test_login_blocked_for_suspended_organization(self):
        user = User.objects.create_user(
            username="suspendeduser",
            email="suspended@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        org = Organization.objects.create(
            name="Suspended Org",
            org_type=OrganizationType.SCHOOL,
            owner=user,
            status="suspended",
            is_active=False,
        )
        profile = user.profile
        profile.organization = org
        profile.organization_type = OrganizationType.SCHOOL
        profile.role = ProfileRole.MEMBER
        profile.save()

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "suspendeduser", "password": "StrongPass123!"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təşkilatınız dayandırılıb")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_superadmin_can_suspend_and_unsuspend_organizations(self):
        superadmin = User.objects.create_superuser(
            username="superadmin",
            email="superadmin@example.com",
            password="StrongPass123!",
        )
        org_owner = User.objects.create_user(
            username="owner1",
            email="owner1@example.com",
            password="StrongPass123!",
        )
        organization = Organization.objects.create(
            name="Managed Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=org_owner,
            status="active",
            is_active=True,
        )

        self.client.force_login(superadmin)

        response = self.client.post(
            reverse("accounts:superadmin_organizations"),
            {
                "organization_id": str(organization.id),
                "action": "suspend",
                "reason": "Policy violation",
            },
        )
        self.assertRedirects(response, reverse("accounts:superadmin_organizations"))
        organization.refresh_from_db()
        self.assertEqual(organization.status, "suspended")
        self.assertFalse(organization.is_active)
        self.assertEqual(organization.suspension_reason, "Policy violation")

        response = self.client.post(
            reverse("accounts:superadmin_organizations"),
            {
                "organization_id": str(organization.id),
                "action": "unsuspend",
            },
        )
        self.assertRedirects(response, reverse("accounts:superadmin_organizations"))
        organization.refresh_from_db()
        self.assertEqual(organization.status, "active")
        self.assertTrue(organization.is_active)


class RoleAndPermissionTenantIsolationTest(TestCase):
    def setUp(self):
        self.client = Client()

        self.admin_user = User.objects.create_user(
            username="orgadmin",
            email="orgadmin@example.com",
            password="StrongPass123!",
        )
        self.target_user = User.objects.create_user(
            username="target1",
            email="target1@example.com",
            password="StrongPass123!",
        )
        self.external_user = User.objects.create_user(
            username="external1",
            email="external1@example.com",
            password="StrongPass123!",
        )
        self.unassigned_user = User.objects.create_user(
            username="freeuser",
            email="freeuser@example.com",
            password="StrongPass123!",
        )

        self.org_a = Organization.objects.create(
            name="Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.admin_user,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="Org B",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.external_user,
            status="active",
            is_active=True,
        )

        self.org_a_admin_role = self.org_a.roles.order_by("-level").first()
        self.org_a_teacher_role = self.org_a.roles.get(name="teacher")
        self.org_a_member_role = self.org_a.roles.get(name="member")
        self.org_a_student_role = self.org_a.roles.get(name="student")
        self.org_b_student_role = self.org_b.roles.get(name="student")

        self.target_membership = Membership.objects.create(
            user=self.target_user,
            organization=self.org_a,
            role=self.org_a_member_role,
            is_primary=True,
            is_active=True,
        )
        self.external_membership = Membership.objects.create(
            user=self.external_user,
            organization=self.org_b,
            role=self.org_b_student_role,
            is_primary=True,
            is_active=True,
        )
        Membership.objects.create(
            user=self.admin_user,
            organization=self.org_a,
            role=self.org_a_admin_role,
            is_primary=True,
            is_active=True,
        )

        admin_profile = self.admin_user.profile
        admin_profile.organization = self.org_a
        admin_profile.organization_type = self.org_a.org_type
        admin_profile.role = ProfileRole.ORG_ADMIN
        admin_profile.save()

        target_profile = self.target_user.profile
        target_profile.organization = self.org_a
        target_profile.organization_type = self.org_a.org_type
        target_profile.role = ProfileRole.MEMBER
        target_profile.save()

        external_profile = self.external_user.profile
        external_profile.organization = self.org_b
        external_profile.organization_type = self.org_b.org_type
        external_profile.role = ProfileRole.STUDENT
        external_profile.save()

        free_profile = self.unassigned_user.profile
        free_profile.organization = None
        free_profile.organization_type = OrganizationType.INDIVIDUAL
        free_profile.role = ProfileRole.MEMBER
        free_profile.save()

        self.client.force_login(self.admin_user)

    def test_org_admin_can_assign_roles_only_inside_own_tenant(self):
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.target_membership.id),
                "role_id": str(self.org_a_teacher_role.id),
            },
        )
        self.assertRedirects(response, reverse("accounts:role_assignment"))
        self.target_membership.refresh_from_db()
        self.assertEqual(self.target_membership.role, self.org_a_teacher_role)

        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.external_membership.id),
                "role_id": str(self.org_a_teacher_role.id),
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_role_assignment_page_shows_only_same_tenant_users(self):
        response = self.client.get(reverse("accounts:role_assignment"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.target_user.username)
        self.assertNotContains(response, self.external_user.username)

    def test_teacher_can_attach_unassigned_user_and_assign_student_role(self):
        teacher_user = User.objects.create_user(
            username="teacher1",
            email="teacher1@example.com",
            password="StrongPass123!",
        )
        Membership.objects.create(
            user=teacher_user,
            organization=self.org_a,
            role=self.org_a_teacher_role,
            is_primary=True,
            is_active=True,
        )
        teacher_profile = teacher_user.profile
        teacher_profile.organization = self.org_a
        teacher_profile.organization_type = self.org_a.org_type
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.save()

        self.client.force_login(teacher_user)
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "attach_user",
                "user_id": str(self.unassigned_user.id),
                "role_id": str(self.org_a_student_role.id),
            },
        )
        self.assertRedirects(response, reverse("accounts:role_assignment"))

        self.assertTrue(
            Membership.objects.filter(
                user=self.unassigned_user,
                organization=self.org_a,
                role=self.org_a_student_role,
                is_primary=True,
                is_active=True,
            ).exists()
        )
        self.unassigned_user.profile.refresh_from_db()
        self.assertEqual(self.unassigned_user.profile.organization, self.org_a)
        self.assertEqual(self.unassigned_user.profile.role, ProfileRole.STUDENT)

    def test_permission_editor_rejects_grant_when_actor_lacks_permission(self):
        constrained_admin = User.objects.create_user(
            username="limitedadmin",
            email="limitedadmin@example.com",
            password="StrongPass123!",
        )
        role_manager = Role.objects.create(
            organization=self.org_a,
            name="ops_manager",
            display_name="Ops Manager",
            level=85,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["role.assign", "exam.view"],
            is_active=True,
        )
        role_target = Role.objects.create(
            organization=self.org_a,
            name="ops_staff",
            display_name="Ops Staff",
            level=30,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=[],
            is_active=True,
        )
        Membership.objects.create(
            user=constrained_admin,
            organization=self.org_a,
            role=role_manager,
            is_primary=True,
            is_active=True,
        )
        constrained_profile = constrained_admin.profile
        constrained_profile.organization = self.org_a
        constrained_profile.organization_type = self.org_a.org_type
        constrained_profile.role = ProfileRole.ORG_ADMIN
        constrained_profile.save()

        self.client.force_login(constrained_admin)
        response = self.client.post(
            reverse("accounts:permission_editor"),
            {
                "role_id": str(role_target.id),
                "permission": "member.invite",
                "action": "add",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yalnız özünüzdə olan və ya grant edilə bilən permission-ları verə bilərsiniz")
        role_target.refresh_from_db()
        self.assertNotIn("member.invite", role_target.permissions)

    def test_permission_editor_allows_grant_via_grant_prefix(self):
        constrained_admin = User.objects.create_user(
            username="grantadmin",
            email="grantadmin@example.com",
            password="StrongPass123!",
        )
        role_manager = Role.objects.create(
            organization=self.org_a,
            name="grant_manager",
            display_name="Grant Manager",
            level=85,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["role.assign", "grant:member.invite"],
            is_active=True,
        )
        role_target = Role.objects.create(
            organization=self.org_a,
            name="grant_staff",
            display_name="Grant Staff",
            level=30,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=[],
            is_active=True,
        )
        Membership.objects.create(
            user=constrained_admin,
            organization=self.org_a,
            role=role_manager,
            is_primary=True,
            is_active=True,
        )
        constrained_profile = constrained_admin.profile
        constrained_profile.organization = self.org_a
        constrained_profile.organization_type = self.org_a.org_type
        constrained_profile.role = ProfileRole.ORG_ADMIN
        constrained_profile.save()

        self.client.force_login(constrained_admin)
        response = self.client.post(
            reverse("accounts:permission_editor"),
            {
                "role_id": str(role_target.id),
                "permission": "member.invite",
                "action": "add",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        role_target.refresh_from_db()
        self.assertIn("member.invite", role_target.permissions)

        response = self.client.post(
            reverse("accounts:permission_editor"),
            {
                "role_id": str(role_target.id),
                "permission": "member.invite",
                "action": "remove",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        role_target.refresh_from_db()
        self.assertNotIn("member.invite", role_target.permissions)

    def test_permission_editor_is_tenant_scoped(self):
        role_b = Role.objects.create(
            organization=self.org_b,
            name="b_private_role",
            display_name="B Private Role",
            level=30,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=[],
            is_active=True,
        )
        response = self.client.get(reverse("accounts:permission_editor"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, role_b.display_name)

        response = self.client.post(
            reverse("accounts:permission_editor"),
            {
                "role_id": str(role_b.id),
                "permission": "member.view",
                "action": "add",
            },
        )
        self.assertEqual(response.status_code, 404)
