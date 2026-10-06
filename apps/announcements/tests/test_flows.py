"""Elanlar — əsas axınlar: auditoriya, siyahı, birdəfəlik popup, oxundu, tenant izolyasiyası, XSS."""

from __future__ import annotations

import json

from django.test import TestCase
from django.urls import reverse

from apps.announcements.models import AnnouncementReceipt
from apps.announcements.services import snapshot
from core.rls import bypass_rls

from .world import build_world, client_for, days, make_announcement, member

CABINET = "/accounts/profile/?section=announcements"


class AudienceAndListTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annaud")
        cls.f1_students = make_announcement(cls.w, title="F1 tələbələri üçün", units=[cls.w["f1"].pk])
        cls.everyone = make_announcement(
            cls.w, title="Hamıya elan", families=["students", "teachers", "staff"], category="general"
        )
        cls.teachers = make_announcement(cls.w, title="Müəllimlərə", families=["teachers"], category="academic")
        cls.draft = make_announcement(cls.w, title="Qaralama elan", publish=False)

    def _titles(self, user, **params):
        client = client_for(self.w["org"], user)
        response = client.get(reverse("announcements:list"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()["html"]

    def test_faculty_student_sees_faculty_announcement(self):
        html = self._titles(self.w["s1"])
        self.assertIn("F1 tələbələri üçün", html)
        self.assertIn("Hamıya elan", html)
        self.assertNotIn("Müəllimlərə", html)
        self.assertNotIn("Qaralama elan", html)

    def test_other_faculty_student_does_not_see_it(self):
        html = self._titles(self.w["s2"])
        self.assertNotIn("F1 tələbələri üçün", html)
        self.assertIn("Hamıya elan", html)

    def test_teacher_sees_teacher_and_everyone_only(self):
        html = self._titles(self.w["t1"])
        self.assertIn("Müəllimlərə", html)
        self.assertIn("Hamıya elan", html)
        self.assertNotIn("F1 tələbələri üçün", html)

    def test_search_filter_and_category(self):
        html = self._titles(self.w["s1"], q="hamiya")  # diakritikaya dözümlü
        self.assertIn("Hamıya elan", html)
        self.assertNotIn("F1 tələbələri üçün", html)
        html = self._titles(self.w["s1"], category="exam")
        self.assertIn("F1 tələbələri üçün", html)
        self.assertNotIn("Hamıya elan", html)

    def test_detail_hidden_from_untargeted_student(self):
        client = client_for(self.w["org"], self.w["s2"])
        response = client.get(f"{CABINET}&elan={self.f1_students.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("F1 tələbələri üçün", response.content.decode())
        response = client.post(reverse("announcements:read", args=[self.f1_students.pk]))
        self.assertEqual(response.status_code, 404)

    def test_read_receipt_and_unread_filter(self):
        client = client_for(self.w["org"], self.w["s1"])
        response = client.post(reverse("announcements:read", args=[self.f1_students.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["newly_read"])
        self.assertFalse(client.post(reverse("announcements:read", args=[self.f1_students.pk])).json()["newly_read"])
        html = client.get(reverse("announcements:list"), {"unread": "1"}).json()["html"]
        self.assertNotIn("F1 tələbələri üçün", html)
        self.assertIn("Hamıya elan", html)

    def test_expired_goes_to_expired_filter(self):
        with bypass_rls():
            from apps.announcements.models import Announcement

            Announcement.objects.filter(pk=self.everyone.pk).update(publish_at=days(-5), expires_at=days(-1))
        self.assertNotIn("Hamıya elan", self._titles(self.w["s1"]))
        self.assertIn("Hamıya elan", self._titles(self.w["s1"], state="expired"))


class PopupOnceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annpop")
        cls.popup = make_announcement(
            cls.w, title="Vacib popup elan", show_as_popup=True, units=[cls.w["f1"].pk], priority=2
        )

    def test_popup_shows_once_then_never(self):
        client = client_for(self.w["org"], self.w["s1"])
        page = client.get("/accounts/profile/").content.decode()
        self.assertIn("data-ann-popup", page)
        self.assertIn("Vacib popup elan", page)
        # Bağlanmayıbsa növbəti açılışda yenə göstərilir.
        self.assertIn("data-ann-popup", client.get("/accounts/profile/").content.decode())
        response = client.post(
            reverse("announcements:popup_seen"),
            data=json.dumps({"ids": [str(self.popup.pk)]}),
            content_type="application/json",
        )
        self.assertEqual(response.json()["recorded"], 1)
        self.assertNotIn("data-ann-popup", client.get("/accounts/profile/").content.decode())
        # Yeni sessiya (başqa cihaz) — yenə göstərilmir (qəbz DB-dədir).
        other = client_for(self.w["org"], self.w["s1"])
        self.assertNotIn("data-ann-popup", other.get("/accounts/profile/").content.decode())

    def test_untargeted_student_never_gets_popup(self):
        client = client_for(self.w["org"], self.w["s2"])
        self.assertNotIn("data-ann-popup", client.get("/accounts/profile/").content.decode())

    def test_popup_seen_ignores_untargeted_ids(self):
        client = client_for(self.w["org"], self.w["s2"])
        response = client.post(
            reverse("announcements:popup_seen"),
            data=json.dumps({"ids": [str(self.popup.pk)]}),
            content_type="application/json",
        )
        self.assertEqual(response.json()["recorded"], 0)
        with bypass_rls():
            self.assertFalse(AnnouncementReceipt.objects.filter(user=self.w["s2"]).exists())

    def test_no_popup_on_exam_pages(self):
        from django.test import RequestFactory

        from apps.announcements.services.popup import pending_popups

        with bypass_rls():
            from apps.organizations.models import Membership

            memberships = list(
                Membership.objects.filter(user=self.w["s1"], organization=self.w["org"]).select_related("role", "scope_unit")
            )
        for path in ("/exams/final/", "/exams/some-exam/attempt/5/", "/live/play/1234/"):
            request = RequestFactory().get(path)
            request.user, request.organization, request.org_memberships = self.w["s1"], self.w["org"], memberships
            request.session = {}
            self.assertEqual(pending_popups(request), [], path)
        request = RequestFactory().get("/accounts/profile/", {"section": "assigned-exams"})
        request.user, request.organization, request.org_memberships = self.w["s1"], self.w["org"], memberships
        request.session = {}
        self.assertEqual(pending_popups(request), [])

    def test_unpublish_removes_popup_immediately(self):
        from apps.announcements.services import manage
        from apps.announcements.services.access import manage_scope

        from .world import _Req

        with bypass_rls():
            manage.transition(
                _Req(self.w["owner"], self.w["org"]),
                self.w["org"],
                manage_scope(self.w["owner"], self.w["org"]),
                self.popup,
                "unpublish",
            )
            self.w["org"].refresh_from_db()
            self.assertEqual(snapshot.active_items(self.w["org"]), [])
        client = client_for(self.w["org"], self.w["s1"])
        self.assertNotIn("data-ann-popup", client.get("/accounts/profile/").content.decode())


class TenantIsolationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = build_world("annta")
        cls.b = build_world("anntb")
        cls.item = make_announcement(
            cls.a, title="Yalnız A təşkilatı", families=["students", "teachers", "staff"], apply_mode="url",
            apply_url="https://example.org/form",
        )

    def test_other_org_user_cannot_see_read_or_apply(self):
        client = client_for(self.b["org"], self.b["s1"])
        html = client.get(reverse("announcements:list")).json()["html"]
        self.assertNotIn("Yalnız A təşkilatı", html)
        self.assertEqual(client.post(reverse("announcements:read", args=[self.item.pk])).status_code, 404)
        self.assertEqual(client.post(reverse("announcements:apply", args=[self.item.pk])).status_code, 404)
        page = client.get(f"{CABINET}&elan={self.item.pk}").content.decode()
        self.assertNotIn("Yalnız A təşkilatı", page)

    def test_other_org_manager_cannot_open_edit_page(self):
        client = client_for(self.b["org"], self.b["owner"])
        self.assertEqual(client.get(reverse("announcements:manage_edit", args=[self.item.pk])).status_code, 404)


class EscapingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annxss")
        cls.item = make_announcement(
            cls.w,
            title='<script>alert("t")</script>',
            summary="<img src=x onerror=alert(1)>",
            body='Salam <b>qalın</b>\n\n<script>alert("b")</script> https://example.org',
            show_as_popup=True,
        )

    def test_title_summary_body_are_escaped_everywhere(self):
        client = client_for(self.w["org"], self.w["s1"])
        for html in (
            client.get(reverse("announcements:list")).json()["html"],
            client.get(f"{CABINET}&elan={self.item.pk}").content.decode(),
            client.get("/accounts/profile/").content.decode(),  # popup
        ):
            self.assertNotIn('<script>alert("t")</script>', html)
            self.assertNotIn("<img src=x", html)
            self.assertNotIn('<script>alert("b")</script>', html)
        detail = client.get(f"{CABINET}&elan={self.item.pk}").content.decode()
        self.assertIn("&lt;b&gt;qalın&lt;/b&gt;", detail)
        self.assertIn('href="https://example.org"', detail)


class ManagerVisibilityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annmv")

    def test_student_gets_no_management(self):
        client = client_for(self.w["org"], self.w["s1"])
        self.assertEqual(client.get(reverse("announcements:manage_list")).status_code, 403)
        self.assertNotIn(reverse("announcements:manage_list"), client.get(CABINET).content.decode())

    def test_dean_sees_manage_link(self):
        client = client_for(self.w["org"], self.w["dean"])
        self.assertIn(reverse("announcements:manage_list"), client.get(CABINET).content.decode())
        self.assertEqual(client.get(reverse("announcements:manage_list")).status_code, 200)

    def test_neutral_member_sees_section_but_nothing_targeted(self):
        with bypass_rls():
            user = member(self.w["org"], "annmv_member", "member")
        make_announcement(self.w, title="Hamıya", families=["students", "teachers", "staff"])
        client = client_for(self.w["org"], user)
        self.assertNotIn("Hamıya", client.get(reverse("announcements:list")).json()["html"])
