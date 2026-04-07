"""
Service tests for accounts app.
"""

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts import services
from apps.accounts.models import EmailOTP, ProfileRole
from apps.notifications.models import InAppNotification, NotificationType
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class RoleManagementServicesTest(TestCase):
    """Test role management service functions."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="superadmin", email="super@example.com", password="pass123"
        )
        self.organization = Organization.objects.create(
            name="Service Roles Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.superuser,
            status="active",
            is_active=True,
        )
        self.teacher = User.objects.create_user(username="teacher1", email="teacher@example.com", password="pass123")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.student = User.objects.create_user(username="student1", email="student@example.com", password="pass123")
        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

        Membership.objects.create(
            user=self.teacher,
            organization=self.organization,
            role=self.organization.roles.get(name="teacher"),
            is_primary=True,
            is_active=True,
        )
        Membership.objects.create(
            user=self.student,
            organization=self.organization,
            role=self.organization.roles.get(name="student"),
            is_primary=True,
            is_active=True,
        )

        self.teacher.set_active_organization_context(self.organization)
        self.student.set_active_organization_context(self.organization)

    def test_is_superadmin_user(self):
        """Test superadmin detection."""
        self.assertTrue(services.is_superadmin_user(self.superuser))
        self.assertFalse(services.is_superadmin_user(self.teacher))
        self.assertFalse(services.is_superadmin_user(self.student))

    def test_get_user_role_level(self):
        """Test role level retrieval."""
        self.assertEqual(services.get_user_role_level(self.superuser), 999)
        teacher_level = services.get_user_role_level(self.teacher)
        self.assertGreater(teacher_level, 0)
        student_level = services.get_user_role_level(self.student)
        self.assertGreater(student_level, 0)

    def test_user_has_any_role(self):
        """Test role checking."""
        self.assertTrue(services.user_has_any_role(self.teacher, [ProfileRole.TEACHER]))
        self.assertFalse(services.user_has_any_role(self.student, [ProfileRole.TEACHER]))

    def test_role_checks_deny_without_active_tenant_context(self):
        """Memberships alone must not authorize when no active org context is bound."""
        self.teacher.clear_active_organization_context()

        self.assertEqual(services.get_user_role_level(self.teacher), 0)
        self.assertFalse(services.user_has_any_role(self.teacher, [ProfileRole.TEACHER]))


class OTPServicesTest(TestCase):
    """Test OTP and email verification services."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="pass123", is_active=False
        )

    def test_send_verification_otp(self):
        """Test sending verification OTP."""
        code = services.send_verification_otp(self.user)

        self.assertIsNotNone(code)
        self.assertEqual(len(code), 6)

        otp = EmailOTP.objects.filter(user=self.user, is_used=False).first()
        self.assertIsNotNone(otp)
        self.assertNotEqual(otp.otp_hash, code)
        self.assertTrue(otp.matches_code(code))

    def test_verify_otp_code_success(self):
        """Test successful OTP verification."""
        code = services.send_verification_otp(self.user)
        success, otp = services.verify_otp_code(self.user, code)

        self.assertTrue(success)
        self.assertIsNotNone(otp)

    def test_verify_otp_code_invalid(self):
        """Test invalid OTP verification."""
        services.send_verification_otp(self.user)
        success, otp = services.verify_otp_code(self.user, "999999")

        self.assertFalse(success)
        self.assertIsNone(otp)


class ScoreParsingServicesTest(TestCase):
    """Test score parsing services."""

    def test_parse_decimal_score_valid(self):
        """Test parsing valid score values."""
        self.assertEqual(services.parse_decimal_score("95.5"), Decimal("95.5"))
        self.assertEqual(services.parse_decimal_score(85), Decimal("85"))
        self.assertEqual(services.parse_decimal_score(Decimal("75.25")), Decimal("75.25"))

    def test_parse_decimal_score_invalid(self):
        """Test parsing invalid score values."""
        self.assertIsNone(services.parse_decimal_score("invalid"))
        self.assertIsNone(services.parse_decimal_score(None))
        self.assertEqual(services.parse_decimal_score("invalid", default=Decimal("0")), Decimal("0"))


