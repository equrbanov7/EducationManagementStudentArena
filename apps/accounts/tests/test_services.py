"""
Service tests for accounts app.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts import services
from apps.accounts.models import ProfileRole
from apps.blog.models import EmailOTP
from apps.courses.models import Course, CourseMembership
from apps.organizations.models import Country, Membership, Organization
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
        self.assertNotEqual(otp.code, code)
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
