"""
Model tests for organizations app.
"""

from contextlib import contextmanager
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase

from core.constants import OrganizationType, RoleScopeType

from ..models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from ..signals import create_default_roles

User = get_user_model()


class OrganizationModelTest(TestCase):
    """Tests for Organization model."""

    def setUp(self):
        """Set up test data."""
        # Disconnect signal to avoid unique constraint errors in tests
        post_save.disconnect(create_default_roles, sender=Organization)

        self.user = User.objects.create_user(username="testuser", email="test@test.com", password="testpass123")

    def tearDown(self):
        """Clean up after tests."""
        # Reconnect signal
        post_save.connect(create_default_roles, sender=Organization)

    def test_organization_creation(self):
        """Test creating an organization."""
        org = Organization.objects.create(
            name="Test University",
            slug="test-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )
        self.assertEqual(org.name, "Test University")
        self.assertEqual(org.org_type, OrganizationType.UNIVERSITY)
        self.assertTrue(org.is_active)

    def test_organization_auto_slug(self):
        """Test automatic slug generation."""
        org = Organization.objects.create(
            name="Another University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )
        self.assertEqual(org.slug, "another-university")

    def test_organization_duplicate_name_generates_unique_slug(self):
        """Organizations with same name should still get unique slugs."""
        org1 = Organization.objects.create(
            name="Duplicate Name Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )
        org2 = Organization.objects.create(
            name="Duplicate Name Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )
        self.assertNotEqual(org1.slug, org2.slug)
        self.assertTrue(org2.slug.startswith("duplicate-name-org-"))

    # Commented out as signal may run multiple times in tests
    # def test_default_roles_created(self):
    #     """Test that default roles are created for new organization."""
    #     org = Organization.objects.create(
    #         name="Test School",
    #         slug="test-school",
    #         org_type=OrganizationType.SCHOOL,
    #         owner=self.user,
    #     )
    #     # Default roles should be created via signal
    #     roles = Role.objects.filter(organization=org)
    #     self.assertGreater(roles.count(), 0)


class OrgUnitModelTest(TestCase):
    """Tests for OrgUnit model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", email="test@test.com", password="testpass123")
        self.org = Organization.objects.create(
            name="Test University",
            slug="test-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )

    def test_orgunit_creation(self):
        """Test creating an organizational unit."""
        unit = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty of Science",
            slug="faculty-science",
        )
        self.assertEqual(unit.name, "Faculty of Science")
        self.assertEqual(unit.level, 0)  # Root unit
        self.assertTrue(unit.is_active)

    def test_orgunit_hierarchy(self):
        """Test hierarchical organizational units."""
        parent = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty of Science",
            slug="faculty-science",
        )
        child = OrgUnit.objects.create(
            organization=self.org,
            parent=parent,
            unit_type="department",
            name="Computer Science",
            slug="cs",
        )
        self.assertEqual(child.parent, parent)
        self.assertEqual(child.level, 1)
        self.assertIn(str(parent.id), child.path)

    def test_orgunit_root_path(self):
        """Root unit path equals its own id string."""
        root = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty of Arts",
            slug="faculty-arts",
        )
        self.assertEqual(root.path, str(root.id))
        self.assertEqual(root.level, 0)

    def test_orgunit_child_path(self):
        """Child unit path is parent.path/child.id."""
        parent = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty of Engineering",
            slug="faculty-eng",
        )
        child = OrgUnit.objects.create(
            organization=self.org,
            parent=parent,
            unit_type="department",
            name="Electrical Engineering",
            slug="ee",
        )
        self.assertEqual(child.path, f"{parent.path}/{child.id}")
        self.assertEqual(child.level, 1)

    def test_orgunit_grandchild_path(self):
        """Grandchild unit path is grandparent.path/parent.id/grandchild.id."""
        grandparent = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty of Science",
            slug="fos",
        )
        parent = OrgUnit.objects.create(
            organization=self.org,
            parent=grandparent,
            unit_type="department",
            name="Physics",
            slug="physics",
        )
        child = OrgUnit.objects.create(
            organization=self.org,
            parent=parent,
            unit_type="class",
            name="Quantum Lab",
            slug="quantum-lab",
        )
        self.assertEqual(child.path, f"{grandparent.path}/{parent.id}/{child.id}")
        self.assertEqual(child.level, 2)

    def test_orgunit_reparent_updates_unit_path(self):
        """Changing a unit's parent updates its path and level."""
        parent_a = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty A",
            slug="faculty-a",
        )
        parent_b = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty B",
            slug="faculty-b",
        )
        child = OrgUnit.objects.create(
            organization=self.org,
            parent=parent_a,
            unit_type="department",
            name="Dept X",
            slug="dept-x",
        )
        self.assertEqual(child.path, f"{parent_a.path}/{child.id}")

        # Reparent to B
        child.parent = parent_b
        child.save()
        child.refresh_from_db()

        self.assertEqual(child.path, f"{parent_b.path}/{child.id}")
        self.assertEqual(child.level, 1)

    def test_orgunit_reparent_cascades_to_descendants(self):
        """Reparenting a unit cascades path updates to all its descendants."""
        parent_a = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty A",
            slug="fa",
        )
        parent_b = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty B",
            slug="fb",
        )
        child = OrgUnit.objects.create(
            organization=self.org,
            parent=parent_a,
            unit_type="department",
            name="Dept",
            slug="dept",
        )
        grandchild = OrgUnit.objects.create(
            organization=self.org,
            parent=child,
            unit_type="class",
            name="Class",
            slug="class",
        )

        # Reparent child from A to B
        child.parent = parent_b
        child.save()

        grandchild.refresh_from_db()
        child.refresh_from_db()

        self.assertEqual(child.path, f"{parent_b.path}/{child.id}")
        self.assertEqual(grandchild.path, f"{parent_b.path}/{child.id}/{grandchild.id}")
        self.assertEqual(grandchild.level, 2)

    def test_orgunit_auto_slug(self):
        """Slug is auto-generated from name if not provided."""
        unit = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Faculty of Natural Sciences",
        )
        self.assertNotEqual(unit.slug, "")
        self.assertIn("natural", unit.slug)

    def test_orgunit_get_descendants_after_reparent(self):
        """get_descendants() returns correct set after reparenting."""
        root_a = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Root A",
            slug="root-a",
        )
        root_b = OrgUnit.objects.create(
            organization=self.org,
            unit_type="faculty",
            name="Root B",
            slug="root-b",
        )
        child = OrgUnit.objects.create(
            organization=self.org,
            parent=root_a,
            unit_type="department",
            name="Child",
            slug="child",
        )

        # Before reparent: child is under root_a
        self.assertIn(child, root_a.get_descendants())
        self.assertNotIn(child, root_b.get_descendants())

        # Reparent child to root_b
        child.parent = root_b
        child.save()

        root_a.refresh_from_db()
        root_b.refresh_from_db()

        self.assertNotIn(child, root_a.get_descendants())
        self.assertIn(child, root_b.get_descendants())