class RegistrationServicesTest(TestCase):
    """Test registration bootstrap services."""

    def test_create_user_with_organization_preserves_org_admin_role(self):
        """Organization bootstrap should keep ORG_ADMIN as the profile role."""
        user, organization, requested_organization, profile = services.create_user_with_organization(
            username="orgadminsignup",
            email="orgadminsignup@example.com",
            password="StrongPass123!",
            first_name="Org",
            last_name="Admin",
            signup_mode="organization_create",
            organization_type=OrganizationType.SCHOOL,
            country_code="AZ",
            country_name="Azerbaijan",
            institution_not_listed_name="Role Mapping School",
            organization_identifier="",
            organization_license_identifier="",
            initial_role=ProfileRole.ORG_ADMIN,
        )

        self.assertFalse(user.is_active)
        self.assertEqual(profile.role, ProfileRole.ORG_ADMIN)
        self.assertEqual(requested_organization, organization)
        self.assertTrue(
            Membership.objects.filter(
                user=user,
                organization=organization,
                is_primary=True,
                is_active=True,
            ).exists()
        )

    def test_create_user_with_organization_enters_rls_bypass(self):
        entered = {"count": 0}

        @contextmanager
        def recording_bypass():
            entered["count"] += 1
            yield

        with patch("apps.accounts.services.registration.bypass_rls", recording_bypass):
            services.create_user_with_organization(
                username="orgadminsignupbypass",
                email="orgadminsignupbypass@example.com",
                password="StrongPass123!",
                first_name="Org",
                last_name="Admin",
                signup_mode="organization_create",
                organization_type=OrganizationType.SCHOOL,
                country_code="AZ",
                country_name="Azerbaijan",
                institution_not_listed_name="Bypass Role School",
                organization_identifier="",
                organization_license_identifier="",
                initial_role=ProfileRole.ORG_ADMIN,
            )

        self.assertEqual(entered["count"], 1)

    def test_create_user_with_organization_notifies_owner_about_pending_approval(self):
        user, organization, _requested_organization, _profile = services.create_user_with_organization(
            username="orgownernotify",
            email="orgownernotify@example.com",
            password="StrongPass123!",
            first_name="Org",
            last_name="Owner",
            signup_mode="organization_create",
            organization_type=OrganizationType.SCHOOL,
            country_code="AZ",
            country_name="Azerbaijan",
            institution_not_listed_name="Pending Approval School",
            organization_identifier="",
            organization_license_identifier="",
            initial_role=ProfileRole.ORG_ADMIN,
        )

        self.assertEqual(organization.owner_id, user.id)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=user,
                notification_type=NotificationType.APPROVAL,
                title__icontains="baxışdadır",
                metadata__event="organization_pending_approval",
            ).exists()
        )


