"""QA 2026-09 duplicate-query audit — request-scoped RBAC/scoping cache.

Every cabinet section re-resolved the actor's active memberships from
scratch: ``_role_capabilities`` calls ``get_permission_scope`` up to 6x
(course.edit / journal.close / journal.roster / final_score.entry /
analytics.view_all / analytics.view_unit) and ``_collect_actor_permissions``
up to 3x for the SAME (user, organization) — each a fresh ``Membership``
SELECT, because neither function was ever called with a ``request`` from
inside ``_role_capabilities`` so their (unused) request-level caches never
engaged. Unit-scoped roles (dean/chair_head) additionally re-ran the
``OrgUnit`` path lookup once per permission checked.

Fix: memoize the membership rows (and, for unit-scoped roles, the resolved
unit paths) on the ``user`` object — same per-object pattern as
``apps.applications.services.access.active_memberships`` — keyed by
organization pk. See ``apps.organizations.scoping._permission_scope_memberships``
/ ``_resolve_active_unit_paths`` and ``apps.accounts.views._helpers.rbac.
_collect_actor_permissions``.

Two properties are locked here:

1. **Bounded queries.** A single ``_role_capabilities`` build for a
   UNIT-scoped actor with several distinct permission-gated capabilities
   must not re-query memberships/unit-paths per capability.
2. **No stale reads.** A membership mutation via ``_sync_user_role_memberships``
   (the shared role-assignment/management funnel) must invalidate the cache
   it may have already primed earlier in the SAME request — a stale
   permission cache is a security bug, not a perf detail.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import ProfileRole, UserProfile
from apps.accounts.views._helpers.membership import _sync_user_role_memberships
from apps.accounts.views._helpers.rbac import _collect_actor_permissions, _role_capabilities
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"

#: `_role_capabilities` gates on all six of these via `get_permission_scope`
#: (course.edit, journal.close, journal.roster, final_score.entry,
#: analytics.view_all, analytics.view_unit) plus `member.view`/`unit.view`
#: (directory search) and `group.view` (groups section) via
#: `_collect_actor_permissions` — one role carrying all of them exercises
#: every duplicate-prone call site in a single build.
MULTI_GATE_PERMISSIONS = [
    "course.edit",
    "journal.close",
    "journal.roster",
    "final_score.entry",
    "analytics.view_all",
    "analytics.view_unit",
    "member.view",
    "unit.view",
    "group.view",
]


class RbacPermissionScopeQueryCacheTest(TestCase):
    """Locks the query-count improvement for a UNIT-scoped multi-permission actor."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rbac_cache_owner", "owner@example.test", PASSWORD)
        cls.org = Organization.objects.create(
            name="RBAC Cache Org",
            slug="rbac-cache-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.faculty = OrgUnit.objects.create(
            organization=cls.org,
            name="RBAC Cache Faculty",
            unit_type=OrgUnitType.FACULTY,
            path="rbac-cache-faculty",
            is_active=True,
        )
        cls.role = Role.objects.create(
            organization=cls.org,
            name="rbac_cache_multi_gate",
            display_name="Multi-Gate Dean",
            level=70,
            scope_type=RoleScopeType.UNIT,
            permissions=list(MULTI_GATE_PERMISSIONS),
            is_active=True,
        )
        cls.dean = User.objects.create_user("rbac_cache_dean", "dean@example.test", PASSWORD)
        UserProfile.objects.filter(user=cls.dean).update(organization=cls.org)
        Membership.objects.create(
            user=cls.dean,
            organization=cls.org,
            role=cls.role,
            scope_unit=cls.faculty,
            is_active=True,
            is_primary=True,
        )

    def _fresh_dean(self):
        """A brand-new ``User`` Python instance — no request-lifetime caches attached yet."""
        user = User.objects.get(pk=self.dean.pk)
        user.set_active_organization_context(self.org)
        return user

    def test_role_capabilities_build_uses_a_bounded_number_of_queries(self):
        """Six `get_permission_scope` checks + three `_collect_actor_permissions`
        checks for the SAME (user, org) must collapse to one membership fetch
        (plus one unit-path fetch) instead of re-querying per check."""
        user = self._fresh_dean()
        profile = user.profile
        # Cold path: 1 query resolving `_active_org_memberships` (roles.py) +
        # 1 memoized membership fetch for `get_permission_scope` (reused across
        # all 6 permission checks) + 1 unit-path resolution (reused across all
        # UNIT-scoped checks) + 1 memoized `_collect_actor_permissions` fetch
        # (reused across its 2 call sites in this build). Before the fix this
        # was 1 + 6 + up to 6 + 2 = 15+ queries for the same build.
        with self.assertNumQueries(4):
            capabilities = _role_capabilities(user, profile)
        # `can_manage_registrar` requires ORG-WIDE scope specifically (`is_org_wide`);
        # this actor is UNIT-scoped, so it stays False — the other gates below only
        # need `has_structure_access`, which a valid scope_unit satisfies.
        self.assertFalse(capabilities["can_manage_registrar"])
        self.assertTrue(capabilities["can_close_journals"])
        self.assertTrue(capabilities["can_manage_journal_roster"])
        self.assertTrue(capabilities["can_enter_exam_scores"])
        self.assertTrue(capabilities["can_search_directory"])
        self.assertIn("groups", capabilities["allowed_sections"])

    def test_repeated_get_permission_scope_calls_do_not_requery_memberships(self):
        """Direct proof the membership fetch is memoized: 6 distinct-permission
        calls for the same (user, org) cost exactly one membership query plus
        one unit-path query (plus the one-off `is_superadmin` profile lookup,
        cached by Django's own FK descriptor after its first access), not six
        of each."""
        from apps.organizations.scoping import get_permission_scope

        user = self._fresh_dean()
        permissions = [
            "course.edit",
            "journal.close",
            "journal.roster",
            "final_score.entry",
            "analytics.view_all",
            "analytics.view_unit",
        ]
        with self.assertNumQueries(3):
            for permission in permissions:
                scope = get_permission_scope(user, self.org, permission)
                self.assertTrue(scope.has_structure_access, permission)


