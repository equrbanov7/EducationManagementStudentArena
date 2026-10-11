"""Reqressiya (sahib 2026-10-11): RİM əməkdaşının səhvən kafedraya bağlanmış İKİNCİ üzvlüyü geri alınmalıdır.

Prod: «Nurlan» iki `rim_staff` üzvlüyü daşıyır — biri «Proqramlaşdırma … kafedrası»na (səhv, primary), biri
«Rəqəmsal İnkişaf mərkəzi»nə. RİM rəhbəri kafedra üzvlüyünü «×» ilə çıxara bilmirdi.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class RevokeChairScopedRimStaffTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("rr_owner", "rr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RR Univ", slug="rr-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Proqramlaşdırma kafedrası", slug="rr-ch", unit_type=OrgUnitType.CHAIR
            )
            cls.center = OrgUnit.objects.create(
                organization=cls.org,
                name="Rəqəmsal İnkişaf mərkəzi",
                slug="rr-rim",
                unit_type=OrgUnitType.DEPARTMENT,
            )
            cls.head = User.objects.create_user("rr_head", "rr_head@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.head,
                organization=cls.org,
                role=cls.org.roles.get(name="ikt_rehber"),
                is_primary=True,
                is_active=True,
            )
            # RİM rəhbərinin özünün də kafedra müəllimi üzvlüyü var (prod-dakı kimi).
            Membership.objects.create(
                user=cls.head,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                scope_unit=cls.chair,
                is_active=True,
            )
            cls.target = User.objects.create_user("rr_nurlan", "rr_nurlan@qku.edu.az", "pw")
            rim_staff = cls.org.roles.get(name="rim_staff")
            cls.wrong = Membership.objects.create(
                user=cls.target,
                organization=cls.org,
                role=rim_staff,
                scope_unit=cls.chair,
                is_primary=True,
                is_active=True,
            )
            cls.right = Membership.objects.create(
                user=cls.target, organization=cls.org, role=rim_staff, scope_unit=cls.center, is_active=True
            )

    def test_rim_head_can_revoke_the_chair_scoped_duplicate(self):
        client = Client()
        client.force_login(self.head)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.post(
            reverse("accounts:manage_roles"),
            {"action": "revoke_role", "membership_id": str(self.wrong.id), "reason": "səhv kafedra"},
            follow=True,
        )
        notes = [str(m) for m in get_messages(response.wsgi_request)]
        with bypass_rls():
            active = list(
                Membership.objects.filter(user=self.target, is_active=True).values_list("scope_unit_id", flat=True)
            )
        self.assertEqual(active, [self.center.pk], notes)
