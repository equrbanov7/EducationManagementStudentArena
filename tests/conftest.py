"""
Pytest configuration and fixtures for EMS Arena project.
"""

from django.db import connection
from django.db.models.signals import post_save

import pytest

# ---------------------------------------------------------------------------
# RLS bypass — keeps existing tests green
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests(db):
    """Automatically bypass RLS for all tests that touch the database.

    Row-Level Security policies are enforced at the PostgreSQL session level.
    Existing tests were written before RLS was introduced and do not set the
    ``app.current_org_id`` session variable.  Without a bypass those tests
    would receive empty QuerySets for every RLS-protected table.

    This fixture enables the bypass flag at the start of every database-using
    test and clears it afterwards so that the session is clean for the next
    test.  Tests that specifically validate RLS isolation should **opt out**
    by overriding this fixture locally::

        @pytest.fixture(autouse=True)
        def _rls_bypass_for_tests(db):
            # Do NOT call the base fixture — RLS must be active for this test.
            yield

    On non-PostgreSQL backends (e.g. SQLite in local development) the fixture
    is a no-op.
    """
    if connection.vendor != "postgresql":
        yield
        return

    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'on', false)")
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.bypass_rls', 'off', false)")
            cur.execute("SELECT set_config('app.current_org_id', '', false)")


def _get_user_model():
    from django.contrib.auth import get_user_model

    return get_user_model()


@pytest.fixture
def create_user():
    """
    Fixture to create a user.
    """

    def _create_user(username="testuser", email="test@example.com", password="testpass123", **kwargs):
        return _get_user_model().objects.create_user(username=username, email=email, password=password, **kwargs)

    return _create_user


@pytest.fixture
def teacher_user(create_user, db):
    """
    Fixture to create a teacher user with RBAC membership.
    """
    from apps.accounts.models import ProfileRole
    from apps.organizations.models import Membership, Organization
    from core.constants import OrganizationType

    user = create_user(username="teacher", email="teacher@example.com")
    org = Organization.objects.create(
        name="Teacher Test Org",
        slug="teacher-test-org",
        org_type=OrganizationType.UNIVERSITY,
        owner=user,
        status="active",
        is_active=True,
    )
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.role = ProfileRole.TEACHER
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.create(
        user=user,
        organization=org,
        role=org.roles.get(name="teacher"),
        is_primary=True,
        is_active=True,
    )
    return user


@pytest.fixture
def student_user(create_user, db):
    """
    Fixture to create a student user with RBAC membership.
    """
    from apps.accounts.models import ProfileRole
    from apps.organizations.models import Membership, Organization
    from core.constants import OrganizationType

    user = create_user(username="student", email="student@example.com")
    org = Organization.objects.create(
        name="Student Test Org",
        slug="student-test-org",
        org_type=OrganizationType.UNIVERSITY,
        owner=user,
        status="active",
        is_active=True,
    )
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.role = ProfileRole.STUDENT
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.create(
        user=user,
        organization=org,
        role=org.roles.get(name="student"),
        is_primary=True,
        is_active=True,
    )
    return user


# ---------------------------------------------------------------------------
# Organization-aware fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def organization(db):
    """
    Fixture that creates a single Organization with default roles disabled,
    so tests can control role/membership setup precisely.
    """
    from apps.organizations.models import Organization
    from apps.organizations.signals import create_default_roles
    from core.constants import OrganizationType

    owner = _get_user_model().objects.create_user(
        username="org_owner",
        email="org_owner@example.com",
        password="testpass123",
    )

    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        org = Organization.objects.create(
            name="Test Organization",
            slug="test-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)

    return org


@pytest.fixture
def role(organization, db):
    """
    Fixture that creates a teacher-level Role in the given organization.
    """
    from apps.organizations.models import Role
    from core.constants import RoleScopeType

    return Role.objects.create(
        organization=organization,
        name="teacher",
        display_name="Teacher",
        level=60,
        scope_type=RoleScopeType.COURSE,
        permissions=["course.*"],
        is_active=True,
    )


@pytest.fixture
def membership(organization, role, db):
    """
    Fixture that creates a Membership linking the organization owner to the
    organization with the teacher role.
    """
    from apps.organizations.models import Membership

    return Membership.objects.create(
        user=organization.owner,
        organization=organization,
        role=role,
        is_primary=True,
        is_active=True,
    )


@pytest.fixture
def multi_org_user(db):
    """
    Fixture that creates a user who is a member of two separate organizations.
    Returns a dict with keys: ``user``, ``org_a``, ``org_b``,
    ``membership_a``, ``membership_b``.
    """
    from apps.organizations.models import Membership, Organization, Role
    from apps.organizations.signals import create_default_roles
    from core.constants import OrganizationType, RoleScopeType

    user = _get_user_model().objects.create_user(
        username="multi_org_user",
        email="multi_org@example.com",
        password="testpass123",
    )

    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        org_a = Organization.objects.create(
            name="Org Alpha",
            slug="org-alpha",
            org_type=OrganizationType.UNIVERSITY,
            owner=user,
            status="active",
            is_active=True,
        )
        org_b = Organization.objects.create(
            name="Org Beta",
            slug="org-beta",
            org_type=OrganizationType.SCHOOL,
            owner=user,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)

    role_a = Role.objects.create(
        organization=org_a,
        name="teacher",
        display_name="Teacher",
        level=60,
        scope_type=RoleScopeType.COURSE,
        permissions=["course.*"],
        is_active=True,
    )
    role_b = Role.objects.create(
        organization=org_b,
        name="member",
        display_name="Member",
        level=20,
        scope_type=RoleScopeType.ORGANIZATION,
        permissions=[],
        is_active=True,
    )

    membership_a = Membership.objects.create(
        user=user,
        organization=org_a,
        role=role_a,
        is_primary=True,
        is_active=True,
    )
    membership_b = Membership.objects.create(
        user=user,
        organization=org_b,
        role=role_b,
        is_primary=False,
        is_active=True,
    )

    return {
        "user": user,
        "org_a": org_a,
        "org_b": org_b,
        "membership_a": membership_a,
        "membership_b": membership_b,
    }
