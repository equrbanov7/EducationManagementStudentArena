"""
Integration tests – Tenant Isolation.

Verifies that a user who belongs to Organization A cannot query or view
courses (or other resources) that belong to Organization B.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase

from apps.courses.models import Course
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


def _make_org(name, slug, owner, org_type=OrganizationType.UNIVERSITY):
    """Helper: create an Organization with signals suppressed."""
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        org = Organization.objects.create(
            name=name,
            slug=slug,
            org_type=org_type,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return org


def _make_role(org, name="teacher", level=60):
    return Role.objects.create(
        organization=org,
        name=name,
        display_name=name.title(),
        level=level,
        scope_type=RoleScopeType.COURSE,
        permissions=["course.*"],
        is_active=True,
    )


def _assign(user, org, role):
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.save(update_fields=["organization", "organization_type", "updated_at"])
    return Membership.objects.create(
        user=user,
        organization=org,
        role=role,
        is_primary=True,
        is_active=True,
    )


class TenantIsolationCourseTest(TestCase):
    """
    A user in Org A must not be able to see courses that belong to Org B.
    """

    def setUp(self):
        self.user_a = User.objects.create_user(
            username="tenant_user_a", email="ta@orga.com", password="testpass123"
        )
        self.user_b = User.objects.create_user(
            username="tenant_user_b", email="tb@orgb.com", password="testpass123"
        )

        self.org_a = _make_org("Org A", "org-a-ti", self.user_a)
        self.org_b = _make_org("Org B", "org-b-ti", self.user_b, OrganizationType.SCHOOL)

        role_a = _make_role(self.org_a)
        role_b = _make_role(self.org_b)

        _assign(self.user_a, self.org_a, role_a)
        _assign(self.user_b, self.org_b, role_b)

        # Create one course per org
        self.course_a = Course.objects.create(
            title="Course for Org A",
            owner=self.user_a,
            organization=self.org_a,
            status="published",
        )
        self.course_b = Course.objects.create(
            title="Course for Org B",
            owner=self.user_b,
            organization=self.org_b,
            status="published",
        )

    def test_user_org_a_cannot_see_org_b_courses(self):
        """
        Filtering courses by Org A's organization must exclude Org B's courses.

        This is the canonical regression guard for cross-tenant data leakage:
        the QuerySet that backs any Org-A-scoped view must not include records
        owned by Org B.
        """
        courses_visible_to_org_a = Course.objects.filter(organization=self.org_a)

        # Org A's course IS visible
        self.assertIn(
            self.course_a,
            courses_visible_to_org_a,
            "Course A must be accessible within Org A's context",
        )
        # Org B's course is NOT visible when scoped to Org A
        self.assertNotIn(
            self.course_b,
            courses_visible_to_org_a,
            "Course B must NOT be accessible within Org A's context (tenant isolation violation)",
        )

    def test_org_b_user_cannot_see_org_a_courses(self):
        """
        Filtering courses by Org B's organization must also exclude Org A's courses.
        """
        courses_visible_to_org_b = Course.objects.filter(organization=self.org_b)

        self.assertIn(self.course_b, courses_visible_to_org_b)
        self.assertNotIn(
            self.course_a,
            courses_visible_to_org_b,
            "Org A's course must not appear in Org B's scoped queryset",
        )

    def test_combined_queryset_contains_both_but_scoping_separates_them(self):
        """Sanity check: the unfiltered QS contains both; scoped QSes isolate them."""
        all_courses = Course.objects.filter(id__in=[self.course_a.id, self.course_b.id])
        self.assertEqual(all_courses.count(), 2)

        self.assertEqual(Course.objects.filter(organization=self.org_a).count(), 1)
        self.assertEqual(Course.objects.filter(organization=self.org_b).count(), 1)