class OrganizationDefaultRoleSignalTest(TestCase):
    def test_create_default_roles_uses_rls_bypass(self):
        user = User.objects.create_user(username="signaluser", email="signal@test.com", password="testpass123")
        entered = {"count": 0}

        @contextmanager
        def recording_bypass():
            entered["count"] += 1
            yield

        with patch("apps.organizations.signals.bypass_rls", recording_bypass):
            org = Organization.objects.create(
                name="Signal School",
                org_type=OrganizationType.SCHOOL,
                owner=user,
            )

        self.assertEqual(entered["count"], 1)
        self.assertTrue(org.roles.filter(name="teacher").exists())


class RoleModelTest(TestCase):
    """Tests for Role model."""

    def setUp(self):
        """Set up test data."""
        # Disconnect signal to avoid unique constraint errors in tests
        post_save.disconnect(create_default_roles, sender=Organization)

        self.user = User.objects.create_user(username="testuser", email="test@test.com", password="testpass123")
        self.org = Organization.objects.create(
            name="Test University",
            slug="test-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )

    def tearDown(self):
        """Clean up after tests."""
        post_save.connect(create_default_roles, sender=Organization)

    def test_role_creation(self):
        """Test creating a role."""
        role = Role.objects.create(
            organization=self.org,
            name="teacher",
            display_name="Teacher",
            level=50,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.*", "exam.view"],
        )
        self.assertEqual(role.name, "teacher")
        self.assertEqual(role.level, 50)
        self.assertIn("course.*", role.permissions)


class MembershipModelTest(TestCase):
    """Tests for Membership model."""

    def setUp(self):
        """Set up test data."""
        # Disconnect signal to avoid unique constraint errors in tests
        post_save.disconnect(create_default_roles, sender=Organization)

        self.user = User.objects.create_user(username="testuser", email="test@test.com", password="testpass123")
        self.org = Organization.objects.create(
            name="Test University",
            slug="test-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )
        self.role = Role.objects.create(
            organization=self.org,
            name="teacher",
            display_name="Teacher",
            level=50,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.*"],
        )

    def tearDown(self):
        """Clean up after tests."""
        post_save.connect(create_default_roles, sender=Organization)

    def test_membership_creation(self):
        """Test creating a membership."""
        membership = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=self.role,
            is_primary=True,
        )
        self.assertEqual(membership.user, self.user)
        self.assertEqual(membership.organization, self.org)
        self.assertTrue(membership.is_primary)

    def test_single_primary_membership(self):
        """Test only one primary membership per user per organization."""
        membership1 = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=self.role,
            is_primary=True,
        )

        # Create second role
        role2 = Role.objects.create(
            organization=self.org,
            name="admin",
            display_name="Admin",
            level=90,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["*"],
        )

        # Create second membership as primary
        membership2 = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=role2,
            is_primary=True,
        )

        # Refresh first membership
        membership1.refresh_from_db()

        # Only second should be primary
        self.assertFalse(membership1.is_primary)
        self.assertTrue(membership2.is_primary)


class AcademicPeriodModelTest(TestCase):
    """Tests for AcademicPeriod model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", email="test@test.com", password="testpass123")
        self.org = Organization.objects.create(
            name="Test University",
            slug="test-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )

    def test_academic_period_creation(self):
        """Test creating an academic period."""
        from datetime import date

        period = AcademicPeriod.objects.create(
            organization=self.org,
            name="Fall Semester",
            period_type="semester",
            academic_year="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 1, 15),
            is_current=True,
        )
        self.assertEqual(period.name, "Fall Semester")
        self.assertTrue(period.is_current)

    def test_single_current_period(self):
        """Test only one current period per organization."""
        from datetime import date

        period1 = AcademicPeriod.objects.create(
            organization=self.org,
            name="Fall Semester",
            period_type="semester",
            academic_year="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 1, 15),
            is_current=True,
        )

        period2 = AcademicPeriod.objects.create(
            organization=self.org,
            name="Spring Semester",
            period_type="semester",
            academic_year="2024-2025",
            start_date=date(2025, 2, 1),
            end_date=date(2025, 6, 15),
            is_current=True,
        )

        # Refresh first period
        period1.refresh_from_db()

        # Only second should be current
        self.assertFalse(period1.is_current)
        self.assertTrue(period2.is_current)
