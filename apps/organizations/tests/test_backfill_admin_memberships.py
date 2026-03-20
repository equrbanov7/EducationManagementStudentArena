"""
Tests for the backfill_admin_memberships management command.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models.signals import post_save
from django.test import TestCase

from apps.accounts.models import ProfileRole, UserProfile
from core.constants import OrganizationType, RoleScopeType

from ..models import Membership, Organization, Role
from ..signals import create_default_roles

User = get_user_model()


def _make_org(owner, name="Test Org", slug=None, org_type=OrganizationType.SCHOOL):
    """Helper to create an organization without triggering the default-roles signal."""
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        org = Organization.objects.create(
            name=name,
            slug=slug or name.lower().replace(" ", "-"),
            org_type=org_type,
            owner=owner,
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return org


def _make_role(org, name="director", level=100):
    return Role.objects.create(
        organization=org,
        name=name,
        display_name=name.title(),
        level=level,
        scope_type=RoleScopeType.ORGANIZATION,
        is_active=True,
    )


def _make_admin_profile(user, org, role=ProfileRole.ORG_OWNER):
    profile = getattr(user, "profile", None) or UserProfile.objects.get(user=user)
    profile.organization = org
    profile.role = role
    profile.save(update_fields=["organization", "role", "updated_at"])
    return profile


class BackfillAdminMembershipsCommandTest(TestCase):
    """Tests for the backfill_admin_memberships management command."""

    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "Pass123!")
        self.org = _make_org(self.owner)
        self.admin_role = _make_role(self.org, name="director", level=100)

    # ------------------------------------------------------------------
    # Basic backfill
    # ------------------------------------------------------------------

    def test_creates_membership_for_legacy_org_owner(self):
        """A user with ORG_OWNER profile but no membership gets one created."""
        _make_admin_profile(self.owner, self.org, ProfileRole.ORG_OWNER)

        self.assertFalse(
            Membership.objects.filter(user=self.owner, organization=self.org).exists()
        )

        out = StringIO()
        call_command("backfill_admin_memberships", stdout=out, verbosity=1)

        self.assertTrue(
            Membership.objects.filter(user=self.owner, organization=self.org, is_active=True).exists()
        )
        self.assertIn("Created", out.getvalue())

    def test_creates_membership_for_legacy_org_admin(self):
        """A user with ORG_ADMIN profile but no membership gets one created."""
        user = User.objects.create_user("admin2", "admin2@example.com", "Pass123!")
        _make_admin_profile(user, self.org, ProfileRole.ORG_ADMIN)

        out = StringIO()
        call_command("backfill_admin_memberships", stdout=out, verbosity=1)

        self.assertTrue(
            Membership.objects.filter(user=user, organization=self.org, is_active=True).exists()
        )

    def test_skips_user_with_existing_active_membership(self):
        """Users who already have an active membership are not touched."""
        _make_admin_profile(self.owner, self.org, ProfileRole.ORG_OWNER)
        Membership.objects.create(
            user=self.owner,
            organization=self.org,
            role=self.admin_role,
            is_active=True,
            is_primary=True,
        )

        out = StringIO()
        call_command("backfill_admin_memberships", stdout=out, verbosity=1)

        # Still only one membership.
        count = Membership.objects.filter(user=self.owner, organization=self.org).count()
        self.assertEqual(count, 1)
        self.assertIn("Skipped 1", out.getvalue())

    # ------------------------------------------------------------------
    # Dry-run
    # ------------------------------------------------------------------

    def test_dry_run_does_not_write(self):
        """--dry-run prints what would happen but makes no DB changes."""
        _make_admin_profile(self.owner, self.org, ProfileRole.ORG_OWNER)

        out = StringIO()
        call_command("backfill_admin_memberships", "--dry-run", stdout=out, verbosity=1)

        self.assertFalse(
            Membership.objects.filter(user=self.owner, organization=self.org).exists()
        )
        self.assertIn("Would create", out.getvalue())
        self.assertIn("DRY-RUN", out.getvalue())

    # ------------------------------------------------------------------
    # --org filter
    # ------------------------------------------------------------------

    def test_org_filter_limits_scope(self):
        """--org restricts the command to a single organization."""
        other_org = _make_org(self.owner, name="Other Org", slug="other-org")
        _make_role(other_org, name="manager", level=100)

        other_user = User.objects.create_user("other", "other@example.com", "Pass123!")
        _make_admin_profile(self.owner, self.org, ProfileRole.ORG_OWNER)
        _make_admin_profile(other_user, other_org, ProfileRole.ORG_OWNER)

        out = StringIO()
        call_command("backfill_admin_memberships", "--org", self.org.slug, stdout=out, verbosity=1)

        # self.owner should have a membership in self.org.
        self.assertTrue(Membership.objects.filter(user=self.owner, organization=self.org).exists())
        # other_user should NOT have a membership (different org, not in scope).
        self.assertFalse(Membership.objects.filter(user=other_user, organization=other_org).exists())

    def test_invalid_org_slug_raises_command_error(self):
        """Passing an unknown org slug raises CommandError."""
        with self.assertRaises(CommandError):
            call_command("backfill_admin_memberships", "--org", "nonexistent-org")

    # ------------------------------------------------------------------
    # No-role edge-case
    # ------------------------------------------------------------------

    def test_skips_org_with_no_active_roles(self):
        """If an org has no active roles the user is reported but not assigned."""
        # Deactivate all roles so the command has nothing to assign.
        self.admin_role.is_active = False
        self.admin_role.save(update_fields=["is_active"])
        _make_admin_profile(self.owner, self.org, ProfileRole.ORG_OWNER)

        err = StringIO()
        out = StringIO()
        call_command("backfill_admin_memberships", stdout=out, stderr=err, verbosity=1)

        self.assertFalse(Membership.objects.filter(user=self.owner, organization=self.org).exists())
        combined = out.getvalue() + err.getvalue()
        self.assertIn("no active roles found", combined)

    # ------------------------------------------------------------------
    # Inactive org guard
    # ------------------------------------------------------------------

    def test_skips_inactive_org(self):
        """Legacy admins belonging to inactive orgs are silently skipped."""
        _make_admin_profile(self.owner, self.org, ProfileRole.ORG_OWNER)
        self.org.is_active = False
        self.org.save(update_fields=["is_active"])

        out = StringIO()
        call_command("backfill_admin_memberships", stdout=out, verbosity=2)

        self.assertFalse(Membership.objects.filter(user=self.owner, organization=self.org).exists())

    # ------------------------------------------------------------------
    # Non-admin profiles are ignored
    # ------------------------------------------------------------------

    def test_non_admin_profiles_are_not_touched(self):
        """Users with STUDENT or TEACHER profiles are not backfilled."""
        student = User.objects.create_user("student1", "s@example.com", "Pass123!")
        prof = getattr(student, "profile", None) or UserProfile.objects.get(user=student)
        prof.organization = self.org
        prof.role = ProfileRole.STUDENT
        prof.save(update_fields=["organization", "role", "updated_at"])

        out = StringIO()
        call_command("backfill_admin_memberships", stdout=out, verbosity=1)

        self.assertFalse(Membership.objects.filter(user=student, organization=self.org).exists())
        self.assertIn("Nothing to do", out.getvalue())

    # ------------------------------------------------------------------
    # Primary membership flag
    # ------------------------------------------------------------------

    def test_first_membership_is_primary(self):
        """The first backfilled membership for a user is marked is_primary=True."""
        _make_admin_profile(self.owner, self.org, ProfileRole.ORG_OWNER)

        call_command("backfill_admin_memberships", verbosity=0)

        m = Membership.objects.get(user=self.owner, organization=self.org)
        self.assertTrue(m.is_primary)

    def test_second_membership_is_not_primary(self):
        """When the user already has a primary membership elsewhere, new one is not primary."""
        other_org = _make_org(self.owner, name="Primary Org", slug="primary-org")
        other_role = _make_role(other_org, name="rector", level=100)
        Membership.objects.create(
            user=self.owner,
            organization=other_org,
            role=other_role,
            is_primary=True,
            is_active=True,
        )
        _make_admin_profile(self.owner, self.org, ProfileRole.ORG_OWNER)

        call_command("backfill_admin_memberships", "--org", self.org.slug, verbosity=0)

        m = Membership.objects.get(user=self.owner, organization=self.org)
        self.assertFalse(m.is_primary)

    # ------------------------------------------------------------------
    # Empty state
    # ------------------------------------------------------------------

    def test_no_legacy_admins_exits_cleanly(self):
        """When no legacy admin profiles exist the command exits gracefully."""
        out = StringIO()
        call_command("backfill_admin_memberships", stdout=out, verbosity=1)
        self.assertIn("Nothing to do", out.getvalue())
