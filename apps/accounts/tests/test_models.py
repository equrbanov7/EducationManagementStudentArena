"""
Model tests for accounts app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import ProfileRole, UserProfile
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class UserProfileCreationTest(TestCase):
    """Test UserProfile creation and basic functionality."""

    def test_profile_created_automatically_on_user_creation(self):
        """Test that UserProfile is created automatically when a user is created."""
        user = User.objects.create_user("testuser", "test@example.com", "StrongPass123!")
        self.assertTrue(hasattr(user, "profile"))
        self.assertIsInstance(user.profile, UserProfile)

    def test_profile_default_values(self):
        """Test that UserProfile has correct default values."""
        user = User.objects.create_user("defaultuser", "default@example.com", "StrongPass123!")
        profile = user.profile

        self.assertEqual(profile.role, ProfileRole.MEMBER)
        self.assertEqual(profile.organization_type, OrganizationType.INDIVIDUAL)
        self.assertEqual(profile.country, "")
        self.assertEqual(profile.bio, "")
        self.assertIsNone(profile.organization)

    def test_profile_organization_name_property(self):
        """Test organization_name property returns correct value."""
        user = User.objects.create_user("orguser", "org@example.com", "StrongPass123!")
        profile = user.profile

        # Without organization
        self.assertEqual(profile.organization_name, "Fərdi")

        # With organization
        org = Organization.objects.create(
            name="Test School",
            org_type=OrganizationType.SCHOOL,
            owner=user,
            status="active",
            is_active=True,
        )
        profile.organization = org
        profile.save(update_fields=["organization"])

        self.assertEqual(profile.organization_name, "Test School")

    def test_profile_string_representation(self):
        """Test UserProfile __str__ method."""
        user = User.objects.create_user("struser", "str@example.com", "StrongPass123!")
        profile = user.profile
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["role", "updated_at"])

        expected = f"struser - {profile.get_role_display()}"
        self.assertEqual(str(profile), expected)


class ProfileRoleHierarchyTest(TestCase):
    """Test ProfileRole hierarchy and role levels."""

    def test_role_levels_defined(self):
        """Test that all role levels are defined."""
        self.assertIn(ProfileRole.SUPERADMIN, ProfileRole.LEVELS)
        self.assertIn(ProfileRole.ORG_OWNER, ProfileRole.LEVELS)
        self.assertIn(ProfileRole.ORG_ADMIN, ProfileRole.LEVELS)
        self.assertIn(ProfileRole.TEACHER, ProfileRole.LEVELS)
        self.assertIn(ProfileRole.ASSISTANT_TEACHER, ProfileRole.LEVELS)
        self.assertIn(ProfileRole.LEAD_STUDENT, ProfileRole.LEVELS)
        self.assertIn(ProfileRole.STUDENT, ProfileRole.LEVELS)
        self.assertIn(ProfileRole.MEMBER, ProfileRole.LEVELS)
        self.assertIn(ProfileRole.HR, ProfileRole.LEVELS)

    def test_role_hierarchy_order(self):
        """Test that role hierarchy is correctly ordered."""
        # Higher roles should have higher level values
        self.assertGreater(ProfileRole.LEVELS[ProfileRole.SUPERADMIN], ProfileRole.LEVELS[ProfileRole.ORG_OWNER])
        self.assertGreater(ProfileRole.LEVELS[ProfileRole.ORG_OWNER], ProfileRole.LEVELS[ProfileRole.ORG_ADMIN])
        self.assertGreater(ProfileRole.LEVELS[ProfileRole.ORG_ADMIN], ProfileRole.LEVELS[ProfileRole.TEACHER])
        self.assertGreater(ProfileRole.LEVELS[ProfileRole.TEACHER], ProfileRole.LEVELS[ProfileRole.ASSISTANT_TEACHER])
        self.assertGreater(ProfileRole.LEVELS[ProfileRole.ASSISTANT_TEACHER], ProfileRole.LEVELS[ProfileRole.LEAD_STUDENT])
        self.assertGreater(ProfileRole.LEVELS[ProfileRole.LEAD_STUDENT], ProfileRole.LEVELS[ProfileRole.STUDENT])

    def test_role_level_property(self):
        """Test role_level property returns correct value."""
        user = User.objects.create_user("leveluser", "level@example.com", "StrongPass123!")
        profile = user.profile

        # Test different roles
        profile.role = ProfileRole.SUPERADMIN
        profile.save(update_fields=["role", "updated_at"])
        self.assertEqual(profile.role_level, ProfileRole.LEVELS[ProfileRole.SUPERADMIN])
        self.assertEqual(profile.role_level, 100)

        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["role", "updated_at"])
        self.assertEqual(profile.role_level, ProfileRole.LEVELS[ProfileRole.TEACHER])
        self.assertEqual(profile.role_level, 60)

        profile.role = ProfileRole.STUDENT
        profile.save(update_fields=["role", "updated_at"])
        self.assertEqual(profile.role_level, ProfileRole.LEVELS[ProfileRole.STUDENT])
        self.assertEqual(profile.role_level, 10)

    def test_role_choices_contain_all_roles(self):
        """Test that CHOICES contains all defined roles."""
        choice_values = [choice[0] for choice in ProfileRole.CHOICES]

        self.assertIn(ProfileRole.SUPERADMIN, choice_values)
        self.assertIn(ProfileRole.ORG_OWNER, choice_values)
        self.assertIn(ProfileRole.ORG_ADMIN, choice_values)
        self.assertIn(ProfileRole.TEACHER, choice_values)
        self.assertIn(ProfileRole.ASSISTANT_TEACHER, choice_values)
        self.assertIn(ProfileRole.LEAD_STUDENT, choice_values)
        self.assertIn(ProfileRole.STUDENT, choice_values)
        self.assertIn(ProfileRole.MEMBER, choice_values)
        self.assertIn(ProfileRole.HR, choice_values)


class ProfileOrganizationTest(TestCase):
    """Test UserProfile organization-related functionality."""

    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Test Organization",
            org_type=OrganizationType.SCHOOL,
            owner=self.owner,
            status="active",
            is_active=True,
        )

    def test_profile_can_be_linked_to_organization(self):
        """Test that profile can be linked to an organization."""
        user = User.objects.create_user("member", "member@example.com", "StrongPass123!")
        profile = user.profile

        profile.organization = self.org
        profile.organization_type = self.org.org_type
        profile.role = ProfileRole.STUDENT
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        self.assertEqual(profile.organization, self.org)
        self.assertEqual(profile.organization_type, OrganizationType.SCHOOL)

    def test_profile_requested_organization_fields(self):
        """Test requested organization fields work correctly."""
        user = User.objects.create_user("requester", "requester@example.com", "StrongPass123!")
        profile = user.profile

        profile.requested_organization = self.org
        profile.requested_organization_name = "Custom School Name"
        profile.requested_organization_message = "Please let me join"
        profile.save(update_fields=["requested_organization", "requested_organization_name", "requested_organization_message", "updated_at"])

        self.assertEqual(profile.requested_organization, self.org)
        self.assertEqual(profile.requested_organization_name, "Custom School Name")
        self.assertEqual(profile.requested_organization_message, "Please let me join")

    def test_profile_with_student_fields(self):
        """Test student-specific fields."""
        user = User.objects.create_user("student", "student@example.com", "StrongPass123!")
        profile = user.profile

        profile.role = ProfileRole.STUDENT
        profile.student_university_name = "Test University"
        profile.student_school_identifier = "12345"
        profile.save(update_fields=["role", "student_university_name", "student_school_identifier", "updated_at"])

        self.assertEqual(profile.student_university_name, "Test University")
        self.assertEqual(profile.student_school_identifier, "12345")
