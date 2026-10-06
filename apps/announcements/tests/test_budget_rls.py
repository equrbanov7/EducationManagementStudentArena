"""Elanlar — sorğu büdcəsi (popup / sayğac / kabinet bölməsi) və DB səviyyəli RLS."""

from __future__ import annotations

from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

import pytest

from apps.announcements.models import Announcement, AnnouncementAttachment, AnnouncementReceipt
from apps.announcements.services.popup import badge_count, mark_popup_seen, pending_popups
from apps.organizations.models import Membership, Organization
from core.rls import bypass_rls

from .world import build_world, client_for, make_announcement


def _request(world, user, path="/accounts/profile/"):
    with bypass_rls():
        memberships = list(
            Membership.objects.filter(user=user, organization=world["org"], is_active=True).select_related(
                "role", "scope_unit", "organization"
            )
        )
        org = Organization.objects.get(pk=world["org"].pk)  # təzə settings (xülasə)
    request = RequestFactory().get(path)
    request.user, request.organization, request.org_memberships = user, org, memberships
    request.session = {}
    return request


class PopupBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annbud")

    def test_nothing_active_costs_zero_queries(self):
        request = _request(self.w, self.w["s1"])
        with self.assertNumQueries(0):
            self.assertEqual(pending_popups(request), [])
            self.assertEqual(badge_count(self.w["s1"], request.organization, request.org_memberships), 0)

    def test_other_family_popup_costs_zero_queries(self):
        make_announcement(self.w, title="Müəllimlərə popup", families=["teachers"], show_as_popup=True)
        request = _request(self.w, self.w["s1"])
        with self.assertNumQueries(0):
            self.assertEqual(pending_popups(request), [])

    def test_pending_popup_budget_and_session_marker(self):
        item = make_announcement(self.w, title="F1 popup", show_as_popup=True, units=[self.w["f1"].pk])
        request = _request(self.w, self.w["s1"])
        with self.assertNumQueries(3):  # qəbzlər + akademik qeyd (daraltma) + modal sətirləri
            rows = pending_popups(request)
        self.assertEqual([row.pk for row in rows], [item.pk])
        with bypass_rls():
            mark_popup_seen(request, [item.pk])
        request = _request(self.w, self.w["s1"])
        with self.assertNumQueries(1):  # yalnız qəbzlər (hamısı görülüb) → işarə sessiyaya yazılır
            self.assertEqual(pending_popups(request), [])
        session = request.session
        request = _request(self.w, self.w["s1"])
        request.session = session
        with self.assertNumQueries(0):  # sessiya işarəsi — sıfır sorğu
            self.assertEqual(pending_popups(request), [])


class CabinetSectionBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annsec")
        for index in range(12):
            make_announcement(cls.w, title=f"Elan {index}", families=["students", "teachers", "staff"])

    def _fragment_queries(self, user):
        client = client_for(self.w["org"], user)
        client.get("/accounts/profile/api/sections/announcements/")  # isinmə (sessiya/keş)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get("/accounts/profile/api/sections/announcements/")
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["ok"])
        return len(ctx.captured_queries), response.json()["html"]

    def test_fragment_query_count_is_bounded_and_independent_of_rows(self):
        count, html = self._fragment_queries(self.w["s1"])
        self.assertIn("Elan 11", html)
        with bypass_rls():
            for index in range(12, 30):
                Announcement.objects.create(
                    organization=self.w["org"],
                    title=f"Əlavə {index}",
                    status="published",
                    audience_families=["students"],
                    publish_at=Announcement.objects.first().publish_at,
                )
        count_more, _html = self._fragment_queries(self.w["s1"])
        self.assertEqual(count, count_more)

    def test_list_api_budget(self):
        client = client_for(self.w["org"], self.w["s1"])
        client.get("/elanlar/api/list/")
        with CaptureQueriesContext(connection) as ctx:
            client.get("/elanlar/api/list/")
        own = [q for q in ctx.captured_queries if "announcements_" in q["sql"] or "registrar_" in q["sql"]]
        self.assertLessEqual(len(own), 4, [q["sql"][:120] for q in own])


_MODELS = (Announcement, AnnouncementAttachment, AnnouncementReceipt)


def _set(name, value):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _enter_tenant(org_id):
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", str(org_id))
    _set("app.current_user_id", "")
    with connection.cursor() as cur:
        cur.execute("SET LOCAL ROLE rls_app_role")


@pytest.fixture()
def two_tenants(db):
    if connection.vendor != "postgresql":
        pytest.skip("RLS testləri PostgreSQL tələb edir")
    _set("app.bypass_rls", "on")
    worlds = []
    for slug in ("annrlsa", "annrlsb"):
        world = build_world(slug)
        item = make_announcement(world, title=f"{slug} elanı")
        AnnouncementReceipt.objects.create(organization=world["org"], announcement=item, user=world["s1"])
        AnnouncementAttachment.objects.create(
            organization=world["org"], announcement=item, file="announcements/x.pdf", original_name="x.pdf"
        )
        worlds.append(world)
    yield worlds
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", "")


@pytest.mark.postgres
def test_tables_are_tenant_isolated(two_tenants):
    world_a, _world_b = two_tenants
    _enter_tenant(world_a["org"].pk)
    for model in _MODELS:
        assert set(model.objects.values_list("organization_id", flat=True)) == {world_a["org"].pk}, model.__name__


@pytest.mark.postgres
def test_missing_tenant_denies_all(two_tenants):
    _enter_tenant("")
    for model in _MODELS:
        assert model.objects.count() == 0, model.__name__


@pytest.mark.postgres
def test_cross_tenant_write_rejected(two_tenants):
    world_a, world_b = two_tenants
    item_b = Announcement.objects.filter(organization=world_b["org"]).first()
    _enter_tenant(world_a["org"].pk)
    with pytest.raises(DatabaseError), transaction.atomic():
        AnnouncementReceipt.objects.create(organization=world_b["org"], announcement_id=item_b.pk, user=world_a["s1"])
