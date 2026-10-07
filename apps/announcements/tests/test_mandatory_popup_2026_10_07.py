"""Məcburi elan (sahib, 2026-10-07) — istifadəçi tərəfi.

* popup təsdiq edilənədək HƏR tam səhifədə çıxır; ``popup_seen_at`` onu gizlətmir;
* adi popup əvvəlki kimi birdəfəlikdir; modalda məcburi birinci gəlir;
* təsdiq ucu: yalnız ünvanlanmış + görünən elan (yad auditoriya / başqa təşkilat → 404),
  POST + CSRF, açıq ``confirm``, idempotent (paralel klik daxil), sayğac keşi silinir;
* sessiya «gözləyən yoxdur» imzası təsdiqlənməmiş məcburi elanı gizlətmir;
* xülasənin sıfır-sorğulu qısa yolu qorunur;
* kabinet: «Məcburi» çipi, «Təsdiq gözləyir» / «Təsdiq edildi», «Təsdiq gözləyənlər» filtri, detal banneri.
"""

from __future__ import annotations

import json
from unittest import mock

from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.announcements.constants import POPUP_SESSION_KEY
from apps.announcements.models import AnnouncementReceipt
from apps.announcements.services import manage, popup, snapshot
from apps.announcements.services.access import manage_scope
from apps.organizations.models import Membership, Organization
from core.rls import bypass_rls

from .world import _Req, build_world, client_for, make_announcement

PROFILE = "/accounts/profile/"
CABINET = "/accounts/profile/?section=announcements"


def _ack(client, item, confirm=True):
    return client.post(
        reverse("announcements:ack", args=[item.pk]),
        data=json.dumps({"confirm": confirm}),
        content_type="application/json",
    )


def _seen(client, *items):
    return client.post(
        reverse("announcements:popup_seen"),
        data=json.dumps({"ids": [str(item.pk) for item in items]}),
        content_type="application/json",
    )


def _request(world, user, path=PROFILE, **params):
    with bypass_rls():
        memberships = list(
            Membership.objects.filter(user=user, organization=world["org"], is_active=True).select_related(
                "role", "scope_unit", "organization"
            )
        )
        org = Organization.objects.get(pk=world["org"].pk)  # təzə settings (xülasə)
    request = RequestFactory().get(path, params)
    request.user, request.organization, request.org_memberships = user, org, memberships
    request.session = {}
    return request


def _receipt(item, user):
    with bypass_rls():
        return AnnouncementReceipt.objects.filter(announcement=item, user=user).first()


class MandatoryPopupTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annmand")
        cls.item = make_announcement(cls.w, title="Məcburi təlimat elanı", requires_ack=True, units=[cls.w["f1"].pk])

    def test_flags_and_snapshot(self):
        self.assertTrue(self.item.requires_ack)
        self.assertTrue(self.item.show_as_popup)
        with bypass_rls():
            items = snapshot.active_items(Organization.objects.get(pk=self.w["org"].pk))
        self.assertEqual(items[0]["id"], str(self.item.pk))
        self.assertIs(items[0]["req"], True)
        self.assertIs(items[0]["pop"], True)

    def test_popup_repeats_until_acknowledged(self):
        client = client_for(self.w["org"], self.w["s1"])
        page = client.get(PROFILE).content.decode()
        self.assertIn("data-ann-popup", page)
        self.assertIn('data-mandatory="1"', page)
        self.assertIn("Elanı oxudum və tanış oldum", page)
        self.assertIn("is-locked", page)
        # «Ətraflı bax» / bağlama cəhdi popup_seen yazır — məcburi elanı GİZLƏTMİR.
        self.assertEqual(_seen(client, self.item).json()["recorded"], 1)
        for _ in range(3):
            self.assertIn("Məcburi təlimat elanı", client.get(PROFILE).content.decode())
        response = _ack(client, self.item)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["newly"])
        self.assertNotIn("data-ann-popup", client.get(PROFILE).content.decode())
        # Başqa cihaz (yeni sessiya) — təsdiq DB-dədir.
        other = client_for(self.w["org"], self.w["s1"])
        self.assertNotIn("data-ann-popup", other.get(PROFILE).content.decode())

    def test_detail_page_shows_banner_instead_of_its_own_popup(self):
        client = client_for(self.w["org"], self.w["s1"])
        page = client.get(f"{CABINET}&elan={self.item.pk}").content.decode()
        self.assertIn("data-ann-ack", page)
        self.assertIn(reverse("announcements:ack", args=[self.item.pk]), page)
        self.assertNotIn("data-ann-popup-item", page)  # öz detalında bloklayan modal yoxdur
        _ack(client, self.item)
        page = client.get(f"{CABINET}&elan={self.item.pk}").content.decode()
        self.assertNotIn("data-ann-ack-submit", page)
        self.assertIn("ann-ack--done", page)

    def test_ack_sets_seen_and_read_and_is_idempotent(self):
        client = client_for(self.w["org"], self.w["s1"])
        _seen(client, self.item)
        seen_at = _receipt(self.item, self.w["s1"]).popup_seen_at
        first = _ack(client, self.item).json()
        self.assertTrue(first["newly"])
        self.assertTrue(first["newly_read"])
        receipt = _receipt(self.item, self.w["s1"])
        self.assertIsNotNone(receipt.acknowledged_at)
        self.assertEqual(receipt.popup_seen_at, seen_at)  # mövcud dəyər dəyişmir
        self.assertIsNotNone(receipt.read_at)
        second = _ack(client, self.item).json()
        self.assertFalse(second["newly"])
        self.assertFalse(second["newly_read"])
        self.assertEqual(second["acknowledged_at"], first["acknowledged_at"])
        with bypass_rls():
            self.assertEqual(AnnouncementReceipt.objects.filter(announcement=self.item, user=self.w["s1"]).count(), 1)
            self.assertEqual(AnnouncementReceipt.objects.get(pk=receipt.pk).acknowledged_at, receipt.acknowledged_at)

    def test_parallel_click_race_falls_back_to_conditional_update(self):
        # Paralel klik: get_or_create INSERT-i başqa sorğunun yaratdığı sətirə çırpılır (IntegrityError).
        with bypass_rls():
            existing = AnnouncementReceipt.objects.create(
                organization=self.w["org"], announcement=self.item, user=self.w["s1"]
            )
        request = _request(self.w, self.w["s1"])
        with (
            mock.patch.object(
                AnnouncementReceipt.objects, "get_or_create", side_effect=IntegrityError("dup")
            ) as racing,
            bypass_rls(),
        ):
            result = popup.acknowledge(request, self.item.pk)
        racing.assert_called_once()
        self.assertTrue(result.newly)
        with bypass_rls():
            existing.refresh_from_db()
        self.assertIsNotNone(existing.acknowledged_at)
        self.assertIsNotNone(existing.read_at)

    def test_ack_requires_explicit_confirm_and_post(self):
        client = client_for(self.w["org"], self.w["s1"])
        self.assertEqual(_ack(client, self.item, confirm=False).status_code, 400)
        self.assertIsNone(_receipt(self.item, self.w["s1"]))
        self.assertEqual(client.get(reverse("announcements:ack", args=[self.item.pk])).status_code, 405)

    def test_ack_is_csrf_protected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.w["s1"])
        session = client.session
        session["active_organization"] = self.w["org"].slug
        session.save()
        self.assertEqual(_ack(client, self.item).status_code, 403)
        self.assertIsNone(_receipt(self.item, self.w["s1"]))

    def test_foreign_audience_and_anonymous_get_no_ack(self):
        client = client_for(self.w["org"], self.w["s2"])  # F2 tələbəsi — ünvanlanmayıb
        self.assertEqual(_ack(client, self.item).status_code, 404)
        client = client_for(self.w["org"], self.w["t1"])  # müəllim — ailə uyğun deyil
        self.assertEqual(_ack(client, self.item).status_code, 404)
        self.assertEqual(_ack(Client(), self.item).status_code, 403)
        with bypass_rls():
            self.assertFalse(AnnouncementReceipt.objects.filter(announcement=self.item).exists())

    def test_non_mandatory_announcement_cannot_be_acknowledged(self):
        once = make_announcement(self.w, title="Adi popup", show_as_popup=True)
        client = client_for(self.w["org"], self.w["s1"])
        self.assertEqual(_ack(client, once).status_code, 409)
        self.assertIsNone(_receipt(once, self.w["s1"]))

    def test_ack_invalidates_badge_cache(self):
        request = _request(self.w, self.w["s1"])
        with mock.patch("apps.announcements.services.popup.cache") as cache, bypass_rls():
            popup.acknowledge(request, self.item.pk)
        cache.delete.assert_called_once_with(popup._badge_key(request.organization, request.user))


class MandatoryAndOnceTogetherTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annmix")
        cls.once = make_announcement(cls.w, title="Birdəfəlik kritik elan", show_as_popup=True, priority=2)
        cls.mandatory = make_announcement(cls.w, title="Məcburi adi elan", requires_ack=True, priority=0)

    def test_mandatory_comes_first_and_once_stays_once(self):
        rows = popup.pending_popups(_request(self.w, self.w["s1"]))
        self.assertEqual([row.pk for row in rows], [self.mandatory.pk, self.once.pk])
        client = client_for(self.w["org"], self.w["s1"])
        _seen(client, self.once, self.mandatory)
        page = client.get(PROFILE).content.decode()
        self.assertIn("Məcburi adi elan", page)
        self.assertNotIn("Birdəfəlik kritik elan", page)  # adi popup — bir dəfə
        _ack(client, self.mandatory)
        self.assertNotIn("data-ann-popup", client.get(PROFILE).content.decode())

    def test_exam_pages_and_view_as_stay_exempt(self):
        for path in ("/exams/final/", "/live/play/1234/"):
            self.assertEqual(popup.pending_popups(_request(self.w, self.w["s1"], path)), [], path)
        self.assertEqual(popup.pending_popups(_request(self.w, self.w["s1"], section="assigned-exams")), [])
        request = _request(self.w, self.w["s1"])
        request.is_view_as = True
        self.assertEqual(popup.pending_popups(request), [])


class SessionSignatureTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annsig")
        cls.item = make_announcement(cls.w, title="Əvvəl adi, sonra məcburi", show_as_popup=True)

    def test_signature_includes_mandatory_flag(self):
        org = self.w["org"]
        plain = [{"id": str(self.item.pk)}]
        flagged = [{"id": str(self.item.pk), "req": True}]
        self.assertNotEqual(popup._signature(org, plain), popup._signature(org, flagged))

    def test_unacknowledged_mandatory_never_writes_the_clear_marker(self):
        with bypass_rls():
            make_announcement(self.w, title="Məcburi", requires_ack=True)
        request = _request(self.w, self.w["s1"])
        with bypass_rls():
            popup.mark_popup_seen(request, [row.pk for row in popup.pending_popups(request)])
        for _ in range(2):
            request = _request(self.w, self.w["s1"])
            with bypass_rls():
                rows = popup.pending_popups(request)
            self.assertEqual([row.title for row in rows], ["Məcburi"])
            self.assertNotIn(POPUP_SESSION_KEY, request.session)

    def test_stale_clear_marker_does_not_hide_newly_mandatory(self):
        request = _request(self.w, self.w["s1"])
        with bypass_rls():
            popup.mark_popup_seen(request, [self.item.pk])
            request = _request(self.w, self.w["s1"])
            self.assertEqual(popup.pending_popups(request), [])
        session = request.session
        self.assertIn(POPUP_SESSION_KEY, session)  # «gözləyən yoxdur» işarəsi yazıldı
        # Menecer elanı MƏCBURİ edir — eyni sessiya ilə elan yenidən (bloklayan) çıxmalıdır.
        with bypass_rls():
            self.item.requires_ack = True
            self.item.save(update_fields=["requires_ack", "updated_at"])
            snapshot.sync_snapshot(self.w["org"])
        request = _request(self.w, self.w["s1"])
        request.session = session
        with bypass_rls():
            rows = popup.pending_popups(request)
        self.assertEqual([row.pk for row in rows], [self.item.pk])


class MandatoryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annmbud")

    def test_nothing_active_is_zero_queries(self):
        request = _request(self.w, self.w["s1"])
        with self.assertNumQueries(0):
            self.assertEqual(popup.pending_popups(request), [])

    def test_mandatory_for_other_family_is_zero_queries(self):
        make_announcement(self.w, title="Müəllimlərə məcburi", families=["teachers"], requires_ack=True)
        request = _request(self.w, self.w["s1"])
        with self.assertNumQueries(0):
            self.assertEqual(popup.pending_popups(request), [])

    def test_pending_then_acknowledged_budget(self):
        item = make_announcement(self.w, title="F1 məcburi", requires_ack=True, units=[self.w["f1"].pk])
        request = _request(self.w, self.w["s1"])
        with self.assertNumQueries(3):  # qəbzlər + akademik qeyd (daraltma) + modal sətirləri
            self.assertEqual([row.pk for row in popup.pending_popups(request)], [item.pk])
        with bypass_rls():
            popup.acknowledge(_request(self.w, self.w["s1"]), item.pk)
        request = _request(self.w, self.w["s1"])
        with self.assertNumQueries(1):  # yalnız qəbzlər → «gözləyən yoxdur» işarəsi yazılır
            self.assertEqual(popup.pending_popups(request), [])
        session = request.session
        request = _request(self.w, self.w["s1"])
        request.session = session
        with self.assertNumQueries(0):
            self.assertEqual(popup.pending_popups(request), [])


class CabinetAckStateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("anncab")
        cls.mandatory = make_announcement(cls.w, title="Məcburi kabinet elanı", requires_ack=True)
        cls.plain = make_announcement(cls.w, title="Adi kabinet elanı")

    def _html(self, client, **params):
        response = client.get(reverse("announcements:list"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()["html"]

    def test_chip_state_and_pending_filter(self):
        client = client_for(self.w["org"], self.w["s1"])
        html = self._html(client)
        self.assertIn("ann-chip--mandatory", html)
        self.assertIn("Təsdiq gözləyir", html)
        pending = self._html(client, pending="1")
        self.assertIn("Məcburi kabinet elanı", pending)
        self.assertNotIn("Adi kabinet elanı", pending)
        _ack(client, self.mandatory)
        html = self._html(client)
        self.assertIn("Təsdiq edildi", html)
        self.assertNotIn("Təsdiq gözləyir", html)
        pending = self._html(client, pending="1")
        self.assertNotIn("Məcburi kabinet elanı", pending)
        self.assertIn("Təsdiq gözləyən elan yoxdur", pending)

    def test_filters_render_pending_toggle(self):
        client = client_for(self.w["org"], self.w["s1"])
        page = client.get(CABINET).content.decode()
        self.assertIn('name="pending"', page)
        self.assertIn("Təsdiq gözləyənlər", page)

    def test_unpublish_removes_mandatory_popup(self):
        with bypass_rls():
            manage.transition(
                _Req(self.w["owner"], self.w["org"]),
                self.w["org"],
                manage_scope(self.w["owner"], self.w["org"]),
                self.mandatory,
                "unpublish",
            )
        client = client_for(self.w["org"], self.w["s1"])
        self.assertNotIn("data-ann-popup", client.get(PROFILE).content.decode())
        self.assertEqual(_ack(client, self.mandatory).status_code, 404)


class OtherOrganizationAckTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = build_world("annacka")
        cls.b = build_world("annackb")
        cls.item = make_announcement(cls.a, title="Yalnız A məcburi", requires_ack=True, families=["students"])

    def test_other_org_student_gets_404_and_no_receipt(self):
        client = client_for(self.b["org"], self.b["s1"])
        self.assertEqual(_ack(client, self.item).status_code, 404)
        self.assertNotIn("Yalnız A məcburi", client.get(PROFILE).content.decode())
        with bypass_rls():
            self.assertFalse(AnnouncementReceipt.objects.filter(announcement=self.item).exists())
