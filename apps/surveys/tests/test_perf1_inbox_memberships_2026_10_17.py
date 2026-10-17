"""PERF-1 F-15 (2026-10-17): sorğu inbox-u / sidebar sayğacı üzvlükləri middleware snapshot-undan oxuyur.

`inbox._memberships` hər badges çağırışında `Membership(user, org, is_active=True)`-i yenidən oxuyurdu, halbuki
`OrganizationMiddleware` eyni sətirləri (`role`, `scope_unit` yüklü) artıq request-ə bağlayıb. Snapshot yararlıdırsa
sorğu getmir və nəticə canlı sorğu ilə eynidir; yararsızdırsa (epoxa / başqa org) canlı sorğu qalır.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.organizations.models import Membership, Organization
from apps.organizations.request_memberships import bind_request_memberships, membership_epoch
from apps.surveys.services import inbox
from core.constants import OrganizationType
from core.rls import bypass_rls

from .factories import member


class InboxMembershipSnapshotTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user("pf1sv_owner", "pf1sv_owner@x.test", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="PF1 Survey Univ",
                slug="pf1-sv",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            cls.user = member(cls.org, "pf1sv_teacher", "teacher")

    def _rows(self):
        with bypass_rls():
            return list(
                Membership.objects.filter(user=self.user, organization=self.org, is_active=True)
                .select_related("organization", "role", "scope_unit")
                .order_by("-is_primary", "-role__level")
            )

    def test_bound_snapshot_is_used_without_query(self):
        rows = self._rows()
        bind_request_memberships(self.user, self.org, rows, epoch=membership_epoch())
        with CaptureQueriesContext(connection) as ctx:
            memberships = inbox._memberships(self.user, self.org)
        self.assertEqual(len(ctx.captured_queries), 0)
        self.assertEqual([m.pk for m in memberships], [m.pk for m in rows])

    def test_stale_snapshot_falls_back_to_live_query(self):
        rows = self._rows()
        bind_request_memberships(self.user, self.org, rows, epoch=membership_epoch() - 1)
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            memberships = inbox._memberships(self.user, self.org)
        self.assertEqual(len(ctx.captured_queries), 1)
        self.assertEqual({m.pk for m in memberships}, {m.pk for m in rows})
