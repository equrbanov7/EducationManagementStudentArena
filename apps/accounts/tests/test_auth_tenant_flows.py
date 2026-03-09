"""
Integration tests for auth + tenant-scoped role/permission flows.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.blog.models import EmailOTP
from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from apps.organizations.models import Country, Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


class SignupAndLoginFlowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse("accounts:register")
        self.login_url = reverse("accounts:login")
        self.verify_code_url = reverse("accounts:verify_code")
        self.az = Country.objects.get(code="AZ")

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
            "join_organization": "",
            "institution": "",
            "institution_not_listed_name": "",
            "organization_identifier": "",
            "organization_license_identifier": "",
            "initial_role": ProfileRole.MEMBER,
        }
        payload.update(overrides)
        return payload

    def _verify_latest_otp(self, user):
        otp = EmailOTP.objects.filter(user=user, is_used=False).order_by("-created_at").first()
        self.assertIsNotNone(otp)
        response = self.client.post(self.verify_code_url, {"code": otp.code})
        self.assertRedirects(response, self.login_url)
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    def test_signup_user_can_login_immediately_with_username_or_email(self):
        response = self.client.post(self.register_url, self._register_payload())
        self.assertRedirects(response, self.verify_code_url)

        user = User.objects.get(username="newuser")
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertTrue(EmailOTP.objects.filter(user=user, is_used=False).exists())
        self.assertEqual(self.client.session.get("pending_verify_email"), "newuser@example.com")

        # Username login should be blocked until verification.
        self.assertFalse(self.client.login(username="newuser", password="StrongPass123!"))
        self.client.logout()

        # Email login (custom backend) should also be blocked.
        self.assertFalse(self.client.login(username="newuser@example.com", password="StrongPass123!"))

        profile = user.profile
        self.assertEqual(profile.role, ProfileRole.ORG_ADMIN)
        self.assertIsNotNone(profile.organization)
        self.assertEqual(profile.organization.org_type, OrganizationType.INDIVIDUAL)
        self.assertEqual(profile.requested_organization, profile.organization)
        self.assertEqual(profile.requested_organization_name, profile.organization.name)
        self.assertEqual(profile.organization_type, OrganizationType.INDIVIDUAL)
        self.assertTrue(
            Membership.objects.filter(user=user, organization=profile.organization, is_primary=True).exists()
        )

    def test_individual_signup_creates_workspace_without_organization_selection(self):
        response = self.client.post(self.register_url, self._register_payload(join_organization=""))
        self.assertRedirects(response, self.verify_code_url)
        user = User.objects.get(username="newuser")
        self.assertEqual(user.profile.organization.org_type, OrganizationType.INDIVIDUAL)
        self.assertEqual(user.profile.role, ProfileRole.ORG_ADMIN)

    def test_signup_form_does_not_offer_student_role(self):
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'value="student"')

    def test_school_signup_creates_organization_from_manual_name(self):
        response = self.client.post(
            self.register_url,
            self._register_payload(
                username="schooladmin",
                email="schooladmin@example.com",
                organization_type=OrganizationType.SCHOOL,
                institution_not_listed_name="Baku School 500",
                organization_identifier="",
                initial_role=ProfileRole.TEACHER,
            ),
        )
        self.assertRedirects(response, self.verify_code_url)

        user = User.objects.get(username="schooladmin")
        profile = user.profile
        self.assertIsNotNone(profile.organization)
        self.assertEqual(profile.organization.name, "Baku School 500")
        self.assertEqual(profile.organization.organization_identifier, "")
        self.assertEqual(profile.requested_organization, profile.organization)
        self.assertEqual(profile.requested_organization_name, profile.organization.name)
        self.assertEqual(profile.organization_type, OrganizationType.SCHOOL)
        self.assertEqual(profile.country, "Azerbaijan")
        self.assertEqual(profile.role, ProfileRole.ORG_ADMIN)
        self.assertTrue(Membership.objects.filter(user=user, organization=profile.organization, is_primary=True).exists())

    def test_course_center_signup_uses_manual_name(self):
        response = self.client.post(
            self.register_url,
            self._register_payload(
                username="centeradmin",
                email="centeradmin@example.com",
                organization_type=OrganizationType.COURSE_CENTER,
                institution_not_listed_name="My New Center",
                organization_identifier="",
                organization_license_identifier="TAX-991",
                initial_role=ProfileRole.HR,
            ),
        )
        self.assertRedirects(response, self.verify_code_url)
        profile = User.objects.get(username="centeradmin").profile
        self.assertIsNotNone(profile.organization)
        self.assertEqual(profile.organization.name, "My New Center")
        self.assertEqual(profile.organization.license_identifier, "TAX-991")
        self.assertEqual(profile.requested_organization_name, "My New Center")
        self.assertEqual(profile.role, ProfileRole.ORG_ADMIN)

    def test_org_creator_signup_ignores_manual_initial_role_input(self):
        response = self.client.post(
            self.register_url,
            self._register_payload(
                organization_type=OrganizationType.SCHOOL,
                institution_not_listed_name="Role Override School",
                initial_role=ProfileRole.HR,
            ),
        )
        self.assertRedirects(response, self.verify_code_url)
        profile = User.objects.get(username="newuser").profile
        self.assertEqual(profile.role, ProfileRole.ORG_ADMIN)

    def test_university_signup_requires_identifier(self):
        response = self.client.post(
            self.register_url,
            self._register_payload(
                organization_type=OrganizationType.UNIVERSITY,
                institution_not_listed_name="No Identifier Uni",
                organization_identifier="",
                initial_role=ProfileRole.HR,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Universitet üçün rəsmi identifikator")

    def test_student_join_without_organization_selection_is_allowed(self):
        response = self.client.post(
            self.register_url,
            self._register_payload(
                organization_type="school_student",
                join_organization="",
            ),
        )
        self.assertRedirects(response, self.verify_code_url)
        user = User.objects.get(username="newuser")
        self.assertEqual(user.profile.role, ProfileRole.STUDENT)
        self.assertIsNone(user.profile.organization)
        self.assertIsNone(user.profile.requested_organization)
        self.assertEqual(user.profile.requested_organization_name, "")

    def test_student_join_rejects_suspended_organization(self):
        owner = User.objects.create_user(
            username="suspended_owner",
            email="suspended_owner@example.com",
            password="StrongPass123!",
        )
        suspended_org = Organization.objects.create(
            name="Suspended School",
            org_type=OrganizationType.SCHOOL,
            country="Azerbaijan",
            owner=owner,
            status="suspended",
            is_active=False,
        )

        response = self.client.post(
            self.register_url,
            self._register_payload(
                organization_type="school_student",
                join_organization=str(suspended_org.id),
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Seçilən təşkilat aktiv deyil və ya dayandırılıb.")

    def test_student_join_rejects_type_mismatch(self):
        owner = User.objects.create_user(
            username="uni_owner",
            email="uni_owner@example.com",
            password="StrongPass123!",
        )
        university_org = Organization.objects.create(
            name="Mismatch University",
            org_type=OrganizationType.UNIVERSITY,
            country="Azerbaijan",
            owner=owner,
            status="active",
            is_active=True,
        )

        response = self.client.post(
            self.register_url,
            self._register_payload(
                organization_type="school_student",
                join_organization=str(university_org.id),
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Seçilən təşkilat qeydiyyat növünə uyğun deyil.")

    def test_student_join_stays_pending_after_email_verification(self):
        owner = User.objects.create_user(
            username="school_owner",
            email="school_owner@example.com",
            password="StrongPass123!",
        )
        school_org = Organization.objects.create(
            name="Joinable School",
            org_type=OrganizationType.SCHOOL,
            country="Azerbaijan",
            owner=owner,
            status="active",
            is_active=True,
        )

        response = self.client.post(
            self.register_url,
            self._register_payload(
                username="school_student_user",
                email="school_student_user@example.com",
                organization_type="school_student",
                join_organization=str(school_org.id),
            ),
        )
        self.assertRedirects(response, self.verify_code_url)

        user = User.objects.get(username="school_student_user")
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.role, ProfileRole.STUDENT)
        self.assertIsNone(user.profile.organization)
        self.assertEqual(user.profile.requested_organization, school_org)
        self.assertFalse(Membership.objects.filter(user=user, organization=school_org, is_active=True).exists())

        self._verify_latest_otp(user)

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.profile.role, ProfileRole.STUDENT)
        self.assertIsNone(user.profile.organization)
        self.assertEqual(user.profile.requested_organization, school_org)
        self.assertFalse(Membership.objects.filter(user=user, organization=school_org, is_active=True).exists())

        self.assertTrue(self.client.login(username="school_student_user", password="StrongPass123!"))
        response = self.client.get(reverse("accounts:profile") + "?section=profile-info")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təşkilat təsdiqi gözlənilir")


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
                "profile_form": "edit-profile",
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
        self.unassigned_other = User.objects.create_user(
            username="freeuser_other",
            email="freeuser_other@example.com",
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
        self.admin_membership = Membership.objects.create(
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
        free_profile.requested_organization = self.org_a
        free_profile.requested_organization_name = self.org_a.name
        free_profile.save()

        free_other_profile = self.unassigned_other.profile
        free_other_profile.organization = None
        free_other_profile.organization_type = OrganizationType.INDIVIDUAL
        free_other_profile.role = ProfileRole.MEMBER
        free_other_profile.requested_organization = self.org_b
        free_other_profile.requested_organization_name = self.org_b.name
        free_other_profile.save()

        self._activate_org_session(self.admin_user, self.org_a)

    def _activate_org_session(self, user, organization):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = organization.slug
        session.save()

    def test_org_admin_can_assign_roles_only_inside_own_tenant(self):
        fallback_next = f"{reverse('accounts:profile')}?section=role-assignment"
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.target_membership.id),
                "role_id": str(self.org_a_teacher_role.id),
            },
        )
        self.assertRedirects(response, fallback_next)
        self.target_membership.refresh_from_db()
        self.assertEqual(self.target_membership.role, self.org_a_teacher_role)
        success_entry = AuditLog.objects.filter(
            user=self.admin_user,
            organization=self.org_a,
            resource_type="membership",
            resource_id=str(self.target_membership.id),
            new_values__status="success",
            new_values__action_type="update_member",
        ).first()
        self.assertIsNotNone(success_entry)
        self.assertEqual(success_entry.new_values.get("actor_user_id"), str(self.admin_user.id))
        self.assertEqual(success_entry.new_values.get("org_id"), str(self.org_a.id))
        self.assertEqual(success_entry.new_values.get("target_user_id"), str(self.target_user.id))
        self.assertEqual(success_entry.new_values.get("membership_id"), str(self.target_membership.id))
        self.assertEqual(success_entry.new_values.get("old_role_id"), str(self.org_a_member_role.id))
        self.assertEqual(success_entry.new_values.get("new_role_id"), str(self.org_a_teacher_role.id))

        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.external_membership.id),
                "role_id": str(self.org_a_teacher_role.id),
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_role_assignment_post_respects_next_url(self):
        next_url = f"{reverse('accounts:profile')}?section=role-assignment&q={self.target_user.username}"
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.target_membership.id),
                "role_id": str(self.org_a_teacher_role.id),
                "next": next_url,
            },
        )
        self.assertRedirects(response, next_url)
        self.target_membership.refresh_from_db()
        self.assertEqual(self.target_membership.role, self.org_a_teacher_role)

    def test_role_assignment_prepare_operation_returns_operation_token(self):
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "prepare_operation",
                "target_action": "update_member",
                "membership_id": str(self.target_membership.id),
                "new_role_id": str(self.org_a_teacher_role.id),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("success"))
        self.assertTrue(payload.get("operation_token"))
        self.assertEqual(payload.get("action"), "update_member")

    def test_role_assignment_rejects_mismatched_operation_token(self):
        prepare_response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "prepare_operation",
                "target_action": "update_member",
                "membership_id": str(self.target_membership.id),
                "new_role_id": str(self.org_a_teacher_role.id),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(prepare_response.status_code, 200)
        operation_token = prepare_response.json().get("operation_token")
        self.assertTrue(operation_token)

        submit_response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.target_membership.id),
                "role_id": str(self.org_a_student_role.id),
                "operation_token": operation_token,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(submit_response.status_code, 403)
        submit_payload = submit_response.json()
        self.assertFalse(submit_payload.get("success"))
        self.assertEqual(submit_payload.get("reason_code"), "operation_token_mismatch")

        self.target_membership.refresh_from_db()
        self.assertEqual(self.target_membership.role, self.org_a_member_role)

    def test_role_assignment_denied_attempt_writes_audit_event(self):
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.external_membership.id),
                "role_id": str(self.org_a_teacher_role.id),
            },
        )
        self.assertEqual(response.status_code, 403)
        denied_entry = AuditLog.objects.filter(
            user=self.admin_user,
            organization=self.org_a,
            resource_type="membership",
            resource_id=str(self.external_membership.id),
            new_values__reason_code="membership_outside_active_organization",
        ).first()
        self.assertIsNotNone(denied_entry)
        self.assertEqual(denied_entry.new_values.get("status"), "denied")
        self.assertEqual(denied_entry.new_values.get("action_type"), "update_member")
        self.assertEqual(denied_entry.new_values.get("actor_user_id"), str(self.admin_user.id))
        self.assertEqual(denied_entry.new_values.get("org_id"), str(self.org_a.id))
        self.assertEqual(denied_entry.new_values.get("new_role_id"), str(self.org_a_teacher_role.id))

    def test_role_assignment_denies_self_role_update(self):
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.admin_membership.id),
                "role_id": str(self.org_a_teacher_role.id),
            },
        )
        self.assertEqual(response.status_code, 403)
        self.admin_membership.refresh_from_db()
        self.assertEqual(self.admin_membership.role, self.org_a_admin_role)

    def test_role_assignment_denies_assigning_role_at_or_above_actor_level(self):
        high_actor = User.objects.create_user(
            username="vice_actor",
            email="vice_actor@example.com",
            password="StrongPass123!",
        )
        vice_role = Role.objects.create(
            organization=self.org_a,
            name="vice_secure_actor",
            display_name="Vice Secure Actor",
            level=90,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["role.assign", "org.manage_members"],
            is_active=True,
        )
        Membership.objects.create(
            user=high_actor,
            organization=self.org_a,
            role=vice_role,
            is_primary=True,
            is_active=True,
        )
        high_actor_profile = high_actor.profile
        high_actor_profile.organization = self.org_a
        high_actor_profile.organization_type = self.org_a.org_type
        high_actor_profile.role = ProfileRole.ORG_ADMIN
        high_actor_profile.save()

        self._activate_org_session(high_actor, self.org_a)
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.target_membership.id),
                "role_id": str(vice_role.id),
            },
        )
        self.assertEqual(response.status_code, 403)
        self.target_membership.refresh_from_db()
        self.assertEqual(self.target_membership.role, self.org_a_member_role)

    def test_role_assignment_denies_updating_user_with_higher_or_equal_level(self):
        higher_target = User.objects.create_user(
            username="higher_target",
            email="higher_target@example.com",
            password="StrongPass123!",
        )
        top_role = Role.objects.create(
            organization=self.org_a,
            name="top_secure_role",
            display_name="Top Secure Role",
            level=95,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["org.manage_members"],
            is_active=True,
        )
        higher_membership = Membership.objects.create(
            user=higher_target,
            organization=self.org_a,
            role=top_role,
            is_primary=True,
            is_active=True,
        )

        actor = User.objects.create_user(
            username="mid_actor",
            email="mid_actor@example.com",
            password="StrongPass123!",
        )
        actor_role = Role.objects.create(
            organization=self.org_a,
            name="mid_secure_actor",
            display_name="Mid Secure Actor",
            level=90,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["role.assign", "org.manage_members"],
            is_active=True,
        )
        Membership.objects.create(
            user=actor,
            organization=self.org_a,
            role=actor_role,
            is_primary=True,
            is_active=True,
        )
        actor_profile = actor.profile
        actor_profile.organization = self.org_a
        actor_profile.organization_type = self.org_a.org_type
        actor_profile.role = ProfileRole.ORG_ADMIN
        actor_profile.save()

        self._activate_org_session(actor, self.org_a)
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(higher_membership.id),
                "role_id": str(self.org_a_member_role.id),
            },
        )
        self.assertEqual(response.status_code, 403)
        higher_membership.refresh_from_db()
        self.assertEqual(higher_membership.role, top_role)

    def test_role_assignment_blocks_demoting_last_owner(self):
        superadmin = User.objects.create_superuser(
            username="owner_guard_super",
            email="owner_guard_super@example.com",
            password="StrongPass123!",
        )
        super_profile = superadmin.profile
        super_profile.organization = self.org_a
        super_profile.organization_type = self.org_a.org_type
        super_profile.role = ProfileRole.SUPERADMIN
        super_profile.save()

        self._activate_org_session(superadmin, self.org_a)

        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "update_member",
                "membership_id": str(self.admin_membership.id),
                "role_id": str(self.org_a_member_role.id),
            },
        )
        self.assertEqual(response.status_code, 409)
        self.admin_membership.refresh_from_db()
        self.assertEqual(self.admin_membership.role, self.org_a_admin_role)

    def test_role_assignment_page_shows_only_same_tenant_users(self):
        standalone_response = self.client.get(reverse("accounts:role_assignment"))
        expected_profile_url = f"{reverse('accounts:profile')}?section=role-assignment"
        self.assertRedirects(standalone_response, expected_profile_url)

        response = self.client.get(expected_profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.target_user.username)
        self.assertNotContains(response, self.external_user.username)
        self.assertContains(response, self.unassigned_user.username)
        self.assertNotContains(response, self.unassigned_other.username)
        self.assertContains(response, "Rolu yenilə")
        self.assertContains(response, "Təşkilata əlavə et")
        self.assertContains(response, "js-role-assignment-action-confirm")
        self.assertContains(response, "roleAssignmentActionConfirmModal")
        self.assertContains(response, "Dəyişəcək rol")
        self.assertContains(response, "Təşkilat")

    def test_org_admin_can_bulk_approve_pending_students(self):
        free_profile = self.unassigned_user.profile
        free_profile.organization = None
        free_profile.organization_type = OrganizationType.INDIVIDUAL
        free_profile.role = ProfileRole.STUDENT
        free_profile.requested_organization = self.org_a
        free_profile.requested_organization_name = self.org_a.name
        free_profile.save()

        response = self.client.get(reverse("accounts:student_organization_management"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.unassigned_user.username)
        self.assertContains(response, "Təşkilatdan uzaqlaşdır")
        self.assertContains(response, "Təşkilata əlavə et")
        self.assertContains(response, "Dəvət et")
        self.assertContains(response, "removeStudentConfirmModal")
        self.assertContains(response, "pendingAddConfirmModal")
        self.assertContains(response, "inviteConfirmModal")
        self.assertContains(response, "Dəyişəcək rol")
        self.assertContains(response, "Təşkilat")

        response = self.client.post(
            reverse("accounts:student_organization_management"),
            {
                "action": "bulk_approve_requested_students",
                "selected_pending_user_ids": [str(self.unassigned_user.id)],
                "next": reverse("accounts:student_organization_management"),
            },
            follow=True,
        )
        self.assertRedirects(response, reverse("accounts:student_organization_management"))
        self.assertContains(response, "Uğurla əlavə edildi: 1 tələbə əlavə edildi.")
        pending_user_ids = {item.user_id for item in response.context["pending_requested_students"].object_list}
        self.assertNotIn(self.unassigned_user.id, pending_user_ids)

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

    def test_pending_students_empty_state_outside_table_and_bulk_disabled(self):
        self.unassigned_user.profile.requested_organization = None
        self.unassigned_user.profile.requested_organization_name = ""
        self.unassigned_user.profile.save(update_fields=["requested_organization", "requested_organization_name", "updated_at"])

        StudentOrganizationRequest.objects.filter(
            user=self.unassigned_user,
            organization=self.org_a,
        ).delete()

        response = self.client.get(reverse("accounts:student_organization_management"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təsdiq gözləyən tələbə yoxdur.")
        self.assertNotContains(response, '<td colspan="8" class="text-center">Təsdiq gözləyən tələbə yoxdur.</td>')
        self.assertContains(response, "js-pending-add-bulk-label")
        self.assertContains(response, "data-selected-label=\"Seçilənləri təşkilata əlavə et ({count} seçildi)\"")
        self.assertContains(response, "data-disabled-tooltip=\"Ən az 1 tələbə seçin\"")
        self.assertContains(response, "id=\"selectAllPendingStudents\"")

    def test_org_admin_can_reject_pending_student_request(self):
        free_profile = self.unassigned_user.profile
        free_profile.organization = None
        free_profile.organization_type = OrganizationType.INDIVIDUAL
        free_profile.role = ProfileRole.STUDENT
        free_profile.requested_organization = self.org_a
        free_profile.requested_organization_name = self.org_a.name
        free_profile.requested_organization_message = "Müraciət test mesajı"
        free_profile.save()

        response = self.client.post(
            reverse("accounts:student_organization_management"),
            {
                "action": "bulk_approve_requested_students",
                "reject_user_id": str(self.unassigned_user.id),
                "next": reverse("accounts:student_organization_management"),
            },
        )
        self.assertRedirects(response, reverse("accounts:student_organization_management"))

        free_profile.refresh_from_db()
        self.assertIsNone(free_profile.requested_organization)
        self.assertEqual(free_profile.requested_organization_name, "")
        self.assertEqual(free_profile.requested_organization_message, "")
        self.assertFalse(
            Membership.objects.filter(
                user=self.unassigned_user,
                organization=self.org_a,
                is_active=True,
            ).exists()
        )

    def test_removed_student_does_not_return_to_pending_requests(self):
        free_profile = self.unassigned_user.profile
        free_profile.organization = None
        free_profile.organization_type = OrganizationType.INDIVIDUAL
        free_profile.role = ProfileRole.STUDENT
        free_profile.requested_organization = self.org_a
        free_profile.requested_organization_name = self.org_a.name
        free_profile.save()

        response = self.client.post(
            reverse("accounts:student_organization_management"),
            {
                "action": "bulk_approve_requested_students",
                "selected_pending_user_ids": [str(self.unassigned_user.id)],
                "next": reverse("accounts:student_organization_management"),
            },
        )
        self.assertRedirects(response, reverse("accounts:student_organization_management"))
        self.assertTrue(
            Membership.objects.filter(
                user=self.unassigned_user,
                organization=self.org_a,
                is_active=True,
                role=self.org_a_student_role,
            ).exists()
        )

        response = self.client.post(
            reverse("accounts:student_organization_management"),
            {
                "action": "remove_student",
                "user_id": str(self.unassigned_user.id),
                "remove_reason": "Sınaq uzaqlaşdırma",
                "next": reverse("accounts:student_organization_management"),
            },
        )
        self.assertRedirects(response, reverse("accounts:student_organization_management"))

        free_profile.refresh_from_db()
        self.assertIsNone(free_profile.organization)
        self.assertIsNone(free_profile.requested_organization)
        self.assertEqual(free_profile.requested_organization_name, "")
        self.assertEqual(free_profile.requested_organization_message, "")
        self.assertFalse(
            Membership.objects.filter(
                user=self.unassigned_user,
                organization=self.org_a,
                is_active=True,
            ).exists()
        )

        response = self.client.get(reverse("accounts:student_organization_management"))
        self.assertEqual(response.status_code, 200)
        pending_user_ids = {item.user_id for item in response.context["pending_requested_students"].object_list}
        self.assertNotIn(self.unassigned_user.id, pending_user_ids)

    def test_org_admin_can_bulk_invite_unassigned_students(self):
        invite_candidate_1 = User.objects.create_user(
            username="bulk_invite_student_1",
            email="bulk_invite_student_1@example.com",
            password="StrongPass123!",
        )
        invite_candidate_2 = User.objects.create_user(
            username="bulk_invite_student_2",
            email="bulk_invite_student_2@example.com",
            password="StrongPass123!",
        )
        for user in [invite_candidate_1, invite_candidate_2]:
            profile = user.profile
            profile.organization = None
            profile.organization_type = OrganizationType.INDIVIDUAL
            profile.role = ProfileRole.STUDENT
            profile.requested_organization = None
            profile.requested_organization_name = ""
            profile.requested_organization_message = ""
            profile.save()

        response = self.client.post(
            reverse("accounts:student_organization_management"),
            {
                "action": "bulk_invite_students",
                "selected_unassigned_user_ids": [str(invite_candidate_1.id), str(invite_candidate_2.id)],
                "next": reverse("accounts:student_organization_management"),
            },
        )
        self.assertRedirects(response, reverse("accounts:student_organization_management"))
        self.assertEqual(
            Membership.objects.filter(
                organization=self.org_a,
                is_active=False,
                title="__student_pending_invite__",
                user__in=[invite_candidate_1, invite_candidate_2],
            ).count(),
            2,
        )

    def test_org_admin_can_revoke_sent_invites_in_bulk(self):
        revoke_candidate_1 = User.objects.create_user(
            username="bulk_revoke_student_1",
            email="bulk_revoke_student_1@example.com",
            password="StrongPass123!",
        )
        revoke_candidate_2 = User.objects.create_user(
            username="bulk_revoke_student_2",
            email="bulk_revoke_student_2@example.com",
            password="StrongPass123!",
        )

        for user in [revoke_candidate_1, revoke_candidate_2]:
            profile = user.profile
            profile.organization = None
            profile.organization_type = OrganizationType.INDIVIDUAL
            profile.role = ProfileRole.STUDENT
            profile.requested_organization = self.org_a
            profile.requested_organization_name = self.org_a.name
            profile.requested_organization_message = ""
            profile.save()
            Membership.objects.create(
                user=user,
                organization=self.org_a,
                role=self.org_a_student_role,
                assigned_by=self.admin_user,
                is_primary=False,
                is_active=False,
                title="__student_pending_invite__",
            )

        response = self.client.post(
            reverse("accounts:student_organization_management"),
            {
                "action": "revoke_sent_invites",
                "selected_sent_invite_user_ids": [str(revoke_candidate_1.id), str(revoke_candidate_2.id)],
                "next": reverse("accounts:student_organization_management"),
            },
        )
        self.assertRedirects(response, reverse("accounts:student_organization_management"))
        self.assertFalse(
            Membership.objects.filter(
                organization=self.org_a,
                is_active=False,
                title="__student_pending_invite__",
                user__in=[revoke_candidate_1, revoke_candidate_2],
            ).exists()
        )
        response = self.client.get(reverse("accounts:student_organization_management"))
        self.assertEqual(response.status_code, 200)
        unassigned_ids = {item.user_id for item in response.context["unassigned_students"].object_list}
        pending_request_ids = {item.user_id for item in response.context["pending_requested_students"].object_list}
        sent_invite_ids = {item.user_id for item in response.context["sent_student_invites"].object_list}
        self.assertIn(revoke_candidate_1.id, unassigned_ids)
        self.assertIn(revoke_candidate_2.id, unassigned_ids)
        self.assertNotIn(revoke_candidate_1.id, pending_request_ids)
        self.assertNotIn(revoke_candidate_2.id, pending_request_ids)
        self.assertNotIn(revoke_candidate_1.id, sent_invite_ids)
        self.assertNotIn(revoke_candidate_2.id, sent_invite_ids)

    def test_unassigned_student_gets_invite_then_can_accept_and_leave_with_reason(self):
        free_profile = self.unassigned_user.profile
        free_profile.organization = None
        free_profile.organization_type = OrganizationType.INDIVIDUAL
        free_profile.role = ProfileRole.STUDENT
        free_profile.requested_organization = None
        free_profile.requested_organization_name = ""
        free_profile.save()

        response = self.client.post(
            reverse("accounts:student_organization_management"),
            {
                "action": "invite_student",
                "user_id": str(self.unassigned_user.id),
                "next": reverse("accounts:student_organization_management"),
            },
        )
        self.assertRedirects(response, reverse("accounts:student_organization_management"))

        invite_membership = Membership.objects.filter(
            user=self.unassigned_user,
            organization=self.org_a,
            is_active=False,
            title="__student_pending_invite__",
        ).first()
        self.assertIsNotNone(invite_membership)
        self.assertFalse(
            Membership.objects.filter(
                user=self.unassigned_user,
                organization=self.org_a,
                is_active=True,
            ).exists()
        )
        self.unassigned_user.profile.refresh_from_db()
        self.assertIsNone(self.unassigned_user.profile.organization)
        self.assertEqual(self.unassigned_user.profile.requested_organization, self.org_a)

        self.client.force_login(self.unassigned_user)
        response = self.client.post(
            reverse("accounts:student_org_invitation_action"),
            {
                "invite_id": str(invite_membership.id),
                "action": "accept",
                "next": reverse("accounts:profile") + "?section=profile-info",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile") + "?section=profile-info")
        self.unassigned_user.profile.refresh_from_db()
        self.assertEqual(self.unassigned_user.profile.organization, self.org_a)
        self.assertTrue(
            Membership.objects.filter(
                user=self.unassigned_user,
                organization=self.org_a,
                is_active=True,
                role__name="student",
            ).exists()
        )

        response = self.client.post(
            reverse("accounts:student_leave_organization"),
            {
                "leave_reason": "Qrafik uyğun gəlmir",
                "next": reverse("accounts:profile") + "?section=profile-info",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile") + "?section=profile-info")
        self.unassigned_user.profile.refresh_from_db()
        self.assertIsNone(self.unassigned_user.profile.organization)
        self.assertFalse(
            Membership.objects.filter(
                user=self.unassigned_user,
                organization=self.org_a,
                is_active=True,
            ).exists()
        )

    def test_student_can_send_join_request_with_message_and_org_admin_sees_it(self):
        student_user = User.objects.create_user(
            username="request_student",
            email="request_student@example.com",
            password="StrongPass123!",
        )
        student_profile = student_user.profile
        student_profile.organization = None
        student_profile.organization_type = OrganizationType.INDIVIDUAL
        student_profile.role = ProfileRole.STUDENT
        student_profile.requested_organization = None
        student_profile.requested_organization_name = ""
        student_profile.requested_organization_message = ""
        student_profile.save()

        self.client.force_login(student_user)
        response = self.client.post(
            reverse("accounts:student_organization_request"),
            {
                "action": "submit_request",
                "organization_id": str(self.org_a.id),
                "request_message": "Mən bu təşkilata qoşulmaq istəyirəm.",
                "next": reverse("accounts:profile") + "?section=student-organization-request",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile") + "?section=student-organization-request")
        student_profile.refresh_from_db()
        self.assertEqual(student_profile.requested_organization, self.org_a)
        self.assertEqual(student_profile.requested_organization_name, self.org_a.name)
        self.assertEqual(student_profile.requested_organization_message, "Mən bu təşkilata qoşulmaq istəyirəm.")

        self._activate_org_session(self.admin_user, self.org_a)
        response = self.client.get(reverse("accounts:student_organization_management"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mən bu təşkilata qoşulmaq istəyirəm.")

    def test_student_join_request_message_has_max_length_limit(self):
        student_user = User.objects.create_user(
            username="request_limit_student",
            email="request_limit_student@example.com",
            password="StrongPass123!",
        )
        student_profile = student_user.profile
        student_profile.organization = None
        student_profile.organization_type = OrganizationType.INDIVIDUAL
        student_profile.role = ProfileRole.STUDENT
        student_profile.save()

        self.client.force_login(student_user)
        response = self.client.post(
            reverse("accounts:student_organization_request"),
            {
                "action": "submit_request",
                "organization_id": str(self.org_a.id),
                "request_message": "x" * 281,
                "next": reverse("accounts:profile") + "?section=student-organization-request",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "maksimum 280 simvol")
        student_profile.refresh_from_db()
        self.assertEqual(student_profile.requested_organization_message, "")

    def test_student_notifications_show_all_pending_join_requests(self):
        student_user = User.objects.create_user(
            username="multi_request_student",
            email="multi_request_student@example.com",
            password="StrongPass123!",
        )
        student_profile = student_user.profile
        student_profile.organization = None
        student_profile.organization_type = OrganizationType.INDIVIDUAL
        student_profile.role = ProfileRole.STUDENT
        student_profile.requested_organization = None
        student_profile.requested_organization_name = ""
        student_profile.requested_organization_message = ""
        student_profile.save()

        self.client.force_login(student_user)
        first_response = self.client.post(
            reverse("accounts:student_organization_request"),
            {
                "action": "submit_request",
                "organization_id": str(self.org_a.id),
                "request_message": "Org A üçün müraciət",
                "next": reverse("accounts:profile") + "?section=student-organization-request",
            },
        )
        self.assertRedirects(first_response, reverse("accounts:profile") + "?section=student-organization-request")

        second_response = self.client.post(
            reverse("accounts:student_organization_request"),
            {
                "action": "submit_request",
                "organization_id": str(self.org_b.id),
                "request_message": "Org B üçün müraciət",
                "next": reverse("accounts:profile") + "?section=student-organization-request",
            },
        )
        self.assertRedirects(second_response, reverse("accounts:profile") + "?section=student-organization-request")

        response = self.client.get(reverse("accounts:profile") + "?section=notifications")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.org_a.name)
        self.assertContains(response, self.org_b.name)
        self.assertContains(response, "Org A üçün müraciət")
        self.assertContains(response, "Org B üçün müraciət")
        self.assertEqual(
            StudentOrganizationRequest.objects.filter(
                user=student_user,
                status=StudentOrganizationRequestStatus.PENDING,
            ).count(),
            2,
        )
        self.assertEqual(response.context["notifications_unread_count"], 2)

    def test_approving_one_org_auto_closes_other_pending_requests(self):
        student_user = User.objects.create_user(
            username="auto_close_student",
            email="auto_close_student@example.com",
            password="StrongPass123!",
        )
        student_profile = student_user.profile
        student_profile.organization = None
        student_profile.organization_type = OrganizationType.INDIVIDUAL
        student_profile.role = ProfileRole.STUDENT
        student_profile.requested_organization = None
        student_profile.requested_organization_name = ""
        student_profile.requested_organization_message = ""
        student_profile.save()

        self.client.force_login(student_user)
        self.client.post(
            reverse("accounts:student_organization_request"),
            {
                "action": "submit_request",
                "organization_id": str(self.org_a.id),
                "request_message": "A müraciət",
                "next": reverse("accounts:profile") + "?section=student-organization-request",
            },
        )
        self.client.post(
            reverse("accounts:student_organization_request"),
            {
                "action": "submit_request",
                "organization_id": str(self.org_b.id),
                "request_message": "B müraciət",
                "next": reverse("accounts:profile") + "?section=student-organization-request",
            },
        )

        self._activate_org_session(self.admin_user, self.org_a)
        approve_response = self.client.post(
            reverse("accounts:student_organization_management"),
            {
                "action": "bulk_approve_requested_students",
                "single_user_id": str(student_user.id),
                "next": reverse("accounts:student_organization_management"),
            },
        )
        self.assertRedirects(approve_response, reverse("accounts:student_organization_management"))

        student_profile.refresh_from_db()
        self.assertEqual(student_profile.organization, self.org_a)

        request_a = StudentOrganizationRequest.objects.filter(
            user=student_user,
            organization=self.org_a,
        ).latest("created_at")
        request_b = StudentOrganizationRequest.objects.filter(
            user=student_user,
            organization=self.org_b,
        ).latest("created_at")
        self.assertEqual(request_a.status, StudentOrganizationRequestStatus.APPROVED)
        self.assertEqual(request_b.status, StudentOrganizationRequestStatus.AUTO_CLOSED)
        self.assertIn(self.org_a.name, request_b.resolution_note)

        org_b_admin = User.objects.create_user(
            username="org_b_admin_viewer",
            email="org_b_admin_viewer@example.com",
            password="StrongPass123!",
        )
        org_b_admin_role = self.org_b.roles.order_by("-level").first()
        Membership.objects.create(
            user=org_b_admin,
            organization=self.org_b,
            role=org_b_admin_role,
            is_primary=True,
            is_active=True,
        )
        org_b_admin_profile = org_b_admin.profile
        org_b_admin_profile.organization = self.org_b
        org_b_admin_profile.organization_type = self.org_b.org_type
        org_b_admin_profile.role = ProfileRole.ORG_ADMIN
        org_b_admin_profile.save()

        self._activate_org_session(org_b_admin, self.org_b)
        management_response = self.client.get(reverse("accounts:student_organization_management"))
        self.assertEqual(management_response.status_code, 200)
        self.assertContains(management_response, f"İstifadəçi artıq {self.org_a.name} təşkilatının üzvüdür.")

    def test_teacher_cannot_access_student_org_management(self):
        teacher_user = User.objects.create_user(
            username="teacher_locked",
            email="teacher_locked@example.com",
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

        self._activate_org_session(teacher_user, self.org_a)
        response = self.client.get(reverse("accounts:student_organization_management"))
        self.assertRedirects(response, reverse("accounts:profile"))

    def test_student_leave_requires_reason(self):
        student_user = User.objects.create_user(
            username="leave_no_reason",
            email="leave_no_reason@example.com",
            password="StrongPass123!",
        )
        Membership.objects.create(
            user=student_user,
            organization=self.org_a,
            role=self.org_a_student_role,
            is_primary=True,
            is_active=True,
        )
        student_profile = student_user.profile
        student_profile.organization = self.org_a
        student_profile.organization_type = self.org_a.org_type
        student_profile.role = ProfileRole.STUDENT
        student_profile.save()

        self._activate_org_session(student_user, self.org_a)
        response = self.client.post(
            reverse("accounts:student_leave_organization"),
            {
                "leave_reason": "",
                "next": reverse("accounts:profile") + "?section=profile-info",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "səbəb qeyd etmək məcburidir")
        student_profile.refresh_from_db()
        self.assertEqual(student_profile.organization, self.org_a)

    def test_teacher_can_attach_unassigned_user_and_assign_student_role(self):
        teacher_user = User.objects.create_user(
            username="teacher1",
            email="teacher1@example.com",
            password="StrongPass123!",
        )
        teacher_role = Role.objects.create(
            organization=self.org_a,
            name="teacher_attach_allowed",
            display_name="Teacher Attach Allowed",
            level=50,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["role.assign", "org.manage_members"],
            is_active=True,
        )
        Membership.objects.create(
            user=teacher_user,
            organization=self.org_a,
            role=teacher_role,
            is_primary=True,
            is_active=True,
        )
        teacher_profile = teacher_user.profile
        teacher_profile.organization = self.org_a
        teacher_profile.organization_type = self.org_a.org_type
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.save()

        self._activate_org_session(teacher_user, self.org_a)
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "attach_user",
                "user_id": str(self.unassigned_user.id),
                "role_id": str(self.org_a_student_role.id),
            },
        )
        self.assertRedirects(response, f"{reverse('accounts:profile')}?section=role-assignment")

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
        attached_membership = Membership.objects.filter(
            user=self.unassigned_user,
            organization=self.org_a,
            role=self.org_a_student_role,
            is_active=True,
        ).first()
        self.assertIsNotNone(attached_membership)
        success_entry = AuditLog.objects.filter(
            user=teacher_user,
            organization=self.org_a,
            resource_type="membership",
            resource_id=str(attached_membership.id),
            new_values__status="success",
            new_values__action_type="attach_user",
        ).first()
        self.assertIsNotNone(success_entry)
        self.assertEqual(success_entry.new_values.get("actor_user_id"), str(teacher_user.id))
        self.assertEqual(success_entry.new_values.get("org_id"), str(self.org_a.id))
        self.assertEqual(success_entry.new_values.get("target_user_id"), str(self.unassigned_user.id))
        self.assertEqual(success_entry.new_values.get("membership_id"), str(attached_membership.id))
        self.assertEqual(success_entry.new_values.get("new_role_id"), str(self.org_a_student_role.id))

    def test_attach_user_requires_manage_members_permission(self):
        teacher_user = User.objects.create_user(
            username="teacher_no_assign",
            email="teacher_no_assign@example.com",
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

        self._activate_org_session(teacher_user, self.org_a)
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "attach_user",
                "user_id": str(self.unassigned_user.id),
                "role_id": str(self.org_a_student_role.id),
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Membership.objects.filter(
                user=self.unassigned_user,
                organization=self.org_a,
                role=self.org_a_student_role,
                is_active=True,
            ).exists()
        )

    def test_attach_unassigned_user_rejected_when_requested_other_tenant(self):
        teacher_user = User.objects.create_user(
            username="teacher_blocked",
            email="teacher_blocked@example.com",
            password="StrongPass123!",
        )
        teacher_role = Role.objects.create(
            organization=self.org_a,
            name="teacher_attach_block_check",
            display_name="Teacher Attach Block Check",
            level=50,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["role.assign", "org.manage_members"],
            is_active=True,
        )
        Membership.objects.create(
            user=teacher_user,
            organization=self.org_a,
            role=teacher_role,
            is_primary=True,
            is_active=True,
        )
        teacher_profile = teacher_user.profile
        teacher_profile.organization = self.org_a
        teacher_profile.organization_type = self.org_a.org_type
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.save()

        self._activate_org_session(teacher_user, self.org_a)
        response = self.client.post(
            reverse("accounts:role_assignment"),
            {
                "action": "attach_user",
                "user_id": str(self.unassigned_other.id),
                "role_id": str(self.org_a_student_role.id),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "signup zamanı seçməyib")
        self.assertFalse(
            Membership.objects.filter(
                user=self.unassigned_other,
                organization=self.org_a,
                is_active=True,
            ).exists()
        )

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

        self._activate_org_session(constrained_admin, self.org_a)
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

        self._activate_org_session(constrained_admin, self.org_a)
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

    def test_org_owner_without_membership_gets_permission_editor_access(self):
        owner_without_membership = User.objects.create_user(
            username="owner_no_membership",
            email="owner_no_membership@example.com",
            password="StrongPass123!",
        )
        owner_profile = owner_without_membership.profile
        owner_profile.organization = self.org_a
        owner_profile.organization_type = self.org_a.org_type
        owner_profile.role = ProfileRole.ORG_OWNER
        owner_profile.save()

        self._activate_org_session(owner_without_membership, self.org_a)
        response = self.client.get(reverse("accounts:permission_editor"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Permission idarəetməsi üçün `role.assign` səlahiyyəti tələb olunur.")
        self.assertTrue(
            Membership.objects.filter(
                user=owner_without_membership,
                organization=self.org_a,
                is_active=True,
            ).exists()
        )

    def test_permission_editor_bulk_add_and_remove(self):
        role_target = Role.objects.create(
            organization=self.org_a,
            name="bulk_perm_role",
            display_name="Bulk Perm Role",
            level=30,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=[],
            is_active=True,
        )

        response = self.client.post(
            reverse("accounts:permission_editor"),
            {
                "role_id": str(role_target.id),
                "action": "bulk_add",
                "permissions": ["member.view", "member.invite"],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        role_target.refresh_from_db()
        self.assertIn("member.view", role_target.permissions)
        self.assertIn("member.invite", role_target.permissions)

        response = self.client.post(
            reverse("accounts:permission_editor"),
            {
                "role_id": str(role_target.id),
                "action": "bulk_remove",
                "permissions": ["member.view"],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        role_target.refresh_from_db()
        self.assertNotIn("member.view", role_target.permissions)
        self.assertIn("member.invite", role_target.permissions)

    def test_permission_editor_bulk_add_rejects_non_grantable_permissions(self):
        constrained_admin = User.objects.create_user(
            username="bulk_limited_admin",
            email="bulk_limited_admin@example.com",
            password="StrongPass123!",
        )
        role_manager = Role.objects.create(
            organization=self.org_a,
            name="bulk_limited_manager",
            display_name="Bulk Limited Manager",
            level=85,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["role.assign", "exam.view"],
            is_active=True,
        )
        role_target = Role.objects.create(
            organization=self.org_a,
            name="bulk_limited_target",
            display_name="Bulk Limited Target",
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

        self._activate_org_session(constrained_admin, self.org_a)
        response = self.client.post(
            reverse("accounts:permission_editor"),
            {
                "role_id": str(role_target.id),
                "action": "bulk_add",
                "permissions": ["member.invite", "member.view"],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yalnız özünüzdə olan və ya grant edilə bilən permission-ları verə bilərsiniz")
        role_target.refresh_from_db()
        self.assertNotIn("member.invite", role_target.permissions)
        self.assertNotIn("member.view", role_target.permissions)