class OTPDeliveryServiceTest(TestCase):
    """Tests for OTP generation and email delivery."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="otpdeliveryuser",
            email="otpdelivery@example.com",
            password="StrongPass123!",
            is_active=False,
        )

    def test_issue_email_otp_creates_otp_record(self):
        """issue_email_otp must create an EmailOTP record that matches the returned code."""
        from apps.accounts.services import issue_email_otp

        code, expires_at, _otp = issue_email_otp(self.user)

        self.assertIsNotNone(code)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        # The OTP is stored hashed; verify with matches_code
        otp_record = EmailOTP.objects.filter(user=self.user, is_used=False).order_by("-id").first()
        self.assertIsNotNone(otp_record)
        self.assertTrue(otp_record.matches_code(code))

    def test_issue_email_otp_invalidates_previous_codes(self):
        """A fresh OTP must mark older pending OTPs as used."""
        from apps.accounts.services import issue_email_otp

        # Create two stale OTPs
        EmailOTP.objects.create(user=self.user, code="111111")
        EmailOTP.objects.create(user=self.user, code="222222")

        issue_email_otp(self.user)

        # Existing records are now is_used=True – the raw code values are no longer
        # stored verbatim (they are hashed), so we check via is_used flag.
        self.assertEqual(
            EmailOTP.objects.filter(user=self.user, is_used=False).count(),
            1,
            "Only the freshly issued OTP should remain active",
        )

    def test_verify_otp_code_valid(self):
        """verify_otp_code returns True and the OTP object for a valid code."""
        from apps.accounts.services import issue_email_otp, verify_otp_code

        code, _expires_at, _otp = issue_email_otp(self.user)
        is_valid, otp = verify_otp_code(self.user, code)

        self.assertTrue(is_valid)
        self.assertIsNotNone(otp)
        # The returned OTP object must match the plaintext code
        self.assertTrue(otp.matches_code(code))

    def test_verify_otp_code_invalid(self):
        """verify_otp_code returns (False, None) for a wrong code."""
        from apps.accounts.services import issue_email_otp, verify_otp_code

        issue_email_otp(self.user)
        is_valid, otp = verify_otp_code(self.user, "000000")

        self.assertFalse(is_valid)
        self.assertIsNone(otp)

    def test_activate_user_account_sets_is_active(self):
        """activate_user_account sets user.is_active to True."""
        from apps.accounts.services import activate_user_account

        self.assertFalse(self.user.is_active)
        activate_user_account(self.user)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)


class TeacherStaffRequestFlowTest(TestCase):
    """Tests for teacher/staff join request creation and approval."""

    def setUp(self):
        from apps.organizations.models import Organization

        self.owner = User.objects.create_user(
            username="ts_org_owner",
            email="ts_org_owner@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.org = Organization.objects.create(
            name="TS Test University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )

    def _register_teacher(self, username="teacher_req", email=None):
        """Create a teacher user who has requested to join self.org."""
        email = email or f"{username}@example.com"
        return services.create_user_with_organization(
            username=username,
            email=email,
            password="StrongPass123!",
            first_name="Test",
            last_name="Teacher",
            signup_mode="teacher_join",
            organization_type=OrganizationType.UNIVERSITY,
            country_code="AZ",
            country_name="Azerbaijan",
            join_organization=self.org,
            institution_not_listed_name="",
            organization_identifier="",
            organization_license_identifier="",
            initial_role=ProfileRole.TEACHER,
        )

    def _register_staff(self, username="staff_req", email=None):
        """Create a staff user who has requested to join self.org."""
        email = email or f"{username}@example.com"
        return services.create_user_with_organization(
            username=username,
            email=email,
            password="StrongPass123!",
            first_name="Test",
            last_name="Staff",
            signup_mode="staff_join",
            organization_type=OrganizationType.UNIVERSITY,
            country_code="AZ",
            country_name="Azerbaijan",
            join_organization=self.org,
            institution_not_listed_name="",
            organization_identifier="",
            organization_license_identifier="",
            initial_role=ProfileRole.MEMBER,
        )

    def test_teacher_signup_creates_pending_request(self):
        """Teacher join signup must create a PENDING teacher request."""
        from apps.notifications.models import (
            MembershipRequestRoleType,
            StudentOrganizationRequest,
            StudentOrganizationRequestStatus,
        )

        user, _, _, profile = self._register_teacher()

        self.assertEqual(profile.role, ProfileRole.TEACHER)
        self.assertIsNone(profile.organization)
        self.assertEqual(profile.requested_organization, self.org)

        req = StudentOrganizationRequest.objects.filter(
            user=user,
            organization=self.org,
            role_type=MembershipRequestRoleType.TEACHER,
            status=StudentOrganizationRequestStatus.PENDING,
        ).first()
        self.assertIsNotNone(req, "No TEACHER pending request was created at registration")

    def test_staff_signup_creates_pending_request(self):
        """Staff join signup must create a PENDING staff request."""
        from apps.notifications.models import (
            MembershipRequestRoleType,
            StudentOrganizationRequest,
            StudentOrganizationRequestStatus,
        )

        user, _, _, profile = self._register_staff()

        self.assertEqual(profile.role, ProfileRole.MEMBER)
        self.assertIsNone(profile.organization)

        req = StudentOrganizationRequest.objects.filter(
            user=user,
            organization=self.org,
            role_type=MembershipRequestRoleType.STAFF,
            status=StudentOrganizationRequestStatus.PENDING,
        ).first()
        self.assertIsNotNone(req, "No STAFF pending request was created at registration")

    def test_email_verification_updates_existing_teacher_request(self):
        """After email verification activate_verified_membership does not duplicate requests."""
        from apps.accounts.services import activate_verified_membership
        from apps.notifications.models import (
            InAppNotification,
            MembershipRequestRoleType,
            NotificationType,
            StudentOrganizationRequest,
            StudentOrganizationRequestStatus,
        )

        user, _, _, _ = self._register_teacher()
        user.is_active = False
        user.save()

        # Should not create a second request
        activate_verified_membership(user)

        req_count = StudentOrganizationRequest.objects.filter(
            user=user,
            organization=self.org,
            role_type=MembershipRequestRoleType.TEACHER,
            status=StudentOrganizationRequestStatus.PENDING,
        ).count()
        self.assertEqual(req_count, 1, "Duplicate teacher request was created on verification")
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.owner,
                notification_type=NotificationType.APPROVAL,
                title__icontains="Yeni müəllim müraciəti",
            ).exists()
        )

    def test_activate_verified_membership_enters_rls_bypass(self):
        from apps.accounts.services import organization_requests

        entered = {"count": 0}

        @contextmanager
        def recording_bypass():
            entered["count"] += 1
            yield

        user, _, _, _ = self._register_teacher(username="teacher_req_bypass")
        with patch.dict(
            organization_requests.activate_verified_membership.__globals__,
            {"bypass_rls": recording_bypass},
        ):
            organization_requests.activate_verified_membership(user)

        self.assertEqual(entered["count"], 1)

    def test_teacher_signup_notifies_org_owner(self):
        """Teacher join signup should notify the target organization owner."""
        from apps.notifications.models import InAppNotification, NotificationType

        user, _, _, _ = self._register_teacher(username="teacher_notify_owner")

        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.owner,
                notification_type=NotificationType.APPROVAL,
                title__icontains="Yeni müəllim müraciəti",
                metadata__user_id=user.id,
            ).exists()
        )

    def test_pending_teacher_appears_in_management_section(self):
        """pending_teacher_staff_requests in the management section must include teacher requests."""
        from django.test import RequestFactory

        from apps.accounts.views._helpers import _build_student_org_management_section

        user, _, _, _ = self._register_teacher()
        user.is_active = True
        user.save()

        factory = RequestFactory()
        request = factory.get("/")
        request.GET = {}
        request.user = self.owner

        context = _build_student_org_management_section(
            request=request,
            organization=self.org,
            is_superadmin=False,
            user_level=999,
        )
        ts_requests = list(context["pending_teacher_staff_requests"].object_list)
        self.assertTrue(
            any(r.user_id == user.pk for r in ts_requests),
            "Teacher's pending request not found in management section",
        )