class RbacPermissionCacheInvalidationTest(TestCase):
    """A membership write must never leave a stale read behind in the same request."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rbac_inval_owner", "owner2@example.test", PASSWORD)
        cls.org = Organization.objects.create(
            name="RBAC Invalidation Org",
            slug="rbac-invalidation-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.target = User.objects.create_user("rbac_inval_target", "target@example.test", PASSWORD)
        UserProfile.objects.get_or_create(user=cls.target)

    def test_sync_user_role_memberships_invalidates_the_already_primed_cache(self):
        """Mirrors the real call chain in role_assignment/_management_flow:
        `_ensure_profile_admin_membership` (or here, `_sync_user_role_memberships`)
        mutates membership, and code right after reads permissions again in the
        SAME request/object. Without invalidation the second read would return
        the pre-mutation (empty) cache — a stale-permission security bug."""
        target = User.objects.get(pk=self.target.pk)

        # Prime the cache BEFORE any membership exists — mirrors an earlier
        # `_role_capabilities` build in the same request/pipeline.
        actor_permissions, _ = _collect_actor_permissions(target, self.org)
        self.assertEqual(actor_permissions, set())

        _sync_user_role_memberships(target, self.org, {ProfileRole.TEACHER})

        # Same Python object, same request lifetime: must see the freshly
        # assigned teacher role's permissions, not the stale empty cache.
        actor_permissions, _ = _collect_actor_permissions(target, self.org)
        self.assertIn("course.view", actor_permissions)
        self.assertTrue(
            Membership.objects.filter(user=target, organization=self.org, is_active=True).exists(),
        )
